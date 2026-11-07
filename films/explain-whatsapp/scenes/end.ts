// End card (1.5 s): the series tag and the film's question, answered in three words each.
import { Explainer, ramp, note, GREEN, type Ctx } from './lib';
import { glowInk } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { F, font } from '@engine/type';
import { ease } from '@engine/util';

export default class End extends Explainer {
  protected marks = {};
  protected override title = '';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const words = ['Tiny processes.', "Messages that don't linger.", 'Keys on your phone.'];
    words.forEach((w, i) => note(c, w, 500, 330 + i * 60, ramp(t, 0.1 + i * 0.12, 0.35), { size: 30, color: i === 2 ? GREEN : '#A89E92' }));
    void g;
  }

  override headline(c: Ctx, g: Ctx, t: number) {
    const u = this.u;
    const k = ramp(t, 0, 0.45, ease.outQuart);
    c.save();
    c.textAlign = 'center';
    c.font = font(F.ui(600), 22 * u);
    c.letterSpacing = `${0.08 * 22 * u}px`;
    c.fillStyle = `rgba(242,236,228,${0.75 * k})`;
    c.fillText('SYSTEM DESIGN IN 60 SECONDS', W / 2, 0.24 * H);
    c.letterSpacing = '0px';
    c.font = font(F.display(100, 800), 76 * u);
    c.fillStyle = `rgba(242,236,228,${k})`;
    c.fillText('100+ billion messages a day', W / 2, 0.34 * H + (1 - k) * 20 * u);
    c.restore();
    const r = ramp(t, 0.2, 0.6, ease.inOutCubic);
    c.fillStyle = GREEN;
    c.fillRect(W / 2 - 70 * u * r, 0.39 * H, 140 * u * r, 3 * u);
    g.fillStyle = glowInk('accent', 0.7 * r);
    g.fillRect(W / 2 - 70 * u * r, 0.39 * H - u, 140 * u * r, 5 * u);
  }
}
