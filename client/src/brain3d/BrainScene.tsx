// ── AKKI Brain 3D — scene assembly ──────────────────────────────────────────
// Wires together the procedural/ambient neuron backdrop, the live "graph"
// neuron layer (actual concepts, capable of growing in as the brain learns),
// the synapse Signals layer, camera controls, and the holographic
// post-processing stack.
//
// Prop-shape design notes (the brief's `<BrainScene graph stream />` is a
// rough sketch — this is the concrete, documented interface):
//
//  - `graph.nodes` identity is the hard-reset trigger: replacing this array
//    (e.g. starting a brand-new query) rebuilds the neuron buffers from
//    scratch, with every node rendered already-grown (no pop-in — a first
//    load shouldn't look like it "grew"). `graph.edges` / `graph.activePath`
//    can be replaced on every render cheaply and do NOT reset anything —
//    Signals just re-derives its line geometry from current node positions.
//  - Live growth (new concepts arriving mid-query, e.g. an SSE "grew" event)
//    does NOT go through the `graph` prop at all — it goes through the
//    imperative handle (`ref`) this component exposes: `appendNodes(...)`
//    and `updateActivations(...)`. This is deliberate: a plain prop/state
//    setter living in a *parent* component has no access to the live R3F
//    clock (`state.clock.elapsedTime`), which only exists inside the Canvas
//    render loop — and a newly-appended point's `spawnTime` must be stamped
//    with that live value for NeuronField's grow-in shader to ease it in
//    from "just born" rather than "always existed" or "born at time 0."
//    The bridge: an `elapsedRef` (plain React ref, created in this
//    component, outside the Canvas) is kept live by a tiny <ClockBridge>
//    function component rendered *inside* the Canvas, which does nothing
//    but `useFrame((state) => { elapsedRef.current = state.clock.elapsedTime })`
//    every rendered frame. `appendNodes`, called from outside the Canvas
//    (e.g. by an SSE handler in a parent/hook), reads `elapsedRef.current`
//    at call time — always the last value the render loop observed — and
//    uses it as the new points' `spawnTime`. No prop drilling of the clock,
//    no re-render of the whole tree just to read a number.
//  - Under `prefers-reduced-motion`, appended points are stamped with a
//    sentinel far in the past instead of "now," so they render already at
//    full size — grow-in pop is itself a motion effect, so it's suppressed
//    the same way autoRotate and the signal pulse are, without touching
//    NeuronField's shader.

import * as THREE from "three";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { AdaptiveDpr, OrbitControls } from "@react-three/drei";
import { Bloom, ChromaticAberration, EffectComposer } from "@react-three/postprocessing";
import NeuronField from "./NeuronField";
import Signals, { type SignalEdge } from "./Signals";
import { regionForConcept } from "./regions";
import { generateBrainPoints } from "./proceduralBrain";

export interface BrainSceneNode {
  id: string;
  /** Concept text — biases placement toward a brain region via `regionForConcept`. */
  label: string;
  /** 0..1. Answer-path / recently-touched concepts flare gold. Defaults to 0. */
  activation?: number;
}

export interface BrainSceneEdge {
  /** Stable id, e.g. `${from}->${to}`. */
  id: string;
  from: string; // node id
  to: string; // node id
}

export interface BrainSceneGraph {
  nodes: BrainSceneNode[];
  edges: BrainSceneEdge[];
  /** Edge ids currently on the highlighted answer/reasoning path. */
  activePath?: string[];
}

export interface BrainSceneStreamOptions {
  /** Point-buffer headroom for live growth without a geometry realloc. Default: max(nodes*4, 1000). */
  maxNodes?: number;
  /** Ambient procedural background neuron count layered behind the graph nodes. Default 20000. */
  ambientCount?: number;
}

export interface BrainSceneHandle {
  /**
   * Append newly-learned concepts live (e.g. an SSE "grew" event), popping
   * them in from the current moment. Ids already present are ignored.
   */
  appendNodes(nodes: BrainSceneNode[]): void;
  /** Patch activation for existing nodes by id (e.g. flare the answer path gold on an "answer" event). */
  updateActivations(patch: Record<string, number>): void;
}

export interface BrainSceneProps {
  graph: BrainSceneGraph;
  stream?: BrainSceneStreamOptions;
  className?: string;
}

// Sentinel spawn time meaning "always existed" — mirrors NeuronField's own
// private constant in spirit (a value far enough in the past that
// `uTime - spawnTime` is always well past the ~0.8s grow-in window).
const ALREADY_SPAWNED = -1e6;

const DEFAULT_AMBIENT_COUNT = 20000;

interface GrowableBuffers {
  positions: Float32Array;
  activations: Float32Array;
  spawnTimes: Float32Array;
  count: number;
  capacity: number;
}

interface GraphState {
  buffers: GrowableBuffers;
  index: Map<string, number>;
}

function hashToUnit(id: string, salt: number): number {
  let h = (0x811c9dc5 ^ salt) >>> 0;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return ((h >>> 0) / 0xffffffff) * 2 - 1; // [-1, 1]
}

/** Region-biased placement: centroid from `regionForConcept`, jittered so same-region concepts don't overlap exactly. */
function positionForNode(node: BrainSceneNode): [number, number, number] {
  const { centroid } = regionForConcept(node.label);
  const jitterRadius = 0.16;
  return [
    centroid[0] + hashToUnit(node.id, 1) * jitterRadius,
    centroid[1] + hashToUnit(node.id, 2) * jitterRadius,
    centroid[2] + hashToUnit(node.id, 3) * jitterRadius,
  ];
}

function capacityFor(nodeCount: number, maxNodes?: number): number {
  return Math.max(nodeCount, maxNodes ?? Math.max(nodeCount * 4, 1000));
}

function buildStateFromGraph(nodes: BrainSceneNode[], capacity: number): GraphState {
  const safeCapacity = Math.max(capacity, nodes.length, 1);
  const positions = new Float32Array(safeCapacity * 3);
  const activations = new Float32Array(safeCapacity);
  const spawnTimes = new Float32Array(safeCapacity);
  const index = new Map<string, number>();
  nodes.forEach((node, i) => {
    const [x, y, z] = positionForNode(node);
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    activations[i] = node.activation ?? 0;
    spawnTimes[i] = ALREADY_SPAWNED; // a fresh snapshot renders fully grown, not "popping in"
    index.set(node.id, i);
  });
  return {
    buffers: { positions, activations, spawnTimes, count: nodes.length, capacity: safeCapacity },
    index,
  };
}

/** Renders nothing — just keeps `elapsedRef` fresh with the live R3F clock, for use by imperative append calls made from outside the Canvas. */
function ClockBridge({ elapsedRef }: { elapsedRef: MutableRefObject<number> }) {
  useFrame((state) => {
    elapsedRef.current = state.clock.elapsedTime;
  });
  return null;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    try {
      return typeof window !== "undefined" && !!window.matchMedia
        ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
        : false;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    let mql: MediaQueryList;
    try {
      mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    } catch {
      return;
    }
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);

  return reduced;
}

const BrainScene = forwardRef<BrainSceneHandle, BrainSceneProps>(function BrainScene(
  { graph, stream, className },
  ref
) {
  const reducedMotion = usePrefersReducedMotion();
  const reducedMotionRef = useRef(reducedMotion);
  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
  }, [reducedMotion]);

  const elapsedRef = useRef(0);

  const ambientCount = stream?.ambientCount ?? DEFAULT_AMBIENT_COUNT;
  const ambientPoints = useMemo(() => generateBrainPoints(ambientCount), [ambientCount]);

  const maxNodes = stream?.maxNodes;
  const [state, setState] = useState<GraphState>(() =>
    buildStateFromGraph(graph.nodes, capacityFor(graph.nodes.length, maxNodes))
  );

  // Only `graph.nodes` identity resets the growable neuron buffers (a hard
  // "load this snapshot" signal, e.g. a brand-new query) — see module doc
  // comment. `graph.edges` / `graph.activePath` are read directly below and
  // can change every render without resetting growth.
  useEffect(() => {
    setState(buildStateFromGraph(graph.nodes, capacityFor(graph.nodes.length, maxNodes)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph.nodes]);

  const appendNodes = useCallback((newNodes: BrainSceneNode[]) => {
    if (newNodes.length === 0) return;
    const spawnNow = reducedMotionRef.current ? ALREADY_SPAWNED : elapsedRef.current;
    setState((prev) => {
      const fresh = newNodes.filter((n) => !prev.index.has(n.id));
      if (fresh.length === 0) return prev;

      const needed = prev.buffers.count + fresh.length;
      let { positions, activations, spawnTimes, capacity } = prev.buffers;

      if (needed > capacity) {
        const newCapacity = Math.max(needed, Math.ceil(capacity * 1.5) + 64);
        const p2 = new Float32Array(newCapacity * 3);
        const a2 = new Float32Array(newCapacity);
        const s2 = new Float32Array(newCapacity);
        p2.set(positions.subarray(0, prev.buffers.count * 3));
        a2.set(activations.subarray(0, prev.buffers.count));
        s2.set(spawnTimes.subarray(0, prev.buffers.count));
        positions = p2;
        activations = a2;
        spawnTimes = s2;
        capacity = newCapacity;
      } else {
        // Same capacity: copy so React (and NeuronField's effect, which
        // keys off array identity) sees new references rather than a
        // silent in-place mutation.
        positions = positions.slice();
        activations = activations.slice();
        spawnTimes = spawnTimes.slice();
      }

      const index = new Map(prev.index);
      let count = prev.buffers.count;
      for (const node of fresh) {
        const [x, y, z] = positionForNode(node);
        positions[count * 3] = x;
        positions[count * 3 + 1] = y;
        positions[count * 3 + 2] = z;
        activations[count] = node.activation ?? 0;
        spawnTimes[count] = spawnNow;
        index.set(node.id, count);
        count++;
      }

      return { buffers: { positions, activations, spawnTimes, count, capacity }, index };
    });
  }, []);

  const updateActivations = useCallback((patch: Record<string, number>) => {
    setState((prev) => {
      const activations = prev.buffers.activations.slice();
      let changed = false;
      for (const id of Object.keys(patch)) {
        const idx = prev.index.get(id);
        if (idx === undefined) continue;
        activations[idx] = patch[id];
        changed = true;
      }
      if (!changed) return prev;
      return { buffers: { ...prev.buffers, activations }, index: prev.index };
    });
  }, []);

  useImperativeHandle(ref, () => ({ appendNodes, updateActivations }), [appendNodes, updateActivations]);

  const edgesForSignals = useMemo<SignalEdge[]>(() => {
    const { positions } = state.buffers;
    const { index } = state;
    const result: SignalEdge[] = [];
    for (const edge of graph.edges) {
      const fi = index.get(edge.from);
      const ti = index.get(edge.to);
      if (fi === undefined || ti === undefined) continue;
      result.push({
        id: edge.id,
        from: [positions[fi * 3], positions[fi * 3 + 1], positions[fi * 3 + 2]],
        to: [positions[ti * 3], positions[ti * 3 + 1], positions[ti * 3 + 2]],
      });
    }
    return result;
  }, [graph.edges, state]);

  const chromaticOffset = useMemo(() => new THREE.Vector2(0.0006, 0.0006), []);

  return (
    <div className={className} style={{ width: "100%", height: "100%" }}>
      <Canvas
        dpr={[1, 2]}
        frameloop="demand"
        gl={{ antialias: true, alpha: false }}
        camera={{ position: [0, 0, 2.6], fov: 45, near: 0.05, far: 20 }}
      >
        <color attach="background" args={["#050810"]} />
        <ambientLight intensity={0.15} />

        <ClockBridge elapsedRef={elapsedRef} />

        {/* Ambient backdrop: dense, dim, non-growing procedural cloud giving the brain its shape. */}
        <NeuronField points={ambientPoints} maxCount={ambientCount} baseSize={3.2} />

        {/* Live concept layer: the actual graph, capable of growing in via appendNodes(). */}
        <NeuronField
          points={state.buffers.positions.subarray(0, state.buffers.count * 3)}
          activations={state.buffers.activations.subarray(0, state.buffers.count)}
          spawnTimes={state.buffers.spawnTimes.subarray(0, state.buffers.count)}
          maxCount={state.buffers.capacity}
          baseSize={7}
        />

        <Signals edges={edgesForSignals} activePath={graph.activePath} reducedMotion={reducedMotion} />

        <OrbitControls
          makeDefault
          enableDamping
          autoRotate={!reducedMotion}
          autoRotateSpeed={0.6}
          minDistance={0.9}
          maxDistance={6}
        />
        <AdaptiveDpr />

        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur luminanceThreshold={0.15} luminanceSmoothing={0.3} intensity={1.1} />
          <ChromaticAberration offset={chromaticOffset} radialModulation={false} modulationOffset={0} />
        </EffectComposer>
      </Canvas>
    </div>
  );
});

export default BrainScene;
