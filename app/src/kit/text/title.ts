// TitleCard: a title as a film opens or turns a chapter. A KineticText with title-card defaults (a big display title
// rising word by word on the beat, a mono kicker above, a sub below) and a hairline rule in the accent that draws out
// from the title's middle as the title lands and glows.
//
// Params: title (or text / lines: the KineticText copy), kicker, sub, rule true, ruleColor 'accent', and every
// KineticText param (reveal, unit, size 170, align, x, y, sync, emphasis, exit...).
import type { Frame } from '../scene2d';
import { glowInk } from '../scene2d';
import { rgba } from '../../engine/palette';
import { ease, prog } from '../../engine/util';
import { KineticText, type KineticParams, type LineSpec } from './kinetic';

export class TitleCard extends KineticText {
  protected override defaults: Partial<KineticParams> = { size: 170, width: 87.5, weight: 800, reveal: 'rise', unit: 'word', stagger: 0.09, push: 0.03 };

  protected override specs(): LineSpec[] {
    const title = this.ctx.params.title as string | undefined;
    if (title !== undefined && this.ctx.params.text === undefined && this.ctx.params.lines === undefined) return title.split('\n').map((text) => ({ text }));
    return super.specs();
  }

  protected override drawAfter(c: CanvasRenderingContext2D, f: Frame, push: number) {
    if (!this.p('rule', true)) return;
    const main = this.setLines.filter((l) => l.kind === 'main');
    const last = main[main.length - 1];
    if (!last) return;
    const align = this.k('align', 'center');
    // between the title and the sub (or under the title)
    const sub = this.setLines.find((l) => l.kind === 'sub');
    const y = sub ? (last.y + last.lay.m.desc * last.lay.size + (sub.y - sub.lay.m.cap * sub.lay.size)) / 2 : last.y + 0.42 * last.lay.size;
    const w = Math.min(this.box.x1 - this.box.x0, 0.22 * (this.box.x1 - this.box.x0) + 120 * this.u);
    const k = prog(f.t, this.lastAt - 0.05, this.lastAt + 0.55, ease.outExpo);
    if (k <= 0) return;
    const ex = this.exitOf(last, f.t).alpha;
    const th = Math.max(2, 2.5 * this.u);
    const cx = align === 'center' ? (this.box.x0 + this.box.x1) / 2 : align === 'left' ? this.box.x0 + (w * k) / 2 : this.box.x1 - (w * k) / 2;
    const color = this.p('ruleColor', 'accent');
    c.save();
    c.globalAlpha = ex;
    c.fillStyle = rgba(color);
    c.fillRect(cx - (w * k) / 2, y - th / 2, w * k, th);
    c.restore();
    const g = this.glowAt(push);
    if (g) {
      g.save();
      g.globalAlpha = ex;
      g.fillStyle = glowInk(color, 0.8);
      g.fillRect(cx - (w * k) / 2, y - th / 2, w * k, th);
      g.restore();
    }
  }
}

export default TitleCard;
