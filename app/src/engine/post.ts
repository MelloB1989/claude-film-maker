// Global post-processing: bloom + halation, chromatic aberration, tone shoulder, the grade (saturation, contrast,
// warmth, a tint wash, lift, scanlines), film grain, vignette, fades/flash, letterbox bars. Operates on the composited
// HDR (linear) frame. The grade is neutral by default and skipped when neutral, so a frame that sets none of it renders
// exactly as before it existed.
import * as THREE from 'three';
import { FSPass, makeRT, W, H, SCALE } from './gl';
import { BLOOM_CHROMA, LOOK, linearToSrgb } from './look';
import { NEUTRAL_GRADE, letterboxBar } from './looks';
import { lin } from './palette';

/** The tone shoulder (linear HDR -> 0..1 linear), shared with the engine's sampling error estimate. */
export const SHOULDER_GLSL = /* glsl */ `
vec3 shoulder(vec3 x) {
  // Identity below k. Above it the brightest channel rolls off along a smooth exponential shoulder and the other two
  // scale with it, so a glow keeps its hue and saturation: per channel, red clipped first and hot accent went pink,
  // hot accent2 mint. Only hot cores, from about 4 on the brightest channel, whiten.
  const float k = 0.72;
  float m = max(max(x.r, x.g), x.b);
  vec3 y = m <= k ? x : x * ((k + (1.0 - k) * (1.0 - exp(-(m - k) / (1.0 - k)))) / m);
  return mix(y, vec3(1.0), smoothstep(4.0, 16.0, m) * 0.85);
}`;

export interface PostParams {
  exposure: number;
  bloom: number; // bloom strength
  /** On a pixel's brightest channel (look.ts bloomLum): bloom opens at threshold - knee, gated by chroma (bloomKey). */
  bloomThreshold: number;
  bloomKnee: number; // soft knee half-width
  bloomRadius: number; // 0..1 upsample spread
  halation: number; // accent-red film halation around glows, driven by their red: accent halates, accent2 doesn't
  ca: number; // chromatic aberration: R and B shift 1.58·ca px at the left/right frame edges (2.4·ca px in the corners)
  grain: number; // grain amplitude (sRGB units), ~0.04-0.1
  vignette: number; // 0..1
  hud: number; // HUD opacity multiplier (crop marks)
  /** 0..1: the crop-mark frame (1 = in place, 0 = flown out past the edges); off unless a scene asks for it. */
  frame: number;
  /** 0..1: the frame is light (bone paper) — the HUD draws its crop marks in ink. */
  paper: number;
  fade: number; // fade to black 0..1
  flash: number; // additive bone-white flash 0..1+
  shake: [number, number]; // frame offset in px
  zoom: number; // frame zoom (1 = none), for punch-ins on hits
  invert: number; // 0..1 invert (ink <-> bone), applied before grain
  // the grade (looks.ts NEUTRAL_GRADE documents each; neutral by default)
  saturation: number;
  contrast: number;
  warmth: number;
  tint: number;
  tintColor: string;
  lift: number;
  letterbox: number;
  scanlines: number;
}

/** Every frame starts from the film look (look.ts: the values and the renders that set them); scenes override. */
export const DEFAULT_POST: PostParams = {
  ...LOOK,
  hud: 1,
  frame: 0,
  paper: 0,
  fade: 0,
  flash: 0,
  shake: [0, 0],
  zoom: 1,
  invert: 0,
  ...NEUTRAL_GRADE,
};

/** True when a frame's grade does anything (else the shader skips it: the frame renders as it did before it existed). */
export const isGraded = (p: PostParams) =>
  p.saturation !== 1 || p.contrast !== 1 || p.warmth !== 0 || p.tint !== 0 || p.lift !== 0 || p.scanlines !== 0;

const MIPS = 7;
const displayOf = (c: [number, number, number]): [number, number, number] => [linearToSrgb(c[0]), linearToSrgb(c[1]), linearToSrgb(c[2])];

export class Post {
  private prefilter: FSPass;
  private down: FSPass;
  private up: FSPass;
  private final: FSPass;
  private mips: THREE.WebGLRenderTarget[] = [];
  private ups: THREE.WebGLRenderTarget[] = [];

  constructor() {
    // the bloom pyramid stays at the logical resolution at every output scale (same radii, same look)
    let w = W >> 1, h = H >> 1;
    for (let i = 0; i < MIPS; i++) {
      this.mips.push(makeRT(Math.max(2, w), Math.max(2, h), { depthBuffer: false, pxScale: 1 }));
      this.ups.push(makeRT(Math.max(2, w), Math.max(2, h), { depthBuffer: false, pxScale: 1 }));
      w >>= 1; h >>= 1;
    }
    this.prefilter = new FSPass(/* glsl */ `
      uniform sampler2D src; uniform vec2 texel; uniform float threshold, knee;
      void main() {
        // 4-tap box downsample + soft threshold on luminance
        vec3 c = vec3(0.0);
${SCALE === 1 ? `        c += texture(src, vUv + texel * vec2(-1, -1)).rgb; c += texture(src, vUv + texel * vec2(1, -1)).rgb;
        c += texture(src, vUv + texel * vec2(-1, 1)).rgb;  c += texture(src, vUv + texel * vec2(1, 1)).rgb;
        c *= 0.25;` : `        // output scale > 1: the same 4x4-logical-px box from a SCALE x larger source, as 2x2-texel bilinear taps
        const int N = ${SCALE * 2};
        for (int j = 0; j < N; j++) for (int i = 0; i < N; i++)
          c += texture(src, vUv + texel * (vec2(float(i), float(j)) * 2.0 - float(N - 1)) / PX_SCALE).rgb;
        c /= float(N * N);`}
        c = min(c, vec3(40.0));
        float l = max(c.r, max(c.g, c.b));
        float rq = clamp(l - threshold + knee, 0.0, 2.0 * knee);
        rq = rq * rq / (4.0 * knee + 1e-5);
        float w = max(rq, l - threshold) / max(l, 1e-5);
        // only colour glows (look.ts bloomKey): gated by chroma, (max - min) / max, which no intensity changes, so bone,
        // white light and specular highlights never bloom however bright, while accent and accent2 pass whole
        w *= smoothstep(${BLOOM_CHROMA[0].toFixed(3)}, ${BLOOM_CHROMA[1].toFixed(3)}, (l - min(c.r, min(c.g, c.b))) / max(l, 1e-5));
        fragColor = vec4(c * w, 1.0);
      }`, { src: { value: null }, texel: { value: new THREE.Vector2() }, threshold: { value: 1 }, knee: { value: 0.5 } });
    this.down = new FSPass(/* glsl */ `
      uniform sampler2D src; uniform vec2 texel;
      void main() {
        // 13-tap downsample (Jimenez 2014)
        vec3 a = texture(src, vUv + texel * vec2(-2, -2)).rgb, b = texture(src, vUv + texel * vec2(0, -2)).rgb, c = texture(src, vUv + texel * vec2(2, -2)).rgb;
        vec3 d = texture(src, vUv + texel * vec2(-1, -1)).rgb, e = texture(src, vUv + texel * vec2(1, -1)).rgb;
        vec3 f = texture(src, vUv + texel * vec2(-2, 0)).rgb, g = texture(src, vUv).rgb, h = texture(src, vUv + texel * vec2(2, 0)).rgb;
        vec3 i = texture(src, vUv + texel * vec2(-1, 1)).rgb, j = texture(src, vUv + texel * vec2(1, 1)).rgb;
        vec3 k = texture(src, vUv + texel * vec2(-2, 2)).rgb, l = texture(src, vUv + texel * vec2(0, 2)).rgb, m = texture(src, vUv + texel * vec2(2, 2)).rgb;
        vec3 o = (d + e + i + j) * 0.125 + (a + b + g + f) * 0.03125 + (b + c + h + g) * 0.03125 + (f + g + l + k) * 0.03125 + (g + h + m + l) * 0.03125;
        fragColor = vec4(o, 1.0);
      }`, { src: { value: null }, texel: { value: new THREE.Vector2() } });
    this.up = new FSPass(/* glsl */ `
      uniform sampler2D src; uniform sampler2D prev; uniform vec2 texel; uniform float radius;
      void main() {
        // 9-tap tent upsample of the smaller level, added to this level
        vec2 o = texel * radius;
        vec3 s = texture(src, vUv - o).rgb + 2.0 * texture(src, vUv + vec2(0, -o.y)).rgb + texture(src, vUv + vec2(o.x, -o.y)).rgb
          + 2.0 * texture(src, vUv + vec2(-o.x, 0)).rgb + 4.0 * texture(src, vUv).rgb + 2.0 * texture(src, vUv + vec2(o.x, 0)).rgb
          + texture(src, vUv + vec2(-o.x, o.y)).rgb + 2.0 * texture(src, vUv + vec2(0, o.y)).rgb + texture(src, vUv + o).rgb;
        fragColor = vec4(texture(prev, vUv).rgb + s / 16.0, 1.0);
      }`, { src: { value: null }, prev: { value: null }, texel: { value: new THREE.Vector2() }, radius: { value: 1 } });
    this.final = new FSPass(/* glsl */ `
      uniform sampler2D src; uniform sampler2D bloomTex; uniform sampler2D haloTex; uniform sampler2D hudTex;
      uniform float exposure, bloom, halation, ca, grain, vignette, hud, fade, flash, time, zoom, invert;
      uniform vec2 shake; uniform vec2 res;
      uniform bool graded; uniform float saturation, contrast, warmth, tint, lift, scanlines, bar;
      uniform vec3 tintS; uniform vec3 liftS;
      ${SHOULDER_GLSL}
      void main() {
        vec2 uv = (vUv - 0.5) / zoom + 0.5 - shake / res;
        vec2 dc = uv - 0.5;
        float r2 = dot(dc * vec2(res.x / res.y, 1.0), dc * vec2(res.x / res.y, 1.0));
        vec2 off = dc * r2 * ca / res.x * 4.0;
        vec3 col;
        col.r = texture(src, uv + off).r;
        col.g = texture(src, uv).g;
        col.b = texture(src, uv - off).b;
        vec3 bl = texture(bloomTex, uv).rgb;
        vec3 ha = texture(haloTex, uv).rgb;
        col += bl * bloom;
        // film halation is the red layer's: it follows the red in the glow, scaled so accent halates exactly as a luma
        // drive would. (On luma, accent2, bright in green and low in red, threw 4x accent's red haze and muddied its glow.)
        col += C_ACCENT_BRIGHT * ha.r * (luma(C_ACCENT) / C_ACCENT.r) * halation;
        col *= exposure;
        // the HUD is a 2D layer: it mixes in display space like every Layer2D (gl.ts, Compositor 'srgb'), before the
        // shoulder so it gets grain & vignette too. A canvas uploads straight alpha: h.rgb is its colour as drawn.
        vec4 h = texture(hudTex, vUv);
        float hudA = h.a * hud;
        if (hudA > 0.0) col = toLinear(mix(toSRGB(max(col, 0.0)), toSRGB(h.rgb), hudA));
        col = shoulder(col);
        col = mix(col, vec3(0.8515) - col * 0.84, invert); // ink<->bone in linear-ish space
        col += C_FG * flash;
        if (graded) {
          // white balance (luma kept), then saturation about luma, in light
          if (warmth != 0.0) {
            float l0 = luma(col);
            col *= vec3(1.0 + 0.14 * warmth, 1.0 + 0.02 * warmth, 1.0 - 0.2 * warmth);
            col *= l0 / max(luma(col), 1e-6);
          }
          if (saturation != 1.0) col = max(mix(vec3(luma(col)), col, saturation), 0.0);
        }
        // vignette
        float v = smoothstep(0.95, 0.25, length(dc * vec2(1.0, 0.8)));
        col *= mix(1.0, v, vignette);
        col *= (1.0 - fade);
        vec3 s = toSRGB(sat(col));
        if (graded) {
          // in display values: an S-curve about mid-grey (0 and 1 kept), a soft-light wash, the lifted black, scanlines
          if (contrast != 1.0) { vec3 a = pow(s, vec3(contrast)), b = pow(1.0 - s, vec3(contrast)); s = a / max(a + b, 1e-6); }
          if (tint > 0.0) s = mix(s, (1.0 - 2.0 * tintS) * s * s + 2.0 * tintS * s, tint);
          if (lift > 0.0) s += lift * (1.0 - s) * liftS;
          if (scanlines > 0.0) s *= 1.0 - scanlines * 0.35 * (0.5 + 0.5 * cos(TAU * FRAG_PX.y / max(2.0, min(res.x, res.y) / 360.0)));
        }
        // film grain: two scales, stronger in mid-tones
${SCALE === 1 ? `        float g1 = hash12(gl_FragCoord.xy + fract(time * 13.37) * 1000.0) - 0.5;
        float g2 = hash12(floor(gl_FragCoord.xy / 2.0) + fract(time * 7.13) * 1000.0) - 0.5;` : `        // output scale > 1: the fine grain is per physical px with its amplitude raised by PX_SCALE so its
        // power per logical px (what survives a downscale) matches 1x; the coarse grain keeps 2x2-logical-px cells
        float g1 = (hash12(gl_FragCoord.xy + fract(time * 13.37) * 1000.0) - 0.5) * PX_SCALE;
        float g2 = hash12(floor(FRAG_PX / 2.0) + fract(time * 7.13) * 1000.0) - 0.5;`}
        float lm = luma(s);
        float amt = grain * (0.55 + 1.2 * lm * (1.0 - lm));
        s += (g1 * 0.6 + g2 * 0.4) * amt;
        s += (hash12(gl_FragCoord.xy * 1.37 + time) - 0.5) / 255.0; // dither
        // letterbox bars in the theme's bg, clean (after grain), anti-aliased over a physical px
        if (bar > 0.0) {
          float y = gl_FragCoord.y, ph = res.y * PX_SCALE;
          s = mix(toSRGB(C_BG), s, sat(min(y, ph - y) - bar * ph + 0.5));
        }
        fragColor = vec4(sat(s), 1.0);
      }`, {
      src: { value: null }, bloomTex: { value: null }, haloTex: { value: null }, hudTex: { value: null },
      exposure: { value: 1 }, bloom: { value: 0.5 }, halation: { value: 0.2 }, ca: { value: 1 }, grain: { value: 0.05 },
      vignette: { value: 0.3 }, hud: { value: 1 }, fade: { value: 0 }, flash: { value: 0 }, time: { value: 0 },
      zoom: { value: 1 }, invert: { value: 0 }, shake: { value: new THREE.Vector2() }, res: { value: new THREE.Vector2(W, H) },
      graded: { value: false }, saturation: { value: 1 }, contrast: { value: 1 }, warmth: { value: 0 }, tint: { value: 0 },
      lift: { value: 0 }, scanlines: { value: 0 }, bar: { value: 0 }, tintS: { value: new THREE.Vector3() }, liftS: { value: new THREE.Vector3() },
    });
  }

  /** Apply the chain: src (HDR linear) -> out (sRGB 8-bit target or screen). */
  render(renderer: THREE.WebGLRenderer, src: THREE.Texture, hud: THREE.Texture, out: THREE.WebGLRenderTarget | null, p: PostParams, time: number) {
    // bloom pyramid
    this.prefilter.u.src!.value = src;
    (this.prefilter.u.texel!.value as THREE.Vector2).set(1 / W, 1 / H);
    this.prefilter.u.threshold!.value = p.bloomThreshold;
    this.prefilter.u.knee!.value = p.bloomKnee;
    this.prefilter.render(renderer, this.mips[0]!);
    for (let i = 1; i < MIPS; i++) {
      const s = this.mips[i - 1]!;
      this.down.u.src!.value = s.texture;
      (this.down.u.texel!.value as THREE.Vector2).set(1 / s.width, 1 / s.height);
      this.down.render(renderer, this.mips[i]!);
    }
    // upsample: ups[i] = mips[i] + up(ups[i+1])
    let prevTex = this.mips[MIPS - 1]!.texture;
    for (let i = MIPS - 2; i >= 0; i--) {
      const small = i === MIPS - 2 ? this.mips[MIPS - 1]! : this.ups[i + 1]!;
      this.up.u.src!.value = prevTex;
      this.up.u.prev!.value = this.mips[i]!.texture;
      (this.up.u.texel!.value as THREE.Vector2).set(1 / small.width, 1 / small.height);
      this.up.u.radius!.value = 0.5 + p.bloomRadius;
      this.up.render(renderer, this.ups[i]!);
      prevTex = this.ups[i]!.texture;
    }
    const f = this.final.u;
    f.src!.value = src;
    f.bloomTex!.value = this.ups[0]!.texture;
    f.haloTex!.value = this.ups[3]!.texture;
    f.hudTex!.value = hud;
    f.exposure!.value = p.exposure;
    f.bloom!.value = p.bloom / 3; // pyramid sums ~MIPS levels; normalize
    f.halation!.value = p.halation;
    f.ca!.value = p.ca;
    f.grain!.value = p.grain;
    f.vignette!.value = p.vignette;
    f.hud!.value = p.hud;
    f.fade!.value = p.fade;
    f.flash!.value = p.flash;
    f.time!.value = time;
    f.zoom!.value = p.zoom;
    f.invert!.value = p.invert;
    (f.shake!.value as THREE.Vector2).set(p.shake[0], p.shake[1]);
    f.graded!.value = isGraded(p);
    f.saturation!.value = p.saturation;
    f.contrast!.value = p.contrast;
    f.warmth!.value = p.warmth;
    f.tint!.value = p.tint;
    f.lift!.value = p.lift;
    f.scanlines!.value = p.scanlines;
    f.bar!.value = letterboxBar(p.letterbox, W, H);
    if (p.tint !== 0) (f.tintS!.value as THREE.Vector3).set(...displayOf(lin(p.tintColor)));
    if (p.lift !== 0) {
      // the theme's bg2, its brightest display channel at 1: the lift's hue
      const d = displayOf(lin('bg2')), m = Math.max(d[0], d[1], d[2], 1e-6);
      (f.liftS!.value as THREE.Vector3).set(d[0] / m, d[1] / m, d[2] / m);
    }
    this.final.render(renderer, out);
  }
}
