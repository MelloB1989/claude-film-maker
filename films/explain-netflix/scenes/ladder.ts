// Per-title encoding: two titles, two ladders. A flat animated show reaches 1080p on a fraction of the bits a grainy
// action film needs, so each title is analysed and gets its own set of renditions (bitrates illustrative).
// params: kick, title, a / b ({ name, sub, rungs: [kbps x5] })
import { NfScene, rev, land, text, kicker, heading, card, pill, rgba, glowInk, hash, lerp, clamp, ease, TAU, type Frame } from './lib';

const RES = ['240p', '360p', '480p', '720p', '1080p'];

export default class Ladder extends NfScene {
  protected nominal = 6.1;
  protected override panelTitle = 'Per-title encoding';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    heading(c, this.p('kick', 'Step 3 · Encode per title'), this.p('title', 'Every title gets its own ladder'), t);
    const A = this.p('a', { name: 'Cartoon', sub: 'flat colour, clean lines', rungs: [150, 300, 550, 900, 1600] });
    const B = this.p('b', { name: 'Action film', sub: 'grain, fast motion', rungs: [300, 750, 1500, 3000, 5800] });
    const max = Math.max(...B.rungs, ...A.rungs);
    const cols = [{ d: A, x: 140, at: this.cue('cartoon', 0.3) - 0.05, kind: 'flat' as const }, { d: B, x: 1000, at: this.cue('action', 2.2) - 0.05, kind: 'grain' as const }];
    for (const col of cols) {
      const k = rev(t, col.at, 0.4);
      const x = col.x, y = 220;
      card(c, x, y + (1 - k) * 30, 780, 580, { a: k, r: 24 });
      if (k <= 0) continue;
      c.save(); c.translate(0, (1 - k) * 30); c.globalAlpha *= k;
      // the thumbnail
      this.thumb(c, x + 40, y + 40, 220, 124, col.kind, f.t);
      text(c, col.d.name, x + 290, y + 92, { size: 38, weight: 700, face: 'display', width: 87.5 });
      text(c, col.d.sub, x + 290, y + 132, { size: 22, color: 'fgDim' });
      // the ladder
      const bx = x + 150, bw = 520;
      for (let i = 0; i < 5; i++) {
        const ry = y + 520 - i * 70, kr = rev(t, col.at + 0.25 + i * 0.09, 0.45, ease.outQuart);
        const v = col.d.rungs[i]!, w = (bw * v) / max;
        text(c, RES[i]!, bx - 22, ry + 9, { size: 24, weight: 600, face: 'mono', align: 'right', color: i === 4 ? 'fg' : 'fgDim' });
        c.fillStyle = 'rgba(255,225,200,0.06)'; c.fillRect(bx, ry - 14, bw, 28);
        const hi = i === 4 ? rev(t, col.kind === 'flat' ? this.cue('fewer', 1.3) : this.cue('film', 2.65), 0.35) : 0;
        const grd = c.createLinearGradient(bx, 0, bx + w, 0);
        grd.addColorStop(0, rgba('accentDim')); grd.addColorStop(1, rgba(i === 4 ? 'accentBright' : 'accent'));
        c.fillStyle = grd; c.fillRect(bx, ry - 14, w * kr, 28);
        if (hi > 0) { g.save(); g.globalAlpha *= k * hi * 0.5; g.fillStyle = glowInk('accent'); g.fillRect(bx, ry - 16, w * kr, 32); g.restore(); }
        if (i === 4 && hi > 0) text(c, col.kind === 'flat' ? 'fewer bits' : 'more bits', bx + w * kr + 14, ry + 8, { size: 22, weight: 600, color: col.kind === 'flat' ? 'accentBright' : 'fgDim', alpha: hi });
      }
      c.restore();
    }
    // the 1080p comparison
    const kc = land(t, this.cue('each', 3.95), 0.55);
    if (kc > 0) {
      c.save(); c.globalAlpha *= clamp(kc);
      pill(c, g, 'Same 1080p · far fewer bits', W2, 846 - (1 - kc) * 20, { color: 'accent', filled: true, size: 26 });
      c.restore();
    }
    text(c, 'bitrates illustrative', 1780, 226, { size: 18, color: 'fgFaint', align: 'right', alpha: rev(t, 0.5, 0.4) });
    pill(c, g, 'Its own ladder', 1640, 150, { a: rev(t, this.cue('ladder', 4.9), 0.35), color: 'accent', size: 24 });
    void TAU; void hash; void lerp; void kicker;
  }

  /** A tiny "frame" of each title: flat shapes, or a noisy, high-detail scene. */
  private thumb(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, kind: 'flat' | 'grain', ft: number) {
    c.save(); c.beginPath(); c.roundRect(x, y, w, h, 10); c.clip();
    if (kind === 'flat') {
      c.fillStyle = '#f2b44c'; c.fillRect(x, y, w, h);
      c.fillStyle = '#e5242c'; c.beginPath(); c.arc(x + w * 0.7, y + h * 0.35, 26, 0, TAU); c.fill();
      c.fillStyle = '#3a2416'; c.fillRect(x, y + h * 0.72, w, h * 0.28);
      c.fillStyle = '#5a3a24'; c.beginPath(); c.moveTo(x + 20, y + h * 0.72); c.lineTo(x + 70, y + h * 0.3); c.lineTo(x + 120, y + h * 0.72); c.fill();
    } else {
      const fr = Math.floor(ft * 12);
      c.fillStyle = '#20140f'; c.fillRect(x, y, w, h);
      for (let i = 0; i < 260; i++) {
        const px = x + hash(i, fr) * w, py = y + hash(i, fr + 7) * h, s = 2 + hash(i, 3) * 6;
        c.fillStyle = `rgba(${200 + hash(i, 4) * 55 | 0},${90 + hash(i, 5) * 100 | 0},${40 + hash(i, 6) * 60 | 0},${0.35 + 0.4 * hash(i, fr + 2)})`;
        c.fillRect(px, py, s, s);
      }
      // a streak of motion
      c.strokeStyle = 'rgba(255,200,140,0.55)'; c.lineWidth = 3;
      for (let i = 0; i < 6; i++) { const yy = y + 20 + i * 18; c.beginPath(); c.moveTo(x + 10 + i * 9, yy); c.lineTo(x + w - 30 + i * 3, yy - 30); c.stroke(); }
    }
    c.restore();
    c.strokeStyle = 'rgba(255,225,200,0.25)'; c.lineWidth = 1.5; c.beginPath(); c.roundRect(x, y, w, h, 10); c.stroke();
  }
}
const W2 = 960;
