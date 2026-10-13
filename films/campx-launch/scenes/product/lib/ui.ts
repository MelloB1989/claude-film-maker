// UiScene: a real product screenshot sold the way a keynote sells it. The screenshot floats in a softly lit studio,
// tilted a few degrees about its vertical axis (true perspective, drawn as slices), under a slow camera. Focus pulls
// push into a region: the rest of the frame defocuses and dims behind a feathered spotlight. Refined callouts with thin
// leader lines, highlight boxes with question tags, drawn ticks, a gliding cursor with click ripples and pulsing chips
// all live in image coordinates, so they follow the camera and the tilt.
//
// Everything is data: a Cfg (geometry.ts) per scene, in params.ts. Swapping the stand-in sheets for the real
// screenshots is a change to `images`, `base` and the coordinates. A frame is a pure function of its time.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { openSource, type MediaSource } from '@kit/media';
import { Layer2D, W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { clamp, lerp, mulberry32 } from '@engine/util';
import { disposeLayer } from '@engine/scene';
import { camAt, cursorAt, project, quad, rise, window, type Cfg, type View } from './geometry';

const SLICES = 560;

export abstract class UiScene extends Scene2D {
  protected abstract readonly cfg: Cfg;
  private media: MediaSource[] = [];
  private buf = new Layer2D();
  private sharp = new Layer2D();
  private tmp = new Layer2D();
  private bokeh: { x: number; y: number; r: number; a: number; hue: number; sp: number }[] = [];

  constructor(ctx: ConstructorParameters<typeof Scene2D>[0]) {
    super(ctx);
    const rnd = mulberry32(7);
    for (let i = 0; i < 16; i++) this.bokeh.push({ x: rnd(), y: rnd(), r: 40 + rnd() * 120, a: 0.03 + rnd() * 0.05, hue: rnd(), sp: 0.004 + rnd() * 0.01 });
  }

  override async init() {
    const cfg = this.config();
    this.media = await Promise.all(cfg.images.map((im) => openSource(im.src, { id: this.ctx.id, start: this.ctx.start })));
  }

  /** The scene's config with the film's params laid over it (film.ts may tweak any key). */
  protected config(): Cfg {
    return { ...this.cfg, ...(this.ctx.params.cfg as Partial<Cfg> | undefined) };
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const cfg = this.config();
    const u = this.u, t = f.lt;
    const m0 = this.media[0];
    if (!m0) return;
    const aspect = m0.width / Math.max(1, m0.height);
    const view = this.view(cfg, aspect, t);
    this.studio(c, cfg, t, camAt(cfg.cam, t, cfg.anchor));

    // the frame: slices of the screenshot in perspective, into the buffer
    const b = this.buf.ctx;
    this.buf.clear();
    const entry = rise(t, 0, 0.9);
    this.screenshot(b, cfg, view, t, entry);

    // focus: every spot in play at t (crossing spots overlap, so the stage stays dark through a hand-over)
    const live: { a: number; q: { x: number; y: number }[]; dim: number }[] = [];
    for (const s of cfg.spots ?? []) {
      const a = window(t, s.t0, s.t1, 0.7, 0.7);
      if (a > 0.002) live.push({ a, q: quad(view, s.rect, s.pad ?? 0.01), dim: s.dim ?? 0.86 });
    }
    const spot = Math.min(1, live.reduce((m, l) => m + l.a, 0));
    const dim = live.reduce((m, l) => Math.max(m, l.dim), 0);
    c.save();
    // the screenshot is drawn opaque into the buffer and faded in here, so its slices never seam
    c.globalAlpha = entry;
    if (live.length) {
      // the rest of the stage falls away: defocused, then down toward near-black
      c.filter = `blur(${(spot * 9 * u).toFixed(2)}px)`;
      c.drawImage(this.buf.canvas, 0, 0, W, H);
      c.filter = 'none';
      c.globalAlpha = 1;
      c.fillStyle = `rgba(3,2,9,${(dim * spot).toFixed(3)})`;
      c.fillRect(0, 0, W, H);
      // a soft vignette round the lit region, so it reads as a spotlight on a dark stage
      const lead = live.reduce((m, l) => (l.a > m.a ? l : m));
      const cx = lead.q.reduce((a, p) => a + p.x, 0) / lead.q.length, cy = lead.q.reduce((a, p) => a + p.y, 0) / lead.q.length;
      const r0 = Math.max(...lead.q.map((p) => Math.hypot(p.x - cx, p.y - cy)));
      const vg = c.createRadialGradient(cx, cy, r0 * 0.9, cx, cy, r0 + 0.75 * W);
      vg.addColorStop(0, 'rgba(0,0,0,0)');
      vg.addColorStop(1, `rgba(0,0,0,${(0.6 * spot).toFixed(3)})`);
      c.fillStyle = vg;
      c.fillRect(0, 0, W, H);
      // the sharp copy, cut by a tightly feathered mask (the union of the spots in play): crisp and at full
      // contrast, nothing laid over it
      const mk = this.tmp.ctx;
      this.tmp.clear();
      mk.save();
      mk.filter = `blur(${(7 * u).toFixed(1)}px)`;
      for (const l of live) {
        mk.fillStyle = `rgba(0,0,0,${Math.min(1, 1.6 * l.a).toFixed(3)})`;
        mk.beginPath();
        l.q.forEach((p, i) => (i ? mk.lineTo(p.x, p.y) : mk.moveTo(p.x, p.y)));
        mk.closePath();
        mk.fill();
      }
      mk.restore();
      const s = this.sharp.ctx;
      this.sharp.clear();
      s.drawImage(this.buf.canvas, 0, 0, W, H);
      s.globalCompositeOperation = 'destination-in';
      s.drawImage(this.tmp.canvas, 0, 0, W, H);
      s.globalCompositeOperation = 'source-over';
      c.globalAlpha = entry;
      c.drawImage(this.sharp.canvas, 0, 0, W, H);
      // a faint hairline round each spot
      const g = this.glow;
      for (const l of live) {
        g.strokeStyle = glowInk('accentBright', 0.25 * l.a);
        g.lineWidth = 1.2 * u;
        g.beginPath();
        l.q.forEach((p, i) => (i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y)));
        g.closePath();
        g.stroke();
      }
    } else {
      c.drawImage(this.buf.canvas, 0, 0, W, H);
    }
    c.restore();
    this.vignette(c);

    this.sheen(c, view, t, 1 - spot);
    this.boxes(c, cfg, view, t);
    this.ticks(c, cfg, view, t);
    this.callouts(c, cfg, view, t);
    this.chips(c, cfg, view, t);
    this.cursor(c, cfg, view, t);
  }

  /** The camera at t: the focus point, zoom and yaw (a slow drift on top of the keys). */
  private view(cfg: Cfg, aspect: number, t: number): View {
    const cam = camAt(cfg.cam, t, cfg.anchor);
    const u = this.u;
    const b0w = cfg.base.w !== undefined ? cfg.base.w * W : cfg.base.h! * H * aspect;
    const b0h = b0w / aspect;
    const drift = 7 * u;
    return {
      sx: cam.ax * W + Math.sin(t * 0.37) * drift,
      sy: cam.ay * H + Math.cos(t * 0.29) * drift * 0.7,
      bw: b0w * cam.z, bh: b0h * cam.z,
      fx: cam.x, fy: cam.y,
      yaw: ((cfg.yaw ?? -14) + cam.yaw + Math.sin(t * 0.31) * 0.7) * Math.PI / 180,
      dist: (cfg.dist ?? 2000) * u,
    };
  }

  /** Soft studio light behind the frame, and a few out-of-focus lights drifting. */
  private studio(c: CanvasRenderingContext2D, cfg: Cfg, t: number, cam: { x: number; y: number; z: number }) {
    const mode = cfg.light ?? 'brand';
    const pools: [number, number, number, string, number][] = [
      [0.28 + Math.sin(t * 0.21) * 0.03, 0.42, 0.55, mode === 'warm' ? 'accent2' : 'accentDim', 0.9],
      [0.74 + Math.cos(t * 0.17) * 0.03, 0.62, 0.5, mode === 'cool' ? 'accentDim' : 'accent', 0.34],
      [0.5, 1.05, 0.7, 'accent2Dim', 0.5],
    ];
    for (const [x, y, r, key, a] of pools) {
      const R = r * Math.max(W, H);
      const g = c.createRadialGradient(x * W, y * H, 0, x * W, y * H, R);
      g.addColorStop(0, rgba(key, Math.min(1, a * 0.95)));
      g.addColorStop(1, rgba(key, 0));
      c.fillStyle = g;
      c.fillRect(0, 0, W, H);
    }
    // a pale key light behind the frame separates it from the dark
    const kl = c.createRadialGradient(W * 0.5, H * 0.5, 0, W * 0.5, H * 0.5, 0.5 * W);
    kl.addColorStop(0, 'rgba(255,240,235,0.10)');
    kl.addColorStop(1, 'rgba(255,240,235,0)');
    c.fillStyle = kl;
    c.fillRect(0, 0, W, H);
    // parallax: the far lights slide against the camera's pan and spread a little as it pushes in
    const zs = Math.pow(cam.z, 0.3), px = -(cam.x - 0.5) * 0.3 * W, py = -(cam.y - 0.5) * 0.2 * H;
    for (const k of this.bokeh) {
      const x0 = ((k.x + t * k.sp) % 1.2 - 0.1) * W, y0 = k.y * H + Math.sin(t * 0.3 + k.hue * 9) * 12;
      const x = W / 2 + (x0 - W / 2) * zs + px, y = H / 2 + (y0 - H / 2) * zs + py;
      const g = c.createRadialGradient(x, y, 0, x, y, k.r * this.u);
      const key = k.hue < 0.5 ? 'accentBright' : 'accent2Bright';
      g.addColorStop(0, rgba(key, k.a));
      g.addColorStop(0.7, rgba(key, k.a * 0.6));
      g.addColorStop(1, rgba(key, 0));
      c.fillStyle = g;
      c.fillRect(x - k.r * this.u, y - k.r * this.u, 2 * k.r * this.u, 2 * k.r * this.u);
    }
  }

  /** The screenshot (or the crossfade between them) in perspective, with a soft shadow and a lit rim. */
  private screenshot(b: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number, entry: number) {
    const u = this.u;
    const full = quad(v, [0, 0, 1, 1]);
    const lift = (1 - entry) * 26 * u;
    b.save();
    b.translate(0, lift);
    // shadow plate
    b.save();
    b.shadowColor = 'rgba(0,0,0,0.7)';
    b.shadowBlur = 90 * u;
    b.shadowOffsetY = 40 * u;
    b.fillStyle = rgba('bg2');
    b.beginPath();
    full.forEach((p, i) => (i ? b.lineTo(p.x, p.y) : b.moveTo(p.x, p.y)));
    b.closePath();
    b.fill();
    b.restore();
    // slices, visible part only
    b.imageSmoothingQuality = 'high';
    this.cfg.images.forEach((im, i) => {
      const m = this.media[i];
      const pic = m?.frame(0);
      if (!m || !pic) return;
      const a = i === 0 ? 1 : rise(t, im.from ?? 0, im.fade ?? 0.6);
      if (a <= 0.001) return;
      // a crossfading image is sliced opaque into its own layer, then laid over at its alpha (no seams)
      const x = a < 0.999 ? this.tmp.ctx : b;
      if (a < 0.999) { this.tmp.clear(); x.imageSmoothingQuality = 'high'; }
      for (let k = 0; k < SLICES; k++) {
        const u0 = k / SLICES, u1 = (k + 1) / SLICES;
        const p0 = project(v, u0, 0), p1 = project(v, u1, 0);
        const x0 = p0.x, x1 = p1.x;
        if (x1 < -4 || x0 > W + 4) continue;
        const y0 = project(v, u0, 0).y, y1 = project(v, u0, 1).y;
        x.drawImage(pic.el, u0 * pic.width, 0, Math.max(1, pic.width / SLICES), pic.height, x0 - 0.35, y0, x1 - x0 + 0.7, y1 - y0);
      }
      if (a < 0.999) {
        // (b carries the entry lift, so the layer picks it up here)
        b.save();
        b.globalAlpha = a;
        b.drawImage(this.tmp.canvas, 0, 0, W, H);
        b.restore();
      }
    });
    // the rim: a hairline, lit from the upper left
    const lg = b.createLinearGradient(full[0]!.x, full[0]!.y, full[2]!.x, full[2]!.y);
    lg.addColorStop(0, rgba('fg', 0.55));
    lg.addColorStop(0.5, rgba('fg', 0.12));
    lg.addColorStop(1, rgba('accentBright', 0.35));
    b.strokeStyle = lg;
    b.lineWidth = 1.4 * u;
    b.beginPath();
    full.forEach((p, i) => (i ? b.lineTo(p.x, p.y) : b.moveTo(p.x, p.y)));
    b.closePath();
    b.stroke();
    b.restore();
  }

  /** The studio's edges fall off to near-black, whatever the camera does. */
  private vignette(c: CanvasRenderingContext2D) {
    const g = c.createRadialGradient(W / 2, H / 2, 0.42 * W, W / 2, H / 2, 0.78 * W);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(1, 'rgba(0,0,0,0.45)');
    c.fillStyle = g;
    c.fillRect(0, 0, W, H);
  }

  /** A slow light sweep across the glass (k: how much of it shows; none over a focus pull). */
  private sheen(c: CanvasRenderingContext2D, v: View, t: number, k: number) {
    if (k < 0.01) return;
    const full = quad(v, [0, 0, 1, 1]);
    c.save();
    c.beginPath();
    full.forEach((p, i) => (i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y)));
    c.closePath();
    c.clip();
    const x = lerp(-0.3, 1.3, ((t * 0.07) % 1)) * W;
    const g = c.createLinearGradient(x - 220 * this.u, 0, x + 220 * this.u, 260 * this.u);
    g.addColorStop(0, 'rgba(255,255,255,0)');
    g.addColorStop(0.5, `rgba(255,255,255,${(0.055 * k).toFixed(4)})`);
    g.addColorStop(1, 'rgba(255,255,255,0)');
    c.fillStyle = g;
    c.fillRect(0, 0, W, H);
    c.restore();
  }

  private boxes(c: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number) {
    const u = this.u, g = this.glow;
    for (const bx of cfg.boxes ?? []) {
      const a = window(t, bx.t, bx.until, 0.5, 0.4);
      if (a < 0.003) continue;
      const q = quad(v, bx.rect, 0.004 * (1 - a));
      const key = bx.tone ?? 'accent2';
      const path = (cx: CanvasRenderingContext2D) => {
        cx.beginPath();
        q.forEach((p, i) => (i ? cx.lineTo(p.x, p.y) : cx.moveTo(p.x, p.y)));
        cx.closePath();
      };
      c.save();
      path(c);
      c.fillStyle = rgba(key + 'Bright', 0.09 * a);
      c.fill();
      c.strokeStyle = rgba(key + 'Bright', 0.95 * a);
      c.lineWidth = 2.2 * u;
      c.stroke();
      c.restore();
      g.save();
      path(g);
      g.strokeStyle = glowInk(key, 0.7 * a);
      g.lineWidth = 3 * u;
      g.stroke();
      g.restore();
      if (bx.label) this.tag(c, bx.label, q[0]!.x, q[0]!.y - 2 * u, a, key);
    }
  }

  /** A small label chip sitting on a point (bottom-left at x, y). */
  private tag(c: CanvasRenderingContext2D, text: string, x: number, y: number, a: number, key: string) {
    const u = this.u;
    c.save();
    c.globalAlpha = a;
    c.font = font(F.ui(650), 19 * u);
    const w = c.measureText(text).width + 22 * u, h = 30 * u;
    c.fillStyle = rgba(key + 'Bright');
    c.beginPath();
    c.roundRect(x, y - h, w, h, h / 2);
    c.fill();
    c.fillStyle = rgba('bg');
    c.textBaseline = 'middle';
    c.fillText(text, x + 11 * u, y - h / 2 + 1 * u);
    c.restore();
  }

  private ticks(c: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number) {
    const u = this.u, g = this.glow;
    for (const tk of cfg.ticks ?? []) {
      const a = rise(t, tk.t, 0.35);
      if (a < 0.003) continue;
      const p = project(v, tk.at[0], tk.at[1]);
      const r = 17 * u * p.s;
      const key = tk.tone ?? 'accent2';
      for (const [cx, ink] of [[c, (x: number) => rgba(key + 'Bright', x)], [g, (x: number) => glowInk(key, x * 0.8)]] as const) {
        cx.save();
        cx.strokeStyle = ink(a);
        cx.lineWidth = 3.4 * u;
        cx.lineCap = cx.lineJoin = 'round';
        // the ring scales in, then the check draws itself
        cx.beginPath();
        cx.arc(p.x, p.y, r * (0.7 + 0.3 * a), 0, Math.PI * 2);
        cx.stroke();
        const d = clamp((a - 0.3) / 0.7);
        const pts = [[-0.42, 0.02], [-0.1, 0.34], [0.46, -0.3]].map(([x, y]) => [p.x + x * r * 1.2, p.y + y * r * 1.2]);
        cx.beginPath();
        cx.moveTo(pts[0]![0]!, pts[0]![1]!);
        const k1 = Math.min(1, d * 2);
        cx.lineTo(lerp(pts[0]![0]!, pts[1]![0]!, k1), lerp(pts[0]![1]!, pts[1]![1]!, k1));
        if (d > 0.5) {
          const k2 = (d - 0.5) * 2;
          cx.lineTo(lerp(pts[1]![0]!, pts[2]![0]!, k2), lerp(pts[1]![1]!, pts[2]![1]!, k2));
        }
        cx.stroke();
        cx.restore();
      }
    }
  }

  private callouts(c: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number) {
    const u = this.u, g = this.glow;
    for (const co of cfg.callouts ?? []) {
      const a = window(t, co.t, co.until, 0.5, 0.45);
      if (a < 0.003) continue;
      const p = project(v, co.at[0], co.at[1]);
      const tx = p.x + co.off[0] * u, ty = p.y + co.off[1] * u;
      // measure
      c.save();
      c.font = font(F.display(87.5, 600), 28 * u);
      const tw = c.measureText(co.text).width;
      c.font = font(F.ui(400), 19 * u);
      const sw = co.sub ? c.measureText(co.sub).width : 0;
      const w = Math.max(tw, sw) + 44 * u, h = (co.sub ? 80 : 56) * u;
      // pill box anchored so the leader meets its nearest edge midpoint
      const bx = co.off[0] >= 0 ? tx : tx - w, by = ty - h / 2;
      const ex = co.off[0] >= 0 ? bx : bx + w, ey = ty;
      // leader: draws from the anchor to the pill
      const k = rise(t, co.t, 0.55);
      const lx = lerp(p.x, ex, k), ly = lerp(p.y, ey, k);
      c.globalAlpha = a;
      // a dark under-stroke keeps the hairline readable on the white UI as well as the dark studio
      c.lineCap = 'round';
      for (const [ink, lw] of [['rgba(12,8,24,0.4)', 3.6], [rgba('fg', 0.9), 1.5]] as const) {
        c.strokeStyle = ink;
        c.lineWidth = lw * u;
        c.beginPath();
        c.moveTo(p.x, p.y);
        c.lineTo(lx, ly);
        c.stroke();
      }
      // anchor: a dot and a ring
      c.fillStyle = rgba('accentBright');
      c.beginPath();
      c.arc(p.x, p.y, 4.5 * u, 0, Math.PI * 2);
      c.fill();
      c.strokeStyle = rgba('accentBright', 0.8);
      c.lineWidth = 1.6 * u;
      c.beginPath();
      c.arc(p.x, p.y, (11 + 5 * Math.sin(t * 2.4)) * u, 0, Math.PI * 2);
      c.stroke();
      // the pill
      c.globalAlpha = a * rise(t, co.t + 0.2, 0.4);
      c.shadowColor = 'rgba(0,0,0,0.55)';
      c.shadowBlur = 30 * u;
      c.shadowOffsetY = 10 * u;
      c.fillStyle = rgba('surface', 0.92);
      c.beginPath();
      c.roundRect(bx, by, w, h, 14 * u);
      c.fill();
      c.shadowColor = 'transparent';
      c.strokeStyle = rgba('ruleStrong', 1);
      c.lineWidth = 1.2 * u;
      c.stroke();
      c.fillStyle = rgba('accentBright');
      c.beginPath();
      c.roundRect(bx + 14 * u, by + 16 * u, 5 * u, h - 32 * u, 2.5 * u);
      c.fill();
      c.fillStyle = rgba('fg');
      c.textBaseline = 'middle';
      c.font = font(F.display(87.5, 600), 28 * u);
      // whole pixels: the type stays crisp at 1080p
      c.fillText(co.text, Math.round(bx + 32 * u), Math.round(by + (co.sub ? 29 * u : h / 2) + 1 * u));
      if (co.sub) {
        c.fillStyle = rgba('fgDim');
        c.font = font(F.ui(400), 19 * u);
        c.fillText(co.sub, Math.round(bx + 32 * u), Math.round(by + 56 * u));
      }
      c.restore();
      g.save();
      g.strokeStyle = glowInk('accentBright', 0.5 * a);
      g.lineWidth = 2.4 * u;
      g.beginPath();
      g.arc(p.x, p.y, 11 * u, 0, Math.PI * 2);
      g.stroke();
      g.restore();
    }
  }

  private chips(c: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number) {
    const u = this.u, g = this.glow;
    for (const ch of cfg.chips ?? []) {
      const a = window(t, ch.t, ch.until, 0.35, 0.4);
      if (a < 0.003) continue;
      const p = project(v, ch.at[0], ch.at[1]);
      const x = p.x + (ch.off?.[0] ?? 0) * u, y = p.y + (ch.off?.[1] ?? 0) * u;
      const key = ch.tone ?? 'accent2';
      c.save();
      c.font = font(F.display(87.5, 600), 25 * u);
      const w = c.measureText(ch.text).width + 64 * u, h = 46 * u;
      const pop = 0.88 + 0.12 * rise(t, ch.t, 0.4);
      const pulse = ch.pulse ? 0.5 + 0.5 * Math.sin((t - ch.t) * 5) : 0;
      c.translate(x, y);
      c.scale(pop, pop);
      c.globalAlpha = a;
      c.shadowColor = rgba(key, 0.5 + 0.3 * pulse);
      c.shadowBlur = (24 + 18 * pulse) * u;
      c.fillStyle = rgba('surface2', 0.96);
      c.beginPath();
      c.roundRect(-w / 2, -h / 2, w, h, h / 2);
      c.fill();
      c.shadowColor = 'transparent';
      c.strokeStyle = rgba(key + 'Bright', 0.9);
      c.lineWidth = 1.8 * u;
      c.stroke();
      c.fillStyle = rgba(key + 'Bright');
      c.beginPath();
      c.arc(-w / 2 + 26 * u, 0, (6.5 + 2 * pulse) * u, 0, Math.PI * 2);
      c.fill();
      c.fillStyle = rgba('fg');
      c.textBaseline = 'middle';
      c.fillText(ch.text, -w / 2 + 44 * u, 1 * u);
      c.restore();
      g.save();
      g.translate(x, y);
      g.scale(pop, pop);
      g.strokeStyle = glowInk(key, (0.35 + 0.45 * pulse) * a);
      g.lineWidth = 3 * u;
      g.beginPath();
      g.roundRect(-w / 2, -h / 2, w, h, h / 2);
      g.stroke();
      g.restore();
    }
  }

  private cursor(c: CanvasRenderingContext2D, cfg: Cfg, v: View, t: number) {
    const cur = cursorAt(cfg.cursor ?? [], t);
    if (!cur) return;
    const u = this.u, g = this.glow;
    const p = project(v, cur.at[0], cur.at[1]);
    // in before its first key; it leaves a beat after its last
    const fadeIn = rise(t, (cfg.cursor![0]!.t) - 0.4, 0.4) * (1 - rise(t, cfg.cursor![cfg.cursor!.length - 1]!.t + 0.5, 0.5));
    if (fadeIn < 0.003) return;
    for (const age of cur.clicks) {
      if (age > 0.7) continue;
      const k = age / 0.7;
      g.strokeStyle = glowInk('accentBright', 0.8 * (1 - k));
      g.lineWidth = 3 * u * (1 - k) + 0.5;
      g.beginPath();
      g.arc(p.x, p.y, (10 + 46 * k) * u, 0, Math.PI * 2);
      g.stroke();
    }
    const press = cur.clicks.length && cur.clicks[cur.clicks.length - 1]! < 0.16 ? 0.9 : 1;
    c.save();
    c.globalAlpha = fadeIn;
    c.translate(p.x, p.y);
    c.scale(1.05 * u * press, 1.05 * u * press);
    c.shadowColor = 'rgba(0,0,0,0.5)';
    c.shadowBlur = 8;
    c.shadowOffsetY = 3;
    c.beginPath();
    // a standard arrow pointer, tip at the origin
    c.moveTo(0, 0); c.lineTo(0, 24); c.lineTo(6.2, 18.6); c.lineTo(10.4, 28); c.lineTo(14.2, 26.3); c.lineTo(10, 17.2); c.lineTo(17.6, 17.2); c.closePath();
    c.fillStyle = '#ffffff';
    c.fill();
    c.shadowColor = 'transparent';
    c.strokeStyle = 'rgba(8,8,16,0.9)';
    c.lineWidth = 1.8;
    c.lineJoin = 'round';
    c.stroke();
    c.restore();
  }

  override dispose() {
    for (const m of this.media) m.dispose();
    this.media = [];
    disposeLayer(this.buf);
    disposeLayer(this.sharp);
    disposeLayer(this.tmp);
    super.dispose();
  }
}
