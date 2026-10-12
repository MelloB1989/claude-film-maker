// LowerThird: a name and a title in the lower third. An accent rule grows, a translucent plate wipes out from it, the
// name slides out from behind the rule and the title rises under it; at the shot's end it all folds back into the rule.
// Transparent by default (it goes over footage or another block: as an overlay, or stacked).
//
// Params:
//   name (required), title     the two lines (title in mono, uppercase, tracked)
//   side 'left'                'left' | 'right'; x, y override the anchor (fractions: the rule's foot)
//   at 0.2                     when it starts (TimeRef); out true (folds away over the last 0.45 s)
//   color 'accent'             the rule's colour; plate true (a translucent surface behind the text)
//   size 58                    the name (reference px); background 'none'
import { Scene2D, glowInk, isTall, safeRect, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { spring } from '../../engine/motion';
import { clamp, ease, prog } from '../../engine/util';
import * as fx from './fx';
import { family, layLine, type LaidLine } from './layout';

export class LowerThird extends Scene2D {
  protected override defaultBackground: Background = 'none';
  private name!: LaidLine;
  private title: LaidLine | null = null;
  private at = 0;
  private foot = { x: 0, y: 0 };

  override init() {
    const u = this.u, tall = isTall();
    const size = this.p('size', tall ? 60 : 58) * u;
    this.name = layLine(this.need<string>('name'), family({ role: 'display', width: 100, weight: 700 }), size, -0.01 * size);
    const title = this.p<string>('title', '');
    const ts = Math.max(20 * u, 0.36 * size);
    this.title = title ? layLine(title.toUpperCase(), family({ role: 'mono', weight: 500 }), ts, 0.2 * ts) : null;
    this.at = fx.resolveTime(this.p<fx.TimeRef>('at', 0.2), this.ctx.start, this.ctx.audio);
    const safe = safeRect(tall ? 'social' : 'title');
    const right = this.p<'left' | 'right'>('side', 'left') === 'right';
    this.foot = {
      x: this.p<number | null>('x', null) !== null ? this.p('x', 0) * W : right ? safe.x1 : safe.x0 + 0.02 * W,
      y: this.p<number | null>('y', null) !== null ? this.p('y', 0) * H : tall ? safe.y1 - 0.02 * H : 0.84 * H,
    };
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t, u = this.u, N = this.name, T = this.title;
    const right = this.p<'left' | 'right'>('side', 'left') === 'right';
    const color = this.p('color', 'accent');
    // in: rule, plate, name, title; out: the same, folding back, over the shot's last 0.45 s
    const out = this.p('out', true) ? prog(t, this.ctx.end - 0.45, this.ctx.end - 0.05, ease.inCubic) : 0;
    const rule = Math.min(spring(t - this.at, 5, 0.75), 1 - prog(out, 0.6, 1));
    if (rule <= 0.001) return;
    const plate = Math.min(prog(t, this.at + 0.12, this.at + 0.55, ease.outExpo), 1 - prog(out, 0.25, 0.8));
    const nameK = Math.min(spring(t - (this.at + 0.18), 4, 0.8), 1 - prog(out, 0, 0.55));
    const titleK = Math.min(spring(t - (this.at + 0.32), 4, 0.8), 1 - prog(out, 0, 0.45));
    const padX = 0.5 * N.size, gap = 0.42 * N.size;
    const nameCap = N.m.cap * N.size;
    const tCap = T ? T.m.cap * T.size : 0;
    const h = nameCap + (T ? gap + tCap : 0) + 0.7 * N.size;
    const w = Math.max(N.width, T?.width ?? 0) + 2 * padX;
    const { x, y } = this.foot; // the rule's foot (bottom), the side it stands on
    const top = y - h;
    const rw = Math.max(3, 5 * u);
    // the plate wipes out from the rule
    if (this.p('plate', true) && plate > 0) {
      c.save();
      c.fillStyle = rgba('surface', 0.82);
      const pw = w * plate;
      c.beginPath();
      c.rect(right ? x - rw / 2 - pw : x + rw / 2, top, pw, h);
      c.fill();
      c.restore();
    }
    // the text, clipped to the plate's side of the rule
    c.save();
    c.beginPath();
    c.rect(right ? x - rw / 2 - w : x + rw / 2, top - 0.5 * N.size, w, h + N.size);
    c.clip();
    const tx = (lw: number, k: number) => (right ? x - rw / 2 - padX - lw + (1 - k) * (lw + padX) : x + rw / 2 + padX - (1 - k) * (lw + padX));
    const ny = top + 0.35 * N.size + nameCap;
    if (nameK > 0) {
      c.font = font(N.family, N.size);
      c.letterSpacing = `${N.track}px`;
      c.fillStyle = rgba('fg');
      c.fillText(N.text, tx(N.width, clamp(nameK)), ny);
      c.letterSpacing = '0px';
    }
    if (T && titleK > 0) {
      c.font = font(T.family, T.size);
      c.letterSpacing = `${T.track}px`;
      c.fillStyle = rgba('fgDim');
      c.globalAlpha = clamp(titleK);
      c.fillText(T.text, tx(T.width, 1), ny + gap + tCap + (1 - clamp(titleK)) * 0.6 * T.size);
      c.letterSpacing = '0px';
    }
    c.restore();
    // the rule, growing up from its foot
    const rh = h * clamp(rule);
    c.fillStyle = rgba(color);
    c.fillRect(x - rw / 2, y - rh, rw, rh);
    const g = this.glowLevel > 0 ? this.glow : null;
    if (g) {
      g.fillStyle = glowInk(color, 0.75);
      g.fillRect(x - rw / 2, y - rh, rw, rh);
    }
  }
}

export default LowerThird;
