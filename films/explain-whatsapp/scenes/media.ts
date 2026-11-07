// Media (W15): "Photos go to a blob store, encrypted. Only the key rides in the message." The photo is sealed on the
// phone and uploaded to the blob store; the chat message carries only the key (and where to fetch it); the friend's
// phone pulls the blob and unlocks it.
import { Explainer, phone, cylinder, curve, wire, packet, lock, key, pill, note, ramp, pop, rr, withA, GREEN, TXT, TXT2, type Ctx } from './lib';
import { clamp, lerp, ease } from '@engine/util';

export default class Media extends Explainer {
  protected marks = {};
  protected override kicker = 'Photos and video';
  protected override title = 'Blob store +\na key';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const photos = this.w('photos', 0.375), blob = this.w('blob', 1.29), enc = this.w('encrypted', 2.04);
    const only = this.w('only', 3.125), ky = this.w('key', 3.54), rides = this.w('rides', 3.83), msg = this.w('message', 4.375);
    const A = { x: 140, y: 600 }, B = { x: 860, y: 600 }, D = { x: 500, y: 190 };
    phone(c, g, A.x, A.y, 250, { a: ramp(t, 0, 0.25), label: 'you' });
    phone(c, g, B.x, B.y, 250, { a: ramp(t, 0, 0.25), label: 'friend', on: 0.5 + 0.5 * ramp(t, msg, 0.3) });
    cylinder(c, D.x, D.y, 220, 150, { a: ramp(t, blob - 0.35, 0.35), label: '' });
    note(c, 'blob store', D.x, D.y + 135, ramp(t, blob, 0.35), { size: 24 * L, color: TXT });
    note(c, 'served via CDN', D.x, D.y + 182, ramp(t, blob + 0.4, 0.35), { size: 17 * L, color: TXT2 });
    // the photo: a little framed landscape, sealed, then up to the store
    const up = curve({ x: A.x, y: A.y - 150 }, { x: D.x - 120, y: D.y }, 0.2);
    const u = ease.inOutCubic(clamp((t - (blob - 0.55)) / 0.75));
    const ph = up(u);
    const pa = ramp(t, photos - 0.1, 0.3);
    const sealed = ramp(t, blob - 0.75, 0.25);
    const inStore = u >= 1;
    const sc = lerp(1, 0.7, u);
    if (pa > 0) {
      c.save(); c.globalAlpha = pa; c.translate(ph.x, ph.y); c.scale(sc, sc);
      rr(c, -60, -45, 120, 90, 10); c.fillStyle = '#2e251f'; c.fill(); c.strokeStyle = withA('#F2ECE4', 0.7); c.lineWidth = 3; c.stroke();
      c.save(); rr(c, -60, -45, 120, 90, 10); c.clip();
      c.fillStyle = 'rgba(200,135,74,0.55)'; c.beginPath(); c.arc(28, -16, 13, 0, Math.PI * 2); c.fill();
      c.fillStyle = 'rgba(37,211,102,0.45)'; c.beginPath(); c.moveTo(-60, 45); c.lineTo(-18, -5); c.lineTo(14, 30); c.lineTo(34, 12); c.lineTo(60, 45); c.fill();
      c.restore();
      // sealed: the picture scrambles under a dark veil
      if (sealed > 0) { rr(c, -60, -45, 120, 90, 10); c.fillStyle = withA('#120E0B', 0.75 * sealed); c.fill(); }
      c.restore();
      lock(c, g, ph.x, ph.y, 48 * sc, { a: sealed * pa, glow: ramp(t, enc - 0.1, 0.2) * (1 - ramp(t, enc + 0.4, 0.3)) });
    }
    wire(c, g, up, ramp(t, blob - 0.6, 0.4), { a: 0.6, width: 2, dash: [8, 8], flow: t * 30 });
    pill(c, 'encrypted', ph.x, ph.y + 75 * sc, 17 * L, { a: ramp(t, enc - 0.1, 0.3) * (inStore ? 0 : 1) });
    if (inStore) pill(c, 'encrypted', D.x, D.y - 110, 17 * L, { a: ramp(t, enc - 0.1, 0.3), color: GREEN });
    // the message: only the key (and the blob's address) rides, through the chat server, phone to phone
    const mp = curve({ x: A.x + 70, y: A.y + 20 }, { x: B.x - 70, y: B.y + 20 }, -0.12);
    const m = clamp((t - (rides - 0.05)) / (Math.max(0.6, msg - rides + 0.1)));
    // the wire's glow is added over the layer, so while the message rides it stops short of the pill
    const riding = m > 0 && m < 1 && ramp(t, ky - 0.2, 0.3) > 0;
    wire(c, g, mp, riding ? Math.min(ramp(t, only - 0.2, 0.4), Math.max(0, m - 0.16)) : ramp(t, only - 0.2, 0.4), { a: 0.8, width: 2.5, color: GREEN, glow: 0.3 });
    if (riding) wire(c, g, mp, ramp(t, only - 0.2, 0.4), { s0: Math.min(1, m + 0.16), a: 0.8, width: 2.5, color: GREEN, glow: 0.3 });
    const mpt = mp(m);
    const ka = ramp(t, ky - 0.2, 0.3);
    if (ka > 0 && m < 1) {
      const k = pop(t, ky - 0.25, 0.45);
      c.save(); c.translate(mpt.x, mpt.y); c.scale(k, k);
      rr(c, -124, -36, 264, 72, 22); c.fillStyle = '#1f5c3a'; c.fill(); c.strokeStyle = GREEN; c.lineWidth = 2.5; c.stroke();
      c.restore();
      key(c, g, mpt.x - 72 * k, mpt.y, 52 * k, { color: '#F2ECE4', glow: 0.5 });
      note(c, '+ link', mpt.x + 44 * k, mpt.y, ka, { size: 15, color: TXT });
    }
    pill(c, 'only the key rides in the message', 500, 850, 20 * L, { a: ramp(t, ky, 0.35), color: GREEN });
    // the friend fetches the blob and unlocks it
    const dn = curve({ x: D.x + 120, y: D.y }, { x: B.x, y: B.y - 150 }, 0.2);
    const d = ease.inOutCubic(clamp((t - (msg + 0.05)) / 0.6));
    if (d > 0) {
      const p = dn(d);
      wire(c, g, dn, d, { a: 0.6, width: 2, dash: [8, 8], flow: t * 30 });
      lock(c, g, p.x, p.y, 40, { open: ramp(t, msg + 0.6, 0.3), glow: ramp(t, msg + 0.6, 0.2) * 0.8 });
    }
    // unlocked: the photo shows on the friend's phone
    const shown = ramp(t, msg + 0.75, 0.35);
    if (shown > 0) {
      c.save(); c.globalAlpha = shown; c.translate(B.x, B.y - 10); c.scale(0.8, 0.8);
      rr(c, -60, -45, 120, 90, 10); c.fillStyle = '#2e251f'; c.fill(); c.strokeStyle = withA('#F2ECE4', 0.7); c.lineWidth = 3; c.stroke();
      rr(c, -60, -45, 120, 90, 10); c.clip();
      c.fillStyle = 'rgba(200,135,74,0.55)'; c.beginPath(); c.arc(28, -16, 13, 0, Math.PI * 2); c.fill();
      c.fillStyle = 'rgba(37,211,102,0.45)'; c.beginPath(); c.moveTo(-60, 45); c.lineTo(-18, -5); c.lineTo(14, 30); c.lineTo(34, 12); c.lineTo(60, 45); c.fill();
      c.restore();
    }
    void pop;
  }
}
