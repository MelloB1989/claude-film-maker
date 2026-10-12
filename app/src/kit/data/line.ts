// LineChart: a smooth line that draws itself across the chart (in one sweep, or point by point on the beat), an
// accent gradient filling in under it, a glowing head carrying the current value, faint gridlines with their values.
//
// Params:
//   data (required)    numbers, or [{ label, value }]; labels: x labels (default: the data's, first and last shown)
//   min, max           the scale (default: from the data, with headroom; min 0 when every value is positive)
//   prefix, suffix, decimals
//   title, kicker      a heading above
//   at { beat: 0 }     when the line starts; dur 1.8 (s to draw), or every (beats per point: points land on beats)
//   color 'accent', area true, grid true; x 0.5, y 0.54, width 0.72, height 0.44
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { clamp, ease, lerp, pointAtLength, polylineLengths, prog, pulse, type V2 } from '../../engine/util';
import * as fx from '../text/fx';
import { Heading } from '../text/list';
import { family } from '../text/layout';
import { decimalsOf, formatNumber, niceScale, smoothLine } from './num';

export class LineChart extends Scene2D {
  private head: Heading | null = null;
  private headTop = 0;
  private rect = { x: 0, y: 0, w: 0, h: 0 };
  private pts: V2[] = [];
  private values: number[] = [];
  private labels: string[] = [];
  private line: V2[] = [];
  private lens = new Float32Array(0);
  private ptAt: number[] = [];
  private times: number[] = [];
  private scale = { min: 0, max: 1, step: 1 };
  private dec = 0;

  override init() {
    const u = this.u, tall = isTall();
    const raw = this.need<(number | { label: string; value: number })[]>('data');
    this.values = raw.map((d) => (typeof d === 'number' ? d : d.value));
    this.labels = this.p<string[] | null>('labels', null) ?? raw.map((d) => (typeof d === 'number' ? '' : d.label));
    this.dec = this.p('decimals', Math.max(...this.values.map(decimalsOf)));
    const lo = Math.min(...this.values), hi = Math.max(...this.values);
    this.scale = niceScale(this.p('min', lo >= 0 ? 0 : lo), this.p('max', hi));
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    const w = this.p('width', tall ? 0.8 : 0.66) * W, h = this.p('height', tall ? 0.36 : 0.42) * H;
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 70 : 76) * u, w) : null;
    const headH = this.head ? this.head.height + 80 * u : 0;
    const top = this.p('y', 0.52) * H - (headH + h + 50 * u) / 2;
    this.headTop = top;
    // room on the left for the grid's values
    this.rect = { x: this.p('x', 0.5) * W - w / 2 + 40 * u, y: top + headH, w: w - 40 * u, h };
    const R = this.rect, n = this.values.length;
    this.pts = this.values.map((v, i) => ({ x: R.x + (n > 1 ? (i / (n - 1)) * R.w : R.w / 2), y: R.y + R.h - ((v - this.scale.min) / (this.scale.max - this.scale.min)) * R.h }));
    const sm = smoothLine(this.pts);
    this.line = sm.line;
    this.ptAt = sm.at;
    this.lens = polylineLengths(this.line);
    const { audio, start } = this.ctx;
    const first = fx.resolveTime(this.p<fx.TimeRef>('at', this.head ? { beat: 2 } : { beat: 0 }), start, audio);
    const every = this.p<number | null>('every', null);
    this.times = every ? fx.staggerTimes(n, first, { every, grid: audio }) : this.values.map((_, i) => first + (n > 1 ? i / (n - 1) : 1) * this.p('dur', 1.8));
  }

  /** How far along the line (arc length) at t, and the fractional point index it has reached. */
  private reach(t: number): { s: number; idx: number } {
    const T = this.times, n = T.length;
    if (t <= T[0]!) return { s: 0, idx: 0 };
    if (n < 2 || t >= T[n - 1]!) return { s: this.lens[this.lens.length - 1]!, idx: n - 1 };
    let idx: number;
    if (this.p<number | null>('every', null)) {
      // point by point: each span eased onto its beat
      let i = 0;
      while (i < n - 2 && t >= T[i + 1]!) i++;
      idx = i + ease.outCubic(prog(t, T[i]!, T[i + 1]!));
    } else idx = prog(t, T[0]!, T[n - 1]!, ease.inOutCubic) * (n - 1); // one sweep, eased over the whole line
    const j = Math.min(n - 2, Math.floor(idx));
    return { s: lerp(this.lens[this.ptAt[j]!]!, this.lens[this.ptAt[j + 1]!]!, idx - j), idx };
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, u = this.u, R = this.rect;
    const color = this.p('color', 'accent');
    if (this.head) this.head.draw(c, R.x + R.w / 2 - 20 * u, this.headTop, t, this.ctx.start + 0.1);
    const g = this.glowLevel > 0 ? this.glow : null;
    const gk = prog(t, this.ctx.start + 0.05, this.ctx.start + 0.7, ease.outCubic);
    const mono = family({ role: 'mono', weight: 500 });
    const fs = (isTall() ? 22 : 18) * u;
    const pre = this.p<string>('prefix', ''), suf = this.p<string>('suffix', '');
    // the grid: faint lines with their values, drawing out from the left
    if (this.p('grid', true)) {
      c.font = font(mono, fs);
      for (let v = this.scale.min; v <= this.scale.max + 1e-9; v += this.scale.step) {
        const y = R.y + R.h - ((v - this.scale.min) / (this.scale.max - this.scale.min)) * R.h;
        c.fillStyle = rgba(v === this.scale.min ? 'ruleStrong' : 'rule', gk);
        c.fillRect(R.x, y, R.w * gk, Math.max(1, u));
        c.fillStyle = rgba('fgFaint', gk);
        c.textAlign = 'right';
        c.fillText(pre + formatNumber(v, decimalsOf(this.scale.step)) + suf, R.x - 14 * u, y + 0.35 * fs);
      }
      c.textAlign = 'left';
    }
    // x labels: first and last (or all, when few)
    const labs = this.labels, n = labs.length;
    c.font = font(mono, fs);
    c.fillStyle = rgba('fgDim', gk);
    labs.forEach((l, i) => {
      if (!l || (n > 6 && i !== 0 && i !== n - 1)) return;
      c.textAlign = i === 0 ? 'left' : i === n - 1 ? 'right' : 'center';
      c.fillText(l.toUpperCase(), this.pts[i]!.x, R.y + R.h + 2 * fs);
    });
    c.textAlign = 'left';
    const { s, idx } = this.reach(t);
    if (s <= 0) return;
    // the drawn part of the line, as a path
    const L = this.lens;
    let last = 0;
    while (last < L.length - 1 && L[last + 1]! <= s) last++;
    const head = pointAtLength(this.line, L, s);
    const path = new Path2D();
    path.moveTo(this.line[0]!.x, this.line[0]!.y);
    for (let i = 1; i <= last; i++) path.lineTo(this.line[i]!.x, this.line[i]!.y);
    path.lineTo(head.x, head.y);
    if (this.p('area', true)) {
      const area = new Path2D(path);
      area.lineTo(head.x, R.y + R.h);
      area.lineTo(this.line[0]!.x, R.y + R.h);
      area.closePath();
      const grad = c.createLinearGradient(0, R.y, 0, R.y + R.h);
      grad.addColorStop(0, rgba(color, 0.3));
      grad.addColorStop(1, rgba(color, 0));
      c.fillStyle = grad;
      c.fill(area);
    }
    const lw = Math.max(2, 4 * u);
    c.lineWidth = lw;
    c.lineJoin = 'round';
    c.lineCap = 'round';
    c.strokeStyle = rgba(color);
    c.stroke(path);
    if (g) {
      g.lineWidth = lw;
      g.lineJoin = 'round';
      g.lineCap = 'round';
      g.strokeStyle = glowInk(color, 0.6);
      g.stroke(path);
    }
    // the points it has passed, and the head with its value
    this.pts.forEach((p, i) => {
      if (i > idx + 1e-6) return;
      c.fillStyle = rgba('bg');
      c.strokeStyle = rgba(color);
      c.lineWidth = Math.max(1.5, 2.5 * u);
      c.beginPath();
      c.arc(p.x, p.y, 5 * u, 0, Math.PI * 2);
      c.fill();
      c.stroke();
    });
    const T = this.times, landed = t >= T[T.length - 1]!;
    const ring = landed ? pulse(t, T[T.length - 1]!, 0.35) : 0;
    c.fillStyle = rgba(color);
    c.beginPath();
    c.arc(head.x, head.y, 8 * u, 0, Math.PI * 2);
    c.fill();
    if (ring > 0.01) {
      c.strokeStyle = rgba(color, ring);
      c.lineWidth = 2 * u;
      c.beginPath();
      c.arc(head.x, head.y, (8 + 30 * (1 - ring)) * u, 0, Math.PI * 2);
      c.stroke();
    }
    if (g) {
      g.fillStyle = glowInk(color, 0.9);
      g.beginPath();
      g.arc(head.x, head.y, 9 * u, 0, Math.PI * 2);
      g.fill();
    }
    // the value at the head
    const j = Math.min(this.values.length - 2, Math.floor(idx));
    const v = this.values.length > 1 ? lerp(this.values[j]!, this.values[j + 1]!, clamp(idx - j)) : this.values[0]!;
    const vs = (isTall() ? 52 : 46) * u;
    c.font = font(family({ role: 'display', width: 87.5, weight: 800 }), vs);
    c.fillStyle = rgba('fg');
    c.textAlign = head.x > R.x + R.w * 0.8 ? 'right' : 'left';
    c.fillText(pre + formatNumber(v, this.dec) + suf, head.x + (c.textAlign === 'right' ? -0.3 : 0.3) * vs, head.y - 0.55 * vs);
    c.textAlign = 'left';
  }
}

export default LineChart;
