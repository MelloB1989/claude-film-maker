// Depth of field: a thin lens (cocPx), and a two-pass gather that renders it from a colour + depth pair (DofPass).
//
// 1. Half-resolution gather (two outputs, MRT). Each half-res pixel stands for a 2x2 block of the full-res frame and
//    reads full-res pixels over a graded Poisson disc on the pixel lattice, sorted by radius. A sample's colour and
//    depth come from the same pixel, so nothing is ever classified by one surface and coloured by another. Two layers,
//    kept apart so neither bleeds into the other:
//    - near: pixels in front of the focus plane, scattered as gathered. A pixel lends this one a/(pi c²) of its light
//      (its share a of the kernel's area over the area of its own disc) if its disc reaches here, so the layer's
//      coverage is physical and falls off softly past a near object's silhouette.
//    - far and focus: gathered over this pixel's own disc, a sample reaching only as far as the smaller of the two discs
//      does, so a sharp object never smears into the soft background behind it and the background never creeps over
//      it. Behind a near pixel, what is visible around it stands in for what it hides.
//    The far layer keeps its block's signed CoC in alpha for the second pass.
// 2. Full-resolution composite: the near layer (premultiplied, a small tent) over a blend of the sharp frame and the
//    far layer by the pixel's own CoC. The far layer is upsampled bilaterally (texels whose CoC differs from the
//    pixel's drop out), so a sharp edge keeps no rim of the soft layer around it.
// No noise, no history: a pure function of its inputs. The disc comes in four interleaved quarters; a supersampling
// tap (SS_TAP, or the Stage's own passes) gathers one quarter, so the four taps of a frame add up to the whole disc.
import * as THREE from 'three';
import { FSPass, H, SS_TAP } from './gl';
import { GLSL_COMMON } from './glsl/common';

export interface DofParams {
  /** Focus distance: world units (metres) along the camera's view axis (Stage.depthOf gives it for a point). */
  focus: number;
  /** Aperture as an f-number (1.4 is wide open and shallow, 8 is deep). */
  fstop: number;
  /** Cap on the CoC diameter, in px of the logical 1080p frame (the same look at every output scale). */
  maxBlurPx?: number;
}

/**
 * The camera behind cocPx: a full-frame 36 mm gate shooting 16:9, so the picture is 20.25 mm tall. The vertical fov
 * then fixes the focal length (a 20° fov is a 57 mm lens, 30° is 38 mm) and the f-number its aperture.
 */
export const DOF_SENSOR_H = 0.02025;
/** Default cap on the CoC diameter (logical px). */
export const DOF_MAX_BLUR_PX = 48;

const focal = (fovDeg: number) => DOF_SENSOR_H / 2 / Math.tan((fovDeg * Math.PI) / 360);
/** The focus distance, kept beyond the focal length, where the thin lens stops forming an image. */
const focusOf = (p: DofParams, f: number) => Math.max(p.focus, f * 1.0001 + 1e-6);

/**
 * K in cocPx = K · |1/focus − 1/depth| (before the cap): f² · S / (N · (S − f)) on the sensor, in px of an image
 * `imageHeightPx` tall.
 */
export function cocScale(p: DofParams, fovDeg: number, imageHeightPx: number): number {
  const f = focal(fovDeg), S = focusOf(p, f);
  return (f * f * S * imageHeightPx) / (Math.max(p.fstop, 0.1) * (S - f) * DOF_SENSOR_H);
}

/**
 * A camera's vertical fov as its lens: with camera.zoom applied (three's getEffectiveFOV), so a punch-in by zoom blurs
 * as the longer lens it is (the circle grows with f², 2.26x for a 1.5x zoom). Exactly camera.fov at zoom 1.
 */
export const lensFov = (cam: THREE.PerspectiveCamera) => (cam.zoom === 1 ? cam.fov : cam.getEffectiveFOV());

/**
 * The lens as the DoF shaders take it, for an image `imgHeight` px tall: `s` its px per logical px, `maxR` the cap on
 * the CoC radius (px), and `coc` the uCoc uniform, the signed CoC radius as c = A + B·d of a perspective depth-buffer
 * value d (c = K·(1/S − 1/z), and 1/z = 1/n − d·(f − n)/(n·f)), with the cap. The lens is the camera's, zoom included.
 */
export function dofUniforms(p: DofParams, cam: THREE.PerspectiveCamera, imgHeight: number) {
  const s = imgHeight / H, fov = lensFov(cam);
  const K = (cocScale(p, fov, H) * s) / 2, S = focusOf(p, focal(fov)), n = cam.near, f = cam.far;
  const maxR = ((p.maxBlurPx ?? DOF_MAX_BLUR_PX) * s) / 2;
  return { s, maxR, coc: [K / S - K / n, (K * (f - n)) / (n * f), maxR] as [number, number, number] };
}

/**
 * Thin-lens circle of confusion: the blur-disc DIAMETER, in px of an image `imageHeightPx` tall, of a point `depth`
 * metres down the view axis, for a camera with vertical field of view `fovDeg` (on DOF_SENSOR_H) focused per `p`.
 * 0 at the focus distance, proportional to |1/focus − 1/depth|, capped at p.maxBlurPx (DOF_MAX_BLUR_PX by default).
 * Pure: the shaders use the same K.
 */
export function cocPx(depth: number, p: DofParams, fovDeg: number, imageHeightPx: number): number {
  const S = focusOf(p, focal(fovDeg));
  const c = cocScale(p, fovDeg, imageHeightPx) * Math.abs(1 / S - 1 / depth);
  return Math.min(c, p.maxBlurPx ?? DOF_MAX_BLUR_PX);
}

// ---------------------------------------------------------------------------------------------------- the kernel

/**
 * A graded Poisson disc on the pixel lattice, for a gather centred on a pixel corner (a half-res pixel's 2x2 block):
 * - every pixel centre (i + ½, j + ½) out to `core` px, then a fraction core / r of each 1 px ring (a sample every
 *   ~sqrt(r / core) px), the picks spread by best-candidate (each the ring pixel farthest from every pick so far);
 * - point-symmetric about the centre, so the disc has no drift;
 * - each sample carries the area it stands for, so a sum over the kernel integrates over the disc;
 * - sorted by radius, inside out.
 * With `parts` > 1 it is dealt into interleaved parts: all of them share the dense core, and each outer ring's picks
 * (in angle order, with their mirrors) go round the parts; each part is a whole disc on its own, and together they
 * are the full one. Returns one Float32Array of [x, y, r, area] per part. The full disc has about 12·R samples at
 * core 2 (296 at R = 24, the default cap at 1080p): it grows linearly with R, not with the disc's area. Core 2 renders
 * the stage test within a level or two of core 3 (mean 0.09 levels) for two thirds of the gather's cost.
 */
export function latticeDisc(R: number, parts = 1, core = 2): Float32Array[] {
  const rings: [number, number, number][][] = [];
  const lim = Math.ceil(R) + 1;
  // the upper half-plane (j >= 0); each pick is mirrored to (-x, -y)
  for (let j = 0; j < lim; j++) for (let i = -lim; i < lim; i++) {
    const x = i + 0.5, y = j + 0.5, r = Math.hypot(x, y);
    if (r <= R + 0.5) (rings[Math.floor(r)] ??= []).push([x, y, r]);
  }
  const all: number[][] = []; // every pick so far, both halves (for best-candidate)
  const out: number[][][] = Array.from({ length: parts }, () => []);
  for (let k = 0; k < rings.length; k++) {
    const ring = rings[k];
    if (!ring) continue;
    const m = Math.max(1, Math.round(ring.length * Math.min(1, core / (k + 0.5))));
    const near = all.filter((p) => p[2]! > k - 2.5); // earlier picks close enough to matter
    const pool = ring.slice(), picks: [number, number, number][] = [];
    for (let n = 0; n < m; n++) {
      let best = 0, bestD = -1;
      for (let a = 0; a < pool.length; a++) {
        const [x, y] = pool[a]!;
        let d = Infinity;
        for (const p of near) d = Math.min(d, (p[0]! - x) ** 2 + (p[1]! - y) ** 2);
        if (d > bestD + 1e-9) { bestD = d; best = a; }
      }
      const [x, y, r] = pool.splice(best, 1)[0]!;
      picks.push([x, y, r]);
      near.push([x, y, r], [-x, -y, r]);
      all.push([x, y, r], [-x, -y, r]);
    }
    // deal the ring: shared by every part when it is dense (the core) or too thin to go round
    const shared = m === ring.length || m < parts;
    picks.sort((a, b) => Math.atan2(a[1], a[0]) - Math.atan2(b[1], b[0]));
    for (let p = 0; p < parts; p++) {
      const mine = shared ? picks : picks.filter((_, j) => (j + k) % parts === p);
      const area = ring.length / mine.length;
      for (const [x, y, r] of mine) out[p]!.push([x, y, r, area], [-x, -y, r, area]);
    }
  }
  return out.map((o) => {
    o.sort((a, b) => a[2]! - b[2]! || Math.atan2(a[1]!, a[0]!) - Math.atan2(b[1]!, b[0]!));
    return Float32Array.from(o.flat());
  });
}

/** Parts the disc is dealt into: one per supersampling tap. */
const PARTS = 4;

// ---------------------------------------------------------------------------------------------------- the passes

// The thin lens in GLSL: the signed CoC RADIUS in px of the target (+ behind the focus plane, − in front), capped.
// 1/z is linear in a perspective depth-buffer value d, so the CoC is too: c = A + B·d.
const LENS_GLSL = /* glsl */ `
uniform sampler2D tDepth;
uniform vec3 uCoc; // A, B, cap
float cocAt(ivec2 q) { return clamp(uCoc.x + uCoc.y * texelFetch(tDepth, q, 0).r, -uCoc.z, uCoc.z); }`;

const GATHER_FRAG = /* glsl */ `
precision highp float;
precision highp int;
precision highp sampler2D;
${GLSL_COMMON}
uniform sampler2D tColor;
uniform sampler2D tKern;  // latticeDisc, one row per part (the last row: the whole disc), a texel per sample
uniform int uRow, uN;
uniform float uNearMin;   // a pixel joins the near layer from this CoC radius (px) in front of the focus
${LENS_GLSL}
layout(location = 0) out vec4 oNear;
layout(location = 1) out vec4 oFar;

float nearness(float c) { return smoothstep(uNearMin, 2.0 * uNearMin, -c); }

void main() {
  ivec2 b = ivec2(gl_FragCoord.xy) * 2;
  ivec2 lim = textureSize(tColor, 0) - 1;
  vec2 o = vec2(b) + 1.0; // the block's centre, a pixel corner
  // the block's four pixels: the most blurred one speaks for the block, with those that agree with it
  float cB = 0.0;
  float cs4[4];
  vec3 col4[4];
  for (int i = 0; i < 4; i++) {
    ivec2 q = min(b + ivec2(i & 1, i >> 1), lim);
    cs4[i] = cocAt(q);
    col4[i] = texelFetch(tColor, q, 0).rgb;
    if (abs(cs4[i]) > abs(cB)) cB = cs4[i];
  }
  vec3 cCol = vec3(0.0);
  float cn = 0.0, tol = max(1.0, 0.25 * abs(cB));
  for (int i = 0; i < 4; i++) if (abs(cs4[i] - cB) <= tol) { cCol += col4[i]; cn += 1.0; }
  cCol /= max(cn, 1.0);

  float Rc = abs(cB), nC = nearness(cB);
  vec4 nearAcc = vec4(0.0), farAcc = vec4(0.0);
  for (int i = 0; i < uN; i++) {
    vec4 k = texelFetch(tKern, ivec2(i, uRow), 0); // x, y (px from the centre), r, area (px²)
    ivec2 q = clamp(ivec2(floor(o + k.xy)), ivec2(0), lim);
    float cs = cocAt(q);
    vec3 col = texelFetch(tColor, q, 0).rgb;
    float r = k.z, ac = abs(cs), ns = nearness(cs);
    // near: its light spread over its own disc lands here in proportion area / (pi c²), if the disc reaches
    nearAcc += vec4(col, 1.0) * (ns * sat(ac - r + 0.5) * k.w / (PI * max(ac * ac, uNearMin * uNearMin)));
    // far and focus, over this pixel's own disc: a sample reaches as far as the smaller disc does; behind a near
    // pixel, whatever is visible within its disc stands in for what it hides
    if (r <= Rc + 0.5) {
      float ce = mix(min(Rc, ac), Rc, nC);
      farAcc += vec4(col, 1.0) * ((1.0 - ns) * sat(ce - r + 0.5) * k.w / max(ce * ce, 1.0));
    }
  }
  float a = min(1.0, nearAcc.a);
  oNear = nearAcc.a > 0.0 ? vec4(nearAcc.rgb / nearAcc.a * a, a) : vec4(0.0);
  oFar = vec4(farAcc.a > 1e-8 ? farAcc.rgb / farAcc.a : cCol, cB);
}`;

const COMPOSITE_FRAG = /* glsl */ `
uniform sampler2D tColor;
uniform sampler2D tNear;
uniform sampler2D tFar;
${LENS_GLSL}
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec3 S = texelFetch(tColor, p, 0).rgb;
  float c = cocAt(p);
  ivec2 hs = textureSize(tFar, 0), hl = hs - 1;
  // far: the 4 nearest half-res texels, bilinear weights times CoC agreement (texel CoC in alpha)
  vec2 hp = (vec2(p) + 0.5) * 0.5 - 0.5;
  ivec2 h0 = ivec2(floor(hp));
  vec2 fr = hp - vec2(h0);
  vec4 acc = vec4(0.0), accB = vec4(0.0);
  for (int j = 0; j < 2; j++) for (int i = 0; i < 2; i++) {
    vec4 F = texelFetch(tFar, clamp(h0 + ivec2(i, j), ivec2(0), hl), 0);
    float wb = (i == 0 ? 1.0 - fr.x : fr.x) * (j == 0 ? 1.0 - fr.y : fr.y);
    float d = (c - F.a) / (1.0 + 0.25 * max(abs(c), abs(F.a)));
    acc += vec4(F.rgb, 1.0) * (wb * exp(-d * d));
    accB += vec4(F.rgb, 1.0) * wb;
  }
  vec3 far = acc.a > 1e-4 ? acc.rgb / acc.a : accB.rgb / max(accB.a, 1e-6);
  // near: premultiplied, smooth; four bilinear taps half a texel out make a small tent
  vec2 uv = (vec2(p) + 0.5) / vec2(textureSize(tColor, 0)), ht = 0.5 / vec2(hs);
  vec4 N = 0.25 * (texture(tNear, uv - ht) + texture(tNear, uv + ht) + texture(tNear, uv + vec2(ht.x, -ht.y)) + texture(tNear, uv + vec2(-ht.x, ht.y)));
  fragColor = vec4(N.rgb + (1.0 - N.a) * mix(S, far, smoothstep(0.5, 1.5, abs(c))), 1.0);
}`;

let tri: THREE.BufferGeometry | null = null;

/**
 * The two-pass depth of field (see the top of this file). `render` reads a colour texture and its depth texture (same
 * size, perspective depth from `cam`) and writes every pixel of `out` (the same size). `tap` (default SS_TAP) picks
 * the quarter of the disc to gather, 0..3; a negative tap gathers all of it. The half-res targets are made on first
 * use and follow the input size.
 */
export class DofPass {
  private half: THREE.WebGLRenderTarget | null = null;
  private kernels = new Map<number, { tex: THREE.DataTexture; n: number[] }>();
  private gather: THREE.RawShaderMaterial;
  private scene = new THREE.Scene();
  private cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private composite: FSPass;

  constructor() {
    tri ??= new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
    this.gather = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: 'precision highp float;\nin vec3 position;\nvoid main() { gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: GATHER_FRAG,
      uniforms: {
        tDepth: { value: null }, uCoc: { value: new THREE.Vector3() }, tColor: { value: null },
        tKern: { value: null }, uRow: { value: 0 }, uN: { value: 0 }, uNearMin: { value: 1 },
      },
      depthTest: false, depthWrite: false, blending: THREE.NoBlending,
    });
    const mesh = new THREE.Mesh(tri, this.gather);
    mesh.frustumCulled = false;
    this.scene.add(mesh);
    this.composite = new FSPass(COMPOSITE_FRAG, {
      tDepth: { value: null }, uCoc: { value: new THREE.Vector3() }, tColor: { value: null }, tNear: { value: null }, tFar: { value: null },
    });
  }

  /** The disc for a cap radius (px): PARTS rows, then the whole disc; `n` samples per row. */
  private kernel(R: number) {
    const key = Math.max(1, Math.round(R * 4) / 4);
    let k = this.kernels.get(key);
    if (!k) {
      const rows = [...latticeDisc(key, PARTS), ...latticeDisc(key, 1)];
      const n = rows.map((r) => r.length / 4), w = Math.max(...n);
      const data = new Float32Array(w * rows.length * 4);
      rows.forEach((r, i) => data.set(r, i * w * 4));
      const tex = new THREE.DataTexture(data, w, rows.length, THREE.RGBAFormat, THREE.FloatType);
      tex.minFilter = tex.magFilter = THREE.NearestFilter;
      tex.generateMipmaps = false;
      tex.needsUpdate = true;
      k = { tex, n };
      this.kernels.set(key, k);
    }
    return k;
  }

  render(renderer: THREE.WebGLRenderer, color: THREE.Texture, depth: THREE.DepthTexture, cam: THREE.PerspectiveCamera, p: DofParams, out: THREE.WebGLRenderTarget | null, tap = SS_TAP.value) {
    const img = color.image as { width: number; height: number };
    const hw = Math.ceil(img.width / 2), hh = Math.ceil(img.height / 2);
    if (!this.half || this.half.width !== hw || this.half.height !== hh) {
      this.half?.dispose();
      this.half = new THREE.WebGLRenderTarget(hw, hh, {
        count: 2, type: THREE.HalfFloatType, format: THREE.RGBAFormat, depthBuffer: false,
        minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
      });
    }
    // the lens in px of this image (maxBlurPx and cocPx are logical 1080p px)
    const { s, maxR, coc } = dofUniforms(p, cam, img.height);
    const k = this.kernel(maxR), row = tap >= 0 ? tap % PARTS : PARTS;
    const g = this.gather.uniforms, u = this.composite.u;
    for (const v of [g, u]) {
      v.tDepth!.value = depth;
      (v.uCoc!.value as THREE.Vector3).set(coc[0], coc[1], coc[2]);
      v.tColor!.value = color;
    }
    g.tKern!.value = k.tex;
    g.uRow!.value = row;
    g.uN!.value = k.n[row]!;
    g.uNearMin!.value = s;
    renderer.setRenderTarget(this.half);
    renderer.render(this.scene, this.cam);

    u.tNear!.value = this.half.textures[0];
    u.tFar!.value = this.half.textures[1];
    this.composite.render(renderer, out);
  }

  dispose() {
    this.half?.dispose();
    for (const k of this.kernels.values()) k.tex.dispose();
    this.kernels.clear();
    this.gather.dispose();
    this.composite.mat.dispose();
  }
}
