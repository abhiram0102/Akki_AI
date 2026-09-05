// ── AKKI Brain 3D — synapse signal flow ─────────────────────────────────────
// Renders edges between neurons as glowing, pulsing lines: a bright pulse
// travels along each edge (per-vertex arc-length attribute `aArc` in [0,1] +
// a shared `uTime` uniform), so the whole ambient graph animates in one
// LineSegments draw call. Edges on the current answer/reasoning path
// ("activePath") are upgraded to individual emissive TubeGeometry meshes —
// thicker, brighter, and still riding the same pulse function so they read
// as "the same signal, just louder" rather than a different visual language.
//
// Design choices (see task-8 report for the full rationale):
//  - The brief's own prop sketch (`<Signals edges activePath />`) is a rough
//    interface note. Concretely: `edges` is the full ambient edge list with
//    resolved world-space endpoints (BrainScene resolves node ids -> [x,y,z]
//    once per graph change); `activePath` is the subset of those edge ids
//    that should be upgraded to tubes.
//  - Both the ambient LineSegments material and the per-edge active Tube
//    materials are unlit, additive-blended custom ShaderMaterials sharing
//    the same GLSL pulse function (spliced in via template literals) so
//    there's one visual "signal" language across both draw-call shapes.
//    Tubes are NOT lit MeshStandardMaterial — that would need normals/light
//    setup for no visual gain here, and additive-glow is more consistent
//    with the hologram look than a lit, occluding surface.
//  - `reducedMotion` freezes the pulse phase (skips advancing `uTime`) per
//    the design doc's graceful-degradation rule, without touching geometry.

import * as THREE from "three";
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";

export interface SignalEdge {
  /** Stable id, e.g. `${fromNodeId}->${toNodeId}`. Matched against `activePath`. */
  id: string;
  from: readonly [number, number, number];
  to: readonly [number, number, number];
}

export interface SignalsProps {
  /** All ambient edges currently in the graph, with resolved world-space endpoints. */
  edges: SignalEdge[];
  /** Edge ids on the current answer/reasoning path — rendered as emissive tubes instead of ambient pulse lines. */
  activePath?: string[];
  /** Pulse cycles per second along an edge's full length. */
  speed?: number;
  /** Freeze the pulse phase (no `uTime` advance) — set when `prefers-reduced-motion` matches. */
  reducedMotion?: boolean;
}

// Shared fragment-shader pulse function, spliced into both the ambient-line
// and active-tube fragment shaders so they read as one visual language.
// `vArc` in [0,1] is the position along the edge; the moving pulse position
// is `fract(uTime * uSpeed - vOffset)`. Distance wraps at the 0/1 seam so the
// pulse doesn't visibly snap when it loops.
const PULSE_GLSL = /* glsl */ `
float pulseBrightness(float arc, float phase) {
  float d = abs(arc - phase);
  d = min(d, 1.0 - d); // wrap around the 0..1 seam
  float sigma = 0.09;
  return exp(-(d * d) / (2.0 * sigma * sigma));
}
`;

const AMBIENT_VERTEX_SHADER = /* glsl */ `
attribute float aArc;
attribute float aOffset;
varying float vArc;
varying float vOffset;
void main() {
  vArc = aArc;
  vOffset = aOffset;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const AMBIENT_FRAGMENT_SHADER = /* glsl */ `
uniform float uTime;
uniform float uSpeed;
varying float vArc;
varying float vOffset;

${PULSE_GLSL}

void main() {
  float phase = fract(uTime * uSpeed - vOffset);
  float pulse = pulseBrightness(vArc, phase);
  // Dim ambient base glow (so idle edges are still faintly visible) plus the
  // travelling pulse on top.
  vec3 color = vec3(0.24, 0.55, 0.95);
  float intensity = 0.12 + pulse * 1.4;
  gl_FragColor = vec4(color * intensity, 0.25 + pulse * 0.75);
}
`;

const ACTIVE_VERTEX_SHADER = /* glsl */ `
varying float vArc;
void main() {
  // TubeGeometry's default UVs run 0..1 along the path length in uv.x.
  vArc = uv.x;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const ACTIVE_FRAGMENT_SHADER = /* glsl */ `
uniform float uTime;
uniform float uSpeed;
uniform float uOffset;
varying float vArc;

${PULSE_GLSL}

void main() {
  float phase = fract(uTime * uSpeed - uOffset);
  float pulse = pulseBrightness(vArc, phase);
  // Hot gold, matching the NeuronField "activated" color — brighter and more
  // saturated than the ambient lines so the answer path reads as "the signal
  // that matters."
  vec3 color = vec3(1.0, 0.82, 0.35);
  float intensity = 0.55 + pulse * 2.2;
  gl_FragColor = vec4(color * intensity, 0.6 + pulse * 0.4);
}
`;

/** Deterministic per-edge pulse-phase offset so edges don't all pulse in lockstep. */
function offsetForId(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0) / 0xffffffff;
}

const ACTIVE_TUBE_RADIUS = 0.008;
const ACTIVE_TUBE_SEGMENTS = 12;

function ActiveEdgeTube({
  edge,
  speed,
  reducedMotion,
}: {
  edge: SignalEdge;
  speed: number;
  reducedMotion: boolean;
}) {
  const geometry = useMemo(() => {
    const curve = new THREE.LineCurve3(
      new THREE.Vector3(...edge.from),
      new THREE.Vector3(...edge.to)
    );
    return new THREE.TubeGeometry(curve, ACTIVE_TUBE_SEGMENTS, ACTIVE_TUBE_RADIUS, 6, false);
  }, [edge.from, edge.to]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSpeed: { value: speed },
      uOffset: { value: offsetForId(edge.id) },
    }),
    // uTime is pushed every frame below; uSpeed/uOffset are pushed via effects
    // rather than recreated so the ShaderMaterial isn't rebuilt each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [edge.id]
  );

  useEffect(() => {
    uniforms.uSpeed.value = speed;
  }, [uniforms, speed]);

  useFrame((state) => {
    if (!reducedMotion) {
      uniforms.uTime.value = state.clock.elapsedTime;
    }
  });

  return (
    <mesh geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={ACTIVE_VERTEX_SHADER}
        fragmentShader={ACTIVE_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

export default function Signals({ edges, activePath, speed = 0.35, reducedMotion = false }: SignalsProps) {
  const activeSet = useMemo(() => new Set(activePath ?? []), [activePath]);

  const ambientEdges = useMemo(() => edges.filter((e) => !activeSet.has(e.id)), [edges, activeSet]);
  const activeEdges = useMemo(() => edges.filter((e) => activeSet.has(e.id)), [edges, activeSet]);

  const geometryRef = useRef<THREE.BufferGeometry>(null);

  // Capacity-headroom buffers, grown (never shrunk) as needed — mirrors the
  // pattern NeuronField/BrainScene already use for the neuron buffers. This
  // matters because THREE.BufferAttribute has no `.dispose()`, and swapping
  // the object attached via `<primitive attach="attributes-position">` does
  // NOT free the outgoing attribute's GPU buffer (only full geometry/
  // renderer disposal does). Reallocating fresh attributes on every
  // `ambientEdges.length` change (which fluctuates continuously during
  // learn-on-demand graph growth — exactly this feature's core use case)
  // would orphan a GPU buffer per distinct edge count visited in a session.
  // Keeping one growable set of attributes, reused in place whenever the
  // current edge count still fits, bounds that to the same rare "capacity
  // ceiling exceeded" case NeuronField/BrainScene already accept.
  const ambientBuffersRef = useRef<{
    positionAttr: THREE.BufferAttribute;
    arcAttr: THREE.BufferAttribute;
    offsetAttr: THREE.BufferAttribute;
    capacity: number; // vertex capacity (2 per edge)
  } | null>(null);

  const { positionAttr, arcAttr, offsetAttr } = useMemo(() => {
    const neededVerts = Math.max(ambientEdges.length * 2, 1);
    const prev = ambientBuffersRef.current;
    if (!prev || neededVerts > prev.capacity) {
      const capacity = Math.max(neededVerts, prev ? Math.ceil(prev.capacity * 1.5) : 0, 64);
      ambientBuffersRef.current = {
        positionAttr: new THREE.BufferAttribute(new Float32Array(capacity * 3), 3),
        arcAttr: new THREE.BufferAttribute(new Float32Array(capacity), 1),
        offsetAttr: new THREE.BufferAttribute(new Float32Array(capacity), 1),
        capacity,
      };
    }
    // Always non-null here: either it already was, or the branch above just set it.
    return ambientBuffersRef.current!;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ambientEdges.length]);

  useEffect(() => {
    const pos = positionAttr.array as Float32Array;
    const arc = arcAttr.array as Float32Array;
    const off = offsetAttr.array as Float32Array;
    for (let i = 0; i < ambientEdges.length; i++) {
      const e = ambientEdges[i];
      const offset = offsetForId(e.id);
      const a = i * 2;
      const b = a + 1;
      pos[a * 3] = e.from[0];
      pos[a * 3 + 1] = e.from[1];
      pos[a * 3 + 2] = e.from[2];
      pos[b * 3] = e.to[0];
      pos[b * 3 + 1] = e.to[1];
      pos[b * 3 + 2] = e.to[2];
      arc[a] = 0;
      arc[b] = 1;
      off[a] = offset;
      off[b] = offset;
    }
    positionAttr.needsUpdate = true;
    arcAttr.needsUpdate = true;
    offsetAttr.needsUpdate = true;
    geometryRef.current?.setDrawRange(0, ambientEdges.length * 2);
    geometryRef.current?.computeBoundingSphere();
  }, [ambientEdges, positionAttr, arcAttr, offsetAttr]);

  const ambientUniforms = useMemo(
    () => ({ uTime: { value: 0 }, uSpeed: { value: speed } }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    ambientUniforms.uSpeed.value = speed;
  }, [ambientUniforms, speed]);

  useFrame((state) => {
    if (!reducedMotion) {
      ambientUniforms.uTime.value = state.clock.elapsedTime;
    }
  });

  return (
    <group>
      <lineSegments frustumCulled={false}>
        <bufferGeometry ref={geometryRef}>
          <primitive object={positionAttr} attach="attributes-position" />
          <primitive object={arcAttr} attach="attributes-aArc" />
          <primitive object={offsetAttr} attach="attributes-aOffset" />
        </bufferGeometry>
        <shaderMaterial
          uniforms={ambientUniforms}
          vertexShader={AMBIENT_VERTEX_SHADER}
          fragmentShader={AMBIENT_FRAGMENT_SHADER}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </lineSegments>
      {activeEdges.map((edge) => (
        <ActiveEdgeTube key={edge.id} edge={edge} speed={speed} reducedMotion={reducedMotion} />
      ))}
    </group>
  );
}
