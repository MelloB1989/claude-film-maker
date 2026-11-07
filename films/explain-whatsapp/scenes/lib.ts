// The explainer's drawing kit: a base scene that lays a diagram out full frame (a headline column on the left, the
// diagram on the right, over a warm studio backdrop with depth) or as a side panel (the diagram alone on a dark glass
// card on the right, for a presenter on the left), and the marks every diagram is made of: glass cards, phones,
// servers, wires with glowing packets, chat bubbles with ticks, locks, keys, a blob store and a CDN.
//
// Diagrams are drawn in a design box of BOX_W x BOX_H units; the base maps the box into the frame. Every mark is a
// pure function of the shot's local time. A beat's times are named marks (`M`) with defaults, overridable by the
// shot's `marks` param so the film can be re-timed to the voice without touching the scene.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { clamp, ease, lerp, mulberry32, noise1, TAU } from '@engine/util';

/** Captions run below this fraction of the frame's height on every shot: graphics keep out. */
export const CAPTION_TOP = 0.85;

export const BOX_W = 1000;
export const BOX_H = 900;

/** The read-receipt blue (a hue of its own: the theme has no role for it). */
export const BLUE = '#53bdeb';
export const GREEN = '#25D366';
/** GFX.md neutrals. */
export const INK = '#120E0B', INK2 = '#1E1813', CARD = '#241D18', BORDER = '#3B3129', TXT = '#F2ECE4', TXT2 = '#A89E92', PANEL = '#1A1410';

export type Layout = 'full' | 'panel';
export type Ctx = CanvasRenderingContext2D;

/** Eased 0..1 from `at` over `dur` s. */
export const ramp = (t: number, at: number, dur = 0.5, fn: (x: number) => number = ease.outCubic) =>
  fn(clamp((t - at) / Math.max(1e-6, dur)));

/** In at `a`, out at `b` (each over `d` s). */
export const life = (t: number, a: number, b: number, d = 0.35) => Math.min(ramp(t, a, d), 1 - ramp(t, b, d, ease.inCubic));

/** A soft pop-in scale: overshoots a little, settles at 1. */
export const pop = (t: number, at: number, dur = 0.55) => {
  const x = clamp((t - at) / dur);
  return x <= 0 ? 0 : ease.outBack(x, 1.6);
};

export interface Pt { x: number; y: number }

export abstract class Explainer extends Scene2D {
  /** Default mark times (local s). */
  protected abstract marks: Record<string, number>;
  /** Draw the diagram in box units (0..BOX_W, 0..BOX_H) on c (the layer) and g (the glow layer), at local time t. */
  protected abstract diagram(c: Ctx, g: Ctx, t: number, f: Frame): void;
  /** Headline column text (full layout), overridable by params kicker/title/sub. */
  protected kicker = '';
  protected title = '';
  protected sub = '';

  protected M(name: string): number {
    const o = this.p<Record<string, number>>('marks', {});
    return o[name] ?? this.marks[name] ?? 0;
  }

  /** When a word of the shot's line is spoken (local s; the film passes `words` from the EDL), else `fallback`. */
  protected w(word: string, fallback: number, nth = 0): number {
    const ws = this.p<{ w: string; t: number }[]>('words', []);
    const hits = ws.filter((x) => x.w === word.toLowerCase());
    return hits[nth]?.t ?? fallback;
  }

  protected get layout(): Layout {
    return this.p<Layout>('layout', 'full');
  }

  draw(c: Ctx, f: Frame) {
    const t = f.lt, dur = f.end - f.start;
    const g = this.glow;
    const full = this.layout === 'full';
    // the camera: a slow dolly in with a lateral drift; planes at different depths move by different amounts
    const pan = ease.inOutQuad(clamp(t / Math.max(1, dur)));
    const cam = { x: (lerp(-34, 34, pan) + 8 * Math.sin(t * 0.37)) * this.u, y: (5 * Math.sin(t * 0.29 + 1)) * this.u, push: 1 + 0.06 * ease.inOutQuad(clamp(t / Math.max(1, dur))) };
    if (full && this.p('backdrop', true)) backdrop(c, g, t, f.t, cam);
    // the diagram's region
    let rx: number, ry: number, rw: number, rh: number;
    if (full) {
      const head = this.p('headline', true) && (this.p('title', this.title) !== '');
      // bottom 15 % of the frame stays clear: the captions run there
      rx = head ? 0.4 * W : 0.2 * W; ry = 0.05 * H; rw = head ? 0.56 * W : 0.6 * W; rh = 0.79 * H;
    } else {
      // the panel (GFX.md): box x 1010-1860, y 150-930 of 1920x1080, a frosted card PANEL @ 78 %, 18 px radius, 1 px BORDER
      const px0 = (1010 / 1920) * W, px1 = (1860 / 1920) * W, py0 = (150 / 1080) * H, py1 = (930 / 1080) * H;
      const k = ramp(t, 0, 0.3);
      c.save();
      c.globalAlpha = k;
      c.shadowColor = 'rgba(0,0,0,0.35)';
      c.shadowBlur = 40 * this.u;
      c.shadowOffsetY = 12 * this.u;
      rr(c, px0, py0, px1 - px0, py1 - py0, 18 * this.u);
      c.fillStyle = withA(PANEL, 0.78);
      c.fill();
      c.shadowColor = 'transparent';
      c.strokeStyle = BORDER;
      c.lineWidth = Math.max(1, this.u);
      c.stroke();
      c.restore();
      const title = this.p('title', this.title);
      const tx = px0 + 36 * this.u, ty = py0 + 58 * this.u;
      if (title) {
        c.save();
        const hk = ramp(t, 0.1, 0.5);
        c.globalAlpha = k * hk;
        c.textAlign = 'left';
        c.font = font(F.mono(500), 24 * this.u);
        c.fillStyle = rgba('accent');
        c.fillText(this.p('kicker', this.kicker).toUpperCase(), tx, ty - 26 * this.u);
        c.font = font(F.display(100, 800), 40 * this.u);
        c.fillStyle = TXT;
        c.fillText(title.replace(/\n/g, ' '), tx, ty + 12 * this.u + (1 - hk) * 10 * this.u);
        c.restore();
      }
      rx = px0 + 24 * this.u; rw = px1 - px0 - 48 * this.u;
      ry = py0 + (title ? 96 : 24) * this.u; rh = py1 - ry - 24 * this.u;
    }
    const s = Math.min(rw / BOX_W, rh / BOX_H);
    // a slow push and drift: the camera breathes
    const push = full ? cam.push : 1 + 0.02 * ease.inOutQuad(clamp(t / Math.max(1, dur)));
    const dx = full ? -cam.x * 0.55 : -cam.x * 0.12, dy = full ? -cam.y * 0.55 : 0;
    const ox = rx + rw / 2 + dx, oy = ry + rh / 2 + dy;
    // labels never fall under LABEL_MIN px on the frame
    labelMin = LABEL_MIN * (W / 1920) / (s * push);
    for (const k of [c, g]) {
      k.save();
      // the caption band (y > 0.85 of the frame) stays clear of every diagram mark, by construction
      k.beginPath();
      k.rect(0, 0, W, CAPTION_TOP * H);
      k.clip();
      k.translate(ox, oy);
      k.scale(s * push, s * push);
      k.translate(-BOX_W / 2, -BOX_H / 2);
    }
    this.diagram(c, g, t, f);
    c.restore();
    g.restore();
    if (full && this.p('backdrop', true)) foreground(c, f.t, cam);
    if (full && this.p('headline', true)) this.headline(c, g, t);
  }

  /** The headline column: kicker, title (lines), a sub line, an accent rule. */
  protected headline(c: Ctx, g: Ctx, t: number) {
    const title = this.p('title', this.title);
    if (!title) return;
    const u = this.u, x = 0.065 * W;
    const lines = title.split('\n');
    const size = this.p('titleSize', 84) * u, lh = size * 1.06;
    const top = H / 2 - (lines.length * lh) / 2 + size * 0.2;
    const at = this.p('headAt', 0.15);
    c.save();
    c.textAlign = 'left';
    c.textBaseline = 'alphabetic';
    const kk = ramp(t, at, 0.5);
    c.font = font(F.mono(500), 28 * u);
    c.fillStyle = rgba('accent', kk);
    c.fillText(this.p('kicker', this.kicker).toUpperCase(), x + 3 * u, top - lh * 0.95 + (1 - kk) * 10 * u);
    lines.forEach((ln, i) => {
      const k = ramp(t, at + 0.12 + i * 0.1, 0.7, ease.outQuart);
      c.font = font(F.display(100, 800), size);
      c.fillStyle = rgba('fg', k);
      c.fillText(ln, x, top + i * lh + (1 - k) * 28 * u);
    });
    const rk = ramp(t, at + 0.45, 0.8, ease.inOutCubic);
    const ry = top + (lines.length - 1) * lh + 0.55 * lh;
    c.fillStyle = rgba('accent', 0.9);
    c.fillRect(x + 2 * u, ry, 90 * u * rk, 3 * u);
    g.fillStyle = glowInk('accent', 0.6 * rk);
    g.fillRect(x + 2 * u, ry - 1 * u, 90 * u * rk, 5 * u);
    const sub = this.p('sub', this.sub);
    if (sub) {
      const sk = ramp(t, at + 0.6, 0.6);
      c.font = font(F.ui(400), 32 * u);
      c.fillStyle = rgba('fgDim', sk);
      sub.split('\n').forEach((s, i) => c.fillText(s, x + 2 * u, ry + 56 * u + i * 38 * u));
    }
    c.restore();
  }
}

// ── the backdrop ──────────────────────────────────────────────────────────────────────────────────────────────────

/**
 * The ground (GFX.md): warm charcoal INK -> INK2 radial and an amber key glow (#C8874A, 6 %) top left, over a floor:
 * the 64 px grid laid on a plane in perspective, receding to a hazy horizon, drifting toward the lens and panning
 * with the camera at the far plane's rate. Out-of-focus motes hang at depth.
 */
export function backdrop(c: Ctx, _g: Ctx, _t: number, ft: number, cam: { x: number; y: number; push: number }) {
  const u = Math.min(W, H) / 1080;
  let gr = c.createRadialGradient(0.55 * W, 0.45 * H, 0, 0.55 * W, 0.45 * H, 0.75 * W);
  gr.addColorStop(0, INK2);
  gr.addColorStop(1, INK);
  c.fillStyle = gr;
  c.fillRect(0, 0, W, H);
  gr = c.createRadialGradient(0.12 * W, 0.08 * H, 0, 0.12 * W, 0.08 * H, 0.7 * W);
  gr.addColorStop(0, 'rgba(200,135,74,0.06)');
  gr.addColorStop(0.5, 'rgba(200,135,74,0.025)');
  gr.addColorStop(1, 'rgba(200,135,74,0)');
  c.fillStyle = gr;
  c.fillRect(0, 0, W, H);
  // the floor: x = X/Z, y = horizon + camH/Z, cells of 1 unit; the camera pans in X and creeps forward in Z
  const horizon = 0.3 * H - cam.y * 0.3, f = 0.9 * W * cam.push, camH = 0.62;
  const camX = -cam.x / (120 * u), z0 = (ft * 0.22) % 1;
  const P = (X: number, Z: number) => ({ x: W / 2 + ((X - camX) * f) / Z, y: horizon + (camH * f) / Z });
  c.save();
  c.lineWidth = Math.max(1, u);
  const Zn = 0.75, Zf = 16;
  for (let i = 0; i < 40; i++) {
    const Z = Zn + i - z0 + 1;
    if (Z > Zf) break;
    const a = 0.1 * Math.min(1, (Zf - Z) / 8) * Math.min(1, (Z - Zn) * 2);
    const l = P(-12, Z), r = P(12, Z);
    c.strokeStyle = `rgba(242,228,210,${a})`;
    c.beginPath(); c.moveTo(l.x, l.y); c.lineTo(r.x, r.y); c.stroke();
  }
  for (let X = -12; X <= 12; X++) {
    const n = P(X, Zn), fr = P(X, Zf);
    const lg = c.createLinearGradient(n.x, n.y, fr.x, fr.y);
    lg.addColorStop(0, 'rgba(242,228,210,0.09)');
    lg.addColorStop(1, 'rgba(242,228,210,0)');
    c.strokeStyle = lg;
    c.beginPath(); c.moveTo(n.x, n.y); c.lineTo(fr.x, fr.y); c.stroke();
  }
  c.restore();
  // haze at the horizon, and the wall above it with a faint flat grid (the far plane)
  gr = c.createLinearGradient(0, horizon - 0.25 * H, 0, horizon + 0.12 * H);
  gr.addColorStop(0, 'rgba(30,24,19,0)');
  gr.addColorStop(0.7, 'rgba(36,28,22,0.55)');
  gr.addColorStop(1, 'rgba(30,24,19,0)');
  c.fillStyle = gr;
  c.fillRect(0, horizon - 0.25 * H, W, 0.37 * H);
  // edge falloff
  gr = c.createRadialGradient(0.5 * W, 0.5 * H, 0.3 * W, 0.5 * W, 0.5 * H, 0.8 * W);
  gr.addColorStop(0, 'rgba(18,14,11,0)');
  gr.addColorStop(1, 'rgba(18,14,11,0.7)');
  c.fillStyle = gr;
  c.fillRect(0, 0, W, H);
  // far motes, fine and slow, panning less than the diagram
  const rnd = mulberry32(7);
  for (let i = 0; i < 30; i++) {
    const depth = rnd(), x0 = rnd(), y0 = rnd(), ph = rnd() * TAU;
    const x = ((x0 + ft * lerp(0.002, 0.01, depth) + 2) % 1.2 - 0.1) * W - cam.x * lerp(0.15, 0.4, depth);
    const y = (y0 * 0.8 + 0.02 * Math.sin(ft * 0.3 + ph)) * H;
    const r = lerp(1.2, 7, depth) * u;
    const a = lerp(0.16, 0.06, depth) * (0.6 + 0.4 * Math.sin(ft * 0.8 + ph));
    c.fillStyle = `rgba(230,180,130,${a})`;
    c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
  }
}

/** The near plane: a few large, soft, out-of-focus discs that cross faster than the diagram (depth of field). */
export function foreground(c: Ctx, ft: number, cam: { x: number; y: number }) {
  const u = Math.min(W, H) / 1080;
  const rnd = mulberry32(19);
  for (let i = 0; i < 6; i++) {
    const x0 = rnd(), y0 = rnd(), r = lerp(70, 160, rnd()) * u, ph = rnd() * TAU;
    const x = ((x0 + ft * 0.012 + 3) % 1.4 - 0.2) * W - cam.x * 1.8;
    const y = (0.15 + 0.75 * y0) * H + 20 * u * Math.sin(ft * 0.2 + ph) - cam.y * 1.8;
    const m = c.createRadialGradient(x, y, r * 0.55, x, y, r);
    m.addColorStop(0, 'rgba(255,200,150,0.035)');
    m.addColorStop(0.85, 'rgba(255,200,150,0.045)');
    m.addColorStop(1, 'rgba(255,200,150,0)');
    c.fillStyle = m;
    c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
  }
}

// ── surfaces ──────────────────────────────────────────────────────────────────────────────────────────────────────

/** Label sizes: small labels read at phone size only this much larger than the design's. */
const LABEL_MIN = 30;
let labelMin = 28;
const ts = (z: number) => (z < 40 ? Math.max(z * 1.3, labelMin) : z);

/** A soft contact shadow on the floor under an object whose base is at (x, y), `w` wide. */
export function shadow(c: Ctx, x: number, y: number, w: number, a = 1) {
  if (a <= 0.001) return;
  c.save();
  c.translate(x, y);
  c.scale(1, 0.16);
  const gr = c.createRadialGradient(0, 0, 0, 0, 0, w * 0.7);
  gr.addColorStop(0, `rgba(0,0,0,${0.55 * a})`);
  gr.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = gr;
  c.beginPath(); c.arc(0, 0, w * 0.7, 0, TAU); c.fill();
  c.restore();
}

/** A slab: a rounded card with visible thickness (its lower edge extruded by `d`), filled `fill`, rimmed `stroke`. */
export function slab(c: Ctx, x: number, y: number, w: number, h: number, r: number, o: { fill?: string; stroke?: string; d?: number; a?: number; lw?: number } = {}) {
  const a = o.a ?? 1, d = o.d ?? Math.min(14, h * 0.08);
  if (a <= 0.001) return;
  c.save();
  c.globalAlpha *= a;
  c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = Math.max(w, h) * 0.08; c.shadowOffsetY = Math.max(w, h) * 0.04;
  rr(c, x, y + d, w, h, r);
  c.fillStyle = '#0f0b08';
  c.fill();
  c.shadowColor = 'transparent';
  const side = c.createLinearGradient(0, y + h - r, 0, y + h + d);
  side.addColorStop(0, '#2a221b'); side.addColorStop(1, '#16110d');
  rr(c, x, y + d * 0.5, w, h + d * 0.5, r);
  c.fillStyle = side;
  c.fill();
  rr(c, x, y, w, h, r);
  const face = c.createLinearGradient(0, y, 0, y + h);
  face.addColorStop(0, o.fill ?? '#2c241d'); face.addColorStop(1, o.fill ?? CARD);
  c.fillStyle = face;
  c.fill();
  c.strokeStyle = o.stroke ?? BORDER;
  c.lineWidth = o.lw ?? 2;
  c.stroke();
  // top edge catch light
  c.beginPath();
  c.moveTo(x + r, y + 1); c.lineTo(x + w - r, y + 1);
  c.strokeStyle = 'rgba(255,225,190,0.18)';
  c.lineWidth = 1.5;
  c.stroke();
  c.restore();
}

export function rr(c: Ctx, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.roundRect(x, y, w, h, Math.min(r, w / 2, h / 2));
}

/** A dark glass card: a soft shadow under it, a warm top-lit gradient, a hairline rim brighter along the top. */
export function glassCard(c: Ctx, x: number, y: number, w: number, h: number, r: number, o: { alpha?: number; shadow?: boolean; tint?: string; rim?: number; border?: number; fill?: string } = {}) {
  const a = o.alpha ?? 1;
  c.save();
  if (o.shadow !== false) {
    c.shadowColor = `rgba(0,0,0,${0.55 * a})`;
    c.shadowBlur = Math.max(w, h) * 0.08;
    c.shadowOffsetY = Math.max(w, h) * 0.03;
  }
  const gr = c.createLinearGradient(0, y, 0, y + h);
  gr.addColorStop(0, `rgba(44,36,30,${a})`);
  gr.addColorStop(1, `rgba(34,28,23,${a})`);
  rr(c, x, y, w, h, r);
  c.fillStyle = gr;
  c.fill();
  c.restore();
  c.save();
  rr(c, x, y, w, h, r);
  c.clip();
  if (o.tint) {
    const tg = c.createRadialGradient(x + w * 0.3, y, 0, x + w * 0.3, y, Math.max(w, h));
    tg.addColorStop(0, o.tint);
    tg.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = tg;
    c.fillRect(x, y, w, h);
  }
  const rim = c.createLinearGradient(0, y, 0, y + h);
  rim.addColorStop(0, `rgba(200,170,140,${0.55 * a * (o.rim ?? 1)})`);
  rim.addColorStop(0.25, `rgba(59,49,41,${1 * a * (o.rim ?? 1)})`);
  rim.addColorStop(1, `rgba(59,49,41,${1 * a * (o.rim ?? 1)})`);
  c.strokeStyle = rim;
  c.lineWidth = o.border ?? 1.5;
  rr(c, x, y, w, h, r);
  c.stroke();
  c.restore();
}

export function text(c: Ctx, s: string, x: number, y: number, size0: number, o: { color?: string; a?: number; align?: CanvasTextAlign; weight?: number; face?: 'ui' | 'mono' | 'display'; base?: CanvasTextBaseline } = {}) {
  const size = ts(size0);
  c.save();
  const fam = o.face === 'mono' ? F.mono(o.weight ?? 500) : o.face === 'display' ? F.display(87.5, o.weight ?? 700) : F.ui(o.weight ?? 500);
  c.font = font(fam, size);
  c.textAlign = o.align ?? 'center';
  c.textBaseline = o.base ?? 'middle';
  c.fillStyle = (o.color ?? 'fg').startsWith('#') || (o.color ?? '').startsWith('rgb') ? withA(o.color!, o.a ?? 1) : rgba(o.color ?? 'fg', o.a ?? 1);
  c.fillText(s, x, y);
  c.restore();
}

/** A #hex (or rgb()) at alpha a. */
export function withA(col: string, a: number): string {
  if (col.startsWith('#')) {
    const n = parseInt(col.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  if (col.startsWith('rgb')) return col;
  return rgba(col, a);
}

/** A pill label: rounded capsule with a text. */
export function pill(c: Ctx, s: string, x: number, y: number, size0: number, o: { color?: string; a?: number; fill?: string; align?: 'center' | 'left' } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const size = ts(size0);
  c.save();
  c.font = font(F.mono(500), size);
  const w = c.measureText(s).width + size * 1.4, h = size * 1.9;
  const x0 = o.align === 'left' ? x : x - w / 2;
  rr(c, x0, y - h / 2, w, h, h / 2);
  c.fillStyle = withA(o.fill ?? CARD, 0.92 * a);
  c.fill();
  c.strokeStyle = withA(o.color ?? TXT2, 0.45 * a);
  c.lineWidth = 1.5;
  c.stroke();
  c.fillStyle = withA(o.color ?? TXT, a);
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(s, x0 + w / 2, y + size * 0.05);
  c.restore();
}

// ── devices ───────────────────────────────────────────────────────────────────────────────────────────────────────

/**
 * A phone, centred on (x, y), `h` tall: a dark body with a rim light, a screen (lit when online), a status dot. The
 * `screen` callback draws into the screen rect (clipped).
 */
export function phone(c: Ctx, g: Ctx, x: number, y: number, h: number, o: { on?: number; a?: number; label?: string; screen?: (c: Ctx, sx: number, sy: number, sw: number, sh: number) => void; accent?: string } = {}) {
  const a = o.a ?? 1, on = o.on ?? 1;
  if (a <= 0.001) return;
  const w = h * 0.5, r = w * 0.2;
  shadow(c, x, y + h / 2 + h * 0.02, w * 1.1, a);
  c.save();
  c.globalAlpha *= a;
  // the body's thickness, seen a little from the side
  rr(c, x - w / 2 + h * 0.018, y - h / 2 + h * 0.012, w, h, r);
  c.fillStyle = '#0d0a08';
  c.fill();
  c.shadowColor = 'rgba(0,0,0,0.6)';
  c.shadowBlur = h * 0.18;
  c.shadowOffsetY = h * 0.06;
  rr(c, x - w / 2, y - h / 2, w, h, r);
  const body = c.createLinearGradient(x - w / 2, 0, x + w / 2, 0);
  body.addColorStop(0, '#2e2620');
  body.addColorStop(0.5, '#18130f');
  body.addColorStop(1, '#30271f');
  c.fillStyle = body;
  c.fill();
  c.shadowColor = 'transparent';
  c.strokeStyle = 'rgba(240,222,200,0.32)';
  c.lineWidth = h * 0.008;
  c.stroke();
  // screen
  const m = w * 0.07, sx = x - w / 2 + m, sy = y - h / 2 + m, sw = w - 2 * m, sh = h - 2 * m;
  rr(c, sx, sy, sw, sh, r * 0.7);
  const scr = c.createLinearGradient(0, sy, 0, sy + sh);
  scr.addColorStop(0, `rgba(${lerp(30, 52, on)},${lerp(25, 45, on)},${lerp(21, 38, on)},1)`);
  scr.addColorStop(1, `rgba(${lerp(20, 30, on)},${lerp(17, 26, on)},${lerp(14, 22, on)},1)`);
  c.fillStyle = scr;
  c.fill();
  // notch
  rr(c, x - w * 0.14, sy + sh * 0.02, w * 0.28, h * 0.028, h * 0.014);
  c.fillStyle = '#0a0806';
  c.fill();
  if (!o.screen && on > 0.01 && h >= 150) {
    // an idle chat on the screen, faint
    o.screen = (k, x2, y2, w2, h2) => {
      bubble(k, x2 + w2 * 0.08, y2 + h2 * 0.1, w2 * 0.55, h2 * 0.075, { mine: false, a: 0.55 });
      bubble(k, x2 + w2 * 0.34, y2 + h2 * 0.21, w2 * 0.58, h2 * 0.075, { mine: true, a: 0.55 });
      bubble(k, x2 + w2 * 0.08, y2 + h2 * 0.32, w2 * 0.45, h2 * 0.075, { mine: false, a: 0.55 });
    };
  }
  if (o.screen && on > 0.01) {
    c.save();
    rr(c, sx, sy, sw, sh, r * 0.7);
    c.clip();
    c.globalAlpha *= on;
    o.screen(c, sx, sy + sh * 0.07, sw, sh * 0.93);
    c.restore();
  }
  c.restore();
  // the screen's glow on the glow layer
  if (on > 0.01 && o.accent) {
    g.save();
    g.globalAlpha *= a * on * 0.05;
    rr(g, sx, sy, sw, sh, r * 0.7);
    g.fillStyle = glowInk(o.accent ?? 'accent', 0.5);
    g.fill();
    g.restore();
  }
  if (o.label) text(c, o.label, x, y + h / 2 + h * 0.13, h * 0.11, { color: 'fgDim', a: a, weight: 500 });
}

/** A chat bubble on a phone screen (or anywhere): rounded, with a tail, a text line and the receipt ticks. */
export function bubble(c: Ctx, x: number, y: number, w: number, h: number, o: { mine?: boolean; textW?: number; ticks?: number; blue?: number; a?: number; lines?: number } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const mine = o.mine ?? true;
  c.save();
  c.globalAlpha *= a;
  rr(c, x, y, w, h, h * 0.32);
  c.fillStyle = mine ? '#1f5c3a' : '#2e2620';
  c.fill();
  // tail
  c.beginPath();
  if (mine) { c.moveTo(x + w - h * 0.2, y + h); c.lineTo(x + w + h * 0.18, y + h); c.lineTo(x + w - h * 0.05, y + h * 0.65); }
  else { c.moveTo(x + h * 0.2, y + h); c.lineTo(x - h * 0.18, y + h); c.lineTo(x + h * 0.05, y + h * 0.65); }
  c.fill();
  // text lines (abstract)
  const n = o.lines ?? 1;
  for (let i = 0; i < n; i++) {
    const lw = (o.textW ?? 0.62) * w * (i === n - 1 && n > 1 ? 0.6 : 1);
    rr(c, x + h * 0.28, y + h * (0.3 + 0.0) + i * h * 0.26, lw, h * 0.13, h * 0.065);
    c.fillStyle = 'rgba(242,236,228,0.75)';
    c.fill();
  }
  if (o.ticks) ticks(c, x + w - h * 0.62, y + h * 0.72, h * 0.3, o.ticks, o.blue ?? 0);
  c.restore();
}

/** Receipt ticks: n = 1 (sent) or 2 (delivered), blue 0..1 (read), drawn at (x, y), `s` tall. */
export function ticks(c: Ctx, x: number, y: number, s: number, n: number, blue: number, lw?: number) {
  const col = mixHex(TXT2, BLUE, blue);
  c.save();
  c.strokeStyle = col;
  c.lineWidth = lw ?? s * 0.16;
  c.lineCap = 'round';
  c.lineJoin = 'round';
  const one = (ox: number, k: number) => {
    if (k <= 0) return;
    // the tick draws on: the short stroke, then the long one
    const p0 = { x: ox - s * 0.5, y: y }, p1 = { x: ox - s * 0.15, y: y + s * 0.35 }, p2 = { x: ox + s * 0.5, y: y - s * 0.4 };
    c.beginPath();
    c.moveTo(p0.x, p0.y);
    const k1 = clamp(k * 2.2), k2 = clamp(k * 2.2 - 1.2);
    c.lineTo(lerp(p0.x, p1.x, k1), lerp(p0.y, p1.y, k1));
    if (k2 > 0) c.lineTo(lerp(p1.x, p2.x, k2), lerp(p1.y, p2.y, k2));
    c.stroke();
  };
  one(x - s * 0.18, clamp(n));
  if (n > 1) one(x + s * 0.18, clamp(n - 1));
  c.restore();
}

export function mixHex(a: string, b: string, k: number): string {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(lerp((pa >> s) & 255, (pb >> s) & 255, clamp(k)));
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

/** A server tower centred on (x, y), `h` tall, with `units` rack units whose LEDs blink (seeded) at `activity`. */
export function server(c: Ctx, g: Ctx, x: number, y: number, h: number, o: { a?: number; units?: number; activity?: number; t?: number; label?: string; seed?: number; led?: string } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const w = h * 0.62, n = o.units ?? 6, t = o.t ?? 0;
  shadow(c, x, y + h / 2 + h * 0.03, w * 1.2, a);
  c.save();
  c.globalAlpha *= a;
  // the tower's side face: extruded to the right, in shade
  c.beginPath();
  c.moveTo(x + w / 2, y - h / 2 + h * 0.02); c.lineTo(x + w / 2 + w * 0.12, y - h / 2 - h * 0.03);
  c.lineTo(x + w / 2 + w * 0.12, y + h / 2 - h * 0.06); c.lineTo(x + w / 2, y + h / 2);
  c.closePath();
  c.fillStyle = '#16110d';
  c.fill();
  c.beginPath();
  c.moveTo(x - w / 2 + h * 0.03, y - h / 2); c.lineTo(x - w / 2 + w * 0.12 + h * 0.02, y - h / 2 - h * 0.03);
  c.lineTo(x + w / 2 + w * 0.12, y - h / 2 - h * 0.03); c.lineTo(x + w / 2, y - h / 2);
  c.closePath();
  c.fillStyle = '#4a3c30';
  c.fill();
  c.shadowColor = 'rgba(0,0,0,0.6)';
  c.shadowBlur = h * 0.15;
  c.shadowOffsetY = h * 0.05;
  rr(c, x - w / 2, y - h / 2, w, h, h * 0.05);
  const body = c.createLinearGradient(0, y - h / 2, 0, y + h / 2);
  body.addColorStop(0, '#33291f');
  body.addColorStop(1, '#1a1511');
  c.fillStyle = body;
  c.fill();
  c.shadowColor = 'transparent';
  c.strokeStyle = 'rgba(240,222,200,0.26)';
  c.lineWidth = h * 0.006;
  c.stroke();
  const m = h * 0.06, uh = (h - 2 * m) / n;
  for (let i = 0; i < n; i++) {
    const uy = y - h / 2 + m + i * uh;
    rr(c, x - w / 2 + m, uy + uh * 0.12, w - 2 * m, uh * 0.76, uh * 0.12);
    c.fillStyle = '#110d0a';
    c.fill();
    // vents
    for (let v = 0; v < 6; v++) {
      c.fillStyle = 'rgba(240,222,200,0.07)';
      c.fillRect(x - w / 2 + m + uh * 0.3 + v * w * 0.06, uy + uh * 0.35, w * 0.035, uh * 0.3);
    }
    // LEDs
    for (let l = 0; l < 3; l++) {
      const on = noise1(t * 6 + i * 3.1 + l * 7.7, (o.seed ?? 1) + l) > 1 - 2 * (o.activity ?? 0.3) ? 1 : 0.15;
      const lx = x + w / 2 - m - uh * 0.25 - l * uh * 0.28, ly = uy + uh * 0.5;
      c.fillStyle = withA(o.led ?? GREEN, on);
      c.beginPath();
      c.arc(lx, ly, uh * 0.07, 0, TAU);
      c.fill();
      if (on > 0.5) {
        g.fillStyle = glowInk(o.led ?? GREEN, 0.9 * a);
        g.beginPath();
        g.arc(lx, ly, uh * 0.11, 0, TAU);
        g.fill();
      }
    }
  }
  c.restore();
  if (o.label) text(c, o.label, x, y + h / 2 + h * 0.1, h * 0.085, { color: 'fgDim', a, weight: 500 });
}

/** A database / blob store cylinder centred on (x, y). */
export function cylinder(c: Ctx, x: number, y: number, w: number, h: number, o: { a?: number; fill?: number; label?: string } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const e = w * 0.16;
  shadow(c, x, y + h / 2 + e * 0.5, w * 1.1, a);
  c.save();
  c.globalAlpha *= a;
  c.shadowColor = 'rgba(0,0,0,0.55)';
  c.shadowBlur = h * 0.2;
  c.shadowOffsetY = h * 0.06;
  c.beginPath();
  c.ellipse(x, y - h / 2, w / 2, e, 0, Math.PI, 0);
  c.lineTo(x + w / 2, y + h / 2);
  c.ellipse(x, y + h / 2, w / 2, e, 0, 0, Math.PI);
  c.closePath();
  const gr = c.createLinearGradient(x - w / 2, 0, x + w / 2, 0);
  gr.addColorStop(0, '#211a14');
  gr.addColorStop(0.45, '#3d3227');
  gr.addColorStop(1, '#1a1511');
  c.fillStyle = gr;
  c.fill();
  c.shadowColor = 'transparent';
  c.strokeStyle = 'rgba(240,222,200,0.3)';
  c.lineWidth = w * 0.01;
  c.stroke();
  for (const k of [0.33, 0.66]) {
    c.beginPath();
    c.ellipse(x, y - h / 2 + h * k, w / 2, e, 0, 0, Math.PI);
    c.strokeStyle = 'rgba(240,222,200,0.14)';
    c.stroke();
  }
  c.beginPath();
  c.ellipse(x, y - h / 2, w / 2, e, 0, 0, TAU);
  c.fillStyle = '#4a3d31';
  c.fill();
  c.strokeStyle = 'rgba(240,222,200,0.4)';
  c.stroke();
  c.restore();
  if (o.label) text(c, o.label, x, y + h / 2 + e + w * 0.16, w * 0.13, { color: 'fgDim', a, weight: 500 });
}

/** A padlock centred on (x, y), `s` tall; `open` 0..1 lifts the shackle. */
export function lock(c: Ctx, g: Ctx, x: number, y: number, s: number, o: { a?: number; open?: number; color?: string; glow?: number } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const col = o.color ?? GREEN, op = o.open ?? 0;
  const bw = s * 0.72, bh = s * 0.52;
  for (const [k, isG] of [[c, false], [g, true]] as const) {
    if (isG && !(o.glow ?? 0)) continue;
    k.save();
    k.globalAlpha *= a * (isG ? o.glow! : 1);
    k.strokeStyle = isG ? glowInk(col, 1) : col;
    k.lineWidth = s * 0.1;
    k.lineCap = 'round';
    k.beginPath();
    const sy = y - bh * 0.05 - op * s * 0.18;
    k.arc(x, sy - s * 0.12, s * 0.22, Math.PI, 0);
    k.lineTo(x + s * 0.22, sy + (op > 0 ? -s * 0.02 : s * 0.05));
    k.moveTo(x - s * 0.22, sy - s * 0.12);
    k.lineTo(x - s * 0.22, sy + s * 0.05);
    k.stroke();
    rr(k, x - bw / 2, y - bh * 0.05, bw, bh, s * 0.1);
    k.fillStyle = isG ? glowInk(col, 1) : col;
    k.fill();
    if (!isG) {
      k.fillStyle = 'rgba(18,14,11,0.85)';
      k.beginPath();
      k.arc(x, y + bh * 0.38, s * 0.065, 0, TAU);
      k.fill();
      k.fillRect(x - s * 0.025, y + bh * 0.38, s * 0.05, bh * 0.28);
    }
    k.restore();
  }
}

/** A key centred on (x, y), `s` long, pointing right. */
export function key(c: Ctx, g: Ctx, x: number, y: number, s: number, o: { a?: number; color?: string; glow?: number; rot?: number } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  const col = o.color ?? GREEN;
  for (const [k, isG] of [[c, false], [g, true]] as const) {
    if (isG && !(o.glow ?? 0)) continue;
    k.save();
    k.globalAlpha *= a * (isG ? o.glow! : 1);
    k.translate(x, y);
    k.rotate(o.rot ?? 0);
    k.strokeStyle = isG ? glowInk(col, 1) : col;
    k.fillStyle = k.strokeStyle;
    k.lineWidth = s * 0.08;
    k.lineCap = 'round';
    k.beginPath();
    k.arc(-s * 0.3, 0, s * 0.17, 0, TAU);
    k.stroke();
    k.beginPath();
    k.moveTo(-s * 0.13, 0);
    k.lineTo(s * 0.48, 0);
    k.moveTo(s * 0.3, 0);
    k.lineTo(s * 0.3, s * 0.14);
    k.moveTo(s * 0.42, 0);
    k.lineTo(s * 0.42, s * 0.11);
    k.stroke();
    k.restore();
  }
}

/** A globe-ish CDN edge node: a ring of meridians, centred on (x, y), radius r. */
export function globe(c: Ctx, g: Ctx, x: number, y: number, r: number, o: { a?: number; t?: number; label?: string; glow?: number } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001) return;
  c.save();
  c.globalAlpha *= a;
  const gr = c.createRadialGradient(x - r * 0.3, y - r * 0.4, 0, x, y, r);
  gr.addColorStop(0, '#352b22');
  gr.addColorStop(1, '#15100c');
  c.fillStyle = gr;
  c.beginPath();
  c.arc(x, y, r, 0, TAU);
  c.fill();
  c.strokeStyle = 'rgba(240,222,200,0.32)';
  c.lineWidth = r * 0.03;
  c.stroke();
  c.strokeStyle = 'rgba(37,211,102,0.35)';
  c.lineWidth = r * 0.025;
  const sp = (o.t ?? 0) * 0.5;
  for (let i = 0; i < 4; i++) {
    const ph = ((i / 4 + sp) % 1) * Math.PI;
    const rx = Math.abs(Math.cos(ph)) * r;
    c.beginPath();
    c.ellipse(x, y, Math.max(0.5, rx), r, 0, 0, TAU);
    c.stroke();
  }
  for (const k of [-0.5, 0, 0.5]) {
    c.beginPath();
    c.ellipse(x, y + k * r, r * Math.sqrt(1 - k * k), r * 0.12 * Math.sqrt(1 - k * k), 0, 0, TAU);
    c.stroke();
  }
  c.restore();
  if (o.glow) {
    g.save();
    g.globalAlpha *= a * o.glow;
    g.strokeStyle = glowInk('accent', 0.8);
    g.lineWidth = r * 0.05;
    g.beginPath();
    g.arc(x, y, r * 1.02, 0, TAU);
    g.stroke();
    g.restore();
  }
  if (o.label) text(c, o.label, x, y + r * 1.42, r * 0.3, { color: 'fgDim', a, weight: 500 });
}

// ── wires and packets ─────────────────────────────────────────────────────────────────────────────────────────────

/** A quadratic wire from a to b bowed by `bend` (fraction of its length, + to the left). */
export function curve(a: Pt, b: Pt, bend = 0): (s: number) => Pt {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y;
  const cx = mx - dy * bend, cy = my + dx * bend;
  return (s: number) => ({
    x: (1 - s) * (1 - s) * a.x + 2 * (1 - s) * s * cx + s * s * b.x,
    y: (1 - s) * (1 - s) * a.y + 2 * (1 - s) * s * cy + s * s * b.y,
  });
}

/** Draw a wire along `path` from s0 to s1 (it draws on as s1 grows); dashed when `dash`. */
export function wire(c: Ctx, g: Ctx, path: (s: number) => Pt, s1: number, o: { s0?: number; a?: number; color?: string; width?: number; dash?: number[]; glow?: number; flow?: number } = {}) {
  const a = o.a ?? 1, s0 = o.s0 ?? 0;
  if (a <= 0.001 || s1 <= s0) return;
  const N = 48;
  const trace = (k: Ctx) => {
    k.beginPath();
    for (let i = 0; i <= N; i++) {
      const p = path(lerp(s0, s1, i / N));
      i ? k.lineTo(p.x, p.y) : k.moveTo(p.x, p.y);
    }
  };
  c.save();
  c.globalAlpha *= a;
  c.strokeStyle = o.color ? withA(o.color, 1) : 'rgba(200,184,165,0.34)';
  c.lineWidth = o.width ?? 2.2;
  c.lineCap = 'round';
  if (o.dash) {
    c.setLineDash(o.dash);
    c.lineDashOffset = -(o.flow ?? 0);
  }
  trace(c);
  c.stroke();
  c.restore();
  if (o.glow) {
    g.save();
    g.globalAlpha *= a * o.glow;
    g.strokeStyle = glowInk(o.color ?? 'accent', 0.6);
    g.lineWidth = (o.width ?? 2.2) * 1.6;
    g.lineCap = 'round';
    trace(g);
    g.stroke();
    g.restore();
  }
}

/** A glowing packet (a capsule with a comet tail) at position s along `path`. */
export function packet(c: Ctx, g: Ctx, path: (s: number) => Pt, s: number, o: { color?: string; size?: number; a?: number; tail?: number; kind?: 'dot' | 'msg' | 'cipher' } = {}) {
  const a = o.a ?? 1;
  if (a <= 0.001 || s < 0 || s > 1) return;
  const col = o.color ?? GREEN, z = o.size ?? 12;
  const p = path(s), q = path(Math.max(0, s - 0.01));
  const ang = Math.atan2(p.y - q.y, p.x - q.x);
  // tail
  const tl = o.tail ?? 0.12;
  g.save();
  g.lineCap = 'round';
  for (let i = 0; i < 10; i++) {
    const s0 = s - (tl * i) / 10, s1 = s - (tl * (i + 1)) / 10;
    if (s1 < 0) break;
    const p0 = path(s0), p1 = path(s1);
    g.strokeStyle = glowInk(col, a * 0.5 * (1 - i / 10));
    g.lineWidth = z * 0.7 * (1 - i / 12);
    g.beginPath();
    g.moveTo(p0.x, p0.y);
    g.lineTo(p1.x, p1.y);
    g.stroke();
  }
  g.fillStyle = glowInk(col, a);
  g.beginPath();
  g.arc(p.x, p.y, z * 0.9, 0, TAU);
  g.fill();
  g.restore();
  c.save();
  c.globalAlpha *= a;
  c.translate(p.x, p.y);
  if (o.kind === 'msg' || o.kind === 'cipher') {
    c.rotate(0);
    rr(c, -z * 1.5, -z, z * 3, z * 2, z * 0.6);
    c.fillStyle = o.kind === 'cipher' ? '#2e2620' : '#1f5c3a';
    c.fill();
    c.strokeStyle = withA(col, 0.9);
    c.lineWidth = z * 0.14;
    c.stroke();
    if (o.kind === 'cipher') {
      c.font = font(F.mono(700), z * 0.95);
      c.fillStyle = 'rgba(220,200,175,0.95)';
      c.textAlign = 'center';
      c.textBaseline = 'middle';
      const glyphs = '#%&*@$?!';
      const i = Math.floor(s * 40);
      c.fillText(glyphs[i % 8]! + glyphs[(i * 3 + 1) % 8]! + glyphs[(i * 5 + 2) % 8]!, 0, z * 0.05);
    } else {
      c.fillStyle = 'rgba(242,236,228,0.85)';
      rr(c, -z * 0.95, -z * 0.28, z * 1.9, z * 0.22, z * 0.11); c.fill();
      rr(c, -z * 0.95, z * 0.12, z * 1.2, z * 0.22, z * 0.11); c.fill();
    }
  } else {
    c.fillStyle = 'rgba(255,250,240,0.95)';
    c.beginPath();
    c.arc(0, 0, z * 0.45, 0, TAU);
    c.fill();
  }
  void ang;
  c.restore();
}

/** A ripple ring (an arrival): expands and fades over `dur` from `at`. */
export function ripple(g: Ctx, x: number, y: number, r: number, t: number, at: number, col = 'accent2', dur = 0.7) {
  const k = (t - at) / dur;
  if (k < 0 || k > 1) return;
  g.save();
  g.strokeStyle = glowInk(col, (1 - k) * 0.9);
  g.lineWidth = r * 0.08 * (1 - k) + 1;
  g.beginPath();
  g.arc(x, y, r * (0.4 + 1.2 * ease.outCubic(k)), 0, TAU);
  g.stroke();
  g.restore();
}

/** A small caption under/over the diagram in box units: mono, tracked, dim. */
export function note(c: Ctx, s: string, x: number, y: number, a: number, o: { size?: number; color?: string; align?: CanvasTextAlign } = {}) {
  if (a <= 0.001) return;
  c.save();
  c.font = font(F.mono(500), ts(o.size ?? 22));
  c.textAlign = o.align ?? 'center';
  c.textBaseline = 'middle';
  c.fillStyle = withA(o.color ?? TXT2, a);
  c.letterSpacing = '1px';
  c.fillText(s, x, y + (1 - a) * 8);
  c.restore();
}
