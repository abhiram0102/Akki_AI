// ── AKKI Brain 3D — neuron point glow shaders ───────────────────────────────
// A single additive-blended THREE.Points draw call for the whole neuron
// field. Per-point attributes drive spawn-in growth animation, base size,
// and activation (dim ambient neuron -> hot gold "on the answer path").

export const NEURON_VERTEX_SHADER = /* glsl */ `
uniform float uTime;
uniform float uBaseSize;
uniform float uPixelRatio;

attribute float aSpawnTime;
attribute float aSize;
attribute float aActivation;

varying float vActivation;

// Back-ease "pop" (overshoot then settle) - the GPU version of a spawn-in bounce.
float spawnEase(float t) {
  t = clamp(t, 0.0, 1.0);
  const float c4 = 2.0943951; // (2 * PI) / 3
  if (t <= 0.0) return 0.0;
  if (t >= 1.0) return 1.0;
  return pow(2.0, -10.0 * t) * sin((t * 10.0 - 0.75) * c4) + 1.0;
}

void main() {
  vActivation = aActivation;

  // Points not yet "born" (aSpawnTime in the future, or just spawned) grow
  // in over ~0.8s; points spawned long ago are simply at full size.
  float age = uTime - aSpawnTime;
  float growT = clamp(age / 0.8, 0.0, 1.0);
  float grow = spawnEase(growT);

  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);

  // Distance-based LOD: closer points render larger, up to a cap, and very
  // distant points shrink instead of holding a constant screen size.
  float dist = max(-mvPosition.z, 0.0001);
  float lod = clamp(220.0 / dist, 0.2, 2.6);

  // Active (on the current answer/reasoning path) neurons flare larger.
  float activationBoost = 1.0 + vActivation * 1.6;

  gl_PointSize = uBaseSize * aSize * grow * lod * activationBoost * uPixelRatio;
  gl_Position = projectionMatrix * mvPosition;
}
`;

export const NEURON_FRAGMENT_SHADER = /* glsl */ `
varying float vActivation;

void main() {
  // Soft radial glow from the point sprite center, discard outside the circle.
  vec2 centered = gl_PointCoord - vec2(0.5);
  float d = length(centered) * 2.0;
  if (d > 1.0) discard;

  float core = smoothstep(1.0, 0.0, d);
  float glow = pow(core, 2.2);

  // Dormant neurons: cool bioluminescent cyan/blue. Activated (answer path
  // / recently learned): warm gold — matches the 2D field's "truth" color.
  vec3 dim = vec3(0.24, 0.55, 0.95);
  vec3 hot = vec3(1.0, 0.82, 0.35);
  vec3 color = mix(dim, hot, clamp(vActivation, 0.0, 1.0));

  float intensity = glow * (0.6 + vActivation * 1.8);
  gl_FragColor = vec4(color * intensity, glow);
}
`;
