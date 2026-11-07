// Group (W12): "In a group, your phone encrypts once. The server fans it out to everyone." The message locks on
// "encrypts", one sealed copy goes up on "once", and on "fans" the server sends a copy down to every member.
import { Explainer, phone, server, curve, wire, packet, lock, pill, note, ramp, ripple, GREEN, TXT, TXT2, type Ctx } from './lib';
import { clamp } from '@engine/util';

export default class Group extends Explainer {
  protected marks = {};
  protected override kicker = 'Group messages';
  protected override title = 'Encrypt once,\nfan out';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const grp = this.w('group', 0.625), enc = this.w('encrypts', 1.29), once = this.w('once', 1.71);
    const fans = this.w('fans', 2.67), every = this.w('everyone', 3.33);
    const A = { x: 110, y: 450 }, S = { x: 420, y: 450 };
    phone(c, g, A.x, A.y, 230, { a: ramp(t, 0, 0.3), label: 'you' });
    server(c, g, S.x, S.y, 230, { t, a: ramp(t, 0.05, 0.3), units: 5, activity: 0.3 + 0.4 * ramp(t, fans, 0.3) });
    // members: an arc on the right
    const M = 7;
    const mem = Array.from({ length: M }, (_, i) => {
      const ang = (-0.95 + (1.9 * i) / (M - 1));
      return { x: 610 + 300 * Math.cos(ang), y: 450 + 360 * Math.sin(ang) };
    });
    mem.forEach((m, i) => phone(c, g, m.x, m.y, 105, { a: ramp(t, grp - 0.2 + i * 0.04, 0.35), on: 0.35 + 0.65 * ramp(t, fans + 0.45 + i * 0.05, 0.25) }));
    // the sealed message on your phone
    const lk = ramp(t, enc - 0.1, 0.3);
    lock(c, g, A.x, A.y - 10, 70, { a: lk * (t < once ? 1 : 0.4), glow: lk * 0.5 * (t < once + 0.2 ? 1 : 0) });
    pill(c, 'encrypted once', A.x, A.y - 170, 18 * L, { a: lk, color: GREEN });
    // one copy up
    const up = curve({ x: A.x + 60, y: A.y }, { x: S.x - 70, y: S.y }, -0.15);
    wire(c, g, up, 1, { a: ramp(t, 0.1, 0.3), width: 2.5 });
    const u = clamp((t - (once - 0.2)) / 0.5);
    packet(c, g, up, u, { kind: 'cipher', size: 15, a: u > 0 && u < 1 ? 1 : 0, color: GREEN });
    note(c, '1 upload', (A.x + S.x) / 2, A.y - 70, ramp(t, once + 0.2, 0.3), { size: 20 * L, color: TXT });
    // fan out
    mem.forEach((m, i) => {
      const p = curve({ x: S.x + 70, y: S.y }, { x: m.x - 40, y: m.y }, (i - (M - 1) / 2) * -0.03);
      const k = ramp(t, fans - 0.15 + i * 0.03, 0.35);
      wire(c, g, p, k, { width: 2, color: GREEN, a: 0.8, glow: 0.35 });
      const s = clamp((t - (fans + i * 0.05)) / 0.45);
      packet(c, g, p, s, { kind: 'cipher', size: 11, a: s > 0 && s < 1 ? 1 : 0, color: GREEN });
      ripple(g, m.x, m.y, 60, t, fans + 0.45 + i * 0.05, 'accent', 0.6);
    });
    pill(c, 'server copies it to every member', 610, 860, 20 * L, { a: ramp(t, every - 0.2, 0.35), color: TXT });
    note(c, 'groups up to 1,024 members', S.x, S.y + 185, ramp(t, every + 0.3, 0.4), { size: 19 * L, color: TXT2 });
  }
}
