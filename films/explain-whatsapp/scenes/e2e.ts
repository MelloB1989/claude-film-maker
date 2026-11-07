// End to end (W14): "The Signal protocol keeps the keys on your phones." Two phones, a server between them that only
// ever sees scrambled ciphertext; on "keys" a key lands on each phone and stays there.
import { Explainer, phone, server, curve, wire, packet, key, lock, pill, note, ramp, pop, GREEN, TXT, TXT2, type Ctx } from './lib';
import { glowInk } from '@kit/scene2d';

export default class E2E extends Explainer {
  protected marks = {};
  protected override kicker = 'End-to-end encryption';
  protected override title = 'Signal\nprotocol';
  protected override sub = 'On by default since 2016';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const sig = this.w('signal', 0.33), keys = this.w('keys', 1.54), phones = this.w('phones', 2.04);
    const A = { x: 140, y: 470 }, S = { x: 500, y: 330 }, B = { x: 860, y: 470 };
    phone(c, g, A.x, A.y, 260, { a: ramp(t, 0, 0.25) });
    phone(c, g, B.x, B.y, 260, { a: ramp(t, 0, 0.25) });
    server(c, g, S.x, S.y, 220, { t, a: ramp(t, 0, 0.25), units: 5 });
    note(c, 'server sees only ciphertext', S.x, S.y - 150, ramp(t, sig, 0.35), { size: 21 * L, color: TXT });
    const pa = curve({ x: A.x + 70, y: A.y - 60 }, { x: S.x - 70, y: S.y + 20 }, 0.12);
    const pb = curve({ x: S.x + 70, y: S.y + 20 }, { x: B.x - 70, y: B.y - 60 }, 0.12);
    wire(c, g, pa, 1, { a: ramp(t, 0, 0.3), width: 2.5 });
    wire(c, g, pb, 1, { a: ramp(t, 0, 0.3), width: 2.5 });
    for (let i = 0; i < 3; i++) {
      const s = ((t * 0.55 + i / 3) % 1) * 2;
      if (s < 1) packet(c, g, pa, s, { kind: 'cipher', size: 14, color: GREEN });
      else packet(c, g, pb, s - 1, { kind: 'cipher', size: 14, color: GREEN });
    }
    // the keys land on the phones and stay there
    for (const [P, d] of [[A, 0], [B, 0.12]] as const) {
      const k = pop(t, keys - 0.25 + d, 0.5);
      if (k <= 0) continue;
      c.save(); c.translate(P.x, P.y + 10); c.scale(k, k); c.translate(-P.x, -(P.y + 10));
      key(c, g, P.x, P.y + 10, 120, { glow: 0.7 * ramp(t, phones - 0.1, 0.3) + 0.3, rot: -0.3 });
      c.restore();
    }
    lock(c, g, S.x, S.y + 175, 46, { a: ramp(t, sig + 0.2, 0.3), color: '#A89E92' });
    const ka = ramp(t, phones - 0.1, 0.35);
    pill(c, 'keys stay on the phones', 500, 700, 21 * L, { a: ka, color: GREEN });
    g.fillStyle = glowInk('accent', 0); // (no-op: keeps the glow layer in use for the key glows)
  }
}
