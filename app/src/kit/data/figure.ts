// A figure on a 2D layer: a formatted number set in tabular slots (every digit as wide as the widest, so nothing jitters
// as it counts), its prefix and suffix smaller and top-aligned in the accent, drawn one of three ways at a time t:
//   'roll'   an odometer: every digit a drum rolling up to its face, the rightmost spinning fastest, landing in turn
//   'flip'   a split-flap board: every digit a tile whose flaps fall through seeded digits onto its face
//   'count'  the value counting up (eased), the digits growing leftward from a fixed right edge
// Used by Counter, StatGrid and Compare.
import { rgba } from '../../engine/palette';
import { font, measure } from '../../engine/type';
import { clamp } from '../../engine/util';
import { glowInk } from '../scene2d';
import { metrics, type FaceMetrics } from '../text/layout';
import { columnsOf, countAt, drumAt, drumFace, flapColumn, formatNumber, type Column, type CountEase } from './num';

export type FigureStyle = 'roll' | 'flip' | 'count';

export interface FigureSpec {
  value: number;
  from?: number;
  decimals: number;
  prefix?: string;
  suffix?: string;
  sep?: string;
  point?: string;
}

export interface FigureTiming {
  style: FigureStyle;
  /** When it lands (film s), and how long it counts or rolls before. */
  land: number;
  dur: number;
  stagger?: number;
  ease?: CountEase;
  seed?: number;
}

export interface FigureInk {
  color?: string;
  affixColor?: string;
  /** 0..1: how much the digits glow (a landing flare). */
  flare?: number;
  /** 0..1: how much the prefix and suffix glow. */
  affixGlow?: number;
}

/** A placed column: where it sits (px from the figure's left), how wide, and whether it is a prefix or suffix mark. */
interface Placed { col: Column; x: number; w: number; affix: boolean }

export class Figure {
  readonly text: string;
  readonly width: number;
  readonly m: FaceMetrics;
  readonly slot: number;
  private cols: Placed[] = [];
  private digits: number;
  private affixSize: number;

  constructor(readonly spec: FigureSpec, readonly fam: string, readonly size: number, readonly affixScale = 0.58, readonly flipTiles = false) {
    const body = formatNumber(spec.value, spec.decimals, spec.sep ?? ',', spec.point ?? '.');
    const pre = spec.prefix ?? '', suf = spec.suffix ?? '';
    this.text = pre + body + suf;
    this.m = metrics(fam);
    this.affixSize = size * affixScale;
    // the widest digit, plus the tile's margin on a board
    this.slot = Math.max(...'0123456789'.split('').map((d) => measure(d, fam, size))) + (flipTiles ? 0.16 * size : 0);
    let x = 0;
    const place = (col: Column, affix: boolean) => {
      const w = col.kind === 'digit' ? this.slot : measure(col.ch, fam, affix ? this.affixSize : size) + (affix ? 0.04 * size : 0) + (flipTiles && !affix ? 0.06 * size : 0);
      this.cols.push({ col, x, w, affix });
      x += w;
    };
    for (const ch of Array.from(pre)) place({ kind: 'mark', ch }, true);
    for (const col of columnsOf(body)) place(col, false);
    for (const ch of Array.from(suf)) place({ kind: 'mark', ch }, true);
    this.width = x;
    this.digits = this.cols.filter((c) => c.col.kind === 'digit').length;
  }

  /** Draw at (x, baseline) at time t: `c` the layer, `g` its glow layer (or null). */
  draw(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D | null, x: number, y: number, t: number, tm: FigureTiming, ink: FigureInk = {}) {
    const color = ink.color ?? 'fg', affixColor = ink.affixColor ?? 'accent';
    c.save();
    c.textBaseline = 'alphabetic';
    // the affixes: smaller, their cap tops level with the digits'
    const capTop = y - this.m.cap * this.size;
    const affixY = capTop + this.m.cap * this.affixSize;
    for (const p of this.cols) {
      if (!p.affix || p.col.kind !== 'mark') continue;
      c.font = font(this.fam, this.affixSize);
      c.fillStyle = rgba(affixColor);
      c.fillText(p.col.ch, x + p.x + 0.02 * this.size, affixY);
      if (g && (ink.affixGlow ?? 0) > 0.003) {
        g.save();
        g.font = c.font;
        g.fillStyle = glowInk(affixColor, ink.affixGlow!);
        g.fillText(p.col.ch, x + p.x + 0.02 * this.size, affixY);
        g.restore();
      }
    }
    c.font = font(this.fam, this.size);
    if (tm.style === 'count') this.drawCount(c, x, y, t, tm, color);
    else {
      let i = 0;
      for (const p of this.cols) {
        if (p.affix) continue;
        if (p.col.kind === 'mark') {
          c.fillStyle = rgba(color);
          c.fillText(p.col.ch, x + p.x + (this.flipTiles ? 0.03 * this.size : 0), y);
          continue;
        }
        if (tm.style === 'roll') this.drawDrum(c, x + p.x, y, drumAt(t, p.col.d, i, this.digits, tm.land, { dur: tm.dur, stagger: tm.stagger }), color);
        else this.drawFlap(c, x + p.x, y, flapColumn(t, String(this.spec.from !== undefined ? digitAt(this.spec, i) : 0), String(p.col.d), i, this.digits, tm.land, { stagger: tm.stagger, seed: tm.seed }), color);
        i++;
      }
    }
    // the landing flare: the digits light in the accent and let go
    if (g && (ink.flare ?? 0) > 0.003) {
      g.save();
      g.font = font(this.fam, this.size);
      g.fillStyle = glowInk(affixColor, ink.flare!);
      for (const p of this.cols) {
        if (p.affix || p.col.kind !== 'digit') continue;
        g.fillText(String(p.col.d), x + p.x + (this.slot - measure(String(p.col.d), this.fam, this.size)) / 2, y);
      }
      g.restore();
    }
    c.restore();
  }

  /** A digit centred in its slot. */
  private digit(c: CanvasRenderingContext2D, d: string, x: number, y: number) {
    c.fillText(d, x + (this.slot - c.measureText(d).width) / 2, y);
  }

  private drawDrum(c: CanvasRenderingContext2D, x: number, y: number, pos: number, color: string) {
    const { a, b, f } = drumFace(pos);
    const cap = this.m.cap * this.size, pitch = cap * 1.42;
    c.save();
    c.beginPath();
    c.rect(x - 0.02 * this.size, y - cap - 0.16 * this.size, this.slot + 0.04 * this.size, cap + 0.32 * this.size);
    c.clip();
    for (const [d, off] of [[a, -f * pitch], [b, (1 - f) * pitch]] as const) {
      const k = 1 - clamp(Math.abs(off) / pitch);
      if (k <= 0.01) continue;
      c.fillStyle = rgba(color, Math.pow(k, 0.8));
      this.digit(c, String(d), x, y + off);
    }
    c.restore();
  }

  private drawFlap(c: CanvasRenderingContext2D, x: number, y: number, s: { a: string; b: string; p: number }, color: string) {
    const size = this.size, cap = this.m.cap * size;
    const tw = this.slot - 0.06 * size, th = cap * 1.62, tx = x + 0.03 * size, cy = y - cap / 2, ty = cy - th / 2;
    const r = 0.06 * size;
    const half = (d: string, which: 'top' | 'bottom', sy = 1, shade = 0) => {
      c.save();
      c.beginPath();
      if (which === 'top') c.rect(tx - 1, ty - 1, tw + 2, cy - ty + 1);
      else c.rect(tx - 1, cy, tw + 2, ty + th - cy + 1);
      c.clip();
      if (sy !== 1) {
        c.translate(0, cy);
        c.scale(1, Math.max(0.001, sy));
        c.translate(0, -cy);
      }
      const grad = c.createLinearGradient(0, ty, 0, ty + th);
      grad.addColorStop(0, rgba('surface2'));
      grad.addColorStop(0.5, rgba('surface'));
      grad.addColorStop(1, rgba('surface2'));
      c.fillStyle = grad;
      c.beginPath();
      c.roundRect(tx, ty, tw, th, r);
      c.fill();
      c.fillStyle = rgba(color);
      c.fillText(d, tx + (tw - c.measureText(d).width) / 2, y);
      if (shade > 0.003) {
        c.fillStyle = rgba('bg', shade);
        c.fillRect(tx, ty, tw, th);
      }
      c.restore();
    };
    const k = Math.cos(Math.PI * s.p);
    if (s.p <= 0 || s.a === s.b) {
      half(s.a, 'top');
      half(s.a, 'bottom');
    } else if (k > 0) {
      half(s.b, 'top');
      half(s.a, 'bottom');
      half(s.a, 'top', k, 0.55 * (1 - k));
    } else {
      half(s.b, 'top');
      half(s.a, 'bottom');
      half(s.b, 'bottom', -k, 0.55 * (1 + k));
    }
    // the hinge: a hairline gap across the tile
    c.fillStyle = rgba('bg', 0.85);
    c.fillRect(tx, cy - Math.max(1, 0.012 * size), tw, Math.max(2, 0.024 * size));
  }

  /** The count: the current value's digits right-aligned in the final figure's slots. */
  private drawCount(c: CanvasRenderingContext2D, x: number, y: number, t: number, tm: FigureTiming, color: string) {
    const v = countAt(t, this.spec.from ?? 0, this.spec.value, tm.land, tm.dur, tm.ease ?? 'outExpo');
    const now = columnsOf(formatNumber(v, this.spec.decimals, this.spec.sep ?? ',', this.spec.point ?? '.'));
    const body = this.cols.filter((p) => !p.affix);
    const right = body.length ? body[body.length - 1]!.x + body[body.length - 1]!.w : 0;
    // set from the right edge leftward: digits in slots, marks at their own advance
    let xr = right;
    c.fillStyle = rgba(color);
    for (let i = now.length - 1; i >= 0; i--) {
      const col = now[i]!;
      const w = col.kind === 'digit' ? this.slot : c.measureText(col.ch).width;
      xr -= w;
      if (col.kind === 'digit') this.digit(c, String(col.d), x + xr, y);
      else c.fillText(col.ch, x + xr, y);
    }
  }
}

/** The digit a figure counting from `from` shows in its i-th digit slot (right-aligned), for a board's first face. */
function digitAt(spec: FigureSpec, i: number): number {
  const fin = columnsOf(formatNumber(spec.value, spec.decimals)).filter((c) => c.kind === 'digit').length;
  const st = columnsOf(formatNumber(spec.from ?? 0, spec.decimals)).filter((c) => c.kind === 'digit') as { d: number }[];
  const j = i - (fin - st.length);
  return j >= 0 && j < st.length ? st[j]!.d : 0;
}
