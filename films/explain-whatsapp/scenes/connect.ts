// Connect (W04): "Open the app, and your phone keeps one connection open to WhatsApp." A phone wakes, one wire draws to
// the chat server on "connection" and stays live (heartbeats both ways) from "open".
import { Explainer, phone, server, curve, wire, packet, pill, note, ramp, pop, ripple, bubble, GREEN, type Ctx } from './lib';

export default class Connect extends Explainer {
  protected marks = {};
  protected override kicker = 'Persistent connection';
  protected override title = 'One connection,\nalways open';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const app = this.w('open', 0.37), ph = this.w('phone', 1.63), conn = this.w('connection', 2.46), open = this.w('open', 2.92, 1), wa = this.w('whatsapp', 3.29);
    const P = { x: 190, y: 470 }, S = { x: 800, y: 450 };
    const on = ramp(t, app, 0.4);
    const s = pop(t, 0);
    phone(c, g, P.x, P.y, 420 * Math.min(1, s), {
      on, a: ramp(t, 0, 0.25),
      screen: (k, x, y, w, h) => {
        bubble(k, x + w * 0.08, y + h * 0.1, w * 0.6, h * 0.08, { mine: false, a: on });
        bubble(k, x + w * 0.3, y + h * 0.22, w * 0.62, h * 0.08, { mine: true, ticks: 2, blue: 1, a: on });
        bubble(k, x + w * 0.08, y + h * 0.34, w * 0.5, h * 0.08, { mine: false, a: on });
      },
    });
    ripple(g, P.x, P.y, 160, t, ph, 'accent', 0.8);
    server(c, g, S.x, S.y, 360, { t, a: ramp(t, 0.1, 0.4), activity: 0.35, units: 6 });
    note(c, 'chat server', S.x, S.y + 235, ramp(t, 0.3, 0.4), { size: 24 * L });
    // the wire: draws on at "connection", glows while open
    const path = curve({ x: P.x + 115, y: P.y - 20 }, { x: S.x - 115, y: S.y }, -0.12);
    const k = ramp(t, conn - 0.15, 0.45);
    const live = ramp(t, open - 0.1, 0.4);
    wire(c, g, path, k, { width: 4, color: GREEN, glow: 0.4 + 0.6 * live, a: 1 });
    // heartbeats both ways once open
    if (live > 0) {
      for (let i = 0; i < 3; i++) {
        const u = ((t - open) * 0.7 + i / 3) % 1;
        if (t - open >= i * 0.45) packet(c, g, i % 2 ? (x) => path(1 - x) : path, u, { size: 9, a: live, tail: 0.15, color: GREEN });
      }
    }
    pill(c, 'one TCP connection · kept open', 500, 250, 22 * L, { a: live, color: '#25D366' });
    note(c, 'to WhatsApp', S.x, S.y - 225, ramp(t, wa, 0.4), { size: 22 * L, color: '#F2ECE4' });
  }
}
