// The Netflix explainer's drawing kit: one base scene (NfScene) every cutaway extends, and the marks they share.
//
// NfScene draws, under the scene's own marks:
//   - a dark-warm studio: a warm key pool, a perspective floor grid that fades to black, slow out-of-focus bokeh
//     (three parallax depths), all moving under a slow camera push, so a diagram sits in a room, not on a slide;
//   - the camera: a push (`push`, 0..0.08 of scale) about `focus` plus a drift; background layers move less (parallax).
// Modes (params, set film-wide by film.ts from the render variant):
//   matte: 'black' | 'grey' — no studio, the frame cleared to that colour: the two passes tools/alpha.py turns into
//          straight-alpha PNGs (premultiplied colour from the black pass, coverage from the difference).
//   panel: true — the diagram (authored in the 1920x1080 frame) drawn scaled into a glass card on the right half
//          (x 0.5..0.96 of the frame), a title bar above it, the rest of the frame clear: a side panel beside the
//          presenter.
// Every scene authors its beats in NOMINAL seconds (`nominal`); a shot given another length plays them scaled to
// fit, so a retime to the cue sheet is a `length` change only.
import { THREE } from '@engine/three';
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H, Layer2D } from '@engine/gl';
import { rgba, LIN } from '@engine/palette';
import { Stage } from '@engine/stage';
import { F, font } from '@engine/type';
import { clamp, ease, hash, lerp, mulberry32, noise1, smoothstep, TAU } from '@engine/util';

export { W, H, rgba, F, font, clamp, ease, hash, lerp, smoothstep, TAU, glowInk };
export type { Frame };

type Ctx = CanvasRenderingContext2D;

/** 0..1 progress through [at, at + dur], eased (outCubic by default). */
export const rev = (t: number, at: number, dur = 0.6, fn: (x: number) => number = ease.outCubic) => fn(clamp((t - at) / dur));
/** 0..1 springy landing (a small overshoot) through [at, at + dur]. */
export const land = (t: number, at: number, dur = 0.7) => {
  const x = clamp((t - at) / dur);
  return x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.exp(-6 * x) * Math.cos(7.5 * x) * (1 - x);
};

export interface Look { matte: '' | 'black' | 'grey'; panel: boolean }

// ——— the 3D stage (full-frame shots) ————————————————————————————————————————————————————————————————————————
// A full-frame shot is drawn on five 2D layers that stand at different depths in front of a perspective camera, so a
// slow camera move gives real parallax and the engine's depth of field focuses on the diagram:
//   studio  z = -0.8   the warm ground, grid and bokeh (far: well out of focus)
//   back    z = -0.03  cards and panels (card() draws here): the content floats a little in front of its card
//   mid     z = 0      the diagram (in focus)
//   glow    z = 0.002  the glow layer, added as light at the glow level (it blooms in the post)
//   front   z = +0.018 headings and pills (heading(), pill())
// Each plane is scaled so that at rest (the camera at D on the axis) it maps to the frame exactly as the flat layout.
const D = 1, FOV = 24;
const Z = { studio: -0.8, back: -0.03, mid: 0, glow: 0.002, front: 0.018 } as const;
/** Where card() and pill()/heading() draw while a 3D frame is drawn (null: on the context they are given). */
let BACK: Ctx | null = null, FRONT: Ctx | null = null;
/** Draw on `to` (when set) with `c`'s transform and alpha. */
function on(c: Ctx, to: Ctx | null, draw: (x: Ctx) => void) {
  if (!to) return draw(c);
  to.save(); to.setTransform(c.getTransform()); to.globalAlpha = c.globalAlpha;
  draw(to);
  to.restore();
}
interface S3 { stage: Stage; layers: Record<keyof typeof Z, Layer2D> }

export abstract class NfScene extends Scene2D {
  /** The beats' timebase: the shot's length they were authored for (s). */
  protected abstract nominal: number;
  /** The panel's title (panel mode). */
  protected panelTitle = '';
  /** Scene time in nominal seconds. */
  protected t = 0;
  protected look: Look = { matte: '', panel: false };

  /**
   * The time (s, shot clock) the shot's VO says `word` (its `nth` occurrence, case and punctuation ignored), plus
   * `lag` frames (elements land 0-3 frames after the word starts); `fb` when the word is not in the line.
   */
  protected cue(word: string, fb: number, nth = 0, lag = 2): number {
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9']/g, '');
    const ws = this.p<{ w: string; f: number }[]>('words', []).filter((w) => norm(w.w) === norm(word));
    const w = ws[nth];
    return w ? (w.f + lag) / 24 : fb;
  }

  private s3: S3 | null = null;

  override render(f: Frame, out: THREE.WebGLRenderTarget) {
    if (this.p('matte', '') || this.p('panel', false) || this.p('flat', false)) return super.render(f, out);
    const S = (this.s3 ??= this.build3d());
    const L = S.layers;
    for (const l of Object.values(L)) l.clear();
    this.look = { matte: '', panel: false };
    const len = Math.max(0.1, f.end - f.start);
    this.t = f.lt;
    const k = ease.inOutQuad(clamp(f.lt / len));
    this.studio(L.studio.ctx, L.glow.ctx, f, k);
    BACK = L.back.ctx; FRONT = L.front.ctx;
    try { this.scene(L.mid.ctx, L.glow.ctx, this.t, f); } finally { BACK = FRONT = null; }
    for (const l of Object.values(L)) l.upload();
    // the camera: a slow dolly in with a lateral drift (its side seeded by the shot), breathing a little
    const side = hash(this.ctx.id.length, this.ctx.id.charCodeAt(0)) < 0.5 ? -1 : 1;
    const mv = this.p('move', 1);
    const cam = S.stage.camera;
    const x = side * mv * lerp(-0.045, 0.045, k) + 0.004 * noise1(f.t * 0.3, 1);
    const y = mv * lerp(0.022, -0.012, k) + 0.003 * noise1(f.t * 0.27, 2);
    cam.position.set(x, y, D * lerp(1.035, 0.975, k));
    cam.lookAt(x * 0.35, y * 0.35, 0);
    cam.updateMatrixWorld();
    S.stage.render(out, { dof: { focus: S.stage.depthOf([0, 0, 0]), fstop: this.p('fstop', 2.0), maxBlurPx: 30 } });
  }

  private build3d(): S3 {
    const stage = new Stage(this.ctx.renderer, { fov: FOV, near: 0.02, far: 10, background: LIN.bg, envIntensity: 0 });
    const ppu = H / (2 * D * Math.tan((FOV * Math.PI) / 360));
    const layers = {} as S3['layers'];
    const order: (keyof typeof Z)[] = ['studio', 'back', 'mid', 'glow', 'front'];
    order.forEach((key, i) => {
      const l = (layers[key] = new Layer2D());
      const z = Z[key], extra = key === 'studio' ? 1.3 : 1;
      const sc = ((D - z) / D) * extra;
      const glowL = key === 'glow' ? this.glowLevel : 1;
      const mat = new THREE.MeshBasicMaterial({
        map: l.texture, transparent: key !== 'studio', toneMapped: false, alphaTest: key === 'glow' ? 0 : 0.004,
        depthWrite: key !== 'glow', color: new THREE.Color(glowL, glowL, glowL),
        blending: key === 'glow' ? THREE.AdditiveBlending : THREE.NormalBlending,
      });
      // the layers were drawn to be mixed as display values (Canvas2D); the stage blends linear light, where a faint
      // wash (a 4 % fill) shows far brighter. Over a dark ground, alpha^2.2 mixes in light what alpha mixed on screen.
      if (key !== 'glow' && key !== 'studio') {
        mat.onBeforeCompile = (sh) => {
          sh.fragmentShader = sh.fragmentShader.replace('#include <alphatest_fragment>', 'diffuseColor.a = pow(diffuseColor.a, 2.2);\n#include <alphatest_fragment>');
        };
      }
      const m = new THREE.Mesh(new THREE.PlaneGeometry((W / ppu) * sc, (H / ppu) * sc), mat);
      m.position.z = z; m.renderOrder = i;
      stage.scene.add(m);
    });
    return { stage, layers };
  }

  override dispose() {
    if (this.s3) {
      this.s3.stage.scene.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh) { m.geometry.dispose(); (m.material as THREE.Material).dispose(); } });
      for (const l of Object.values(this.s3.layers)) l.dispose();
      this.s3.stage.dispose();
      this.s3 = null;
    }
    super.dispose();
  }

  /** Draw the diagram in frame px (1920x1080 design space); `g` is the glow layer, same transform. */
  protected abstract scene(c: Ctx, g: Ctx, t: number, f: Frame): void;

  draw(c: Ctx, f: Frame) {
    this.look = { matte: this.p('matte', '') as Look['matte'], panel: this.p('panel', false) };
    const len = Math.max(0.1, f.end - f.start);
    this.t = this.p('fit', false) ? (f.lt * this.nominal) / len : f.lt;
    const t = this.t;
    const g = this.glow;
    const push = this.p('push', 0.035), [fx, fy] = this.p<[number, number]>('focus', [0.5, 0.5]);
    const k = ease.inOutQuad(clamp(f.lt / len));
    if (!this.look.matte && !this.look.panel) this.studio(c, g, f, k);
    // the panel's card, and the diagram's transform into it
    c.save(); g.save();
    let fade = 1;
    if (this.look.panel || this.look.matte) {
      // an overlay leaves on its own: a short fade at the end, in from transparent at the start
      fade = smoothstep(0, 0.25, f.lt) * smoothstep(len, len - 0.3, f.lt);
    }
    if (this.look.panel) {
      const o = panelCard(c, g, this.panelTitle || this.p('title', ''), f.lt, fade);
      c.translate(o.x, o.y); g.translate(o.x, o.y);
    } else {
      const s = 1 + push * k;
      const dx = 6 * noise1(f.t * 0.11, 3), dy = 4 * noise1(f.t * 0.09, 7);
      for (const x of [c, g]) {
        x.translate(W * fx + dx, H * fy + dy); x.scale(s, s); x.translate(-W * fx, -H * fy);
      }
    }
    c.globalAlpha = fade; g.globalAlpha = fade;
    this.scene(c, g, t, f);
    c.restore(); g.restore();
  }

  /** The dark-warm studio behind the diagram. */
  protected studio(c: Ctx, g: Ctx, f: Frame, k: number) {
    // warm charcoal ground: #1E1813 at the key falling to #120E0B, an amber glow (6 %) high on the left
    const kx = W * 0.55, ky = H * 0.42;
    const pool = c.createRadialGradient(kx, ky, 0, kx, ky, W * 0.7);
    pool.addColorStop(0, 'rgba(30,24,19,1)'); pool.addColorStop(1, 'rgba(18,14,11,1)');
    c.fillStyle = pool; c.fillRect(0, 0, W, H);
    const am = c.createRadialGradient(W * 0.12, H * 0.08, 0, W * 0.12, H * 0.08, W * 0.55);
    am.addColorStop(0, 'rgba(200,135,74,0.06)'); am.addColorStop(1, 'rgba(200,135,74,0)');
    c.fillStyle = am; c.fillRect(0, 0, W, H);
    // the 64 px blueprint grid at 4 % warm white, drifting slowly (it sits behind the diagram: parallax)
    if (this.p('floor', true)) {
      const ox = -((f.t * 6 + k * 40) % 64), oy = -((f.t * 3) % 64);
      c.save(); c.strokeStyle = 'rgba(242,232,220,0.04)'; c.lineWidth = 1; c.beginPath();
      for (let x = ox; x < W; x += 64) { c.moveTo(Math.round(x) + 0.5, 0); c.lineTo(Math.round(x) + 0.5, H); }
      for (let y = oy; y < H; y += 64) { c.moveTo(0, Math.round(y) + 0.5); c.lineTo(W, Math.round(y) + 0.5); }
      c.stroke(); c.restore();
    }
    // bokeh at three depths: far small dim, near big soft
    const rnd = mulberry32(9);
    for (let i = 0; i < 26; i++) {
      const depth = rnd(), x0 = rnd() * W, y0 = rnd() * H * 0.9, ph = rnd() * TAU, warm = rnd();
      const par = 0.4 + depth * 1.6;
      const x = x0 + Math.sin(f.t * 0.05 + ph) * 30 * par - k * 60 * par;
      const y = y0 + Math.cos(f.t * 0.04 + ph) * 18 * par;
      const r = (6 + depth * depth * 70);
      const a = (0.015 + 0.035 * (1 - depth)) * (0.6 + 0.4 * Math.sin(f.t * 0.6 + ph));
      const col = warm > 0.7 ? [255, 120, 70] : warm > 0.35 ? [255, 190, 120] : [200, 170, 150];
      const gr = c.createRadialGradient(x, y, 0, x, y, r);
      gr.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},${a})`);
      gr.addColorStop(0.75, `rgba(${col[0]},${col[1]},${col[2]},${a * 0.8})`);
      gr.addColorStop(1, `rgba(${col[0]},${col[1]},${col[2]},0)`);
      c.fillStyle = gr; c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
    }
    void g;
    // vignette (the look adds its own on top; this one shapes the room)
    const v = c.createRadialGradient(W / 2, H * 0.45, H * 0.35, W / 2, H * 0.5, W * 0.72);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.35)');
    c.fillStyle = v; c.fillRect(0, 0, W, H);
  }
}

/** The panel box of a presenter shot (x 1010-1860, y 150-930; GFX.md): a frosted card, a title bar; returns the
 * origin of its content area, which is PANEL_W x PANEL_H (the bottom 160 px of the box are kept clear for captions). */
export const PANEL = { x: 1010, y: 150, w: 850, h: 780 };
export const PANEL_W = 850, PANEL_H = 560;
function panelCard(c: Ctx, g: Ctx, title: string, lt: number, fade: number) {
  const { x, y, w, h } = PANEL;
  const k = rev(lt, 0, 0.45);
  const dy = (1 - k) * 24;
  c.save();
  c.globalAlpha = fade * k;
  c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = 50; c.shadowOffsetY = 18;
  rr(c, x, y + dy, w, h, 18);
  c.fillStyle = 'rgba(26,20,16,0.78)'; c.fill();
  c.shadowColor = 'transparent';
  c.strokeStyle = '#3b3129'; c.lineWidth = 1; c.stroke();
  c.fillStyle = rgba('accent'); c.beginPath(); c.arc(x + 36, y + dy + 38, 6, 0, TAU); c.fill();
  c.font = font(F.ui(600), 30); c.fillStyle = rgba('fg', 0.95); c.textBaseline = 'middle'; c.textAlign = 'left';
  c.fillText(title, x + 56, y + dy + 39);
  c.fillStyle = 'rgba(242,236,228,0.08)'; c.fillRect(x + 24, y + dy + 72, w - 48, 1);
  c.restore();
  g.save(); g.globalAlpha = fade * k * 0.9;
  g.fillStyle = glowInk('accent', 0.9); g.beginPath(); g.arc(x + 36, y + dy + 38, 7, 0, TAU); g.fill();
  g.restore();
  return { x, y: y + 80 + dy };
}

// ——— primitives ——————————————————————————————————————————————————————————————————————————————————————————

export function rr(c: Ctx, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath(); c.roundRect(x, y, w, h, r);
}

/** A glass card with a soft drop shadow (the depth cue every block gets). */
export function card(c0: Ctx, x: number, y: number, w: number, h: number, o: { r?: number; a?: number; edge?: string; fill?: [string, string]; lift?: number } = {}) {
  on(c0, BACK, (c) => cardOn(c, x, y, w, h, o));
}
function cardOn(c: Ctx, x: number, y: number, w: number, h: number, o: { r?: number; a?: number; edge?: string; fill?: [string, string]; lift?: number }) {
  const r = o.r ?? 14, a = o.a ?? 1, lift = o.lift ?? 1;
  c.save();
  c.globalAlpha *= a;
  c.shadowColor = 'rgba(0,0,0,0.6)'; c.shadowBlur = 40 * lift; c.shadowOffsetY = 16 * lift;
  rr(c, x, y, w, h, r);
  const gr = c.createLinearGradient(0, y, 0, y + h);
  gr.addColorStop(0, o.fill?.[0] ?? 'rgba(40,32,27,0.97)'); gr.addColorStop(1, o.fill?.[1] ?? 'rgba(34,27,22,0.97)');
  c.fillStyle = gr; c.fill();
  c.shadowColor = 'transparent';
  c.strokeStyle = o.edge ?? '#3b3129'; c.lineWidth = 1; c.stroke();
  // a top sheen
  const sh = c.createLinearGradient(0, y, 0, y + Math.min(60, h));
  sh.addColorStop(0, 'rgba(255,235,215,0.07)'); sh.addColorStop(1, 'rgba(255,235,215,0)');
  c.fillStyle = sh; rr(c, x + 1, y + 1, w - 2, Math.min(60, h) - 1, r); c.fill();
  c.restore();
}

export interface TextOpt { size?: number; weight?: number; width?: number; color?: string; alpha?: number; align?: CanvasTextAlign; base?: CanvasTextBaseline; face?: 'display' | 'ui' | 'mono'; track?: number }

export function text(c: Ctx, s: string, x: number, y: number, o: TextOpt = {}) {
  const size0 = o.size ?? 28, face = o.face ?? 'ui';
  // small labels read on a phone: everything under 40 px is set a size up
  const size = size0 < 40 ? Math.max(28, Math.round(size0 * 1.25)) : size0;
  const fam = face === 'display' ? F.display(o.width ?? 100, o.weight ?? 600) : face === 'mono' ? F.mono(o.weight ?? 500) : F.ui(o.weight ?? 500);
  c.font = font(fam, size);
  c.textAlign = o.align ?? 'left';
  c.textBaseline = o.base ?? 'alphabetic';
  c.fillStyle = rgba(o.color ?? 'fg', o.alpha ?? 1);
  if (o.track) (c as any).letterSpacing = `${o.track}px`;
  c.fillText(s, x, y);
  if (o.track) (c as any).letterSpacing = '0px';
}

/** A small caps label (kicker). */
export function kicker(c: Ctx, s: string, x: number, y: number, a = 1, color = 'accent', align: CanvasTextAlign = 'left') {
  text(c, s.toUpperCase(), x, y, { size: 22, weight: 600, color, alpha: a, align, track: 4 });
}

/** A point along a cubic bezier. */
export function bez(p0: number[], p1: number[], p2: number[], p3: number[], t: number): [number, number] {
  const u = 1 - t;
  return [
    u * u * u * p0[0]! + 3 * u * u * t * p1[0]! + 3 * u * t * t * p2[0]! + t * t * t * p3[0]!,
    u * u * u * p0[1]! + 3 * u * u * t * p1[1]! + 3 * u * t * t * p2[1]! + t * t * t * p3[1]!,
  ];
}

/** A link from a to b (a gentle S curve), drawn to `k` (0..1), with optional glowing packets flowing along it. */
export function link(c: Ctx, g: Ctx, a: [number, number], b: [number, number], k: number, o: { color?: string; width?: number; packets?: number; t?: number; speed?: number; bend?: number; dash?: boolean; glow?: number; alpha?: number; vertical?: boolean } = {}) {
  if (k <= 0) return;
  const bend = o.bend ?? 0.5;
  const p0 = a, p3 = b;
  const p1 = o.vertical ? [a[0], lerp(a[1], b[1], bend)] : [lerp(a[0], b[0], bend), a[1]];
  const p2 = o.vertical ? [b[0], lerp(a[1], b[1], 1 - bend)] : [lerp(a[0], b[0], 1 - bend), b[1]];
  const n = 48, end = Math.max(1, Math.round(n * k));
  const col = o.color ?? 'accent', alpha = o.alpha ?? 1;
  c.save();
  c.lineCap = 'round';
  c.strokeStyle = rgba(col, 0.55 * alpha); c.lineWidth = o.width ?? 3;
  if (o.dash) c.setLineDash([2, 10]);
  c.beginPath();
  for (let i = 0; i <= end; i++) { const [x, y] = bez(p0, p1, p2, p3, i / n); i ? c.lineTo(x, y) : c.moveTo(x, y); }
  c.stroke();
  c.restore();
  if (o.glow) {
    g.save(); g.lineCap = 'round'; g.strokeStyle = glowInk(col, 0.25 * o.glow * alpha); g.lineWidth = (o.width ?? 3) * 1.4;
    g.beginPath();
    for (let i = 0; i <= end; i++) { const [x, y] = bez(p0, p1, p2, p3, i / n); i ? g.lineTo(x, y) : g.moveTo(x, y); }
    g.stroke(); g.restore();
  }
  const np = o.packets ?? 0;
  if (np && k >= 1) {
    for (let i = 0; i < np; i++) {
      const u = ((o.t ?? 0) * (o.speed ?? 0.5) + i / np) % 1;
      const [x, y] = bez(p0, p1, p2, p3, u);
      const fadeE = smoothstep(0, 0.08, u) * smoothstep(1, 0.92, u);
      packet(c, g, x, y, col, fadeE * alpha);
    }
  }
}

/** A glowing packet: a bright core and a bloom on the glow layer. */
export function packet(c: Ctx, g: Ctx, x: number, y: number, col = 'accent', a = 1, r = 6) {
  c.fillStyle = rgba(col === 'accent' ? 'accentBright' : col === 'accent2' ? 'accent2Bright' : col, a);
  c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
  g.fillStyle = glowInk(col, 0.85 * a);
  g.beginPath(); g.arc(x, y, r * 1.6, 0, TAU); g.fill();
}

// ——— icons (drawn about their centre, `s` = scale; ~100 px at s 1) ———————————————————————————————————————

/** An Open Connect appliance: a 2U server in 3/4 view, LEDs that blink as it serves. */
export function server(c: Ctx, g: Ctx, x: number, y: number, s: number, t: number, o: { a?: number; busy?: number; label?: string; fill?: number } = {}) {
  const a = o.a ?? 1;
  if (a <= 0) return;
  c.save(); c.translate(x, y); c.scale(s, s); c.globalAlpha *= a;
  const w = 150, h = 58, d = 26;
  // shadow on the floor
  c.save(); c.fillStyle = 'rgba(0,0,0,0.45)'; c.filter = 'blur(10px)';
  c.beginPath(); c.ellipse(6, h / 2 + 24, w * 0.62, 12, 0, 0, TAU); c.fill(); c.restore();
  // top face (parallelogram) and front face
  c.beginPath(); c.moveTo(-w / 2, -h / 2); c.lineTo(-w / 2 + d, -h / 2 - d * 0.55); c.lineTo(w / 2 + d, -h / 2 - d * 0.55); c.lineTo(w / 2, -h / 2); c.closePath();
  c.fillStyle = '#3a2d26'; c.fill();
  c.beginPath(); c.moveTo(w / 2, -h / 2); c.lineTo(w / 2 + d, -h / 2 - d * 0.55); c.lineTo(w / 2 + d, h / 2 - d * 0.55); c.lineTo(w / 2, h / 2); c.closePath();
  c.fillStyle = '#1b1411'; c.fill();
  const fr = c.createLinearGradient(0, -h / 2, 0, h / 2);
  fr.addColorStop(0, '#2c221d'); fr.addColorStop(1, '#1d1612');
  rr(c, -w / 2, -h / 2, w, h, 4); c.fillStyle = fr; c.fill();
  c.strokeStyle = 'rgba(255,220,190,0.18)'; c.lineWidth = 1.2; c.stroke();
  // the red bezel stripe
  c.fillStyle = rgba('accent', 0.95); c.fillRect(-w / 2 + 8, -h / 2 + 8, 5, h - 16);
  // vents
  c.fillStyle = 'rgba(0,0,0,0.5)';
  for (let i = 0; i < 9; i++) c.fillRect(-w / 2 + 26 + i * 9, -h / 2 + 12, 4, h - 24);
  // drive bays / LEDs
  const busy = o.busy ?? 0.5;
  for (let i = 0; i < 6; i++) {
    const lx = w / 2 - 54 + (i % 3) * 16, ly = -h / 2 + 18 + Math.floor(i / 3) * 20;
    const on = hash(i, Math.floor(t * 14 + i * 3)) < busy ? 1 : 0.15;
    c.fillStyle = on > 0.5 ? rgba('accent2Bright') : 'rgba(120,90,60,0.5)';
    c.fillRect(lx, ly, 8, 4);
    if (on > 0.5) { g.save(); g.translate(x, y); g.scale(s, s); g.fillStyle = glowInk('accent2', 0.6 * a); g.fillRect(lx - 2, ly - 2, 12, 8); g.restore(); }
  }
  // fill bar (pre-positioning)
  if (o.fill !== undefined) {
    const fw = w - 40;
    c.fillStyle = 'rgba(0,0,0,0.6)'; rr(c, -w / 2 + 20, h / 2 + 12, fw, 8, 4); c.fill();
    c.fillStyle = rgba('accent'); rr(c, -w / 2 + 20, h / 2 + 12, fw * clamp(o.fill), 8, 4); c.fill();
    g.save(); g.translate(x, y); g.scale(s, s); g.fillStyle = glowInk('accent', 0.5 * a); rr(g, -w / 2 + 20, h / 2 + 12, fw * clamp(o.fill), 8, 4); g.fill(); g.restore();
  }
  if (o.label) text(c, o.label, 0, h / 2 + (o.fill !== undefined ? 52 : 40), { size: 22, weight: 500, color: 'fgDim', align: 'center' });
  c.restore();
}

/** A home: a house outline with a TV glowing in the window. */
export function home(c: Ctx, g: Ctx, x: number, y: number, s: number, o: { a?: number; tv?: number; color?: string } = {}) {
  const a = o.a ?? 1;
  if (a <= 0) return;
  c.save(); c.translate(x, y); c.scale(s, s); c.globalAlpha *= a;
  c.fillStyle = 'rgba(0,0,0,0.4)'; c.beginPath(); c.ellipse(0, 46, 54, 8, 0, 0, TAU); c.fill();
  c.beginPath(); c.moveTo(-44, -4); c.lineTo(0, -44); c.lineTo(44, -4); c.lineTo(44, 42); c.lineTo(-44, 42); c.closePath();
  const gr = c.createLinearGradient(0, -44, 0, 42); gr.addColorStop(0, '#3a2c25'); gr.addColorStop(1, '#221914');
  c.fillStyle = gr; c.fill(); c.strokeStyle = 'rgba(255,220,190,0.28)'; c.lineWidth = 2; c.stroke();
  const tv = o.tv ?? 0;
  c.fillStyle = tv > 0 ? rgba(o.color ?? 'accent', 0.35 + 0.65 * tv) : 'rgba(10,8,7,0.9)';
  rr(c, -24, 2, 48, 28, 3); c.fill();
  c.restore();
  if (tv > 0) {
    g.save(); g.translate(x, y); g.scale(s, s); g.globalAlpha *= a;
    g.fillStyle = glowInk(o.color ?? 'accent', 0.45 * tv); rr(g, -26, 0, 52, 32, 4); g.fill(); g.restore();
  }
}

/** A cloud outline (the internet, or AWS). */
export function cloud(c: Ctx, x: number, y: number, w: number, h: number, o: { a?: number; stroke?: string; fill?: string; dash?: boolean } = {}) {
  c.save(); c.globalAlpha *= o.a ?? 1;
  c.beginPath();
  const bumps: [number, number, number][] = [[-0.32, 0.12, 0.26], [-0.12, -0.12, 0.32], [0.16, -0.16, 0.3], [0.34, 0.08, 0.24], [0.02, 0.2, 0.3]];
  for (const [bx, by, br] of bumps) { c.moveTo(x + bx * w + br * w * 0.7, y + by * h); c.ellipse(x + bx * w, y + by * h, br * w * 0.7, br * h * 1.2, 0, 0, TAU); }
  c.fillStyle = o.fill ?? 'rgba(60,46,40,0.35)'; c.fill();
  c.restore();
}

/** A phone / laptop / TV screen glyph. */
export function screen(c: Ctx, g: Ctx, x: number, y: number, kind: 'tv' | 'phone' | 'laptop', s: number, o: { a?: number; on?: number } = {}) {
  const a = o.a ?? 1, on = o.on ?? 1;
  if (a <= 0) return;
  c.save(); c.translate(x, y); c.scale(s, s); c.globalAlpha *= a;
  const [w, h] = kind === 'tv' ? [120, 70] : kind === 'phone' ? [40, 74] : [96, 60];
  rr(c, -w / 2, -h / 2, w, h, kind === 'phone' ? 8 : 5);
  c.fillStyle = '#120d0b'; c.fill(); c.strokeStyle = 'rgba(255,220,190,0.35)'; c.lineWidth = 2.5; c.stroke();
  const sc = c.createLinearGradient(-w / 2, -h / 2, w / 2, h / 2);
  sc.addColorStop(0, rgba('accentDim', 0.9 * on)); sc.addColorStop(1, rgba('accent2Dim', 0.9 * on));
  c.fillStyle = sc; rr(c, -w / 2 + 5, -h / 2 + 5, w - 10, h - 10, 3); c.fill();
  if (kind === 'tv') { c.fillStyle = 'rgba(255,220,190,0.3)'; c.fillRect(-16, h / 2 + 4, 32, 4); }
  if (kind === 'laptop') { c.fillStyle = 'rgba(255,220,190,0.3)'; rr(c, -w / 2 - 12, h / 2 + 2, w + 24, 6, 3); c.fill(); }
  c.restore();
  void g;
}

/** A pill tag. */
export function pill(c0: Ctx, g: Ctx, s: string, x: number, y: number, o: { color?: string; a?: number; size?: number; filled?: boolean; align?: 'center' | 'left' } = {}) {
  let w = 0;
  on(c0, FRONT, (c) => { w = pillOn(c, g, s, x, y, o) ?? 0; });
  return w;
}
function pillOn(c: Ctx, g: Ctx, s: string, x: number, y: number, o: { color?: string; a?: number; size?: number; filled?: boolean; align?: 'center' | 'left' }) {
  const size = Math.max(28, Math.round((o.size ?? 22) * 1.18)), col = o.color ?? 'accent', a = o.a ?? 1;
  if (a <= 0) return;
  c.font = font(F.ui(600), size);
  const w = c.measureText(s).width + size * 1.4, h = size * 1.75;
  const x0 = o.align === 'left' ? x : x - w / 2;
  c.save(); c.globalAlpha *= a;
  rr(c, x0, y - h / 2, w, h, h / 2);
  c.fillStyle = o.filled ? rgba(col, 0.92) : rgba(col, 0.14); c.fill();
  c.strokeStyle = rgba(col, 0.7); c.lineWidth = 1.5; c.stroke();
  c.fillStyle = rgba('fg'); c.textAlign = 'center'; c.textBaseline = 'middle';
  c.fillText(s, x0 + w / 2, y + 1);
  c.restore();
  if (o.filled) { g.save(); g.globalAlpha *= a * 0.5; g.strokeStyle = glowInk(col); g.lineWidth = 3; rr(g, x0, y - h / 2, w, h, h / 2); g.stroke(); g.restore(); }
  return w;
}

/** A headline at the top-left of a diagram: kicker + title, landing in. */
export function heading(c0: Ctx, kick: string, title: string, t: number, at = 0, x = 120, y = 150) {
  on(c0, FRONT, (c) => headingOn(c, kick, title, t, at, x, y));
}
function headingOn(c: Ctx, kick: string, title: string, t: number, at: number, x: number, y: number) {
  const k1 = rev(t, at, 0.35), k2 = rev(t, at + 0.06, 0.45);
  kicker(c, kick, x, y - 62 + (1 - k1) * 14, k1);
  text(c, title, x, y + (1 - k2) * 24, { size: 70, weight: 700, face: 'display', width: 87.5, alpha: k2 });
}
