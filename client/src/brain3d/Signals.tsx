// ── AKKI Brain 3D — synapse signal flow ─────────────────────────────────────
// Renders edges between neurons as glowing pipes. Ambient edges are real 3D
// cylinder geometry (an InstancedMesh, one draw call regardless of edge
// count) so connections have actual thickness/silhouette instead of 1px
// hairlines — each pipe breathes gently in brightness, phase-offset per edge
// so they don't pulse in lockstep. Edges on the current answer/reasoning
// path ("activePath") are upgraded to individual emissive TubeGeometry
// meshes with a genuine travelling pulse along their length (per-vertex
// arc-length `aArc` + a shared `uTime` uniform) — thicker, brighter, and a
// richer animation than the ambient pipes so the answer path reads as "the
// signal that matters," not a different visual language.
//
// Design choices (see task-8 report for the original rationale; ambient
// rendering was later upgraded from flat LineSegments to instanced pipes):
//  - The brief's own prop sketch (`<Signals edges activePath />`) is a rough
//    interface note. Concretely: `edges` is the full ambient edge list with
//    resolved world-space endpoints (BrainScene resolves node ids -> [x,y,z]
//    once per graph change); `activePath` is the subset of those edge ids
//    that should be upgraded to tubes.
//  - Both the ambient pipe material and the per-edge active Tube materials
//    are unlit, additive-blended (MeshBasicMaterial / custom ShaderMaterial
//    respectively) — NOT lit MeshStandardMaterial, which would need
//    normals/light setup for no visual gain here, and additive-glow is more
//    consistent with the hologram look than a lit, occluding surface.
//  - `reducedMotion` freezes the pulse/breathe animation (skips advancing
//    time) per the design doc's graceful-degradation rule, without touching
//    geometry.

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

// Ambient pipes are thinner than the active answer path's tubes, so the
// "signal that matters" still reads as visually louder/thicker.
const AMBIENT_PIPE_RADIUS = 0.005;
const AMBIENT_PIPE_COLOR: readonly [number, number, number] = [0.24, 0.55, 0.95];

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

  // ── Ambient edges as real 3D pipes ──────────────────────────────────────
  // Originally a flat <lineSegments> (hairline, no real thickness — WebGL
  // ignores line-width requests on most platforms). Rendered instead as an
  // InstancedMesh of tiny cylinders so ambient connections read as actual
  // pipe/tract-like structures with real silhouette and occlusion, not a
  // scatter of 1px threads. One draw call regardless of edge count.
  //
  // Capacity-headroom growth, same rationale as NeuronField/BrainScene's own
  // buffer growth: InstancedMesh's instanceMatrix/instanceColor sizes are
  // fixed at construction (unlike a drawRange), so "growth" means building a
  // new, larger InstancedMesh only when the current one is too small — rare,
  // bounded, and the same accepted tradeoff already reviewed/approved
  // elsewhere in this file for the (now-replaced) BufferAttribute growth.
  const pipeGeometry = useMemo(() => new THREE.CylinderGeometry(1, 1, 1, 6, 1, true), []);
  useEffect(() => () => pipeGeometry.dispose(), [pipeGeometry]);

  const pipeMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: 0xffffff, // fully driven by per-instance color below
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    []
  );
  useEffect(() => () => pipeMaterial.dispose(), [pipeMaterial]);

  const ambientMeshRef = useRef<{ mesh: THREE.InstancedMesh; capacity: number } | null>(null);
  const ambientOffsetsRef = useRef<number[]>([]);

  const ambientMesh = useMemo(() => {
    const needed = Math.max(ambientEdges.length, 1);
    const prev = ambientMeshRef.current;
    if (!prev || needed > prev.capacity) {
      const capacity = Math.max(needed, prev ? Math.ceil(prev.capacity * 1.5) : 0, 64);
      const mesh = new THREE.InstancedMesh(pipeGeometry, pipeMaterial, capacity);
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      // The previous mesh's instanceMatrix/instanceColor buffers were
      // already uploaded to the GPU (it was drawn at least once before this
      // capacity outgrew it) — swapping which mesh renders does NOT free
      // that GPU memory on its own. Three.js auto-registers a 'dispose'
      // event listener on every InstancedMesh the first time it renders
      // (see three's WebGLObjects.js: onInstancedMeshDispose), which frees
      // exactly these two buffers — dispatching that event is the correct,
      // public way to trigger it. Left unfixed, a long session with the
      // graph growing repeatedly (learn-on-demand's whole point) accumulates
      // one orphaned buffer per capacity step, which contributed to a real
      // "Context Lost" GPU crash.
      if (prev) prev.mesh.dispatchEvent({ type: "dispose" });
      ambientMeshRef.current = { mesh, capacity };
    }
    return ambientMeshRef.current!.mesh;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ambientEdges.length, pipeGeometry, pipeMaterial]);

  // Scratch objects reused across the (potentially per-edge) matrix rebuild
  // so it doesn't allocate garbage every time the graph grows.
  const scratch = useMemo(
    () => ({
      m4: new THREE.Matrix4(),
      quat: new THREE.Quaternion(),
      from: new THREE.Vector3(),
      to: new THREE.Vector3(),
      dir: new THREE.Vector3(),
      mid: new THREE.Vector3(),
      up: new THREE.Vector3(0, 1, 0),
      scale: new THREE.Vector3(),
      color: new THREE.Color(),
    }),
    []
  );

  useEffect(() => {
    const offsets: number[] = new Array(ambientEdges.length);
    ambientMesh.count = ambientEdges.length;
    for (let i = 0; i < ambientEdges.length; i++) {
      const e = ambientEdges[i];
      offsets[i] = offsetForId(e.id);
      scratch.from.set(e.from[0], e.from[1], e.from[2]);
      scratch.to.set(e.to[0], e.to[1], e.to[2]);
      scratch.mid.addVectors(scratch.from, scratch.to).multiplyScalar(0.5);
      scratch.dir.subVectors(scratch.to, scratch.from);
      const length = scratch.dir.length();
      if (length < 1e-6) {
        scratch.quat.identity(); // coincident endpoints — collapse to a near-zero pipe, no normalize() by zero
      } else {
        scratch.dir.normalize();
        scratch.quat.setFromUnitVectors(scratch.up, scratch.dir);
      }
      scratch.scale.set(AMBIENT_PIPE_RADIUS, Math.max(length, 1e-4), AMBIENT_PIPE_RADIUS);
      scratch.m4.compose(scratch.mid, scratch.quat, scratch.scale);
      ambientMesh.setMatrixAt(i, scratch.m4);
      ambientMesh.setColorAt(i, scratch.color.setRGB(...AMBIENT_PIPE_COLOR));
    }
    ambientOffsetsRef.current = offsets;
    ambientMesh.instanceMatrix.needsUpdate = true;
    if (ambientMesh.instanceColor) {
      ambientMesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
      ambientMesh.instanceColor.needsUpdate = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ambientEdges, ambientMesh]);

  useFrame((state) => {
    if (reducedMotion || ambientEdges.length === 0) return;
    const t = state.clock.elapsedTime * speed;
    const offsets = ambientOffsetsRef.current;
    for (let i = 0; i < ambientEdges.length; i++) {
      // A whole ambient pipe is one instance color (constant along its
      // length) — a travelling dot-along-the-pipe isn't representable this
      // way, so instead each pipe gently breathes in brightness, phase-
      // offset per edge (same deterministic hash as before) so they don't
      // pulse in lockstep. The answer path's pipes (ActiveEdgeTube, below)
      // keep the real travelling pulse — this is only the ambient backdrop.
      const breathe = 0.5 + 0.5 * Math.sin((t - offsets[i]) * Math.PI * 2);
      const intensity = 0.35 + breathe * 0.65;
      scratch.color.setRGB(
        AMBIENT_PIPE_COLOR[0] * intensity,
        AMBIENT_PIPE_COLOR[1] * intensity,
        AMBIENT_PIPE_COLOR[2] * intensity
      );
      ambientMesh.setColorAt(i, scratch.color);
    }
    if (ambientMesh.instanceColor) ambientMesh.instanceColor.needsUpdate = true;
  });

  return (
    <group>
      <primitive object={ambientMesh} />
      {activeEdges.map((edge) => (
        <ActiveEdgeTube key={edge.id} edge={edge} speed={speed} reducedMotion={reducedMotion} />
      ))}
    </group>
  );
}
