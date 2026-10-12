// Compare: before → after. The old figure lands, an arrow writes itself toward the new one, the new figure counts up
// from the old and lands on its beat in the accent while the old one is struck through, and a delta badge pops in
// (accent2) under it: "44% → 91.4%  +47.4 pts".
//
// Params:
//   from, to (required)  numbers or { value, label }
//   prefix, suffix, decimals (default: the values')
//   delta 'auto'         'auto' (points for a %, else the difference), 'diff' | 'ratio' | 'percent', a string, or false;
//                        deltaUnit (' pts' for a % by default)
//   at { beat: 0 }       the old figure lands; arrowAt { beat: 2 }; land { beat: 4 } (the new one lands)
//   size                 the new figure (reference px, 230; the old is 0.55 of it); title, kicker; x 0.5, y 0.5
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { spring } from '../../engine/motion';
import { clamp, ease, lerp, prog, pulse } from '../../engine/util';
import * as fx from '../text/fx';
import { Heading } from '../text/list';
import { family, type LaidLine } from '../text/layout';
import { drawMark } from '../text/marks';
import { Figure } from './figure';
import { decimalsOf, deltaText } from './num';
import { drawLabel, layLabel } from './counter';

type Side = number | { value: number; label?: string };

export class Compare extends Scene2D {
  private a!: { fig: Figure; label: LaidLine | null; x: number; y: number };
  private b!: { fig: Figure; label: LaidLine | null; x: number; y: number };
  private arrow = { x0: 0, y0: 0, x1: 0, y1: 0 };
  private delta = { text: '', x: 0, y: 0, fs: 0, fam: '' };
  private head: Heading | null = null;
  private headTop = 0;
  private times = { a: 0, arrow: 0, b: 0 };

  override init() {
    const u = this.u, tall = isTall();
    const side = (s: Side) => (typeof s === 'number' ? { value: s, label: '' } : { label: '', ...s });
    const A = side(this.need<Side>('from')), B = side(this.need<Side>('to'));
    const pre = this.p<string>('prefix', ''), suf = this.p<string>('suffix', '');
    const fam = family({ role: 'display', width: 87.5, weight: 800 });
    let size = this.p('size', tall ? 210 : 230) * u;
    // each figure as written (44% → 91.4%), unless decimals are given
    const make = (v: number, s: number) => new Figure({ value: v, from: v === B.value ? A.value : 0, decimals: this.p('decimals', decimalsOf(v)), prefix: pre, suffix: suf }, fam, s, 0.55);
    let fa = make(A.value, 0.55 * size), fb = make(B.value, size);
    const gapX = 1.6 * (0.55 * size);
    const room = tall ? 0.86 * W : 0.86 * W;
    const need = tall ? Math.max(fa.width, fb.width) : fa.width + gapX + fb.width;
    if (need > room) {
      size *= room / need;
      fa = make(A.value, 0.55 * size);
      fb = make(B.value, size);
    }
    const ls = Math.max(18 * u, Math.min(26 * u, 0.12 * size));
    const la = A.label ? layLabel(A.label, ls) : null, lb = B.label ? layLabel(B.label, ls) : null;
    // the delta
    const dk = this.p<'auto' | 'diff' | 'ratio' | 'percent' | string | false>('delta', 'auto');
    const kind = dk === 'auto' ? 'diff' : dk;
    const text = dk === false ? '' : kind === 'diff' || kind === 'ratio' || kind === 'percent' ? deltaText(A.value, B.value, kind, { unit: this.p('deltaUnit', suf === '%' ? ' pts' : suf) }) : String(dk);
    const dfs = Math.max(30 * u, 0.2 * size);
    const capB = fb.m.cap * size, capA = fa.m.cap * fa.size;
    const title = this.p('title', ''), kicker = this.p('kicker', '');
    this.head = title || kicker ? new Heading(title, kicker, this.p('titleSize', tall ? 66 : 70) * u, room) : null;
    const headH = this.head ? this.head.height + 90 * u : 0;
    const labelH = 2.2 * ls;
    const cx = this.p('x', 0.5) * W;
    if (tall) {
      // stacked: old, arrow down, new, delta
      const arrowH = 1.0 * size;
      const h = headH + capA + labelH + arrowH + capB + labelH + (text ? 2.4 * dfs : 0);
      const top = this.p('y', 0.5) * H - h / 2;
      this.headTop = top;
      const ya = top + headH + capA;
      const yb = ya + labelH + arrowH + capB;
      this.a = { fig: fa, label: la, x: cx - fa.width / 2, y: ya };
      this.b = { fig: fb, label: lb, x: cx - fb.width / 2, y: yb };
      this.arrow = { x0: cx, y0: ya + labelH + 0.2 * arrowH, x1: cx, y1: ya + labelH + 0.8 * arrowH };
      this.delta = { text, x: cx, y: yb + labelH + 1.6 * dfs, fs: dfs, fam: family({ role: 'display', width: 100, weight: 700 }) };
    } else {
      const w = fa.width + gapX + fb.width;
      const h = headH + capB + labelH + (text ? 2.4 * dfs : 0);
      const top = this.p('y', 0.5) * H - h / 2;
      this.headTop = top;
      const yb = top + headH + capB;
      const x0 = cx - w / 2;
      this.a = { fig: fa, label: la, x: x0, y: yb };
      this.b = { fig: fb, label: lb, x: x0 + fa.width + gapX, y: yb };
      const ay = yb - capA / 2;
      this.arrow = { x0: x0 + fa.width + 0.3 * gapX, y0: ay, x1: x0 + fa.width + 0.7 * gapX, y1: ay };
      this.delta = { text, x: this.b.x + fb.width / 2, y: yb + labelH + 1.5 * dfs, fs: dfs, fam: family({ role: 'display', width: 100, weight: 700 }) };
    }
    const { audio, start } = this.ctx;
    const r = (ref: fx.TimeRef) => fx.resolveTime(ref, start, audio);
    this.times = { a: r(this.p<fx.TimeRef>('at', this.head ? { beat: 1 } : { beat: 0 })), arrow: r(this.p<fx.TimeRef>('arrowAt', { beat: 2 })), b: r(this.p<fx.TimeRef>('land', { beat: 4 })) };
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, u = this.u;
    const g = this.glowLevel > 0 ? this.glow : null;
    if (this.head) this.head.draw(c, W / 2, this.headTop, t, this.ctx.start + 0.1);
    const T = this.times;
    // the old figure: counts in quickly, then dims and is struck through as the new one lands
    const A = this.a, B = this.b;
    const aIn = prog(t, T.a - 0.5, T.a - 0.2, ease.outCubic);
    const strike = fx.sweep(t, T.b - 0.05, 0.3);
    if (aIn > 0) {
      c.save();
      c.globalAlpha = aIn * lerp(1, 0.55, strike);
      A.fig.draw(c, null, A.x, A.y, t, { style: 'count', land: T.a, dur: 0.5, ease: 'outCubic' }, { color: 'fgDim', affixColor: 'fgDim' });
      c.restore();
      if (A.label) drawLabel(c, A.label, A.x + A.fig.width / 2 - A.label.width / 2, A.y + 0.62 * A.label.size + 1.1 * A.label.size, t, T.a - 0.3, 'fgFaint', aIn);
      if (strike > 0) {
        const sy = A.y - A.fig.m.cap * A.fig.size * 0.45, th = Math.max(3 * u, 0.05 * A.fig.size);
        c.fillStyle = rgba('accent');
        c.fillRect(A.x - 0.05 * A.fig.size, sy - th / 2, (A.fig.width + 0.1 * A.fig.size) * strike, th);
      }
    }
    // the arrow writes itself toward the new figure
    const ak = prog(t, T.arrow - 0.1, T.arrow + 0.25, ease.outCubic);
    if (ak > 0) {
      const R = this.arrow, len = Math.hypot(R.x1 - R.x0, R.y1 - R.y0);
      const mx = (R.x0 + R.x1) / 2, my = (R.y0 + R.y1) / 2;
      for (const ctx of g ? [c, g] : [c]) {
        ctx.save();
        ctx.translate(mx, my);
        ctx.rotate(Math.atan2(R.y1 - R.y0, R.x1 - R.x0));
        drawMark(ctx, 'arrow', 0, 0, len, ak, ctx === c ? rgba('accent') : glowInk('accent', 0.6), 0.07);
        ctx.restore();
      }
    }
    // the new figure counts up from the old and lands, in the accent
    const bIn = prog(t, T.b - 1.3, T.b - 1.0, ease.outCubic);
    if (bIn > 0) {
      c.save();
      c.globalAlpha = bIn;
      const flare = t >= T.b ? 0.5 * pulse(t, T.b, 0.16) : 0;
      B.fig.draw(c, g, B.x, B.y, t, { style: 'count', land: T.b, dur: 1.2, ease: 'outExpo' }, { flare, affixGlow: 0.35 });
      c.restore();
      if (B.label) drawLabel(c, B.label, B.x + B.fig.width / 2 - B.label.width / 2, B.y + 0.62 * B.label.size + 1.1 * B.label.size, t, T.b - 1.0, 'fgDim', bIn);
    }
    // the delta badge
    const D = this.delta;
    if (D.text && t >= T.b + 0.15) {
      const k = spring(t - (T.b + 0.15), 5, 0.62);
      c.font = font(D.fam, D.fs);
      const w = c.measureText(D.text).width + 1.1 * D.fs, h = 1.7 * D.fs;
      for (const ctx of g ? [c, g] : [c]) {
        ctx.save();
        ctx.globalAlpha = clamp(k * 2);
        ctx.translate(D.x, D.y - 0.35 * D.fs);
        ctx.scale(0.7 + 0.3 * k, 0.7 + 0.3 * k);
        ctx.fillStyle = ctx === c ? rgba('accent2', 0.16) : glowInk('accent2', 0.12);
        ctx.strokeStyle = ctx === c ? rgba('accent2', 0.7) : glowInk('accent2', 0.4);
        ctx.lineWidth = Math.max(1.5, 2 * u);
        ctx.beginPath();
        ctx.roundRect(-w / 2, -h / 2, w, h, h / 2);
        ctx.fill();
        ctx.stroke();
        if (ctx === c) {
          ctx.font = font(D.fam, D.fs);
          ctx.textAlign = 'center';
          ctx.fillStyle = rgba('accent2Bright');
          ctx.fillText(D.text, 0, 0.36 * D.fs);
        }
        ctx.restore();
      }
    }
  }
}

export default Compare;
