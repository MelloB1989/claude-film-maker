// Ticks (W10-W11): "Your ticks? One: the server has it. Two: it reached their phone. Blue: they've read it." A big
// sent bubble; its ticks land on "One", "Two" and "Blue"; under it three rows, each lit as the voice names it, and a
// small route (you -> server -> friend) whose stage lights with each.
import { Explainer, bubble, ticks, ramp, pop, rr, withA, text, phone, server, curve, wire, packet, BLUE, GREEN, TXT, TXT2, BORDER, type Ctx } from './lib';
import { glowInk } from '@kit/scene2d';
import { clamp } from '@engine/util';

export default class Ticks extends Explainer {
  protected marks = {};
  protected override kicker = 'Read receipts';
  protected override title = 'What the ticks mean';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.2 : 1;
    const tk = this.w('ticks', 0.63), one = this.w('one', 1.33), srv = this.w('server', 2.0), two = this.w('two', 3.0);
    const reached = this.w('reached', 3.83), blue = this.w('blue', 4.92), read = this.w('read', 5.79);
    // the bubble
    const bs = pop(t, Math.max(0, tk - 0.35), 0.5);
    const bw = 560, bh = 150, bx = 500 - bw / 2, by = 60;
    c.save();
    c.translate(500, by + bh / 2); c.scale(bs, bs); c.translate(-500, -(by + bh / 2));
    c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = 40; c.shadowOffsetY = 14;
    bubble(c, bx, by, bw, bh, { mine: true, textW: 0.55, lines: 2, a: Math.min(1, bs * 2) });
    c.restore();
    // the ticks on it, big: one, two, blue — each lands on its word (drawn on over 6 frames before it)
    const n = clamp((t - (one - 0.2)) / 0.25) + clamp((t - (two - 0.2)) / 0.25);
    const bl = ramp(t, blue - 0.1, 0.25);
    ticks(c, bx + bw - 100, by + bh - 42, 44, n, bl, 7);
    if (bl > 0) {
      g.save(); g.globalAlpha = bl * 0.6; g.strokeStyle = glowInk(BLUE, 1); g.lineWidth = 10; g.lineCap = 'round';
      g.beginPath(); g.arc(bx + bw - 100, by + bh - 42, 46, 0, Math.PI * 2); g.stroke(); g.restore();
    }
    // three rows
    const rows = [
      { at: one, n: 1, b: 0, head: 'One tick', body: 'the server has it' },
      { at: two, n: 2, b: 0, head: 'Two ticks', body: 'it reached their phone' },
      { at: blue, n: 2, b: 1, head: 'Blue', body: "they've read it" },
    ];
    rows.forEach((r, i) => {
      const y = 300 + i * 118;
      const a = ramp(t, r.at - 0.15, 0.35);
      const cur = i === 2 ? 1 : 1 - ramp(t, rows[i + 1]!.at - 0.1, 0.4) * 0.45;
      if (a <= 0) return;
      c.save(); c.globalAlpha = a * cur;
      rr(c, 60, y, 880, 96, 18); c.fillStyle = withA('#241D18', 0.95); c.fill(); c.strokeStyle = BORDER; c.lineWidth = 2; c.stroke();
      c.restore();
      ticks(c, 130, y + 48, 34, r.n, r.b, 5.5);
      text(c, r.head, 200, y + 48, 32 * L, { align: 'left', weight: 600, a: a * cur, color: r.b ? BLUE : TXT });
      text(c, r.body, 920, y + 48, 26 * L, { align: 'right', a: a * cur, color: TXT2 });
    });
    // the route, small, at the bottom: lights the stage the receipt confirms
    const ry = 720, A = { x: 200, y: ry }, S = { x: 500, y: ry - 10 }, B = { x: 800, y: ry };
    const ra = ramp(t, one - 0.3, 0.4);
    phone(c, g, A.x, A.y, 120, { a: ra });
    server(c, g, S.x, S.y, 120, { t, a: ra, units: 4 });
    phone(c, g, B.x, B.y, 120, { a: ra, on: 0.4 + 0.6 * ramp(t, read - 0.6, 0.3) });
    const p1 = curve({ x: A.x + 45, y: A.y }, { x: S.x - 50, y: S.y }, 0.1), p2 = curve({ x: S.x + 50, y: S.y }, { x: B.x - 45, y: B.y }, 0.1);
    wire(c, g, p1, 1, { a: ra, width: 2, color: ramp(t, one, 0.2) > 0.5 ? GREEN : undefined, glow: ramp(t, one, 0.3) * 0.5 });
    wire(c, g, p2, 1, { a: ra, width: 2, color: ramp(t, two, 0.2) > 0.5 ? GREEN : undefined, glow: ramp(t, two, 0.3) * 0.5 });
    packet(c, g, p1, clamp((t - (one - 0.45)) / 0.45), { size: 8, a: t < one ? ra : 0 });
    packet(c, g, p2, clamp((t - (two - 0.45)) / 0.45), { size: 8, a: t < two ? ra : 0 });
    void srv; void reached;
  }
}
