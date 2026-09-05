// ── AKKI Brain 3D — outer boundary shell ────────────────────────────────────
// The neuron cloud alone reads as an unbounded scatter of points with no
// perceivable edge. This adds a subtle, translucent wireframe outline of the
// brain's overall two-hemisphere silhouette (reusing the exact ellipsoid
// radii + hemisphere-offset the point cloud itself is built from, so the
// shell always matches the cloud it bounds) plus a faint seam plane down the
// sagittal midline -- the "inner boundary" separating left/right, standing
// in for the medial longitudinal fissure.
//
// Deliberately NOT a solid/lit surface: a filled mesh would occlude the
// neuron glow behind it and fight the hologram look. EdgesGeometry +
// LineBasicMaterial gives a clean holographic wireframe (no z-fighting or
// messy diagonal seams a `wireframe:true` material flag produces on a
// sphere's triangle mesh) at effectively free render cost -- two static
// LineSegments draw calls, never updated per frame.
import * as THREE from "three";
import { useEffect, useMemo } from "react";
import { ELLIPSOID_RADII } from "./proceduralBrain";

const [RX, RY, RZ] = ELLIPSOID_RADII;
// Matches proceduralBrain.ts's own HEMISPHERE_OFFSET_FACTOR (0.55) exactly,
// so this shell traces the same two-lobe layout the point cloud samples.
const HEMISPHERE_OFFSET = RX * 0.55;
// Each hemisphere is narrower than the full ellipsoid width (it's one lobe,
// not the whole brain) -- 0.62 keeps the two shells meeting near the seam
// without overlapping into each other's interior.
const HEMISPHERE_RX = RX * 0.62;

function useHemisphereEdges(sign: 1 | -1): THREE.EdgesGeometry {
  return useMemo(() => {
    const sphere = new THREE.SphereGeometry(1, 20, 14);
    sphere.scale(HEMISPHERE_RX, RY, RZ);
    sphere.translate(sign * HEMISPHERE_OFFSET, 0, 0);
    const edges = new THREE.EdgesGeometry(sphere, 1);
    sphere.dispose();
    return edges;
  }, [sign]);
}

export default function BrainShell() {
  const leftEdges = useHemisphereEdges(-1);
  const rightEdges = useHemisphereEdges(1);
  useEffect(() => () => leftEdges.dispose(), [leftEdges]);
  useEffect(() => () => rightEdges.dispose(), [rightEdges]);

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
  // brain's y/z extent -- reads as a translucent membrane between
  // hemispheres rather than a hard line, matching the hologram aesthetic.
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
      <lineSegments geometry={leftEdges} material={lineMaterial} />
      <lineSegments geometry={rightEdges} material={lineMaterial} />
      {/* Default plane geometry lies in the XY plane (normal +Z); rotate 90°
          around Y so its normal points along X -- perpendicular to the
          hemisphere split, spanning height (Y) and depth (Z). */}
      <mesh geometry={seamGeometry} material={seamMaterial} rotation={[0, Math.PI / 2, 0]} />
    </group>
  );
}
