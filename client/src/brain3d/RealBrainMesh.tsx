// ── AKKI Brain 3D — real anatomical brain mesh ──────────────────────────────
// Loads the real anatomical brain model at /models/human-brain.glb ("human-
// brain" by Yash_Dandavate, CC BY 4.0 -- https://sketchfab.com/3d-models/
// human-brain-e073c2590bc24daaa7323f4daa5b7784; attribution is also shown on
// the /brain page per the license's requirement). Renders it as a
// translucent holographic surface -- NOT the model's own photorealistic skin
// texture, which was replaced entirely with a fresnel rim-light shader
// (dim body, glowing silhouette/fold edges) to match the app's dark
// teal/purple hologram theme. Also exposes `useBrainSurfacePoints(count)`,
// which samples points directly across this real mesh's surface
// (MeshSurfaceSampler) so the scene's ambient neuron dust traces actual
// anatomy instead of a procedural ellipsoid approximation.
//
// Design note: an earlier attempt drew every triangle edge of a procedural
// shape as a wireframe boundary and it read as visual noise, not a clean
// outline -- rejected by the user. This deliberately does NOT wireframe the
// (much denser) real mesh either, for the same reason. The fresnel term
// alone reveals the fold silhouette without literal line clutter.
import * as THREE from "three";
import { useEffect, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import { MeshSurfaceSampler } from "three/addons/math/MeshSurfaceSampler.js";

export const BRAIN_MODEL_URL = "/models/human-brain.glb";
// The model's own bounding box is roughly [-1,1] x [-0.9,0.9] x [-0.82,0.82]
// -- scaled down to sit at the size the rest of the scene (neuron field,
// camera distances) was already built around.
const MODEL_SCALE = 0.62;

const FRESNEL_VERTEX_SHADER = /* glsl */ `
varying vec3 vNormal;
varying vec3 vViewPosition;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  vViewPosition = -mvPosition.xyz;
  gl_Position = projectionMatrix * mvPosition;
}
`;

const FRESNEL_FRAGMENT_SHADER = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying vec3 vNormal;
varying vec3 vViewPosition;
void main() {
  vec3 normal = normalize(vNormal);
  vec3 viewDir = normalize(vViewPosition);
  float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 2.5);
  // Dim body (barely there) + bright glowing rim where the surface curves
  // away from the camera -- the classic hologram-shell look, and it
  // reveals fold silhouettes without drawing a single wireframe line.
  float intensity = 0.05 + fresnel * 1.5;
  gl_FragColor = vec4(uColor * intensity, uOpacity * (0.12 + fresnel * 0.88));
}
`;

function firstMesh(root: THREE.Object3D): THREE.Mesh | null {
  let found: THREE.Mesh | null = null;
  root.traverse((child) => {
    if (!found && (child as THREE.Mesh).isMesh) found = child as THREE.Mesh;
  });
  return found;
}

/** The real mesh's geometry, world-transform baked in and scaled to scene size. Cached per GLTF load. */
export function useBrainSurfaceGeometry(): THREE.BufferGeometry | null {
  const gltf = useGLTF(BRAIN_MODEL_URL);
  return useMemo(() => {
    const mesh = firstMesh(gltf.scene);
    if (!mesh) return null;
    mesh.updateWorldMatrix(true, false);
    const geometry = mesh.geometry.clone();
    geometry.applyMatrix4(mesh.matrixWorld);
    geometry.scale(MODEL_SCALE, MODEL_SCALE, MODEL_SCALE);

    // We only ever need this mesh's geometry -- we render it with our own
    // fresnel shader (below), never the model's own material. The original
    // material carries 3 real textures (base color/normal/roughness) that
    // otherwise sit around for the app's whole lifetime (drei's useGLTF
    // cache never expires) for no benefit. Free them immediately.
    const originalMaterial = mesh.material as THREE.MeshStandardMaterial | THREE.MeshStandardMaterial[];
    const materials = Array.isArray(originalMaterial) ? originalMaterial : [originalMaterial];
    for (const mat of materials) {
      mat.map?.dispose();
      mat.normalMap?.dispose();
      mat.metalnessMap?.dispose();
      mat.roughnessMap?.dispose();
      mat.dispose();
    }

    return geometry;
  }, [gltf]);
}

/** Sample `count` points across the real mesh surface — used as the scene's ambient backdrop dust. */
export function useBrainSurfacePoints(count: number): Float32Array | null {
  const geometry = useBrainSurfaceGeometry();
  return useMemo(() => {
    if (!geometry) return null;
    const mesh = new THREE.Mesh(geometry);
    const sampler = new MeshSurfaceSampler(mesh).build();
    const points = new Float32Array(count * 3);
    const p = new THREE.Vector3();
    for (let i = 0; i < count; i++) {
      sampler.sample(p);
      points[i * 3] = p.x;
      points[i * 3 + 1] = p.y;
      points[i * 3 + 2] = p.z;
    }
    return points;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, count]);
}

export default function RealBrainMesh() {
  const geometry = useBrainSurfaceGeometry();

  const uniforms = useMemo(
    () => ({
      uColor: { value: new THREE.Color(0.3, 0.7, 1.0) },
      uOpacity: { value: 0.9 },
    }),
    []
  );

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms,
        vertexShader: FRESNEL_VERTEX_SHADER,
        fragmentShader: FRESNEL_FRAGMENT_SHADER,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        // FrontSide (not DoubleSide): with depthWrite disabled (needed so
        // this translucent shell doesn't occlude the neuron glow behind
        // it), a double-sided mesh's own front and back triangles have no
        // stable draw order relative to each other -- as the camera
        // orbits, which layer "wins" flips unpredictably, reading as a
        // screen-blink flicker. Culling back faces removes the conflict
        // entirely: only one triangle layer ever rasterizes per pixel.
        side: THREE.FrontSide,
      }),
    [uniforms]
  );
  useEffect(() => () => material.dispose(), [material]);

  if (!geometry) return null;

  return <mesh geometry={geometry} material={material} frustumCulled={false} />;
}

useGLTF.preload(BRAIN_MODEL_URL);
