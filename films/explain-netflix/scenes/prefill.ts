// Pre-positioning: a day of viewing demand drawn as a curve; in the quiet hours (the fill window) the titles people
// are predicted to watch fly from the library into the appliances, whose fill bars rise; by the evening peak the
// video is already local.
// params: kick, title
import { NfScene, rev, land, text, kicker, heading, card, server, pill, bez, rgba, glowInk, hash, lerp, clamp, ease, smoothstep, TAU, type Frame } from './lib';

/** Viewing demand over a day, 0..1 (illustrative shape: a trough before dawn, a peak in the evening). */
const demand = (h: number) => {
  const eve = Math.exp(-Math.pow((h - 21) / 2.6, 2));
  const day = 0.32 * smoothstep(6, 13, h) * (1 - smoothstep(22, 26, h));
  const night = 0.28 * Math.exp(-Math.pow((h + 1) / 2.0, 2));
  return clamp(0.85 * (0.06 + 0.82 * eve + day + night));
};

export default class Prefill extends NfScene {
  protected nominal = 6.75;
  protected override panelTitle = 'Pre-positioning';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const P = this.look.panel;
    const L = P
      ? { X0: 30, X1: 360, Y0: 290, Y1: 70, lx: 640, ly: 120, ocas: [150, 425, 700], oy: 400, os: 0.8, pill: [425, 525] as const, txt: 0.9 }
      : { X0: 140, X1: 900, Y0: 790, Y1: 370, lx: 1450, ly: 360, ocas: [1180, 1450, 1720], oy: 655, os: 1.0, pill: [1450, 846] as const, txt: 1 };
    if (!P) heading(c, this.p('kick', 'Step 2 · Fill it overnight'), this.p('title', 'Tomorrow’s hits, delivered tonight'), t);

    // ——— the day's demand curve ———
    const { X0, X1, Y0, Y1 } = L;
    const hx = (h: number) => lerp(X0, X1, h / 24), dy = (v: number) => lerp(Y0, Y1, v);
    const kA = rev(t, 0.05, 0.4);
    c.save(); c.globalAlpha *= kA;
    c.strokeStyle = 'rgba(255,225,200,0.16)'; c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(X0, Y0); c.lineTo(X1, Y0); c.stroke();
    for (const h of P ? [0, 12, 24] : [0, 6, 12, 18, 24]) {
      text(c, h === 24 ? '24:00' : `${String(h).padStart(2, '0')}:00`, hx(h), Y0 + 36, { size: 20, color: 'fgFaint', align: 'center', face: 'mono' });
      c.fillStyle = 'rgba(255,225,200,0.2)'; c.fillRect(hx(h) - 0.75, Y0, 1.5, 8);
    }
    text(c, 'viewing demand', X1, Y1 - 30, { size: 22, color: 'fgDim', align: 'right', alpha: 1 - rev(t, this.cue('near', 5.5) - 0.2, 0.3) });
    c.restore();
    // fill window band (quiet hours)
    const kW = rev(t, this.cue('night', 0.75), 0.45);
    if (kW > 0) {
      const a = hx(2), b = hx(7);
      const band = c.createLinearGradient(0, Y1, 0, Y0);
      band.addColorStop(0, `rgba(242,180,76,${0.02 * kW})`); band.addColorStop(1, `rgba(242,180,76,${0.16 * kW})`);
      c.fillStyle = band; c.fillRect(a, Y1 - 10, (b - a) * kW, Y0 - Y1 + 10);
      c.strokeStyle = rgba('accent2', 0.5 * kW); c.setLineDash([4, 6]); c.lineWidth = 1.5;
      c.beginPath(); c.moveTo(a, Y1 - 10); c.lineTo(a, Y0); c.moveTo(b, Y1 - 10); c.lineTo(b, Y0); c.stroke(); c.setLineDash([]);
      text(c, 'fill window', (a + b) / 2, Y1 - 22, { size: 22, weight: 600, color: 'accent2', align: 'center', alpha: kW });
    }
    // the curve draws itself
    const kD = rev(t, 0.1, 0.8, ease.inOutCubic);
    if (kD > 0) {
      const n = 120, end = Math.round(n * kD);
      const area = c.createLinearGradient(0, Y1, 0, Y0);
      area.addColorStop(0, 'rgba(229,36,44,0.28)'); area.addColorStop(1, 'rgba(229,36,44,0.02)');
      c.beginPath(); c.moveTo(hx(0), Y0);
      for (let i = 0; i <= end; i++) { const h = (24 * i) / n; c.lineTo(hx(h), dy(demand(h))); }
      c.lineTo(hx((24 * end) / n), Y0); c.closePath(); c.fillStyle = area; c.fill();
      for (const x of [c, g]) {
        x.beginPath();
        for (let i = 0; i <= end; i++) { const h = (24 * i) / n; i ? x.lineTo(hx(h), dy(demand(h))) : x.moveTo(hx(h), dy(demand(h))); }
      }
      c.strokeStyle = rgba('accentBright'); c.lineWidth = 3.5; c.lineJoin = 'round'; c.stroke();
      g.strokeStyle = glowInk('accent', 0.45); g.lineWidth = 6; g.stroke();
    }
    // the clock cursor: sweeps the fill window, then jumps to the evening peak
    const t0 = this.cue('night', 0.75), t1 = this.cue('copies', 4.5) + 1.4;
    const sweep = clamp((t - t0) / (t1 - t0));
    const toPeak = rev(t, this.cue('near', 5.5), 0.5, ease.inOutCubic);
    const hNow = lerp(lerp(2, 7, sweep), 21, toPeak);
    if (t > t0) {
      const x = hx(hNow), y = dy(demand(hNow));
      c.strokeStyle = 'rgba(255,230,210,0.35)'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(x, y); c.lineTo(x, Y0); c.stroke();
      c.fillStyle = rgba(toPeak > 0.5 ? 'accentBright' : 'accent2Bright'); c.beginPath(); c.arc(x, y, 8, 0, TAU); c.fill();
      g.fillStyle = glowInk(toPeak > 0.5 ? 'accent' : 'accent2', 0.8); g.beginPath(); g.arc(x, y, 13, 0, TAU); g.fill();
      const hh = Math.floor(hNow), mm = Math.floor((hNow - hh) * 60 / 15) * 15;
      if (toPeak < 0.5) text(c, `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`, x, y - 22, { size: 22, weight: 600, face: 'mono', align: 'center' });
      if (toPeak > 0.6) text(c, 'evening peak', x, Y1 - 24, { size: 22, weight: 600, color: 'accentBright', align: 'center', alpha: rev(t, this.cue('near', 5.5) + 0.3, 0.3) });
    }

    // ——— library → appliances ———
    const { lx, ly } = L;
    const kL = rev(t, this.cue('predicts', 1.75) - 0.1, 0.4);
    card(c, lx - 210, ly - 70, 420, 120, { a: kL });
    kicker(c, 'Netflix library', lx, ly - 22, kL, 'accent2', 'center');
    text(c, 'predicts your area’s picks', lx, ly + 22, { size: 20, color: 'fgDim', align: 'center', alpha: kL });
    const ocas = L.ocas.map((x, i) => ({ x, y: L.oy, at: this.cue('area', 2.7) + i * 0.08 }));
    const tc = this.cue('copies', 4.5);
    const fillK = (i: number) => ease.inOutCubic(clamp((t - tc - i * 0.12) / 1.5));
    for (const [i, o] of ocas.entries()) {
      server(c, g, o.x, o.y, L.os, f.t + i, { a: rev(t, o.at, 0.5), busy: 0.25 + 0.6 * fillK(i), fill: fillK(i) });
    }
    // the label gives way to the payoff pill, which takes its place on "near"
    text(c, 'the boxes near you', L.ocas[1]!, L.oy + 140 * L.os, { size: 22, color: 'fgDim', align: 'center', alpha: rev(t, ocas[0]!.at, 0.4) * (1 - rev(t, this.cue('near', 5.5), 0.2)) });
    // title tiles flying down during the window
    const cols = ['accent', 'accent2', 'accentDim', 'accent2Dim'];
    for (let i = 0; i < 15; i++) {
      const ti = tc + i * 0.09, u = clamp((t - ti) / 0.8);
      if (u <= 0 || u >= 1) continue;
      const o = ocas[i % 3]!;
      const p0 = [lx + (hash(i, 1) - 0.5) * 200, ly + 50], p3 = [o.x, o.y - 30];
      const [x, y] = bez(p0, [p0[0]!, p0[1]! + 140], [p3[0]!, p3[1]! - 180], p3, ease.inOutCubic(u));
      const s = lerp(1, 0.55, u), a = smoothstep(0, 0.15, u) * smoothstep(1, 0.8, u);
      c.save(); c.translate(x, y); c.rotate((hash(i, 2) - 0.5) * 0.3 * (1 - u)); c.globalAlpha *= a;
      c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = 12; c.shadowOffsetY = 6;
      const tw = 46 * s, th = 66 * s;
      const gr = c.createLinearGradient(0, -th / 2, 0, th / 2);
      gr.addColorStop(0, rgba(cols[i % 4]!)); gr.addColorStop(1, 'rgba(20,14,12,1)');
      c.fillStyle = gr; c.fillRect(-tw / 2, -th / 2, tw, th);
      c.shadowColor = 'transparent';
      c.fillStyle = 'rgba(255,240,225,0.75)'; c.fillRect(-tw / 2 + 5 * s, th / 2 - 14 * s, tw - 10 * s, 3 * s);
      c.restore();
    }
    // the payoff
    pill(c, g, 'At peak, it’s already next door', L.pill[0], L.pill[1], { a: rev(t, this.cue('near', 5.5) + 0.15, 0.35), color: 'accent', filled: true, size: 24 });
    void land;
  }
}
