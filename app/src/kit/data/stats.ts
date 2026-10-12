// StatGrid: two to four stats side by side (2x2 or stacked in a vertical frame), each figure counting up and landing
// on its beat, its label under it, hairline dividers drawing between them.
//
// Params:
//   stats (required)   [{ value, label, prefix?, suffix?, decimals? }] (2 to 4)
//   style 'count'      'count' | 'roll' | 'flip'; columns (default: all in a row; 2 when tall and 4 stats, else 1)
//   at { beat: 0 }     the first lands; every 1 (beats between them); dur 1.2
//   size               the figures (reference px; default fitted to the cells, at most 150); title, kicker (a heading)
//   x 0.5, y 0.5, width 0.86
import { Scene2D, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { pulse, ease, prog } from '../../engine/util';
import * as fx from '../text/fx';
import { Heading } from '../text/list';
import { family, type LaidLine } from '../text/layout';
import { Figure, type FigureStyle } from './figure';
import { decimalsOf } from './num';
import { drawLabel, layLabel } from './counter';

export interface Stat { value: number; label: string; prefix?: string; suffix?: string; decimals?: number }

export class StatGrid extends Scene2D {
  private cells: { fig: Figure; label: LaidLine; x: number; y: number; at: number }[] = [];
  private dividers: { x0: number; y0: number; x1: number; y1: number }[] = [];
  private head: Heading | null = null;
  private headTop = 0;

  override init() {
    const u = this.u, tall = isTall();
    const stats = this.need<Stat[]>('stats');
    const n = stats.length;
    const cols = this.p('columns', tall ? (n === 4 ? 2 : 1) : n);
    const rows = Math.ceil(n / cols);
    const totalW = this.p('width', tall ? 0.86 : 0.86) * W;
    const cw = totalW / cols;
    const fam = family({ role: 'display', width: 87.5, weight: 800 });
    const style = this.p<FigureStyle>('style', 'count');
    // one size for every figure: the largest at which the widest fits its cell
    let size = this.p('size', tall ? 170 : 150) * u;
    const figs = (s: number) => stats.map((st) => new Figure({ value: st.value, decimals: st.decimals ?? decimalsOf(st.value), prefix: st.prefix, suffix: st.suffix }, fam, s, 0.55, style === 'flip'));
    let fs = figs(size);
    const widest = Math.max(...fs.map((f) => f.width));
    if (widest > 0.82 * cw) {
      size *= (0.82 * cw) / widest;
      fs = figs(size);
    }
    const ls = Math.max(18 * u, Math.min(28 * u, 0.17 * size));
    const cap = fs[0]!.m.cap * size;
    const rowH = cap + 0.55 * size + 2.4 * ls;
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 70 : 76) * u, totalW) : null;
    const headH = this.head ? this.head.height + 90 * u : 0;
    const top = this.p('y', 0.5) * H - (headH + rows * rowH) / 2;
    this.headTop = top;
    const x0 = this.p('x', 0.5) * W - totalW / 2;
    const { audio, start } = this.ctx;
    const first = fx.resolveTime(this.p<fx.TimeRef>('at', this.head ? { beat: 2 } : { beat: 0 }), start, audio);
    const times = fx.staggerTimes(n, first, { every: this.p('every', 1), grid: audio });
    this.cells = stats.map((st, i) => {
      const r = Math.floor(i / cols), col = i % cols;
      return { fig: fs[i]!, label: layLabel(st.label, ls), x: x0 + col * cw + cw / 2, y: top + headH + r * rowH + cap, at: times[i]! };
    });
    for (let r = 0; r < rows; r++) for (let col = 1; col < cols; col++) {
      if (r * cols + col >= n) continue;
      const x = x0 + col * cw, y0 = top + headH + r * rowH - 0.1 * size;
      this.dividers.push({ x0: x, y0, x1: x, y1: y0 + cap + 0.4 * size + 2 * ls });
    }
    if (rows > 1) for (let r = 1; r < rows; r++) {
      const y = top + headH + r * rowH - 0.32 * size;
      this.dividers.push({ x0: x0 + 0.08 * totalW, y0: y, x1: x0 + 0.92 * totalW, y1: y });
    }
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, u = this.u;
    if (this.head) this.head.draw(c, W / 2, this.headTop, t, this.ctx.start + 0.1);
    const g = this.glowLevel > 0 ? this.glow : null;
    const k = prog(t, this.ctx.start + 0.1, this.ctx.start + 0.8, ease.outExpo);
    c.fillStyle = rgba('ruleStrong');
    for (const d of this.dividers) {
      const mx = (d.x0 + d.x1) / 2, my = (d.y0 + d.y1) / 2;
      c.fillRect(mx - ((d.x1 - d.x0) * k) / 2 - (d.x0 === d.x1 ? 0.75 * u : 0), my - ((d.y1 - d.y0) * k) / 2 - (d.y0 === d.y1 ? 0.75 * u : 0), Math.max(1.5 * u, (d.x1 - d.x0) * k), Math.max(1.5 * u, (d.y1 - d.y0) * k));
    }
    const style = this.p<FigureStyle>('style', 'count');
    const dur = this.p('dur', 1.2);
    for (const cell of this.cells) {
      const a = prog(t, cell.at - dur - 0.1, cell.at - dur + 0.2, ease.outCubic);
      if (a <= 0) continue;
      c.save();
      c.globalAlpha = a;
      const flare = t >= cell.at ? 0.35 * pulse(t, cell.at, 0.12) : 0;
      cell.fig.draw(c, g, cell.x - cell.fig.width / 2, cell.y, t, { style, land: cell.at, dur, ease: 'outExpo', seed: 2 }, { flare, affixGlow: 0.25 });
      c.restore();
      const L = cell.label;
      drawLabel(c, L, cell.x - L.width / 2, cell.y + 0.42 * cell.fig.size + L.m.cap * L.size, t, cell.at - dur + 0.1, 'fgDim', a);
    }
  }
}

export default StatGrid;
