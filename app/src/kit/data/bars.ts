// BarChart: bars that grow in one by one on the beat, values counting up with them, the highlighted bar in the accent
// with a glow; a hairline baseline and mono category labels, nothing else.
//
// Params:
//   data (required)    [{ label, value, highlight? }]; highlight: an index or a label (instead of the flag)
//   orientation        'vertical' (columns; the default in a landscape frame) | 'horizontal' (rows; default when tall)
//   max                the scale's top (default: the largest value); prefix, suffix, decimals (default: the data's)
//   title, kicker      a heading above (titleSize 76)
//   at { beat: 0 }     when the first bar lands ({ beat: 2 } with a heading); every 0.5 (beats between bars)
//   color 'accent'     the highlight; x 0.5, y 0.54, width 0.7, height 0.46 (fractions of the frame)
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { slam } from '../../engine/motion';
import { clamp, ease, prog } from '../../engine/util';
import * as fx from '../text/fx';
import { Heading } from '../text/list';
import { family, layLine, type LaidLine } from '../text/layout';
import { countAt, decimalsOf, formatNumber } from './num';

export interface Datum { label: string; value: number; highlight?: boolean }

/** The bars' times: the first at `first`, then `every` beats apart. */
export function landTimes(n: number, first: number, every: number, grid: fx.Grid) {
  return fx.staggerTimes(n, first, { every, grid });
}

export class BarChart extends Scene2D {
  private data: (Datum & { lab: LaidLine; at: number; hi: boolean })[] = [];
  private head: Heading | null = null;
  private rect = { x: 0, y: 0, w: 0, h: 0 };
  private max = 1;
  private dec = 0;
  private vfam = '';
  private headTop = 0;

  override init() {
    const u = this.u, tall = isTall();
    const data = this.need<Datum[]>('data');
    const hiParam = this.p<number | string | null>('highlight', null);
    const vertical = this.p('orientation', tall ? 'horizontal' : 'vertical') === 'vertical';
    const ls = (tall ? 24 : 20) * u;
    const lfam = family({ role: 'mono', weight: 500 });
    this.vfam = family({ role: 'display', width: 87.5, weight: 700 });
    this.max = this.p('max', Math.max(...data.map((d) => d.value)));
    this.dec = this.p('decimals', Math.max(...data.map((d) => decimalsOf(d.value))));
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    const w = this.p('width', tall ? 0.84 : 0.7) * W;
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 70 : 76) * u, w) : null;
    const h = this.p('height', tall ? 0.42 : 0.44) * H;
    const headH = this.head ? this.head.height + 70 * u : 0;
    const total = headH + h + (vertical ? 2.4 * ls : 0);
    const top = this.p('y', 0.52) * H - total / 2;
    this.headTop = top;
    this.rect = { x: this.p('x', 0.5) * W - w / 2, y: top + headH, w, h };
    const { audio, start } = this.ctx;
    const first = fx.resolveTime(this.p<fx.TimeRef>('at', this.head ? { beat: 2 } : { beat: 0 }), start, audio);
    const times = landTimes(data.length, first, this.p('every', 0.5), audio);
    this.data = data.map((d, i) => ({
      ...d, at: times[i]!, lab: layLine(d.label.toUpperCase(), lfam, ls, 0.12 * ls),
      hi: d.highlight ?? (hiParam === i || hiParam === d.label),
    }));
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, u = this.u, R = this.rect;
    const tall = isTall();
    const vertical = this.p('orientation', tall ? 'horizontal' : 'vertical') === 'vertical';
    if (this.head) this.head.draw(c, R.x + R.w / 2, this.headTop, t, this.ctx.start + 0.1);
    const g = this.glowLevel > 0 ? this.glow : null;
    const color = this.p('color', 'accent');
    const n = this.data.length;
    const pre = this.p<string>('prefix', ''), suf = this.p<string>('suffix', '');
    // the baseline draws out first
    const base = prog(t, this.ctx.start + 0.05, this.ctx.start + 0.6, ease.outExpo);
    c.fillStyle = rgba('ruleStrong');
    if (vertical) c.fillRect(R.x + (R.w * (1 - base)) / 2, R.y + R.h, R.w * base, Math.max(1, 1.5 * u));
    else c.fillRect(R.x, R.y + (R.h * (1 - base)) / 2, Math.max(1, 1.5 * u), R.h * base);
    const slot = (vertical ? R.w : R.h) / n;
    const thick = slot * 0.58;
    const vs = vertical ? Math.min(0.42 * thick, 46 * u) : Math.min(0.5 * thick, 40 * u);
    this.data.forEach((d, i) => {
      const k = Math.max(0, slam(t, d.at, { freq: 4, damping: 0.7 }));
      const a = clamp(prog(t, d.at - 0.2, d.at));
      if (a <= 0) return;
      const len = (d.value / this.max) * (vertical ? R.h - 1.6 * vs : R.w * 0.82) * k;
      const ink = d.hi ? rgba(color) : rgba('fg', 0.2);
      c.save();
      c.globalAlpha = a;
      const r = Math.min(thick * 0.14, 10 * u);
      c.fillStyle = ink;
      c.beginPath();
      if (vertical) {
        const x = R.x + i * slot + (slot - thick) / 2;
        c.roundRect(x, R.y + R.h - len, thick, len, [r, r, 0, 0]);
      } else {
        const y = R.y + i * slot + (slot - thick) / 2;
        c.roundRect(R.x + 2 * u, y, len, thick, [0, r, r, 0]);
      }
      c.fill();
      if (g && d.hi) {
        g.save();
        g.globalAlpha = a * (0.22 + 0.3 * fx.emphasisGlow(t, d.at, 0));
        g.fillStyle = glowInk(color);
        g.beginPath();
        if (vertical) g.roundRect(R.x + i * slot + (slot - thick) / 2, R.y + R.h - len, thick, len, [r, r, 0, 0]);
        else g.roundRect(R.x + 2 * u, R.y + i * slot + (slot - thick) / 2, len, thick, [0, r, r, 0]);
        g.fill();
        g.restore();
      }
      // the value counts with its bar; the label sits under (or before) it
      const v = countAt(t, 0, d.value, d.at + 0.12, 0.55, 'outCubic');
      const text = pre + formatNumber(v, this.dec) + suf;
      c.font = font(this.vfam, vs);
      c.fillStyle = rgba(d.hi ? color : 'fg', d.hi ? 1 : 0.85);
      const L = d.lab;
      if (vertical) {
        const cx = R.x + i * slot + slot / 2;
        c.textAlign = 'center';
        c.fillText(text, cx, R.y + R.h - len - 0.5 * vs);
        c.font = font(L.family, L.size);
        c.letterSpacing = `${L.track}px`;
        c.fillStyle = rgba(d.hi ? 'fg' : 'fgDim');
        c.fillText(L.text, cx, R.y + R.h + 1.7 * L.size);
      } else {
        const cy = R.y + i * slot + slot / 2;
        c.textAlign = 'left';
        c.fillText(text, R.x + len + 0.45 * vs, cy + 0.36 * vs);
        c.font = font(L.family, L.size);
        c.letterSpacing = `${L.track}px`;
        c.fillStyle = rgba(d.hi ? 'fg' : 'fgDim');
        c.fillText(L.text, R.x + 2 * u, cy - thick / 2 - 0.6 * L.size);
      }
      c.restore();
    });
  }
}

export default BarChart;
