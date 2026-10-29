// Parallax: a 2.5D shot made of pictures at depths, the way a multiplane camera shoots painted cels. A plate (a painted
// background, with an optional depth map so its near rocks slide past its far hills) and the characters cut out of the
// keyframe over it (tools/ film-anime-cutout), and a camera that pans, pushes, rolls and breathes: each layer takes its
// `depth` share of the camera's move, so a near layer slides past a far one. A pure function of time.
//
// Params:
//   layers: [{ src, depth 1, depthMap, relief 0.6, pivot 0.5, x 0, y 0, scale 1, opacity 1, breathe 0, edge, fadeIn 0,
//              fadeOut 0 }], bottom first:
//     src        a picture in the film's folder; a cut-out keeps its alpha (straight alpha in the PNG)
//     depth      the share of the camera's pan and push it takes: 0 stays put (a sky), 1 moves with the focus plane,
//                above 1 is nearer than it (a branch across the lens)
//     depthMap   a grey depth map of the picture (white near, tools/ film-anime-depth): its near parts take `relief` more
//                of the pan than its far parts, so one painting gains depth of its own
//     relief     how much more of the pan white takes than black (0.6: white moves 1.3x the layer, black 0.7x)
//     pivot      the depth map's grey that moves exactly with the layer (0.5)
//     x, y       the layer's offset from the frame's centre, fractions of the frame (+y down)
//     scale      its size: 1 covers the frame (the picture's aspect kept, the overhang cropped evenly)
//     breathe    a slow breath: the layer's height swells by this share (0.004 is a calm breath) about its bottom edge
//     edge       'clamp' (the picture's edge pixels run on past it: plates) or 'clear' (nothing past it: cut-outs);
//                default: 'clamp' for the first layer, 'clear' above it
//     opacity, fadeIn, fadeOut (s from the shot's start and before its end)
//   camera: { from: { x 0, y 0, zoom 1, roll 0 }, to: { ... }, ease 'inOutSine', at [0, 1] }: the move over the shot
//     (`at`: the share of the shot it runs over); x, y in fractions of the frame the camera travels (+x right, +y down:
//     the picture moves the other way), zoom a push in (1.1 = 10% closer at depth 1), roll degrees
//   shake 0: a slow handheld drift, px at the focus plane
//   background 'theme': what shows where no layer covers
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { FSPass, H, W } from '../../engine/gl';
import { filmUrl } from '../../engine/config';
import { ease } from '../../engine/util';
import type { Handles } from '../../engine/transition';
import { clearBackground, type Background } from '../common';

export interface LayerSpec {
  src: string;
  depth?: number;
  depthMap?: string;
  relief?: number;
  pivot?: number;
  x?: number;
  y?: number;
  scale?: number;
  opacity?: number;
  breathe?: number;
  edge?: 'clamp' | 'clear';
  fadeIn?: number;
  fadeOut?: number;
}

export interface CameraKey { x?: number; y?: number; zoom?: number; roll?: number }
export interface CameraMove { from?: CameraKey; to?: CameraKey; ease?: keyof typeof ease | 'inOutSine'; at?: [number, number] }

const inOutSine = (t: number) => 0.5 - 0.5 * Math.cos(Math.PI * t);

/** The camera at progress u (0..1 through the shot): its pan in px, its push and its roll in radians. */
export function cameraAt(m: CameraMove | undefined, u: number): { px: number; py: number; zoom: number; roll: number } {
  const a = m?.from ?? {}, b = m?.to ?? a, [u0, u1] = m?.at ?? [0, 1];
  const x = Math.min(1, Math.max(0, (u - u0) / Math.max(1e-6, u1 - u0)));
  const fn = m?.ease === undefined || m.ease === 'inOutSine' ? inOutSine : ease[m.ease];
  const k = fn(x);
  const lerp = (p = 0, q = p) => p + (q - p) * k;
  return {
    px: lerp(a.x, b.x) * W,
    py: lerp(a.y, b.y) * H,
    zoom: Math.exp(lerp(Math.log(a.zoom ?? 1), Math.log(b.zoom ?? a.zoom ?? 1))),
    roll: (lerp(a.roll, b.roll) * Math.PI) / 180,
  };
}

/** A smooth, seeded drift in -1..1 (two incommensurate sines per axis): the handheld shake. */
export function drift(t: number, seed: number): [number, number] {
  const s = seed * 1.618;
  return [
    0.6 * Math.sin(t * 0.83 + s) + 0.4 * Math.sin(t * 1.97 + 2.1 * s),
    0.6 * Math.sin(t * 0.71 + 3.3 * s) + 0.4 * Math.sin(t * 1.61 + 0.7 * s),
  ];
}

const FRAG = /* glsl */ `
uniform sampler2D tex; uniform sampler2D depth;
uniform bool hasDepth; uniform bool clampEdge;
uniform vec2 frame;      // W, H (logical px)
uniform vec2 size;       // the picture's covering size, px (times its scale)
uniform vec2 off;        // the layer's offset, px (+y down)
uniform vec2 pan;        // the camera's pan this layer takes, px (+y down)
uniform float zoom;      // the push this layer takes
uniform float roll;      // radians
uniform float relief; uniform float pivot;
uniform float breathe;   // the height's swell about the bottom edge (0: none)
uniform float opacity;
void main() {
  // the output pixel in px from the frame's centre, +y down
  vec2 s = (vec2(vUv.x, 1.0 - vUv.y) - 0.5) * frame;
  s = rot2(roll) * s;
  vec2 lp = s / zoom + pan - off;                 // the point on the layer, px from its centre
  lp.y = (lp.y - 0.5 * size.y) / (1.0 + breathe) + 0.5 * size.y;
  vec2 uv = lp / size + 0.5;
  if (hasDepth) {
    // the near parts take more of the pan: three fixed-point steps settle where the displaced ray lands
    vec2 base = uv;
    for (int i = 0; i < 3; i++) {
      float d = texture(depth, vec2(uv.x, 1.0 - uv.y)).r;
      uv = base + pan * relief * (d - pivot) / size;
    }
  }
  if (!clampEdge && (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0)) discard;
  vec4 c = texture(tex, vec2(clamp(uv.x, 0.0, 1.0), 1.0 - clamp(uv.y, 0.0, 1.0)));
  fragColor = vec4(c.rgb * c.a, c.a) * opacity;
}`;

interface Layer { spec: LayerSpec; tex: THREE.Texture; depth: THREE.Texture | null; pass: FSPass; aspect: number }

async function loadTexture(src: string, color: boolean): Promise<{ tex: THREE.Texture; w: number; h: number }> {
  const img = new Image();
  img.decoding = 'async';
  img.src = filmUrl(src);
  try {
    await img.decode();
  } catch {
    throw new Error(`picture ${filmUrl(src)} did not load`);
  }
  const tex = new THREE.Texture(img);
  tex.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  tex.flipY = true; // the picture's top row at v = 1: the shader samples (u, 1 − y), y down
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return { tex, w: img.naturalWidth, h: img.naturalHeight };
}

export class Parallax extends Scene {
  override handles: Handles = { head: 1, tail: 1 };
  private layers: Layer[] = [];

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  private get specs(): LayerSpec[] {
    const l = this.ctx.params.layers as LayerSpec[] | undefined;
    if (!Array.isArray(l) || !l.length) throw new Error(`shot ${this.ctx.id}: Parallax needs \`layers\`: [{ src, depth }, ...]`);
    return l;
  }

  override async init() {
    this.layers = await Promise.all(this.specs.map(async (spec, i) => {
      if (typeof spec.src !== 'string') throw new Error(`shot ${this.ctx.id}: layer ${i} needs a \`src\``);
      const [{ tex, w, h }, dm] = await Promise.all([loadTexture(spec.src, true), spec.depthMap ? loadTexture(spec.depthMap, false) : Promise.resolve(null)]);
      const pass = new FSPass(FRAG, {
        tex: { value: tex }, depth: { value: dm?.tex ?? null }, hasDepth: { value: !!dm },
        clampEdge: { value: (spec.edge ?? (i === 0 ? 'clamp' : 'clear')) === 'clamp' },
        frame: { value: new THREE.Vector2(W, H) }, size: { value: new THREE.Vector2() }, off: { value: new THREE.Vector2() },
        pan: { value: new THREE.Vector2() }, zoom: { value: 1 }, roll: { value: 0 }, relief: { value: spec.relief ?? 0.6 },
        pivot: { value: spec.pivot ?? 0.5 }, breathe: { value: 0 }, opacity: { value: 1 },
      }, { blending: THREE.CustomBlending, transparent: true });
      const m = pass.mat;
      m.blendEquation = THREE.AddEquation;
      m.blendSrc = THREE.OneFactor; m.blendDst = THREE.OneMinusSrcAlphaFactor;
      m.blendSrcAlpha = THREE.OneFactor; m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
      return { spec, tex, depth: dm?.tex ?? null, pass, aspect: w / h };
    }));
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const { renderer } = this.ctx;
    clearBackground(renderer, out, (this.ctx.params.background as Background | undefined) ?? 'theme');
    const u = (f.t - this.ctx.start) / Math.max(1e-6, this.ctx.end - this.ctx.start);
    const cam = cameraAt(this.ctx.params.camera as CameraMove | undefined, u);
    const shake = (this.ctx.params.shake as number | undefined) ?? 0;
    const [sx, sy] = drift(f.t, (this.ctx.params.n as number | undefined) ?? 1);
    const panX = cam.px + shake * sx, panY = cam.py + shake * sy;
    for (const L of this.layers) {
      const s = L.spec, k = s.depth ?? 1, u2 = L.pass.u;
      // cover the frame at scale 1, keeping the picture's aspect
      const cw = Math.max(W, H * L.aspect), ch = Math.max(H, W / L.aspect), sc = s.scale ?? 1;
      (u2.size!.value as THREE.Vector2).set(cw * sc, ch * sc);
      (u2.off!.value as THREE.Vector2).set((s.x ?? 0) * W, (s.y ?? 0) * H);
      (u2.pan!.value as THREE.Vector2).set(panX * k, panY * k);
      u2.zoom!.value = 1 + (cam.zoom - 1) * k;
      u2.roll!.value = cam.roll;
      u2.breathe!.value = (s.breathe ?? 0) * (0.5 + 0.5 * Math.sin(2 * Math.PI * 0.21 * f.t + 1.3 * k));
      const lt = f.t - this.ctx.start, rest = this.ctx.end - f.t;
      const fi = s.fadeIn ? Math.min(1, Math.max(0, lt / s.fadeIn)) : 1, fo = s.fadeOut ? Math.min(1, Math.max(0, rest / s.fadeOut)) : 1;
      u2.opacity!.value = (s.opacity ?? 1) * fi * fo;
      if (u2.opacity!.value > 0.001) L.pass.render(renderer, out);
    }
  }

  override dispose() {
    for (const L of this.layers) {
      L.tex.dispose();
      L.depth?.dispose();
      L.pass.mat.dispose();
    }
    this.layers = [];
  }
}

export default Parallax;
