// The float cloud of scene `ex` as one instanced draw of glyph cells (engine/glyphs.ts): about 40,000 cells, every
// numeral of ex-cloud.ts, animated on the GPU as a pure function of the song time and a few uniforms. Its vertex shader
// is the cloud's choreography (the breath, the shockwaves, the pings, the light, the overwrite's flaps and the collapse);
// the atlas, the cells' fragment shader (plain, flipping or morphing over a tile) and the actors that pose the cards'
// letters and the fatal line are the engine's.
import * as THREE from 'three';
import { GLYPH_VERT_HEAD, HINGE, glyphMaterial, glyphQuad, type GlyphGrid } from '../engine/glyphs';

/** What a cloud cell draws (em about the origin): a digit's ink (JetBrains Mono: 0.08–0.52 by -0.01–0.74), the
 * tile and the outline's anti-aliasing, all inside it. */
const QUAD = { x0: -0.02, y0: -0.17, w: 0.64, h: 1.06 } as const;
const f = (x: number) => x.toFixed(5);

// ------------------------------------------------------------------------------------------------ the cloud

/**
 * The cloud's vertex shader. Each instance is one cell of a numeral, at rest in the lattice; time moves it:
 * - its numeral breathes a fraction of a millimetre;
 * - shockwaves (a stamp's impact, a card's landing) push it out from their centre as their front passes;
 * - pings (a query) brighten it as their shell passes;
 * - light: a key from the upper left across the spheroid, its loose edge falling away, a band sweeping through;
 * - a flip schedule (the overwrite): a split-flap run landing on a beat, a tile behind the numeral while it flips;
 * - the collapse: after the drop (and its delay) its numeral falls under gravity, sliding to its slot on the line,
 *   squeezes into the slot's cell as it lands and goes.
 */
const CLOUD_VERT = /* glsl */ `${GLYPH_VERT_HEAD}
in vec4 aPos;  // the cell's origin (left end, baseline) at rest; its glyph (-1 blank)
in vec4 aNum;  // numeral id, strength, cell index (0..6), flags (1: region, 2: a Berlin slot)
in vec4 aFlip; // from glyph, to glyph, landing time (0: none), flaps (0: this cell stays)
in vec4 aFall; // line slot (0..1), the drop's delay, ellipsoidal radius, seed
uniform float uTime, uEm, uAdv, uStep;
uniform vec4 uShock[4];  // centre, time
uniform vec4 uShockK[4]; // amplitude (m), speed (m/s), width (m), decay (1/s)
uniform vec4 uPing[2];   // origin, time
uniform vec4 uPingK;     // speed (m/s), width (m), strength, life (s)
uniform vec4 uLit;       // numeral id lit (why?), level
uniform vec4 uKey;       // toward the key light, its share of the strength
uniform vec4 uSweep;     // a band's normal (unit), its offset along it (m)
uniform vec4 uSweepK;    // half-width (m), level
uniform vec4 uLine;      // the line's first cell origin (x, y, z), cell pitch
uniform vec4 uCollapse;  // drop time, gravity (m/s²), cells on the line, fade (s)
uniform vec4 uRegion;    // the region's lift, Berlin's landing time, breath (m), extra
uniform vec4 uFade;      // the whole cloud's strength, the far side's dimming, a lift of light (the beat's breath), unused
uniform vec4 uFocus;     // the focus distance (m down the view axis), dimming from, to (m off it), level there
uniform vec3 uSpheroid;

const vec4 QUAD = vec4(${f(QUAD.x0)}, ${f(QUAD.y0)}, ${f(QUAD.w)}, ${f(QUAD.h)}); // x0, y0, w, h (em)

float h1(float x) { return fract(sin(x * 127.1 + 311.7) * 43758.5453); }

void main() {
  float t = uTime;
  float id = aNum.x, bright = aNum.y, cellI = aNum.z, flags = aNum.w, seed = aFall.w;
  // the numeral's centre (its cells share it, so it moves as one)
  vec3 c = aPos.xyz + vec3((3.5 - cellI) * uAdv, ${f(HINGE)} * uEm, 0.0);
  vec3 move = uRegion.z * vec3(sin(t * 0.83 + seed * 6.283), sin(t * 0.61 + seed * 4.1), sin(t * 0.47 + seed * 2.9));
  for (int s = 0; s < 4; s++) {
    vec4 sh = uShock[s], sk = uShockK[s];
    float dt = t - sh.w;
    if (sk.x == 0.0 || dt <= 0.0) continue;
    vec3 d = c - sh.xyz;
    float r = length(d), x = (r - sk.y * dt) / sk.z;
    move += sk.x * exp(-dt * sk.w) * exp(-x * x) * d / max(r, 1e-4);
  }
  // light
  vec3 n = normalize(c / (uSpheroid * uSpheroid) + 1e-6);
  float rn = aFall.z;
  float lit = pow(max(dot(n, uKey.xyz), 0.0), 1.2);
  float edge = 1.0 - smoothstep(0.95, 1.08, rn);
  // within the spec's 25–60% of bone: where in the band is the key light's share (uKey.w) and the numeral's own
  float own = clamp((bright - 0.25) / 0.35, 0.0, 1.0);
  float b = (0.25 + 0.35 * mix(own, lit, uKey.w)) * mix(0.45, 1.0, edge);
  float band = dot(c, uSweep.xyz) - uSweep.w;
  b += uSweepK.y * exp(-band * band / (uSweepK.x * uSweepK.x)) * edge;
  b += uFade.z * edge;
  for (int s = 0; s < 2; s++) {
    vec4 pg = uPing[s];
    float dt = t - pg.w;
    if (dt <= 0.0 || dt > uPingK.w) continue;
    float r = (length(c - pg.xyz) - uPingK.x * dt) / uPingK.y;
    b += uPingK.z * exp(-r * r) * (1.0 - dt / uPingK.w);
  }
  b *= mix(1.0, 0.55, uFade.y * smoothstep(0.0, -uSpheroid.z, c.z));
  // what is far off the focus plane steps back (its blur already spreads it thin; this keeps the haze quiet)
  float vz = -(viewMatrix * modelMatrix * vec4(c + move, 1.0)).z;
  b *= mix(1.0, uFocus.w, smoothstep(uFocus.y, uFocus.z, abs(vz - uFocus.x)));
  bool region = mod(flags, 2.0) > 0.5;
  bool berlin = flags > 1.5;
  if (region) b = mix(b, max(b, 0.64), uRegion.x) + uRegion.w;
  if (abs(id - uLit.x) < 0.5) b = mix(b, 1.0, uLit.y);
  // the glyph: at rest, or a flap of the overwrite (digits are the atlas's first ten glyphs)
  vec4 glyph = vec4(aPos.w, -1.0, 0.0, 0.0);
  float tile = 0.0;
  if (aFlip.z > 0.0) {
    // each cell's own flap speed (a board's motors differ), so the flaps are out of phase; the last lands on the beat
    // (ex-cloud.ts flapAt is the same run on the CPU)
    float flapLen = uStep * (0.72 + 0.56 * h1(seed * 7.7 + cellI * 1.37));
    float land = aFlip.z, steps = aFlip.w, t0 = land - steps * flapLen;
    if (t >= land) glyph.x = aFlip.y;
    else if (steps > 0.5 && t >= t0) {
      float u = (t - t0) / flapLen, k = min(steps - 1.0, floor(u)), p = u - k;
      float digit = aFlip.x >= 0.0 && aFlip.x < 9.5 && aFlip.y >= 0.0 && aFlip.y < 9.5 ? 1.0 : 0.0;
      float between = floor(h1(seed * 13.7 + cellI * 3.1 + k * 7.31) * 10.0);
      float next = floor(h1(seed * 13.7 + cellI * 3.1 + (k + 1.0) * 7.31) * 10.0);
      float fromG = k < 0.5 ? aFlip.x : (digit > 0.5 ? between : aFlip.x);
      float toG = k > steps - 1.5 ? aFlip.y : (digit > 0.5 ? next : aFlip.y);
      glyph = vec4(fromG, toG, p * p, 1.0); // the flap falls under gravity: slow off the hinge, hard onto the stop
    }
    float near = land - 0.42;
    tile = smoothstep(near - 0.06, near + 0.04, t) * (1.0 - smoothstep(land + 0.05, land + 0.5, t));
    b = mix(b, max(b, 0.9), tile);
  }
  float alpha = uFade.x;
  if (berlin) alpha *= step(uRegion.y, t);
  // the collapse: a breath of anticipation first (the whole cloud lifts a few millimetres and hangs), then the drop
  vec3 cNow = c + move;
  float pre = clamp((t - (uCollapse.x - 0.24)) / 0.24, 0.0, 1.0);
  cNow.y += 0.006 * sin(3.14159265 * pre) * step(t, uCollapse.x);
  float squeeze = 0.0;
  float dt = t - (uCollapse.x + aFall.y);
  if (dt > 0.0) {
    // the whole sculpture drops at once (gravity is the same for all), keeping its shape; each numeral swings to its
    // slot only late in its fall, so the cloud's bottom drains into the line first, like an hourglass (ex-cloud.ts fall)
    float g = uCollapse.y;
    float h = max(c.y - uLine.y - ${f(HINGE)} * uEm, 1e-4);
    float dur = sqrt(2.0 * h / g);
    float fallen = min(0.5 * g * dt * dt, h);
    float u = min(dt / dur, 1.0), side = smoothstep(0.42, 1.0, u);
    float slotX = uLine.x + (floor(aFall.x * (uCollapse.z - 1.0) + 0.5) + 0.5) * uLine.w;
    cNow = vec3(mix(cNow.x, slotX, side), c.y - fallen, mix(cNow.z, uLine.z, side));
    squeeze = smoothstep(0.82, 1.0, u);
    alpha *= 1.0 - smoothstep(dur, dur + uCollapse.w, dt);
    b *= mix(1.0, 1.35, squeeze);
    tile = 0.0;
  }
  float cellX = mix((cellI - 3.5) * uAdv, -0.5 * uAdv, squeeze);
  vec3 origin = vec3(cNow.x + cellX, cNow.y - ${f(HINGE)} * uEm, cNow.z);
  // the quad covers a numeral glyph's ink and its flip tile, not the atlas cell's full reach (2.5x the pixels)
  vec2 e = QUAD.xy + corner * QUAD.zw;
  vec3 world = origin + vec3(e.x * (1.0 - 0.35 * squeeze), e.y * (1.0 - 0.2 * squeeze), 0.0) * uEm;
  vUv = (e - vec2(CELL_X0, CELL_Y0)) / vec2(CELL_W, CELL_H);
  vGlyph = glyph;
  vCol = vec4(boneAt(b), alpha);
  vTile = vec2(tile * alpha, 1.0);
  if (alpha <= 0.0 || (glyph.x < -0.5 && glyph.y < -0.5 && tile <= 0.0)) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0); // nothing to draw: outside the clip volume
    return;
  }
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(world, 1.0);
}`;

/** One cell of the cloud, as the cloud's attributes hold it. */
export interface CloudCell {
  /** Origin (left end, baseline) and glyph (-1 blank). */
  x: number; y: number; z: number; glyph: number;
  id: number; bright: number; cell: number; flags: number;
  /** The overwrite: from and to glyphs, the beat the last flap lands on (0: never), how many flaps (0: stays). */
  flipFrom: number; flipTo: number; land: number; steps: number;
  /** Its slot on the line (0..1), the drop's delay (s), its ellipsoidal radius, and a seed in 0..1 (float-safe). */
  slot: number; delay: number; rn: number; seed: number;
}

/** The uniforms the scene drives each frame. */
export function cloudUniforms() {
  const v4 = (x = 0, y = 0, z = 0, w = 0) => new THREE.Vector4(x, y, z, w);
  return {
    uTime: { value: 0 }, uEm: { value: 0.0075 }, uAdv: { value: 0.0045 }, uStep: { value: 0.07 },
    uShock: { value: [v4(), v4(), v4(), v4()] }, uShockK: { value: [v4(), v4(), v4(), v4()] },
    uPing: { value: [v4(0, 0, 0, 1e9), v4(0, 0, 0, 1e9)] }, uPingK: { value: v4(0.5, 0.03, 0, 1) },
    uLit: { value: v4(-1, 0) },
    uKey: { value: v4(0, 0, 1, 0) },
    uSweep: { value: v4(1, 0, 0, 99) }, uSweepK: { value: v4(0.05, 0) },
    uLine: { value: v4() }, uCollapse: { value: v4(1e9, 6, 63, 0.05) },
    uRegion: { value: v4(0, -1e9, 0, 0) },
    uFade: { value: v4(1, 0) },
    uFocus: { value: v4(1, 1e3, 2e3, 1) },
    uSpheroid: { value: new THREE.Vector3(0.5, 0.32, 0.32) },
  };
}
export type CloudUniforms = ReturnType<typeof cloudUniforms>;

export class CloudField {
  mesh: THREE.Mesh;
  u: CloudUniforms;
  private geo: THREE.InstancedBufferGeometry;
  private mat: THREE.RawShaderMaterial;

  constructor(cells: readonly CloudCell[], atlas: GlyphGrid) {
    const n = cells.length;
    const pos = new Float32Array(n * 4), num = new Float32Array(n * 4), flip = new Float32Array(n * 4), fall = new Float32Array(n * 4);
    cells.forEach((c, i) => {
      pos.set([c.x, c.y, c.z, c.glyph], i * 4);
      num.set([c.id, c.bright, c.cell, c.flags], i * 4);
      flip.set([c.flipFrom, c.flipTo, c.land, c.steps], i * 4);
      fall.set([c.slot, c.delay, c.rn, c.seed], i * 4);
    });
    this.geo = new THREE.InstancedBufferGeometry();
    glyphQuad(this.geo);
    this.geo.setAttribute('aPos', new THREE.InstancedBufferAttribute(pos, 4));
    this.geo.setAttribute('aNum', new THREE.InstancedBufferAttribute(num, 4));
    this.geo.setAttribute('aFlip', new THREE.InstancedBufferAttribute(flip, 4));
    this.geo.setAttribute('aFall', new THREE.InstancedBufferAttribute(fall, 4));
    this.geo.instanceCount = n;
    this.u = cloudUniforms();
    this.mat = glyphMaterial(CLOUD_VERT, atlas, this.u);
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
  }

  dispose() {
    this.geo.dispose();
    this.mat.dispose();
  }
}
