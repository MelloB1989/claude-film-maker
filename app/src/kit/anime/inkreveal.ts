// InkReveal: brush calligraphy (or any ink drawing on white) brushed onto the frame: the ink appears down the page (or
// across it) behind a wet, feathered edge, the way a brush lays it down, and a red seal stamps in after it. The picture
// is black (and red) ink on white; its white is taken out, so it lays over whatever is under it (a Stack layer).
//
// Params:
//   src                 the calligraphy, ink on white
//   x 0.5, y 0.5        its centre, a share of the frame (+y down)
//   height 0.8          its height, a share of the frame's height (its aspect kept)
//   ink                 recolour the black ink (a role or #hex); default: the picture's own
//   at 0.3, dur 1.8     when the brushing starts (s from the shot's start) and how long it takes
//   dir 'down'          'down' or 'right': the way the brush travels
//   bleed 0.06          how ragged and wet the brushing edge is
//   seal 0.5            s after the brushing ends that a red seal (the picture's red) stamps in; -1 with the ink
//   opacity 1, fadeOut 0 (s before the shot's end)
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { FSPass, H, W, clearRT } from '../../engine/gl';
import { filmUrl } from '../../engine/config';
import { lin } from '../../engine/palette';
import type { Handles } from '../../engine/transition';

const FRAG = /* glsl */ `
uniform sampler2D tex;
uniform vec2 frame, centre, size;   // px, +y down
uniform float edge, bleed, sealK, opacity, recolour; uniform vec3 inkCol; uniform bool across; uniform float seed;
void main() {
  vec2 s = vec2(vUv.x, 1.0 - vUv.y) * frame;
  vec2 uv = (s - centre) / size + 0.5;
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;
  vec3 I = texture(tex, vec2(uv.x, 1.0 - uv.y)).rgb;
  vec3 Id = toSRGB(I);
  // the ink over white: alpha from the darkest channel, the colour that over white gives the picture
  float a = sat(1.0 - min(Id.r, min(Id.g, Id.b)));
  vec3 C = a > 1e-3 ? sat((Id - (1.0 - a)) / a) : vec3(0.0);
  bool red = C.r - max(C.g, C.b) > 0.35;
  // the brushing: a ragged wet edge travels down (or across) the picture
  float along = across ? uv.x : uv.y;
  float n = fbm(uv * vec2(9.0, 7.0) + seed, 4) * bleed + snoise(uv * 60.0 + seed) * bleed * 0.25;
  float m = smoothstep(edge, edge - 0.04 - bleed, along + n);
  if (red) m = sealK;
  vec3 col = red ? C : mix(C, toSRGB(inkCol), recolour);
  float A = a * m * opacity;
  fragColor = vec4(toLinear(col) * A, A);
}`;

export class InkReveal extends Scene {
  override handles: Handles = { head: 0.5, tail: 0.5 };
  private pass: FSPass | null = null;
  private tex: THREE.Texture | null = null;
  private aspect = 1;

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  private p<T>(k: string, d: T): T {
    const v = this.ctx.params[k];
    return v === undefined ? d : (v as T);
  }

  override async init() {
    const src = this.p<string | undefined>('src', undefined);
    if (!src) throw new Error(`shot ${this.ctx.id}: InkReveal needs a \`src\``);
    const img = new Image();
    img.src = filmUrl(src);
    await img.decode().catch(() => { throw new Error(`picture ${filmUrl(src)} did not load`); });
    this.aspect = img.naturalWidth / img.naturalHeight;
    const tex = new THREE.Texture(img);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.needsUpdate = true;
    this.tex = tex;
    this.pass = new FSPass(FRAG, {
      tex: { value: tex }, frame: { value: new THREE.Vector2(W, H) }, centre: { value: new THREE.Vector2() }, size: { value: new THREE.Vector2() },
      edge: { value: 0 }, bleed: { value: 0.06 }, sealK: { value: 0 }, opacity: { value: 1 }, recolour: { value: 0 },
      inkCol: { value: new THREE.Vector3() }, across: { value: false }, seed: { value: 0 },
    }, { blending: THREE.CustomBlending, transparent: true });
    const m = this.pass.mat;
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = THREE.OneFactor; m.blendDst = THREE.OneMinusSrcAlphaFactor;
    m.blendSrcAlpha = THREE.OneFactor; m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    clearRT(this.ctx.renderer, out, [0, 0, 0], 0);
    const u = this.pass!.u, lt = f.t - this.ctx.start;
    const h = this.p('height', 0.8) * H, w = h * this.aspect;
    (u.centre!.value as THREE.Vector2).set(this.p('x', 0.5) * W, this.p('y', 0.5) * H);
    (u.size!.value as THREE.Vector2).set(w, h);
    const at = this.p('at', 0.3), dur = this.p('dur', 1.8), bleed = this.p('bleed', 0.06);
    const k = Math.min(1, Math.max(0, (lt - at) / dur));
    // an ease-out stroke: fast down the first characters, slowing into the last
    u.edge!.value = -0.1 + (1.2 + bleed) * (1 - Math.pow(1 - k, 1.6));
    u.bleed!.value = bleed;
    const seal = this.p('seal', 0.5), ts = seal < 0 ? at : at + dur + seal;
    u.sealK!.value = lt < ts ? 0 : Math.min(1, (lt - ts) / 0.08);
    const fo = this.p('fadeOut', 0), rest = this.ctx.end - f.t;
    u.opacity!.value = this.p('opacity', 1) * (fo > 0 ? Math.min(1, Math.max(0, rest / fo)) : 1);
    const ink = this.p<string | undefined>('ink', undefined);
    u.recolour!.value = ink ? 1 : 0;
    if (ink) (u.inkCol!.value as THREE.Vector3).set(...lin(ink));
    u.across!.value = this.p<string>('dir', 'down') === 'right';
    u.seed!.value = ((this.ctx.params.n as number | undefined) ?? 1) * 1.37;
    this.pass!.render(this.ctx.renderer, out);
    // the seal lands with a small jolt
    if (lt >= ts && lt < ts + 0.12) return { zoom: 1 + 0.006 * (1 - (lt - ts) / 0.12) };
  }

  override dispose() {
    this.tex?.dispose();
    this.pass?.mat.dispose();
    this.tex = null;
    this.pass = null;
  }
}

export default InkReveal;
