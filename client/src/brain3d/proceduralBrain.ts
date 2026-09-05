// ── AKKI Brain 3D — procedural brain point cloud ────────────────────────────
// Pure geometry generator: no THREE/WebGL imports here, just math. Produces a
// brain-shaped point cloud (two cortical hemispheres + cerebellum + stem) so
// the 3D scene always has *something* to render even before/without a real
// anatomical GLTF model (see design doc §6.1/§6.3 — the model is gated on
// user approval; this is the fallback that always works).
//
// Recipe (per task brief / design doc §6.1):
//   sample sphere directions → ellipsoid radii (0.42, 0.55, 0.75) →
//   hemisphere offset ±rx*0.55 → medial-wall flatten →
//   3-octave noise normal displacement (cortical folds) →
//   denser cerebellum blob → brainstem capsule.
//
// No external noise library — a small dependency-free value-noise/fbm
// stands in for "simplex noise" here; it's smooth, continuous, and cheap,
// which is all the fold displacement needs.

/** Ellipsoid semi-axes for the cerebrum: x = left/right, y = inferior/superior, z = posterior/anterior. */
export const ELLIPSOID_RADII: readonly [number, number, number] = [0.42, 0.55, 0.75];

const HEMISPHERE_OFFSET_FACTOR = 0.55; // hemisphere centers sit at ±rx*0.55
const FISSURE_GAP = 0.035; // half-width of the flattened interhemispheric gap
const SHELL_THICKNESS = 0.16; // cortex points fill a shell, not an infinitely thin surface
const FOLD_AMPLITUDE = 0.045; // gyri/sulci displacement magnitude
const FOLD_FREQUENCY = 3.2; // noise sampling frequency over the unit sphere direction

const CEREBELLUM_CENTER: readonly [number, number, number] = [0, -0.6, -0.7];
const CEREBELLUM_RADII: readonly [number, number, number] = [0.22, 0.16, 0.2];

// Brainstem approximated as a capsule (thick line segment with radial jitter)
// running from just under the cerebrum down toward the cerebellum.
const STEM_TOP: readonly [number, number, number] = [0, -0.1, -0.05];
const STEM_BOTTOM: readonly [number, number, number] = [0, -0.62, -0.35];
const STEM_RADIUS = 0.075;

/** Fraction of points allocated to each part of the brain. Must sum to 1. */
const CORTEX_FRACTION = 0.86;
const CEREBELLUM_FRACTION = 0.1;
// remainder (0.04) goes to the stem.

// ---- tiny deterministic hash + value-noise (no new dependency) ------------

function hash3(x: number, y: number, z: number): number {
  const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453123;
  return s - Math.floor(s);
}

function lerp(a: number, b: number, t: number): number {
  return a + t * (b - a);
}

function fade(t: number): number {
  return t * t * (3 - 2 * t);
}

/** Cheap trilinear value noise, range roughly [-1, 1]. Stands in for simplex noise. */
function valueNoise3(x: number, y: number, z: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const zi = Math.floor(z);
  const u = fade(x - xi);
  const v = fade(y - yi);
  const w = fade(z - zi);

  const c000 = hash3(xi, yi, zi);
  const c100 = hash3(xi + 1, yi, zi);
  const c010 = hash3(xi, yi + 1, zi);
  const c110 = hash3(xi + 1, yi + 1, zi);
  const c001 = hash3(xi, yi, zi + 1);
  const c101 = hash3(xi + 1, yi, zi + 1);
  const c011 = hash3(xi, yi + 1, zi + 1);
  const c111 = hash3(xi + 1, yi + 1, zi + 1);

  const x00 = lerp(c000, c100, u);
  const x10 = lerp(c010, c110, u);
  const x01 = lerp(c001, c101, u);
  const x11 = lerp(c011, c111, u);
  const y0 = lerp(x00, x10, v);
  const y1 = lerp(x01, x11, v);
  return lerp(y0, y1, w) * 2 - 1;
}

/** 3-octave fractal-brownian-motion noise, range roughly [-1, 1]. */
function fbm3(x: number, y: number, z: number, octaves = 3): number {
  let amp = 1;
  let freq = 1;
  let sum = 0;
  let norm = 0;
  for (let o = 0; o < octaves; o++) {
    sum += valueNoise3(x * freq, y * freq, z * freq) * amp;
    norm += amp;
    amp *= 0.5;
    freq *= 2.13; // deliberately non-power-of-2 to avoid octave grid alignment
  }
  return norm > 0 ? sum / norm : 0;
}

function gaussian(): number {
  const u = Math.max(Math.random(), 1e-9);
  const v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** Uniformly-distributed random unit vector (sphere direction). */
function randomUnitDirection(): [number, number, number] {
  let x = 0;
  let y = 0;
  let z = 0;
  let len = 0;
  do {
    x = gaussian();
    y = gaussian();
    z = gaussian();
    len = Math.sqrt(x * x + y * y + z * z);
  } while (len < 1e-6);
  return [x / len, y / len, z / len];
}

// ---- per-region samplers ---------------------------------------------------

function sampleCortexPoint(): [number, number, number] {
  const sign = Math.random() < 0.5 ? -1 : 1;
  const [dx, dy, dz] = randomUnitDirection();

  // Fill a shell near the surface (not an infinitely thin one) so the cloud
  // reads as a volume from any camera angle.
  const shellR = 1 - Math.random() * SHELL_THICKNESS;

  let px = dx * ELLIPSOID_RADII[0] * shellR;
  let py = dy * ELLIPSOID_RADII[1] * shellR;
  let pz = dz * ELLIPSOID_RADII[2] * shellR;

  // Hemisphere offset: push this lobe out along +/-x.
  px += sign * ELLIPSOID_RADII[0] * HEMISPHERE_OFFSET_FACTOR;

  // Medial-wall flatten: clip the inward-facing extent so the two lobes
  // don't interpenetrate across the midline -- this is what opens the
  // longitudinal fissure between hemispheres.
  px = sign > 0 ? Math.max(px, FISSURE_GAP) : Math.min(px, -FISSURE_GAP);

  // 3-octave noise displacement along the (pre-offset) surface normal —
  // cortical gyri/sulci folds.
  const n = fbm3(dx * FOLD_FREQUENCY, dy * FOLD_FREQUENCY, dz * FOLD_FREQUENCY, 3);
  const disp = n * FOLD_AMPLITUDE;
  px += dx * disp;
  py += dy * disp;
  pz += dz * disp;

  // Re-enforce the fissure gap: the fold displacement above can otherwise
  // push a point back across the midline (or even into the other
  // hemisphere) since noise can be negative. The medial wall isn't gyrated
  // in real anatomy anyway, so a hard final clamp here is correct, not just
  // a numerical safety net.
  px = sign > 0 ? Math.max(px, FISSURE_GAP) : Math.min(px, -FISSURE_GAP);

  return [px, py, pz];
}

function sampleCerebellumPoint(): [number, number, number] {
  const [dx, dy, dz] = randomUnitDirection();
  // r^(1/3) => uniform fill of the ellipsoid volume (denser per unit volume
  // than the cortex shell simply because the radii here are much smaller).
  const r = Math.cbrt(Math.random());
  return [
    CEREBELLUM_CENTER[0] + dx * CEREBELLUM_RADII[0] * r,
    CEREBELLUM_CENTER[1] + dy * CEREBELLUM_RADII[1] * r,
    CEREBELLUM_CENTER[2] + dz * CEREBELLUM_RADII[2] * r,
  ];
}

function sampleStemPoint(): [number, number, number] {
  const t = Math.random();
  const cx = lerp(STEM_TOP[0], STEM_BOTTOM[0], t);
  const cy = lerp(STEM_TOP[1], STEM_BOTTOM[1], t);
  const cz = lerp(STEM_TOP[2], STEM_BOTTOM[2], t);
  const [dx, dy, dz] = randomUnitDirection();
  const r = STEM_RADIUS * Math.cbrt(Math.random());
  return [cx + dx * r, cy + dy * r, cz + dz * r];
}

/**
 * Generates a procedural brain-shaped point cloud: two folded cortical
 * hemispheres + a cerebellum blob + a brainstem capsule, all within roughly
 * unit-radius model space (matches the ellipsoid radii above).
 *
 * @param count total number of points to generate.
 * @returns interleaved xyz positions, length === count * 3.
 */
export function generateBrainPoints(count: number): Float32Array {
  const safeCount = Math.max(0, Math.floor(count));
  const positions = new Float32Array(safeCount * 3);

  const nCortex = Math.round(safeCount * CORTEX_FRACTION);
  const nCerebellum = Math.round(safeCount * CEREBELLUM_FRACTION);
  const nStem = safeCount - nCortex - nCerebellum;

  let idx = 0;
  for (let i = 0; i < nCortex; i++, idx += 3) {
    const [x, y, z] = sampleCortexPoint();
    positions[idx] = x;
    positions[idx + 1] = y;
    positions[idx + 2] = z;
  }
  for (let i = 0; i < nCerebellum; i++, idx += 3) {
    const [x, y, z] = sampleCerebellumPoint();
    positions[idx] = x;
    positions[idx + 1] = y;
    positions[idx + 2] = z;
  }
  for (let i = 0; i < nStem; i++, idx += 3) {
    const [x, y, z] = sampleStemPoint();
    positions[idx] = x;
    positions[idx + 1] = y;
    positions[idx + 2] = z;
  }

  return positions;
}
