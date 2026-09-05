// ── AKKI Brain 3D — neuron glow field ───────────────────────────────────────
// Renders a point cloud (positions from proceduralBrain.generateBrainPoints,
// or later a real anatomical surface sample) as one THREE.Points draw call
// with an additive-glow ShaderMaterial. Buffers are pre-allocated to a max
// capacity with setDrawRange so later tasks can grow the field live (SSE
// `grew`/`answer` events appending new neurons) without reallocating
// geometry every frame.

import * as THREE from "three";
import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { NEURON_VERTEX_SHADER, NEURON_FRAGMENT_SHADER } from "./shaders";

export interface NeuronFieldProps {
  /** Interleaved xyz positions, length === pointCount * 3. */
  points: Float32Array;
  /** Per-point activation in [0,1] (dim ambient -> hot gold). Defaults to 0 (all dormant). */
  activations?: Float32Array;
  /**
   * Per-point spawn time in seconds, same clock as the internal `uTime`
   * uniform (THREE.Clock elapsedTime). Points with no entry (or undefined
   * `spawnTimes`) are treated as already fully grown in. Pass real
   * "now" timestamps for points that should visibly pop in.
   */
  spawnTimes?: Float32Array;
  /**
   * Buffer capacity. Must be >= points.length / 3. Pass generous headroom
   * when the caller intends to grow the field live without recreating
   * geometry (each capacity change *does* reallocate). Defaults to the
   * current point count (no headroom).
   */
  maxCount?: number;
  /** Base point size in screen pixels before per-point size/LOD/activation scaling. */
  baseSize?: number;
}

// Sentinel meaning "spawned well before any real clock time" -> always
// renders at full grown-in size regardless of uTime.
const ALREADY_SPAWNED = -1e6;

function pseudoRandom01(i: number): number {
  const s = Math.sin(i * 12.9898) * 43758.5453;
  return s - Math.floor(s);
}

export default function NeuronField({
  points,
  activations,
  spawnTimes,
  maxCount,
  baseSize = 6,
}: NeuronFieldProps) {
  const pointCount = Math.floor(points.length / 3);
  const capacity = Math.max(maxCount ?? pointCount, pointCount, 0);

  const geometryRef = useRef<THREE.BufferGeometry>(null);
  const dpr = useThree((state) => state.viewport.dpr);

  // Buffers are keyed on `capacity` so growth headroom changes reallocate,
  // but ordinary position/activation/spawnTime updates (same capacity) reuse
  // the same typed arrays and are pushed via the effect below.
  const { positionAttr, spawnAttr, sizeAttr, activationAttr } = useMemo(() => {
    return {
      positionAttr: new THREE.BufferAttribute(new Float32Array(Math.max(capacity, 1) * 3), 3),
      spawnAttr: new THREE.BufferAttribute(new Float32Array(Math.max(capacity, 1)), 1),
      sizeAttr: new THREE.BufferAttribute(new Float32Array(Math.max(capacity, 1)), 1),
      activationAttr: new THREE.BufferAttribute(new Float32Array(Math.max(capacity, 1)), 1),
      // eslint-disable-next-line react-hooks/exhaustive-deps
    };
  }, [capacity]);

  useEffect(() => {
    const posArray = positionAttr.array as Float32Array;
    posArray.set(points.subarray(0, pointCount * 3));
    positionAttr.needsUpdate = true;

    const sizes = sizeAttr.array as Float32Array;
    const activationsArr = activationAttr.array as Float32Array;
    const spawnArr = spawnAttr.array as Float32Array;
    for (let i = 0; i < pointCount; i++) {
      sizes[i] = 0.55 + pseudoRandom01(i) * 0.9;
      activationsArr[i] = activations?.[i] ?? 0;
      spawnArr[i] = spawnTimes?.[i] ?? ALREADY_SPAWNED;
    }
    sizeAttr.needsUpdate = true;
    activationAttr.needsUpdate = true;
    spawnAttr.needsUpdate = true;

    geometryRef.current?.setDrawRange(0, pointCount);
    geometryRef.current?.computeBoundingSphere();
  }, [points, activations, spawnTimes, pointCount, positionAttr, sizeAttr, activationAttr, spawnAttr]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uBaseSize: { value: baseSize },
      uPixelRatio: { value: dpr },
    }),
    // Intentionally created once per mount; baseSize/dpr are pushed via the
    // effects below instead of recreating the uniforms object (which would
    // force ShaderMaterial to rebuild).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    uniforms.uBaseSize.value = baseSize;
  }, [uniforms, baseSize]);

  useEffect(() => {
    uniforms.uPixelRatio.value = dpr;
  }, [uniforms, dpr]);

  useFrame((state) => {
    uniforms.uTime.value = state.clock.elapsedTime;
  });

  return (
    <points frustumCulled={false}>
      <bufferGeometry ref={geometryRef}>
        <primitive object={positionAttr} attach="attributes-position" />
        <primitive object={spawnAttr} attach="attributes-aSpawnTime" />
        <primitive object={sizeAttr} attach="attributes-aSize" />
        <primitive object={activationAttr} attach="attributes-aActivation" />
      </bufferGeometry>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={NEURON_VERTEX_SHADER}
        fragmentShader={NEURON_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
