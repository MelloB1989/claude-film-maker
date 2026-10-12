// Device: a screenshot (or a clip) shown in a drawn device: a browser window (title bar, three window lights, a URL
// bar) or a phone (rounded bezel, a dynamic island). A tall screenshot can scroll slowly inside the screen; the device
// rises in, floats gently, and its edge can catch an accent rim light that blooms.
//
// Params (and frame.ts Framed's: src (required; an image, or a clip with extracted frames), x 0.5, y 0.5, entry 'rise',
// delay, entryDur, drift, float 6, shadow 1, exit, background, glow):
//   device 'browser'  'browser' | 'phone'
//   w                 browser: its width (fraction of W; 0.74, 0.9 in a tall frame); h phone: its height (fraction of
//                     H; 0.8). Either shrinks to fit the frame
//   aspect            the screen's aspect, w / h (browser 1.6; phone 9 / 19.5)
//   url 'example.com' browser: the URL bar's text; lights 'mono' (fgFaint) or three colours ['#hex' | role, ...]
//   scroll 0          how far down a tall screenshot is scrolled: a number (0 top, 1 bottom) or [from, to] over
//                     scrollAt [s, s] (default from 0.6 s to 0.6 s before the shot's end)
//   rim 0.35          an accent rim light on the device's edge (0: none), in rimColor 'accent'
//   bezel '#08080a'   phone: the bezel's and the island's colour; frame 'surface' (browser: the window's colour)
//
//   { id: 'app', scene: Device, length: 4, params: { device: 'browser', src: 'assets/dashboard.png', url: 'app.example.com' } }
//   { id: 'feed', scene: Device, length: 5, params: { device: 'phone', src: 'assets/feed.png', scroll: [0, 1] } }
import { glowInk, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font, F } from '../../engine/type';
import { ease, prog } from '../../engine/util';
import { cropRect, roundRect, Framed, type Box } from './frame';

export type DeviceKind = 'browser' | 'phone';

/** The device's outer box and its screen's (logical px), for a frame of W x H. */
export function deviceLayout(kind: DeviceKind, o: { cx: number; cy: number; w?: number; h?: number; aspect?: number; W: number; H: number }): { body: Box; screen: Box; bar: number } {
  const tall = o.H > o.W;
  if (kind === 'browser') {
    const aspect = o.aspect ?? 1.6;
    let bw = (o.w ?? (tall ? 0.9 : 0.74)) * o.W;
    const barOf = (w: number) => Math.max(22, 0.034 * w);
    // shrink to the frame's height (88%)
    const tot = (w: number) => w / aspect + barOf(w);
    if (tot(bw) > 0.88 * o.H) bw *= (0.88 * o.H) / tot(bw);
    const bar = barOf(bw), bh = bw / aspect + bar;
    const body = { x: o.cx * o.W - bw / 2, y: o.cy * o.H - bh / 2, w: bw, h: bh };
    return { body, screen: { x: body.x, y: body.y + bar, w: bw, h: bh - bar }, bar };
  }
  const aspect = o.aspect ?? 9 / 19.5;
  let bh = (o.h ?? 0.8) * o.H;
  let bw = bh * aspect * 1.06;
  if (bw > 0.92 * o.W) {
    bh *= (0.92 * o.W) / bw;
    bw = 0.92 * o.W;
  }
  const bez = 0.03 * bw;
  const body = { x: o.cx * o.W - bw / 2, y: o.cy * o.H - bh / 2, w: bw, h: bh };
  return { body, screen: { x: body.x + bez, y: body.y + bez, w: bw - 2 * bez, h: bh - 2 * bez }, bar: 0 };
}

/** The scroll position (0 top .. 1 bottom) at shot time lt: a fixed number, or [from, to] eased over [s0, s1]. */
export function scrollAt(scroll: number | [number, number], lt: number, span: [number, number]): number {
  if (typeof scroll === 'number') return scroll;
  return scroll[0] + (scroll[1] - scroll[0]) * prog(lt, span[0], span[1], ease.inOutCubic);
}

export class Device extends Framed {
  protected override defaults: Record<string, unknown> = { entry: 'rise', float: 6, shadow: 1, rim: 0.35, to: { zoom: 1 } };

  override async init() {
    const kind = this.k<DeviceKind>('device', 'browser');
    if (kind !== 'browser' && kind !== 'phone') throw new Error(`shot ${this.ctx.id}: device is 'browser' or 'phone', got '${kind}'`);
    await super.init();
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    if (!this.media) return;
    const u = this.u, kind = this.k<DeviceKind>('device', 'browser');
    const L = deviceLayout(kind, { cx: this.k('x', 0.5), cy: this.k('y', 0.5), w: this.ctx.params.w as number | undefined, h: this.ctx.params.h as number | undefined, aspect: this.ctx.params.aspect as number | undefined, W, H });
    const mo = this.motion(f);
    if (mo.alpha <= 0.001) return;
    const len = f.end - f.start;
    const sk = scrollAt(this.k<number | [number, number]>('scroll', 0), f.lt, this.k<[number, number]>('scrollAt', [0.6, Math.max(0.7, len - 0.6)]));
    const { body, screen } = L;
    const cx = body.x + body.w / 2, cy = body.y + body.h / 2;
    const tf = (g: CanvasRenderingContext2D) => {
      g.translate(cx + mo.dx, cy + mo.dy);
      g.scale(mo.scale, mo.scale);
      g.translate(-cx, -cy);
    };
    c.save();
    c.globalAlpha = mo.alpha;
    tf(c);
    const sa = screen.w / screen.h;
    // the picture, scrolled: cover, top-aligned at 0, its bottom at 1
    const crop = (mw: number, mh: number) => cropRect(mw, mh, sa, 1, 0, -1 + 2 * sk);
    let radius: number;
    if (kind === 'browser') {
      radius = Math.max(8, 0.011 * body.w);
      this.drawPicture(c, body, () => ({ sx: 0, sy: 0, sw: 0, sh: 0 }), f.t, { radius, shadow: this.k('shadow', 1), fill: this.k('frame', 'surface') });
      this.drawBrowserChrome(c, body, L.bar, radius);
      c.save();
      roundRect(c, screen.x, screen.y, screen.w, screen.h, 0);
      c.clip();
      this.drawScreen(c, screen, crop, f.t, 0);
      c.restore();
      c.strokeStyle = rgba('ruleStrong', 0.9);
      c.lineWidth = Math.max(1, 1.2 * u);
      roundRect(c, body.x + 0.5, body.y + 0.5, body.w - 1, body.h - 1, radius);
      c.stroke();
    } else {
      radius = 0.16 * body.w;
      const bezel = this.k('bezel', '#08080a');
      this.drawPicture(c, body, () => ({ sx: 0, sy: 0, sw: 0, sh: 0 }), f.t, { radius, shadow: this.k('shadow', 1), fill: bezel });
      const sr = radius - (screen.x - body.x);
      this.drawScreen(c, screen, crop, f.t, sr);
      // the island
      const iw = 0.3 * screen.w, ih = 0.028 * body.h;
      c.fillStyle = rgba(bezel);
      roundRect(c, cx - iw / 2, screen.y + 0.016 * body.h, iw, ih, ih / 2);
      c.fill();
      // the frame's edge: a hairline catching light
      c.strokeStyle = rgba('ruleStrong', 1);
      c.lineWidth = Math.max(1.5, 2.2 * u);
      roundRect(c, body.x + 1, body.y + 1, body.w - 2, body.h - 2, radius);
      c.stroke();
    }
    c.restore();
    // the rim light: the device's edge in the accent, on the glow layer (it blooms)
    const rim = this.k('rim', 0.35);
    if (rim > 0 && this.glowLevel > 0) {
      const g = this.glow;
      g.save();
      g.globalAlpha = mo.alpha;
      tf(g);
      const grad = g.createLinearGradient(body.x, body.y, body.x + body.w, body.y + body.h);
      const col = this.k('rimColor', 'accent');
      grad.addColorStop(0, glowInk(col, rim));
      grad.addColorStop(0.45, glowInk(col, rim * 0.15));
      grad.addColorStop(1, glowInk(col, rim * 0.5));
      g.strokeStyle = grad;
      g.lineWidth = Math.max(1.5, 2 * u);
      roundRect(g, body.x + 1, body.y + 1, body.w - 2, body.h - 2, radius);
      g.stroke();
      g.restore();
    }
  }

  private drawScreen(c: CanvasRenderingContext2D, screen: Box, crop: (mw: number, mh: number) => { sx: number; sy: number; sw: number; sh: number }, t: number, radius: number) {
    this.drawPicture(c, screen, crop, t, { radius, shadow: 0, fill: 'bg' });
  }

  private drawBrowserChrome(c: CanvasRenderingContext2D, body: Box, bar: number, radius: number) {
    const u = this.u;
    c.save();
    roundRect(c, body.x, body.y, body.w, body.h, radius);
    c.clip();
    c.fillStyle = rgba(this.k('frame', 'surface'));
    c.fillRect(body.x, body.y, body.w, bar);
    c.fillStyle = rgba('rule', 1);
    c.fillRect(body.x, body.y + bar - Math.max(1, u), body.w, Math.max(1, u));
    c.restore();
    // the window lights
    const lights = this.k<'mono' | string[]>('lights', 'mono');
    const r = 0.17 * bar, y = body.y + bar / 2;
    for (let i = 0; i < 3; i++) {
      c.fillStyle = Array.isArray(lights) ? rgba(lights[i] ?? 'fgFaint') : rgba('fgFaint', 0.55);
      c.beginPath();
      c.arc(body.x + 0.55 * bar + i * 0.62 * bar, y, r, 0, Math.PI * 2);
      c.fill();
    }
    // the URL bar
    const uw = Math.min(0.42 * body.w, 30 * bar), uh = 0.6 * bar;
    const ux = body.x + body.w / 2 - uw / 2, uy = y - uh / 2;
    c.fillStyle = rgba('bg', 0.6);
    roundRect(c, ux, uy, uw, uh, uh / 2);
    c.fill();
    const url = this.k('url', 'example.com');
    c.font = font(F.mono(500), 0.36 * bar);
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    c.fillStyle = rgba('fgDim');
    c.fillText(url, body.x + body.w / 2, y + 0.02 * bar, uw - uh);
  }
}

export default Device;
