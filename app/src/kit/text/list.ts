// Lists that land on the beat: BulletList (a column of items, each mark writing itself in as its text rises) and
// FeatureList (cards in a grid, one per beat, each with an icon, a title and a line or two of description). Both take an
// optional heading (a mono kicker and a display title) above.
//
// BulletList params:
//   items (required)   strings, or { text, icon?, desc? }
//   icon 'check'       'check' | 'dot' | 'arrow' | 'plus' | 'dash' | 'star' | 'x' | 'spark'; iconColor 'accent'
//   title, kicker      the heading (titleSize 92)
//   size 58            item text (reference px); role 'display', width 100, weight 600
//   at { beat: 0 }     when the first item lands (with a heading: { beat: 2 }); every 1 (beats between items)
//   focus false        earlier items dim as each new one lands
//   x 0.5, y 0.5, maxWidth 0.78 (fractions of the frame)
// FeatureList params:
//   items (required)   { title, desc?, icon? }; columns (auto: up to 3 across, 1 in a vertical frame)
//   title, kicker, at { beat: 0 }, every 1, icon 'spark', iconColor 'accent', size 44 (card title)
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { spring } from '../../engine/motion';
import { clamp, ease, lerp, prog } from '../../engine/util';
import * as fx from './fx';
import { family, layLine, metrics, setToMeasure, type LaidLine } from './layout';
import { drawMark, type MarkKind } from './marks';

export type ListItem = string | { text: string; icon?: MarkKind; desc?: string };
export type FeatureItem = { title: string; desc?: string; icon?: MarkKind };

/** A heading: a mono kicker and a display title (balanced over lines), rising word by word from `at`. */
export class Heading {
  kicker: LaidLine | null;
  lines: LaidLine[];
  height: number;
  private kGap: number;

  constructor(title: string, kicker: string, size: number, maxW: number) {
    const fam = family({ role: 'display', width: 87.5, weight: 800 });
    const set = title ? setToMeasure(title, fam, size, maxW, { tracking: -0.02 }) : { lines: [], size };
    this.lines = set.lines.map((t) => layLine(t, fam, set.size, -0.02 * set.size));
    const ks = Math.max(20, 0.24 * set.size);
    this.kicker = kicker ? layLine(kicker.toUpperCase(), family({ role: 'mono', weight: 500 }), ks, 0.22 * ks) : null;
    this.kGap = 0.5 * set.size;
    const m = metrics(fam);
    this.height = (this.kicker ? this.kicker.m.cap * ks + this.kGap : 0) + (this.lines.length ? m.cap * set.size + (this.lines.length - 1) * 1.02 * set.size : 0);
  }

  /** Draw with its top at y, centred on cx (or left at x when `left`). */
  draw(c: CanvasRenderingContext2D, cx: number, top: number, t: number, at: number, left = false) {
    let y = top;
    const x = (l: LaidLine) => (left ? cx : cx - l.width / 2);
    if (this.kicker) {
      y += this.kicker.m.cap * this.kicker.size;
      const k = this.kicker;
      const shown = Array.from(fx.scrambleText(k.text, t, at, { seed: 5, per: 0.025 }));
      c.font = font(k.family, k.size);
      shown.forEach((ch, i) => {
        const g = k.glyphs[i];
        if (!g || /\s/u.test(ch)) return;
        c.fillStyle = rgba(ch === g.ch ? 'accent' : 'fgDim', ch === g.ch ? 1 : 0.6);
        c.fillText(ch, x(k) + g.x + (g.w - c.measureText(ch).width) / 2, y);
      });
      y += this.kGap;
    }
    this.lines.forEach((l, li) => {
      y += li === 0 ? l.m.cap * l.size : 1.02 * l.size;
      c.save();
      c.beginPath();
      c.rect(0, y - (l.m.cap + 0.3) * l.size, W, (l.m.cap + l.m.desc + 0.4) * l.size);
      c.clip();
      c.font = font(l.family, l.size);
      c.fillStyle = rgba('fg');
      c.letterSpacing = `${-0.02 * l.size}px`;
      l.words.forEach((w, wi) => {
        const st = fx.revealState('rise', t, at + 0.12 + (li * 3 + wi) * 0.07);
        if (st.alpha <= 0.002) return;
        c.globalAlpha = st.alpha;
        c.fillText(w.w, x(l) + w.x0, y + st.dy * l.size);
      });
      c.restore();
    });
  }
}

/** Times on the grid: the first at `first` (a TimeRef), then `every` beats apart. */
function beatTimes(n: number, first: number, every: number, grid: fx.Grid) {
  return fx.staggerTimes(n, first, { every, grid });
}

export class BulletList extends Scene2D {
  private head: Heading | null = null;
  private rows: { lines: LaidLine[]; desc: LaidLine[]; icon: MarkKind; y: number; at: number }[] = [];
  private x0 = 0;
  private top = 0;
  private headAt = 0;
  private size = 0;

  override init() {
    const u = this.u, tall = isTall();
    const items = this.need<ListItem[]>('items').map((it) => (typeof it === 'string' ? { text: it } : it));
    const size = (this.size = this.p('size', tall ? 56 : 58) * u);
    const maxW = this.p('maxWidth', tall ? 0.84 : 0.7) * W;
    const fam = family({ role: this.p('role', 'display'), width: this.p('width', 100), weight: this.p('weight', 600) });
    const dfam = family({ role: 'ui', weight: 400 });
    const indent = 1.05 * size;
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 84 : 92) * u, maxW) : null;
    const { audio } = this.ctx, start = this.ctx.start;
    this.headAt = start + 0.1;
    const first = fx.resolveTime(this.p<fx.TimeRef>('at', this.head ? { beat: 2 } : { beat: 0 }), start, audio);
    const times = beatTimes(items.length, first, this.p('every', 1), audio);
    let y = 0, widest = 0;
    this.rows = items.map((it, i) => {
      const set = setToMeasure(it.text, fam, size, maxW - indent, { tracking: -0.01 });
      const lines = set.lines.map((t) => layLine(t, fam, set.size, -0.01 * set.size));
      const desc = it.desc ? setToMeasure(it.desc, dfam, 0.5 * size, maxW - indent, {}).lines.map((t) => layLine(t, dfam, 0.5 * size, 0)) : [];
      widest = Math.max(widest, ...lines.map((l) => l.width + indent), ...desc.map((l) => l.width + indent));
      if (i > 0) y += 0.62 * size;
      const rowTop = y;
      y += lines[0]!.m.cap * set.size + (lines.length - 1) * 1.12 * set.size + desc.length * 0.5 * size * 1.45;
      return { lines, desc, icon: it.icon ?? this.p<MarkKind>('icon', 'check'), y: rowTop, at: times[i]! };
    });
    const headH = this.head ? this.head.height + 0.9 * size : 0;
    const h = headH + y;
    this.top = this.p('y', 0.5) * H - h / 2;
    this.x0 = this.p('x', 0.5) * W - widest / 2;
    for (const r of this.rows) r.y += this.top + headH;
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, size = this.size;
    const indent = 1.05 * size, iconColor = this.p('iconColor', 'accent');
    if (this.head) this.head.draw(c, this.x0, this.top, t, this.headAt, true);
    const g = this.glowLevel > 0 ? this.glow : null;
    const focus = this.p('focus', false);
    this.rows.forEach((r, i) => {
      const next = this.rows[i + 1];
      const dim = focus && next ? lerp(1, 0.45, prog(t, next.at, next.at + 0.3, ease.outCubic)) : 1;
      const l0 = r.lines[0]!, cap = l0.m.cap * l0.size;
      const iy = r.y + cap / 2;
      // the mark writes itself in, landing on the beat
      const k = prog(t, r.at - 0.08, r.at + 0.22, ease.outCubic);
      const pop = 1 + 0.18 * Math.max(0, Math.sin(Math.PI * prog(t, r.at - 0.04, r.at + 0.2)));
      drawMark(c, r.icon, this.x0 + 0.36 * size, iy, 0.62 * size * pop, k, rgba(iconColor, dim));
      if (g) drawMark(g, r.icon, this.x0 + 0.36 * size, iy, 0.62 * size * pop, k, glowInk(iconColor, 0.55 * dim * (0.6 + 0.4 * fx.emphasisGlow(t, r.at))));
      // the text rises behind its line's mask
      r.lines.forEach((l, li) => {
        const y = r.y + l0.m.cap * l0.size + li * 1.12 * l.size;
        const st = fx.revealState('rise', t, r.at + 0.05 + li * 0.06);
        if (st.alpha <= 0.002) return;
        c.save();
        c.beginPath();
        c.rect(0, y - (l.m.cap + 0.3) * l.size, W, (l.m.cap + l.m.desc + 0.4) * l.size);
        c.clip();
        c.font = font(l.family, l.size);
        c.letterSpacing = `${l.track}px`;
        c.globalAlpha = st.alpha * dim;
        c.fillStyle = rgba('fg');
        c.fillText(l.text, this.x0 + indent, y + st.dy * l.size);
        c.restore();
      });
      r.desc.forEach((l, di) => {
        const y = r.y + l0.m.cap * l0.size + (r.lines.length - 1) * 1.12 * l0.size + (di + 1) * 0.5 * size * 1.45;
        const st = fx.revealState('fade', t, r.at + 0.2 + di * 0.05);
        if (st.alpha <= 0.002) return;
        c.save();
        c.font = font(l.family, l.size);
        c.globalAlpha = st.alpha * dim;
        c.fillStyle = rgba('fgDim');
        c.fillText(l.text, this.x0 + indent, y + st.dy * l.size);
        c.restore();
      });
    });
  }
}

export class FeatureList extends Scene2D {
  private head: Heading | null = null;
  private cards: { x: number; y: number; w: number; h: number; title: LaidLine[]; desc: LaidLine[]; icon: MarkKind; at: number }[] = [];
  private top = 0;
  private headAt = 0;
  private size = 0;

  override init() {
    const u = this.u, tall = isTall();
    const items = this.need<FeatureItem[]>('items');
    const n = items.length;
    const cols = this.p('columns', tall ? 1 : n === 4 ? 2 : Math.min(3, n));
    const rows = Math.ceil(n / cols);
    const size = (this.size = this.p('size', tall ? 44 : 44) * u);
    const gap = 28 * u, pad = 0.9 * size;
    const totalW = this.p('maxWidth', tall ? 0.86 : cols === 2 ? 0.66 : 0.84) * W;
    const cw = (totalW - (cols - 1) * gap) / cols;
    const tfam = family({ role: 'display', width: 100, weight: 700 }), dfam = family({ role: 'ui', weight: 400 });
    const dsize = Math.max(24 * u, 0.6 * size);
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 80 : 84) * u, totalW) : null;
    const { audio } = this.ctx, start = this.ctx.start;
    this.headAt = start + 0.1;
    const first = fx.resolveTime(this.p<fx.TimeRef>('at', this.head ? { beat: 2 } : { beat: 0 }), start, audio);
    const times = beatTimes(n, first, this.p('every', 1), audio);
    const inner = cw - 2 * pad;
    const laid = items.map((it) => ({
      title: setToMeasure(it.title, tfam, size, inner, { tracking: -0.01 }).lines.map((t) => layLine(t, tfam, size, -0.01 * size)),
      desc: it.desc ? setToMeasure(it.desc, dfam, dsize, inner, { fit: 'none' }).lines.map((t) => layLine(t, dfam, dsize, 0)) : [],
    }));
    const iconBox = 1.5 * size;
    const ch = Math.max(...laid.map((l) => pad + iconBox + 1.15 * size + l.title.length * 1.15 * size + (l.desc.length ? 0.35 * size + l.desc.length * 1.4 * dsize : 0) + pad * 0.8));
    const gridH = rows * ch + (rows - 1) * gap;
    const headH = this.head ? this.head.height + 1.1 * size : 0;
    this.top = this.p('y', 0.5) * H - (headH + gridH) / 2;
    const x0 = this.p('x', 0.5) * W - totalW / 2;
    this.cards = items.map((it, i) => {
      const r = Math.floor(i / cols), col = i % cols;
      // a last row with fewer cards is centred
      const inRow = Math.min(cols, n - r * cols);
      const rowX = x0 + ((cols - inRow) * (cw + gap)) / 2;
      return { x: rowX + col * (cw + gap), y: this.top + headH + r * (ch + gap), w: cw, h: ch, title: laid[i]!.title, desc: laid[i]!.desc, icon: it.icon ?? this.p<MarkKind>('icon', 'spark'), at: times[i]! };
    });
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, size = this.size, u = this.u;
    if (this.head) this.head.draw(c, W / 2, this.top, t, this.headAt);
    const g = this.glowLevel > 0 ? this.glow : null;
    const iconColor = this.p('iconColor', 'accent');
    const pad = 0.9 * size, iconBox = 1.5 * size;
    for (const cd of this.cards) {
      const k = spring(t - (cd.at - 0.12), 4, 0.72);
      if (k <= 0) continue;
      const a = clamp(k * 1.6);
      c.save();
      c.globalAlpha = a;
      c.translate(0, (1 - k) * 0.6 * size);
      // the card: a surface with a hairline edge, lit along its top as it lands
      c.fillStyle = rgba('surface', 0.88);
      c.strokeStyle = rgba('ruleStrong');
      c.lineWidth = Math.max(1, 1.25 * u);
      c.beginPath();
      c.roundRect(cd.x, cd.y, cd.w, cd.h, 0.45 * size);
      c.fill();
      c.stroke();
      const sweep = prog(t, cd.at, cd.at + 0.6, ease.outCubic);
      if (sweep > 0 && sweep < 1) {
        const grad = c.createLinearGradient(cd.x, 0, cd.x + cd.w, 0);
        const s = sweep;
        grad.addColorStop(Math.max(0, s - 0.25), rgba(iconColor, 0));
        grad.addColorStop(s, rgba(iconColor, 0.9));
        grad.addColorStop(Math.min(1, s + 0.01), rgba(iconColor, 0));
        c.strokeStyle = grad;
        c.lineWidth = Math.max(1.5, 2 * u);
        c.beginPath();
        c.roundRect(cd.x, cd.y, cd.w, cd.h, 0.45 * size);
        c.stroke();
      }
      // the icon in its tinted well
      const ix = cd.x + pad, iy = cd.y + pad;
      c.fillStyle = rgba(iconColor, 0.14);
      c.beginPath();
      c.roundRect(ix, iy, iconBox, iconBox, 0.3 * size);
      c.fill();
      const mk = prog(t, cd.at, cd.at + 0.3, ease.outCubic);
      drawMark(c, cd.icon, ix + iconBox / 2, iy + iconBox / 2, 0.7 * iconBox, mk, rgba(iconColor));
      let y = iy + iconBox + 1.15 * size;
      c.fillStyle = rgba('fg');
      for (const l of cd.title) {
        c.font = font(l.family, l.size);
        c.letterSpacing = `${l.track}px`;
        c.fillText(l.text, cd.x + pad, y);
        y += 1.15 * l.size;
      }
      c.letterSpacing = '0px';
      if (cd.desc.length) {
        y += 0.35 * size - 0.15 * size;
        c.fillStyle = rgba('fgDim');
        for (const l of cd.desc) {
          c.font = font(l.family, l.size);
          c.fillText(l.text, cd.x + pad, y);
          y += 1.4 * l.size;
        }
      }
      c.restore();
      if (g) {
        g.save();
        g.globalAlpha = a;
        g.translate(0, (1 - k) * 0.6 * size);
        drawMark(g, cd.icon, ix + iconBox / 2, iy + iconBox / 2, 0.7 * iconBox, mk, glowInk(iconColor, 0.5 * (0.5 + 0.5 * fx.emphasisGlow(t, cd.at))));
        g.restore();
      }
    }
  }
}

export default BulletList;
