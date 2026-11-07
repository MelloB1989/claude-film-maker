// Store and forward (W08-W09): "Then it goes straight down their connection. If not, it waits. And once it's
// delivered, it's deleted." Online: a message runs sender -> server -> friend. Offline: the next one waits in the
// friend's queue on the server; the friend comes back, it is delivered, and the server's copy is deleted.
import { Explainer, phone, server, curve, wire, packet, pill, note, ramp, ripple, rr, withA, text, GREEN, TXT, TXT2, type Ctx } from './lib';
import { glowInk } from '@kit/scene2d';
import { clamp, ease, lerp } from '@engine/util';

export default class Store extends Explainer {
  protected marks = {};
  protected override kicker = 'Store and forward';
  protected override title = 'Delivered,\nthen deleted';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const straight = this.w('straight', 0.71), conn = this.w('connection', 1.42), ifNot = this.w('if', 2.25);
    const waits = this.w('waits', 3.0), deliv = this.w('delivered', 4.125), del = this.w('deleted', 4.79);
    const A = { x: 110, y: 520 }, S = { x: 500, y: 330 }, B = { x: 890, y: 520 };
    // the friend: online, offline from "if not", back online just before "delivered"
    const back = deliv - 0.75;
    const offline = ramp(t, ifNot - 0.1, 0.3) * (1 - ramp(t, back, 0.3));
    phone(c, g, A.x, A.y, 260, { a: ramp(t, 0, 0.3), label: 'you' });
    phone(c, g, B.x, B.y, 260, { a: ramp(t, 0, 0.3), on: 1 - offline * 0.85, label: 'friend' });
    pill(c, 'offline', B.x, B.y - 175, 18 * L, { a: offline, color: TXT2 });
    pill(c, 'online', B.x, B.y - 175, 18 * L, { a: ramp(t, back, 0.3) * (1 - ramp(t, del + 0.5, 0.3)), color: GREEN });
    server(c, g, S.x, S.y, 250, { t, a: ramp(t, 0, 0.3), activity: 0.3, units: 5 });
    const pa = curve({ x: A.x + 70, y: A.y - 60 }, { x: S.x - 85, y: S.y + 20 }, 0.12);
    const pb = curve({ x: S.x + 85, y: S.y + 20 }, { x: B.x - 70, y: B.y - 60 }, 0.12);
    wire(c, g, pa, 1, { a: ramp(t, 0.1, 0.4), width: 2.5 });
    wire(c, g, pb, 1, { a: ramp(t, 0.1, 0.4) * (1 - 0.7 * offline), width: 2.5, dash: offline > 0.5 ? [8, 10] : undefined });
    // message 1: straight through (online)
    const m1 = clamp((t - (straight - 0.45)) / 0.55), m2 = clamp((t - (straight + 0.05)) / 0.6);
    packet(c, g, pa, m1, { kind: 'msg', size: 15, a: m1 > 0 && m1 < 1 ? 1 : 0 });
    packet(c, g, pb, m2, { kind: 'msg', size: 15, a: m2 > 0 && m2 < 1 ? 1 : 0 });
    ripple(g, B.x, B.y, 140, t, straight + 0.65, 'accent', 0.7);
    note(c, 'straight down their connection', 500, 760, life2(t, straight, ifNot - 0.15), { size: 22 * L, color: TXT });
    // message 2: up to the server, into the friend's queue, waits, then on; the server's copy is deleted
    const q = { x: S.x, y: S.y + 210 };
    const up = clamp((t - (ifNot + 0.05)) / 0.55);
    packet(c, g, pa, up, { kind: 'msg', size: 15, a: up > 0 && up < 1 ? 1 : 0 });
    // the queue slot under the server
    const qa = ramp(t, ifNot + 0.2, 0.35) * (1 - ramp(t, del + 0.6, 0.4));
    if (qa > 0) {
      c.save(); c.globalAlpha = qa;
      rr(c, q.x - 150, q.y - 46, 300, 92, 16); c.fillStyle = withA('#1A1410', 0.95); c.fill();
      c.setLineDash([6, 6]); c.strokeStyle = withA(TXT2, 0.6); c.lineWidth = 2; c.stroke();
      c.restore();
      text(c, "friend's queue", q.x, q.y - 66, 18 * L, { face: 'mono', color: TXT2, a: qa });
    }
    // the stored copy: drops into the queue, waits (a clock ring), leaves on delivery, and is deleted
    const inQ = ramp(t, ifNot + 0.55, 0.3, ease.outBack as (x: number) => number);
    const leave = clamp((t - (deliv - 0.5)) / 0.5);
    const gone = ramp(t, del, 0.35);
    if (inQ > 0) {
      const y = lerp(S.y + 60, q.y, inQ);
      c.save();
      c.globalAlpha = 1 - gone;
      rr(c, q.x - 46, y - 26, 92, 52, 14); c.fillStyle = '#1f5c3a'; c.fill(); c.strokeStyle = withA(GREEN, 0.9); c.lineWidth = 2.5; c.stroke();
      c.fillStyle = 'rgba(242,236,228,0.85)'; rr(c, q.x - 30, y - 10, 60, 7, 3.5); c.fill(); rr(c, q.x - 30, y + 4, 38, 7, 3.5); c.fill();
      c.restore();
      // the wait: a ring that sweeps while it waits
      const wa = ramp(t, waits - 0.2, 0.3) * (1 - ramp(t, deliv - 0.55, 0.2));
      if (wa > 0) {
        const sw = ((t - waits) * 0.9) % 1;
        c.save(); c.globalAlpha = wa; c.strokeStyle = TXT2; c.lineWidth = 4; c.lineCap = 'round';
        c.beginPath(); c.arc(q.x + 100, y, 20, -Math.PI / 2, -Math.PI / 2 + Math.max(0.01, sw) * Math.PI * 2); c.stroke();
        c.restore();
        text(c, 'waits', q.x - 100, y, 22 * L, { face: 'mono', color: TXT, a: wa });
      }
      // deleted: the copy breaks into dust
      if (gone > 0 && gone < 1) {
        for (let i = 0; i < 18; i++) {
          const ang = i * 2.4, r = 20 + 90 * ease.outCubic(gone);
          g.fillStyle = glowInk('accent', (1 - gone) * 0.8);
          g.fillRect(q.x + Math.cos(ang) * r, y + Math.sin(ang) * r * 0.6, 4, 4);
        }
      }
    }
    packet(c, g, pb, leave, { kind: 'msg', size: 15, a: leave > 0 && leave < 1 ? 1 : 0 });
    ripple(g, B.x, B.y, 140, t, deliv, 'accent', 0.7);
    pill(c, 'delivered', B.x, B.y + 185, 20 * L, { a: ramp(t, deliv, 0.3), color: GREEN });
    pill(c, 'deleted from server', q.x, q.y + 85, 20 * L, { a: ramp(t, del, 0.3), color: TXT });
  }
}

const life2 = (t: number, a: number, b: number) => Math.min(ramp(t, a, 0.35), 1 - ramp(t, b, 0.3));
