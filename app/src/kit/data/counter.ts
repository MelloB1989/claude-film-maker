// Counter: a big number that rolls, flips or counts to its value and lands on a beat, with a label under it.
//
// Params:
//   value (required)   the number it lands on; from 0; decimals (default: as many as value has); sep ',', point '.'
//   prefix, suffix     marks before and after ('$', '%', '×', 'ms'): smaller, top-aligned, in affixColor 'accent'
//   style 'roll'       'roll' (odometer drums) | 'flip' (split-flap tiles) | 'count' (counts up, eased)
//   land { beat: 4 }   when it lands (s after the shot start, { beat }, { bar }); dur (s of rolling or counting)
//   size               reference px (300; 240 vertical), shrunk to fit 0.88 W; role 'display', width 87.5, weight 800
//   color 'fg', affixColor 'accent', affixScale 0.58, flare true (the digits flash in the accent as they land)
//   label              a mono line under it (labelColor 'fgDim'); kicker: a mono line above (kickerColor 'accent')
//   x 0.5, y 0.5       the anchor (fractions of the frame); push 0.02 (a slow scale over the shot)
//   background, glow, exit (Scene2D)
import { Scene2D, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { clamp, ease, lerp, prog, pulse } from '../../engine/util';
import * as fx from '../text/fx';
import { family, layLine, type LaidLine } from '../text/layout';
import { Figure, type FigureStyle } from './figure';
import { decimalsOf, type CountEase } from './num';

/** A mono label line (a counter's, a stat's): uppercase, tracked, scrambling in at `at`. */
export function drawLabel(c: CanvasRenderingContext2D, l: LaidLine, x: number, y: number, t: number, at: number, color: string, alpha = 1, seed = 3) {
  const shown = fx.scrambleText(l.text, t, at, { seed, per: 0.022 });
  if (!shown) return;
  c.save();
  c.font = font(l.family, l.size);
  c.globalAlpha *= alpha * prog(t, at - fx.SCRAMBLE.churn, at - fx.SCRAMBLE.churn + 0.1);
  const chars = Array.from(shown);
  chars.forEach((ch, i) => {
    const g = l.glyphs[i];
    if (!g || /\s/u.test(ch)) return;
    c.fillStyle = ch === g.ch ? rgba(color) : rgba(color, 0.5);
    c.fillText(ch, x + g.x + (g.w - c.measureText(ch).width) / 2, y);
  });
  c.restore();
}

/** A mono label laid out: uppercase, tracked 0.22 em. */
export function layLabel(text: string, size: number): LaidLine {
  return layLine(text.toUpperCase(), family({ role: 'mono', weight: 500 }), size, 0.22 * size);
}

export class Counter extends Scene2D {
  private fig!: Figure;
  private label: LaidLine | null = null;
  private kicker: LaidLine | null = null;
  private land = 0;
  private x = 0;
  private y = 0;

  override init() {
    const u = this.u, tall = isTall();
    const value = this.need<number>('value');
    const style = this.p<FigureStyle>('style', 'roll');
    const fam = family({ role: this.p('role', 'display'), width: this.p('width', 87.5), weight: this.p('weight', 800) });
    let size = this.p('size', tall ? 240 : 300) * u;
    const spec = {
      value, from: this.p('from', 0), decimals: this.p('decimals', decimalsOf(value)),
      prefix: this.p('prefix', ''), suffix: this.p('suffix', ''), sep: this.p('sep', ','), point: this.p('point', '.'),
    };
    const maxW = this.p('maxWidth', 0.88) * W;
    let fig = new Figure(spec, fam, size, this.p('affixScale', 0.58), style === 'flip');
    if (fig.width > maxW) {
      size *= maxW / fig.width;
      fig = new Figure(spec, fam, size, this.p('affixScale', 0.58), style === 'flip');
    }
    this.fig = fig;
    const ls = clamp(0.1 * size, 22 * u, 34 * u);
    const label = this.p('label', ''), kicker = this.p('kicker', '');
    this.label = label ? layLabel(label, ls) : null;
    this.kicker = kicker ? layLabel(kicker, ls) : null;
    this.land = fx.resolveTime(this.p<fx.TimeRef>('land', { beat: 4 }), this.ctx.start, this.ctx.audio);
    // the block: kicker, the figure's cap height, the label
    const cap = fig.m.cap * size, gap = Math.max(26 * u, 0.2 * size) + (style === 'flip' ? 0.31 * cap : 0);
    const top = (this.kicker ? this.kicker.m.cap * ls + gap : 0);
    const h = top + cap + (this.label ? gap + this.label.m.cap * ls : 0);
    const y0 = this.p('y', 0.5) * H - h / 2;
    this.x = this.p('x', 0.5) * W;
    this.y = y0 + top + cap; // the figure's baseline
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, fig = this.fig, u = this.u;
    const style = this.p<FigureStyle>('style', 'roll');
    const push = 1 + this.p('push', 0.02) * f.p;
    const pop = 1 + 0.035 * pulse(t, this.land, 0.12) * (t >= this.land ? 1 : 0);
    const g = this.glowLevel > 0 ? this.glow : null;
    for (const ctx of g ? [c, g] : [c]) {
      ctx.translate(this.x, this.y - fig.m.cap * fig.size / 2);
      ctx.scale(push * pop, push * pop);
      ctx.translate(-this.x, -(this.y - fig.m.cap * fig.size / 2));
    }
    // the figure comes up out of the dark as it starts to move
    const dur = this.p('dur', style === 'count' ? 1.4 : 1.6);
    const start = style === 'flip' ? this.land - 1.2 : this.land - dur;
    const inK = prog(t, Math.min(start, this.ctx.start + 0.05), Math.min(start, this.ctx.start + 0.05) + 0.3, ease.outCubic);
    c.globalAlpha = inK;
    const flare = this.p('flare', true) ? (t >= this.land ? 0.4 * pulse(t, this.land, 0.12) : 0) : 0;
    fig.draw(c, g, this.x - fig.width / 2, this.y + lerp(0.06, 0, inK) * fig.size, t, {
      style, land: this.land, dur, stagger: this.p('stagger', style === 'flip' ? 0.06 : 0.07), ease: this.p<CountEase>('ease', 'outExpo'), seed: this.p('seed', 1),
    }, { color: this.p('color', 'fg'), affixColor: this.p('affixColor', 'accent'), flare, affixGlow: 0.3 * inK });
    c.globalAlpha = 1;
    // (a board's tiles stand taller than the digits' caps)
    const gap = Math.max(26 * u, 0.2 * fig.size) + (style === 'flip' ? 0.31 * fig.m.cap * fig.size : 0);
    const at = this.ctx.start + 0.15;
    if (this.kicker) drawLabel(c, this.kicker, this.x - this.kicker.width / 2, this.y - fig.m.cap * fig.size - gap, t, at, this.p('kickerColor', 'accent'));
    if (this.label) drawLabel(c, this.label, this.x - this.label.width / 2, this.y + gap + this.label.m.cap * this.label.size, t, at + 0.1, this.p('labelColor', 'fgDim'));
  }
}

export default Counter;
