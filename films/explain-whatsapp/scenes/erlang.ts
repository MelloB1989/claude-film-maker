// Erlang (W05-W06): "On the server, each connection is its own tiny Erlang process. One server once held two million
// of them." Phones on the left wire into a server; inside it a grid of process cells, one lighting per connection;
// a callout names one Erlang process; on "two million" the grid goes dense and a counter rolls to 2,000,000.
import { Explainer, phone, curve, wire, packet, note, ramp, rr, withA, text, GREEN, TXT, BORDER, CARD, type Ctx } from './lib';
import { glowInk } from '@kit/scene2d';
import { clamp, ease, hash, lerp } from '@engine/util';

export default class Erlang extends Explainer {
  protected marks = {};
  protected override kicker = 'Erlang / BEAM';
  protected override title = 'One process\nper connection';

  protected diagram(c: Ctx, g: Ctx, t: number) {
    const L = this.layout === 'panel' ? 1.25 : 1;
    const srv = this.w('server', 0.5), each = this.w('each', 1.17), erl = this.w('erlang', 2.83), proc = this.w('process', 3.17);
    const two = this.w('two', 4.96), mil = this.w('million', 5.17);
    // the server: a big card on the right holding the process grid
    const bx = 400, by = 120, bw = 560, bh = 640;
    const ka = ramp(t, Math.max(0, srv - 0.3), 0.45);
    c.save();
    c.globalAlpha = ka;
    c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = 50; c.shadowOffsetY = 18;
    rr(c, bx, by, bw, bh, 22); c.fillStyle = CARD; c.fill();
    c.shadowColor = 'transparent'; c.strokeStyle = BORDER; c.lineWidth = 2; c.stroke();
    c.restore();
    text(c, 'ONE SERVER', bx + 30, by + 36, 20 * L, { face: 'mono', align: 'left', color: '#A89E92', a: ka });
    // the grid: 12 x 12 cells, then (dense) 60 x 60 dots
    const dense = ease.inOutCubic(ramp(t, two - 0.2, 0.9, (x) => x));
    const gx = bx + 40, gy = by + 70, gw = bw - 80, gh = bh - 110;
    const N1 = 10, N2 = 46;
    const phones = 6;
    // connections arriving: one per phone, from "each" on, then many more
    const lit = (i: number) => each + 0.12 * i;
    for (let pass = 0; pass < 2; pass++) {
      const N = pass ? N2 : N1, a = pass ? dense : 1 - dense;
      if (a < 0.01) continue;
      const cw = gw / N, ch = gh / N;
      for (let r = 0; r < N; r++) for (let q = 0; q < N; q++) {
        const i = r * N + q;
        const x = gx + q * cw + cw / 2, y = gy + r * ch + ch / 2;
        // which cells are live: the first ones on each connection, then a fill that sweeps on as time goes
        const h = hash(i, pass * 7 + 1);
        const tOn = pass ? two + h * 0.6 : i < phones ? lit(i) + 0.35 : each + 0.6 + h * 2.2;
        const on = ramp(t, tOn, 0.25);
        const rad = Math.min(cw, ch) * (pass ? 0.3 : 0.32);
        c.fillStyle = withA('#3B3129', a);
        c.beginPath(); c.arc(x, y, rad, 0, Math.PI * 2); c.fill();
        if (on > 0) {
          c.fillStyle = withA(GREEN, a * on * (0.55 + 0.45 * Math.sin(t * 3 + h * 6) ** 2));
          c.beginPath(); c.arc(x, y, rad * 0.8, 0, Math.PI * 2); c.fill();
          if (!pass && i < phones) {
            g.fillStyle = glowInk('accent', a * on * 0.7);
            g.beginPath(); g.arc(x, y, rad * 1.1, 0, Math.PI * 2); g.fill();
          }
        }
      }
    }
    // phones on the left, wired to the first cells
    for (let i = 0; i < phones; i++) {
      const py = 160 + i * 110;
      const pa = ramp(t, 0.05 * i, 0.4) * (1 - dense * 0.6);
      phone(c, g, 120, py, 92, { a: pa, on: ramp(t, lit(i) - 0.2, 0.3) });
      const cw = gw / N1, ch = gh / N1;
      const tx = gx + (i % N1) * cw + cw / 2, ty = gy + ch / 2;
      const path = curve({ x: 150, y: py }, { x: tx, y: ty }, 0.1 - i * 0.02);
      const k = ramp(t, lit(i) - 0.3, 0.4);
      wire(c, g, path, k, { width: 2, color: GREEN, a: 0.75 * (1 - dense), glow: 0.3 * (1 - dense) });
      packet(c, g, path, clamp((t - (lit(i) - 0.3)) / 0.4), { size: 7, a: (1 - dense) * (t < lit(i) + 0.1 ? 1 : 0), color: GREEN });
    }
    // the callout: one cell is one Erlang process
    const ca = ramp(t, erl - 0.1, 0.4) * (1 - dense);
    if (ca > 0) {
      const cw = gw / N1, ch = gh / N1;
      const cx = gx + 2 * cw + cw / 2, cy = gy + ch / 2;
      c.save();
      c.globalAlpha = ca;
      c.strokeStyle = GREEN; c.lineWidth = 3;
      c.beginPath(); c.arc(cx, cy, Math.min(cw, ch) * 0.48, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.moveTo(cx, cy + ch * 0.48); c.lineTo(cx, cy + 150); c.lineTo(cx + 40, cy + 150); c.stroke();
      c.restore();
      const px = cx + 40, py = cy + 150;
      c.save(); c.globalAlpha = ca;
      rr(c, px, py - 52, 330 * L, 104 * L, 16); c.fillStyle = '#1A1410'; c.fill(); c.strokeStyle = withA(GREEN, 0.7); c.lineWidth = 2; c.stroke();
      c.restore();
      text(c, '1 Erlang process', px + 22, py - 18, 30 * L, { align: 'left', weight: 600, a: ca, color: TXT });
      text(c, 'a few KB · its own mailbox', px + 22, py + 22 * L, 20 * L, { face: 'mono', align: 'left', a: ramp(t, proc, 0.4) * ca, color: '#A89E92' });
    }
    // two million
    const n = Math.round(lerp(0, 2_000_000, ease.outCubic(clamp((t - two) / 0.9))));
    const da = ramp(t, two - 0.1, 0.35);
    if (da > 0) {
      c.save(); c.globalAlpha = da;
      rr(c, bx + 60, by + bh - 210, bw - 120, 150, 20); c.fillStyle = withA('#1A1410', 0.92); c.fill(); c.strokeStyle = BORDER; c.lineWidth = 2; c.stroke();
      c.restore();
      text(c, n.toLocaleString('en-US'), bx + bw / 2, by + bh - 150, 66, { face: 'mono', weight: 700, a: da, color: TXT });
      note(c, 'connections on one server (2012)', bx + bw / 2, by + bh - 95, ramp(t, mil, 0.4), { size: 21 * L });
      g.fillStyle = glowInk('accent', 0.25 * da * ramp(t, two + 0.8, 0.3));
      g.fillRect(bx + 120, by + bh - 116, bw - 240, 3);
    }
    void phone;
  }
}
