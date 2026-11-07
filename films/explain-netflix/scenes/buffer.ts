// Buffer health: the network dips, the next chunk comes in a rung lower ("a little softer"), and the buffer ahead of
// the playhead never runs dry. Authored in panel px (850 x 540); the full-frame version is the same layout scaled up
// under a heading.
// params: kick, title
import { NfScene, rev, land, text, kicker, heading, pill, rgba, glowInk, lerp, clamp, ease, smoothstep, TAU, PANEL_W, W, type Frame } from './lib';

export default class Buffer extends NfScene {
  protected nominal = 4.1;
  protected override panelTitle = 'Buffer health';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const tNet = this.cue('network', 0.2), tDip = this.cue('dips', 0.72), tChunk = this.cue('chunk', 1.8), tSoft = this.cue('softer', 2.65);
    if (!this.look.panel) {
      heading(c, this.p('kick', 'When the network dips'), this.p('title', 'Softer for a moment, never a stall'), t);
      const s = 1.4;
      c.save(); g.save();
      for (const x of [c, g]) { x.translate((W - PANEL_W * s) / 2, 236); x.scale(s, s); }
      this.body(c, g, t, f, { tNet, tDip, tChunk, tSoft });
      c.restore(); g.restore();
    } else this.body(c, g, t, f, { tNet, tDip, tChunk, tSoft });
  }

  private body(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame, T: { tNet: number; tDip: number; tChunk: number; tSoft: number }) {
    const X0 = 40, X1 = 810;
    // ——— the network: a scrolling throughput line that dips ———
    const kN = rev(t, Math.min(0, T.tNet - 0.1), 0.35);
    const bw = (x: number) => {
      // x in s of film time; the dip arrives at tDip and recovers ~1.6 s later
      const d = smoothstep(T.tDip - 0.2, T.tDip + 0.25, x) * (1 - smoothstep(T.tDip + 1.6, T.tDip + 2.3, x));
      return 0.82 - 0.5 * d + 0.04 * Math.sin(x * 9.0) + 0.03 * Math.sin(x * 23.0 + 1);
    };
    const NY0 = 150, NY1 = 40;
    kicker(c, 'network', X0, 26, kN, 'accent2');
    c.save(); c.globalAlpha *= kN;
    c.fillStyle = 'rgba(242,236,228,0.04)'; c.fillRect(X0, NY1 - 4, X1 - X0, NY0 - NY1 + 8);
    for (const x of [c, g]) {
      x.beginPath();
      for (let i = 0; i <= 100; i++) {
        const u = i / 100, tt = t - (1 - u) * 2.2; // the last 2.2 s, newest at the right
        const y = lerp(NY0, NY1, bw(tt));
        i ? x.lineTo(lerp(X0, X1, u), y) : x.moveTo(lerp(X0, X1, u), y);
      }
    }
    c.strokeStyle = rgba('accent2Bright'); c.lineWidth = 3; c.stroke();
    g.strokeStyle = glowInk('accent2', 0.35); g.lineWidth = 5; g.stroke();
    const dipNow = bw(t) < 0.55;
    if (dipNow) text(c, 'dip', X1 - 10, lerp(NY0, NY1, bw(t)) + 32, { size: 22, weight: 600, color: 'accentBright', align: 'right' });
    c.restore();

    // ——— chunks arriving into the buffer ———
    const CY = 250, ch = 56, cw = 92, gap = 10;
    kicker(c, 'next chunks', X0, 196, rev(t, 0.05, 0.35), 'fgDim');
    // chunks slide left as the playhead consumes them; one every 0.55 s
    const rate = 0.55;
    c.save(); c.beginPath(); c.rect(X0 - 4, CY - 10, X1 - X0 + 8, ch + 20); c.clip();
    const n0 = Math.floor(t / rate);
    for (let j = -1; j < 9; j++) {
      const id = n0 + j;
      const u = t / rate - n0; // 0..1 slide phase
      const x = X0 + (j - u) * (cw + gap);
      if (x < X0 - cw || x > X1) continue;
      const arrive = id * rate;
      // the chunk requested during the dip comes in softer (720p, lighter, a little blurred look)
      const soft = id >= Math.round(T.tChunk / rate) + 6 && id <= Math.round(T.tChunk / rate) + 8;
      const label = soft ? '720' : '1080';
      const a = clamp((X1 - cw - x) / 50 + 1) * clamp((x - X0) / 50 + 1) * clamp((x - X0 + cw * 0.5) / 40) * rev(t, 0.1, 0.3);
      c.save(); c.globalAlpha *= a;
      c.fillStyle = 'rgba(70,6,10,0.95)'; c.beginPath(); c.roundRect(x + 4, CY + 6, cw, ch, 6); c.fill();
      c.fillStyle = soft ? rgba('accentDim', 0.85) : rgba('accent', 0.95);
      c.beginPath(); c.roundRect(x, CY, cw, ch, 6); c.fill();
      if (soft) { c.strokeStyle = rgba('accent2Bright', 0.9); c.lineWidth = 2; c.stroke(); }
      text(c, label, x + cw / 2, CY + 36, { size: 20, weight: 600, face: 'mono', align: 'center', color: soft ? 'accent2Bright' : 'fg' });
      c.restore();
      void arrive;
    }
    c.restore();
    // the "softer" call-out
    const ks = land(t, T.tSoft - 0.15, 0.5);
    if (ks > 0) pill(c, g, 'a little softer', X0 + 6 * (cw + gap) - (t / rate - n0) * (cw + gap) + cw / 2, CY - 30, { a: clamp(ks), color: 'accent2', size: 22 });

    // ——— the buffer meter ———
    const MY = 400, MH = 40;
    kicker(c, 'buffer ahead of the playhead', X0, MY - 22, rev(t, 0.1, 0.35), 'fgDim');
    const level = 0.78 - 0.1 * smoothstep(T.tDip, T.tDip + 0.8, t) + 0.06 * smoothstep(T.tSoft, T.tSoft + 0.8, t);
    c.fillStyle = 'rgba(242,236,228,0.07)'; c.beginPath(); c.roundRect(X0, MY, X1 - X0, MH, MH / 2); c.fill();
    const lw = (X1 - X0) * level * rev(t, 0.1, 0.6, ease.outCubic);
    const gr = c.createLinearGradient(X0, 0, X0 + lw, 0);
    gr.addColorStop(0, rgba('accentDim')); gr.addColorStop(1, rgba('accentBright'));
    c.fillStyle = gr; c.beginPath(); c.roundRect(X0, MY, lw, MH, MH / 2); c.fill();
    g.fillStyle = glowInk('accent', 0.12); g.beginPath(); g.roundRect(X0, MY - 2, lw, MH + 4, MH / 2); g.fill();
    // the playhead at the meter's start, a tick for the "danger" line
    c.fillStyle = rgba('fg'); c.beginPath(); c.arc(X0 + 20, MY + MH / 2, 9, 0, TAU); c.fill();
    c.fillStyle = 'rgba(242,236,228,0.35)'; c.fillRect(X0 + (X1 - X0) * 0.15, MY - 8, 2, MH + 16);
    pill(c, g, 'No stall', X1 - 70, MY - 34, { a: rev(t, T.tSoft + 0.25, 0.35), color: 'accent', filled: true, size: 22 });
    void f;
  }
}
