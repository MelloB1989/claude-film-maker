// Title: "How WhatsApp delivers 100+ billion messages a day" over a server that messages stream through and never
// stay in (VO W02: "And almost none of them stay on its servers.").
import { Explainer, server, curve, packet, wire, note, ramp, GREEN, type Ctx } from './lib';
import { mulberry32 } from '@engine/util';

export default class Title extends Explainer {
  protected marks = {};
  protected override kicker = 'System design · WhatsApp';
  protected override title = 'How WhatsApp\ndelivers 100+\nbillion messages\na day';
  protected override sub = '';

  override headline(c: Ctx, g: Ctx, t: number) {
    super.headline(c, g, t);
  }

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const none = this.w('none', 1.0), servers = this.w('servers', 1.9);
    const sx = 500, sy = 450;
    // streams in from the left, out to the right: thirty lanes, packets seeded
    const rnd = mulberry32(3);
    const lanes = 14;
    for (let i = 0; i < lanes; i++) {
      const yIn = 90 + (i / (lanes - 1)) * 720, yOut = 90 + (((i * 5) % lanes) / (lanes - 1)) * 720;
      const pin = curve({ x: -40, y: yIn }, { x: sx - 60, y: sy + (i - lanes / 2) * 6 }, 0.08);
      const pout = curve({ x: sx + 60, y: sy + (i - lanes / 2) * 6 }, { x: 1040, y: yOut }, -0.08);
      const a = ramp(t, 0.05 * i, 0.5) * 0.7;
      wire(c, g, pin, 1, { a: a * 0.6, width: 1.4 });
      wire(c, g, pout, 1, { a: a * 0.6, width: 1.4 });
      const sp = 0.55 + rnd() * 0.35, ph = rnd();
      for (let k = 0; k < 2; k++) {
        const s = ((t * sp + ph + k * 0.5) % 1) * 2; // 0..1 in, 1..2 out
        if (s < 1) packet(c, g, pin, s, { size: 7, a, tail: 0.18, color: GREEN });
        else packet(c, g, pout, s - 1, { size: 7, a, tail: 0.18, color: GREEN });
      }
    }
    server(c, g, sx, sy, 330, { t, activity: 0.45, a: ramp(t, 0, 0.5), units: 7 });
    // "none of them stay": the server's store reads empty
    note(c, 'stored on server:  0', sx, sy + 235, ramp(t, none, 0.4), { size: 24, color: '#F2ECE4' });
    note(c, 'delivered, then deleted', sx, sy + 272, ramp(t, servers, 0.4), { size: 20 });
  }
}
