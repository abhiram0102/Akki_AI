// ── AKKI Brain 3D — outer boundary shell ────────────────────────────────────
// The neuron cloud alone reads as an unbounded scatter of points with no
// perceivable edge. This wraps the ACTUAL point cloud in a translucent
// wireframe boundary, built directly from `generateBrainPoints` (the same
// function that places every neuron) via a convex hull per anatomical
// cluster -- so the boundary always matches the real cloud shape (its two
// hemisphere lobes + the cerebellum/stem bulge at the back), rather than a
// generic sphere/ellipsoid approximation that doesn't resemble a brain.
//
// Two hemisphere hulls (with a real gap between them, from the point
// generator's own hemisphere split) give the outer boundary; the gap itself
// plus a faint seam plane in it stand in for the inner boundary -- the
// sagittal fissure separating left/right. A third hull for the
// cerebellum/stem cluster gives that characteristic bulge at the back-
// bottom instead of a smooth ellipsoid tail.
//
// Deliberately NOT a solid/lit surface: a filled mesh would occlude the
// neuron glow behind it and fight the hologram look. EdgesGeometry +
// LineBasicMaterial gives a clean holographic wireframe at effectively free
// render cost -- a handful of static LineSegments draw calls, computed once
// (the hull itself never changes; only individual neurons animate).
import * as THREE from "three";
import { ConvexGeometry } from "three/addons/geometries/ConvexGeometry.js";
import { useEffect, useMemo } from "react";
import { generateBrainPoints, ELLIPSOID_RADII } from "./proceduralBrain";

const [, RY, RZ] = ELLIPSOID_RADII;

// Enough samples for a hull that closely tracks the real point cloud's
// silhouette (folds average out at hull scale; this only needs the overall
// shape) without being expensive -- computed once, not per frame.
const HULL_SAMPLE_COUNT = 3000;

// A point belongs to the cerebellum/stem cluster (rather than a cerebral
// hemisphere) if it's well into the back-bottom region generateBrainPoints
// reserves for that blob (centered around (0, -0.6, -0.7) — see
// proceduralBrain.ts). This is a coarse silhouette classifier, not an
// anatomical atlas: it only needs to separate "the back bulge" from "the two
// main lobes" well enough for the hull shapes to look right.
function isCerebellumStem(x: number, y: number, z: number): boolean {
  return y < -0.35 && z < -0.25;
}

interface HullGroups {
  left: THREE.Vector3[];
  right: THREE.Vector3[];
  cerebellumStem: THREE.Vector3[];
}

function classifyPoints(points: Float32Array): HullGroups {
  const groups: HullGroups = { left: [], right: [], cerebellumStem: [] };
  const count = Math.floor(points.length / 3);
  for (let i = 0; i < count; i++) {
    const x = points[i * 3];
    const y = points[i * 3 + 1];
    const z = points[i * 3 + 2];
    if (isCerebellumStem(x, y, z)) {
      groups.cerebellumStem.push(new THREE.Vector3(x, y, z));
    } else if (x < 0) {
      groups.left.push(new THREE.Vector3(x, y, z));
    } else {
      groups.right.push(new THREE.Vector3(x, y, z));
    }
  }
  return groups;
}

/** ConvexGeometry throws on fewer than 4 (non-degenerate) points -- guard defensively since the classifier's split is heuristic, not guaranteed balanced. */
function safeHullEdges(points: THREE.Vector3[]): THREE.EdgesGeometry | null {
  if (points.length < 4) return null;
  try {
    const hull = new ConvexGeometry(points);
    const edges = new THREE.EdgesGeometry(hull, 1);
    hull.dispose();
    return edges;
  } catch {
    // Degenerate (near-coplanar) point set -- skip that piece rather than crash the scene.
    return null;
  }
}

export default function BrainShell() {
  const hullEdges = useMemo(() => {
    const points = generateBrainPoints(HULL_SAMPLE_COUNT);
    const groups = classifyPoints(points);
    return {
      left: safeHullEdges(groups.left),
      right: safeHullEdges(groups.right),
      cerebellumStem: safeHullEdges(groups.cerebellumStem),
    };
  }, []);

  useEffect(
    () => () => {
      hullEdges.left?.dispose();
      hullEdges.right?.dispose();
      hullEdges.cerebellumStem?.dispose();
    },
    [hullEdges]
  );

  const lineMaterial = useMemo(
    () =>
      new THREE.LineBasicMaterial({
        color: new THREE.Color(0.35, 0.75, 0.95),
        transparent: true,
        opacity: 0.16,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    []
  );
  useEffect(() => () => lineMaterial.dispose(), [lineMaterial]);

  // Sagittal midline seam: a thin, very faint plane at x=0 spanning the
  // brain's y/z extent -- sits in the real gap between the two hemisphere
  // hulls, reading as a translucent membrane rather than a hard line.
  const seamGeometry = useMemo(() => new THREE.PlaneGeometry(RZ * 2.15, RY * 2.15), []);
  useEffect(() => () => seamGeometry.dispose(), [seamGeometry]);

  const seamMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(0.55, 0.85, 1.0),
        transparent: true,
        opacity: 0.05,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        toneMapped: false,
      }),
    []
  );
  useEffect(() => () => seamMaterial.dispose(), [seamMaterial]);

  return (
    <group frustumCulled={false}>
      {hullEdges.left && <lineSegments geometry={hullEdges.left} material={lineMaterial} />}
      {hullEdges.right && <lineSegments geometry={hullEdges.right} material={lineMaterial} />}
      {hullEdges.cerebellumStem && (
        <lineSegments geometry={hullEdges.cerebellumStem} material={lineMaterial} />
      )}
      {/* Default plane geometry lies in the XY plane (normal +Z); rotate 90°
          around Y so its normal points along X -- perpendicular to the
          hemisphere split, spanning height (Y) and depth (Z). */}
      <mesh geometry={seamGeometry} material={seamMaterial} rotation={[0, Math.PI / 2, 0]} />
    </group>
  );
}
