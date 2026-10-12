// Quote: a pull quote. A big opening quote mark in the accent comes up and glows, the words land one by one (or on
// the voiceover), and the attribution follows under them.
//
// Params: quote (or text / lines) required; by (who said it), byline (their title); markColor 'accent'; and any
// KineticText param (size 78, weight 500, reveal 'fade', sync 'vo', emphasis, align: 'center' puts the mark above the
// quote, 'left' hangs it in the margin).
import type { Frame } from '../scene2d';
import { glowInk, isTall } from '../scene2d';
import { rgba } from '../../engine/palette';
import { font, smart } from '../../engine/type';
import { spring } from '../../engine/motion';
import { clamp } from '../../engine/util';
import { KineticText, type KineticParams, type LineSpec } from './kinetic';
import { family, inkBox } from './layout';

export class Quote extends KineticText {
  protected override defaults: Partial<KineticParams> = { size: 78, width: 100, weight: 500, tracking: -0.015, leading: 1.14, reveal: 'fade', unit: 'word', stagger: 0.055, subRole: 'mono', subColor: 'fgDim', push: 0.02, maxWidth: 0.64 };
  private qmark = { x: 0, y: 0, cy: 0, size: 0, fam: '', align: 'center' as CanvasTextAlign };

  protected override specs(): LineSpec[] {
    const q = (this.ctx.params.quote ?? this.ctx.params.text) as string | undefined;
    if (q !== undefined && this.ctx.params.lines === undefined) return smart(q).split('\n').map((text) => ({ text }));
    return super.specs();
  }

  override init() {
    if (isTall()) this.defaults = { ...this.defaults, maxWidth: 0.86 };
    const by = this.p<string>('by', ''), byline = this.p<string>('byline', '');
    if (by) this.defaults = { ...this.defaults, sub: `— ${by}${byline ? `, ${byline}` : ''}`, subSize: 28 };
    this.layoutBlock();
  }

  protected override layoutBlock() {
    super.layoutBlock();
    const main = this.setLines.filter((l) => l.kind === 'main');
    const size = Math.max(...main.map((l) => l.lay.size));
    const fam = family({ role: 'display', width: 100, weight: 800 });
    const ms = 2.8 * size, ink = inkBox('“', fam, ms), gap = 0.55 * size;
    const inkMid = (y: number) => y - (ink.asc - ink.desc) / 2;
    if (this.k('align', 'center') === 'center') {
      // above the block: the block moves down by half the mark's room, and the mark's ink ends `gap` above it
      const room = ink.asc + ink.desc + gap;
      for (const l of this.setLines) l.y += room / 2;
      this.box.y0 += room / 2;
      this.box.y1 += room / 2;
      const y = this.box.y0 - gap - ink.desc;
      this.qmark = { x: (this.box.x0 + this.box.x1) / 2, y, cy: inkMid(y), size: ms, fam, align: 'center' };
    } else {
      // hanging in the margin, its top level with the first line's cap top
      const y = this.box.y0 + ink.asc;
      this.qmark = { x: this.box.x0 - 0.18 * size, y, cy: inkMid(y), size: ms, fam, align: 'right' };
    }
  }

  protected override drawBefore(c: CanvasRenderingContext2D, f: Frame, push: number) {
    const k = spring(f.t - (this.firstAt - 0.25), 4, 0.7);
    if (k <= 0) return;
    const M = this.qmark, color = this.p('markColor', 'accent');
    const ex = this.exitOf(this.setLines[0]!, f.t).alpha;
    for (const ctx of [c, this.glowAt(push)]) {
      if (!ctx) continue;
      ctx.save();
      ctx.globalAlpha = clamp(k * 1.5) * ex;
      ctx.font = font(M.fam, M.size);
      ctx.textAlign = M.align;
      // it grows about its own ink
      ctx.translate(M.x, M.cy);
      ctx.scale(0.6 + 0.4 * k, 0.6 + 0.4 * k);
      ctx.fillStyle = ctx === c ? rgba(color) : glowInk(color, 0.5);
      ctx.fillText('“', 0, M.y - M.cy);
      ctx.restore();
    }
  }
}

export default Quote;
