// ── AKKI Brain 3D — region centroids + concept→region mapping ──────────────
// The plan/design doc reference "centroids from the research" but no such
// literal table exists anywhere in this repo. Per project-controller ruling
// (see task-7 brief), these exact values are used, consistent with the
// procedural brain's ellipsoid radii (0.42, 0.55, 0.75):
//   x = left(-)/right(+) hemisphere axis
//   y = inferior(-)/superior(+)
//   z = posterior(-)/anterior(+)

export type RegionKey =
  | "frontal"
  | "parietal"
  | "temporal"
  | "occipital"
  | "cerebellum"
  | "stem";

export interface RegionDef {
  /**
   * Base centroid. For hemisphere-signed regions this is stored with a
   * positive (right hemisphere) x — callers get the mirrored (left, -x)
   * version via `regionForConcept`, never by reading this table directly
   * for a hemisphere-signed region.
   */
  position: readonly [number, number, number];
  /** true = this region has a left/right mirrored pair; false = midline (x always 0). */
  hemisphereSigned: boolean;
}

export const REGIONS: Record<RegionKey, RegionDef> = {
  frontal: { position: [0.2, 0.15, 0.45], hemisphereSigned: true },
  parietal: { position: [0.2, 0.3, -0.05], hemisphereSigned: true },
  temporal: { position: [0.35, -0.15, 0.1], hemisphereSigned: true },
  occipital: { position: [0.15, 0.05, -0.55], hemisphereSigned: true },
  cerebellum: { position: [0, -0.55, -0.65], hemisphereSigned: false },
  stem: { position: [0, -0.45, -0.15], hemisphereSigned: false },
};

const REGION_KEYS: readonly RegionKey[] = [
  "frontal",
  "parietal",
  "temporal",
  "occipital",
  "cerebellum",
  "stem",
];

/** Deterministic FNV-1a string hash (stable across runs/machines, no Math.random). */
function hashString(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export interface RegionAssignment {
  /** Which of the 6 regions this concept was stably hashed to. */
  region: RegionKey;
  /**
   * true = right hemisphere (+x), false = left (-x). For midline regions
   * (cerebellum/stem) this is always false and has no visual meaning.
   */
  rightHemisphere: boolean;
  /** The region centroid with hemisphere sign already resolved — ready to use as a bias target. */
  centroid: readonly [number, number, number];
}

/**
 * Stably hashes `word` to one of the 6 brain regions. For the four
 * hemisphere-signed regions, a second bit off the same hash also picks a
 * hemisphere (left/right), so the same word always lands in the same spot.
 *
 * Design choice: rather than returning just the region key, this returns the
 * already-resolved `[x,y,z]` centroid (hemisphere sign applied) alongside the
 * region key/side — callers (NeuronField, region-biased placement) can use
 * whichever is most convenient without redoing the sign logic.
 */
export function regionForConcept(word: string): RegionAssignment {
  const normalized = (word ?? "").trim().toLowerCase();
  const h = hashString(normalized);

  const region = REGION_KEYS[h % REGION_KEYS.length];
  const def = REGIONS[region];

  // Independent-ish bit off the same hash (different bit range) decides hemisphere.
  const rightHemisphere = def.hemisphereSigned ? ((h >>> 8) & 1) === 1 : false;
  const sign = def.hemisphereSigned && !rightHemisphere ? -1 : 1;

  const centroid: readonly [number, number, number] = [
    def.position[0] * sign,
    def.position[1],
    def.position[2],
  ];

  return { region, rightHemisphere, centroid };
}
