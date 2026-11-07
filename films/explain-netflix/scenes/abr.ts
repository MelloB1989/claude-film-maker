// Adaptive bitrate: the video, one long strip, is cut into chunks a few seconds long; then the player drops each
// chunk into the rung its bandwidth allows, so the chunks trace a staircase under the network's line.
// params: kick, title, rungs (chunk i's rung, 0 = 240p .. 4 = 1080p), net (bandwidth per chunk, in rungs)
import { NfScene, rev, land, text, heading, pill, screen, rgba, glowInk, lerp, clamp, ease, smoothstep, TAU, type Frame } from './lib';

const RES = ['240p', '360p', '480p', '720p', '1080p'];

export default class Abr extends NfScene {
  protected nominal = 7.3;
  protected override panelTitle = 'Adaptive bitrate';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    heading(c, this.p('kick', 'Step 4 · Adapt every few seconds'), this.p('title', 'Small chunks, the right rung each time'), t);
    const rungs = this.p('rungs', [4, 4, 4, 3, 2, 2, 3, 4, 4, 4, 4, 4]);
    const net = this.p('net', [4.6, 4.5, 4.4, 3.4, 2.5, 2.3, 3.3, 4.3, 4.6, 4.7, 4.6, 4.6]);
    const N = rungs.length;
    const X0 = 330, X1 = 1780, gap = 10, cw = (X1 - X0 - gap * (N - 1)) / N;
    const rowY = 400, ch = 60;
    const laneY = (r: number) => 900 - r * 72;

    const tVideo = this.cue('video', 0.55), tCut = this.cue('cut', 1.0), tFew = this.cue('few', 2.15);
    const tPlayer = this.cue('player', 3.65), tPicks = this.cue('picks', 4.25), tRung = this.cue('rung', 5.0), tEvery = this.cue('every', 5.85);

    // the video: one strip, then cut
    const kV = rev(t, tVideo - 0.1, 0.5, ease.outQuart);
    const cutK = (i: number) => rev(t, tCut + (i / N) * 0.55, 0.25);
    const open = rev(t, tCut + 0.5, 0.45, ease.inOutCubic);
    // lanes (the ladder) appear with the player
    const kLn = rev(t, tPlayer - 0.15, 0.45);
    if (kLn > 0) {
      for (let r = 0; r < 5; r++) {
        const y = laneY(r);
        c.fillStyle = `rgba(242,236,228,${0.035 * kLn})`; c.fillRect(X0 - 10, y - ch / 2 - 4, (X1 - X0 + 20) * kLn, ch + 8);
        text(c, RES[r]!, X0 - 30, y + 8, { size: 24, weight: 600, face: 'mono', align: 'right', color: r === 4 ? 'fg' : 'fgDim', alpha: kLn });
      }
      // the network's line over the lanes, drawn as the chunks are picked
      const kN = clamp((t - tPicks + 0.3) / (tEvery + 0.5 - tPicks + 0.3));
      if (kN > 0) {
        const pts: [number, number][] = [];
        const steps = 80, end = Math.round(steps * kN);
        for (let s = 0; s <= end; s++) {
          const u = (s / steps) * (N - 1);
          const i0 = Math.floor(u), i1 = Math.min(N - 1, i0 + 1), fr = ease.inOutQuad(u - i0);
          const v = lerp(net[i0]!, net[i1]!, fr);
          pts.push([X0 + cw / 2 + u * (cw + gap), laneY(v) - 4]);
        }
        for (const x of [c, g]) { x.beginPath(); pts.forEach(([px, py], j) => (j ? x.lineTo(px, py) : x.moveTo(px, py))); }
        c.strokeStyle = rgba('accent2', 0.9); c.lineWidth = 3; c.setLineDash([10, 8]); c.stroke(); c.setLineDash([]);
        g.strokeStyle = glowInk('accent2', 0.35); g.lineWidth = 5; g.stroke();
        const last = pts[pts.length - 1]!;
        text(c, 'your bandwidth', last[0] + 14, last[1] - 14, { size: 22, color: 'accent2Bright', alpha: smoothstep(0, 0.1, kN) * (1 - smoothstep(0.85, 1, kN)) });
      }
    }
    // the player
    const kP = land(t, tPlayer, 0.6);
    if (kP > 0) {
      screen(c, g, 110, 640, 'tv', 1.0 * clamp(kP), { a: clamp(kP * 1.5), on: rev(t, tPicks, 0.4) });
      text(c, 'your player', 110, 712, { size: 22, color: 'fgDim', align: 'center', alpha: clamp(kP) });
    }

    // the chunks
    for (let i = 0; i < N; i++) {
      const x = X0 + i * (cw + gap * open);
      const xs = X0 + i * (cw + gap) * 1;
      const xx = lerp(X0 + (i * (X1 - X0)) / N, xs, open);
      const pickAt = tPicks + i * ((tEvery + 0.45 - tPicks) / N);
      const kd = rev(t, pickAt, 0.5, ease.inOutCubic);
      const r = rungs[i]!;
      const y = lerp(rowY, laneY(r), kd);
      const w = lerp((X1 - X0) / N + 0.5, cw, open);
      if (kV <= 0) break;
      c.save(); c.globalAlpha *= kV;
      // body: a frame-strip look, brighter on higher rungs once placed
      const hot = kd > 0 ? r / 4 : 0.8;
      const gr = c.createLinearGradient(0, y - ch / 2, 0, y + ch / 2);
      gr.addColorStop(0, rgba(hot > 0.9 ? 'accentBright' : hot > 0.6 ? 'accent' : 'accentDim', 0.95));
      gr.addColorStop(1, rgba('accentDim', 0.95));
      // the block's depth: a darker side and underside
      c.fillStyle = 'rgba(70,6,10,0.95)'; c.beginPath(); c.roundRect(xx + 6, y - ch / 2 + 8, w * kV, ch, 6 * open); c.fill();
      c.fillStyle = gr;
      c.shadowColor = 'rgba(0,0,0,0.5)'; c.shadowBlur = 16 * open; c.shadowOffsetY = 8 * open;
      c.beginPath(); c.roundRect(xx, y - ch / 2, w * kV, ch, 6 * open); c.fill();
      c.shadowColor = 'transparent';
      // sprocket marks
      c.fillStyle = 'rgba(0,0,0,0.35)';
      for (let s = 0; s < 4; s++) { c.fillRect(xx + 10 + s * (w / 4), y - ch / 2 + 5, w / 8, 5); c.fillRect(xx + 10 + s * (w / 4), y + ch / 2 - 10, w / 8, 5); }
      if (kd > 0.6 && r < 4) { c.fillStyle = `rgba(18,14,11,${0.25 * (4 - r)})`; c.beginPath(); c.roundRect(xx, y - ch / 2, w, ch, 6); c.fill(); }
      c.restore();
      if (kd > 0.95 && r === 4) { g.fillStyle = glowInk('accent', 0.25); g.fillRect(xx, y - ch / 2, w, ch); }
      // the cut: a bright blade line at each boundary
      const ck = cutK(i);
      if (i > 0 && ck > 0 && ck < 1) {
        const a = Math.sin(Math.PI * ck);
        c.fillStyle = rgba('fg', a); c.fillRect(x - gap / 2 - 1.5, rowY - ch / 2 - 18, 3, ch + 36);
        g.fillStyle = glowInk('accent', a); g.fillRect(x - gap / 2 - 3, rowY - ch / 2 - 18, 6, ch + 36);
      }
      // a packet arriving at the player as each chunk is picked
      const kf = clamp((t - pickAt) / 0.5);
      if (kf > 0 && kf < 1) {
        const px = lerp(xx + w / 2, 170, ease.inQuad(kf)), py = lerp(y, 640, ease.inQuad(kf));
        c.fillStyle = rgba('accentBright', 0.9 * (1 - kf)); c.beginPath(); c.arc(px, py, 5, 0, TAU); c.fill();
      }
    }
    text(c, 'the video', X0, rowY - ch / 2 - 22, { size: 28, color: 'fgDim', alpha: kV * (1 - rev(t, tPicks, 0.3)) });
    // "a few seconds" bracket under chunk 2
    const kb = rev(t, tFew, 0.4) * (1 - rev(t, tPicks - 0.2, 0.3));
    if (kb > 0) {
      const bx = X0 + 2 * (cw + gap), by = rowY + ch / 2 + 16;
      c.strokeStyle = rgba('fg', 0.8 * kb); c.lineWidth = 2;
      c.beginPath(); c.moveTo(bx, by); c.lineTo(bx, by + 12); c.lineTo(bx + cw, by + 12); c.lineTo(bx + cw, by); c.stroke();
      pill(c, g, 'a few seconds each', bx + cw / 2, by + 52, { a: kb, color: 'accent', size: 24 });
    }
    pill(c, g, 'The right rung, chunk by chunk', 1020, 1000, { a: rev(t, tEvery, 0.35), color: 'accent', filled: true, size: 26 });
    void f; void tRung;
  }
}
