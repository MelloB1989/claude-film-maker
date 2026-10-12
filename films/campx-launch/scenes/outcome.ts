// outcome: three statements, one at a time, on the voice: "Faster results." "Consistent marking." "Complete control."
// Each lands (a focus-pull up from soft), the ones before it settle back, and a hairline in the brand gradient draws
// under the newest.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { HEX, rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, lerp, prog } from '@engine/util';
import { arrive, spoken } from './common';

const LINES: [string, string][] = [
  ['Faster', 'results.'],
  ['Consistent', 'marking.'],
  ['Complete', 'control.'],
];

export default class Outcome extends Scene2D {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const u = this.u, t = f.t, st = this.ctx.start;
    const words = spoken(this.ctx.vo, this.ctx.id);
    // each statement is two spoken words: it lands on the first
    const at = LINES.map((_, i) => words[i * 2]?.at ?? st + 0.7 + i * 1.9);
    const drift = f.p;

    // a slow field of indigo light behind, moving a little
    const gx = W * lerp(0.3, 0.45, drift), gy = H * 0.5;
    const bg = c.createRadialGradient(gx, gy, 0, gx, gy, W * 0.75);
    bg.addColorStop(0, rgba('surface2', 0.85));
    bg.addColorStop(0.55, rgba('bg2', 0.7));
    bg.addColorStop(1, rgba('bg', 0));
    c.fillStyle = bg;
    c.fillRect(0, 0, W, H);

    const size = 118 * u, x0 = W * 0.13, rowH = 178 * u;
    const y0 = H * 0.5 - rowH;
    c.textBaseline = 'alphabetic';
    LINES.forEach(([a, b], i) => {
      const k = arrive(t, at[i]!, 1.0);
      if (k <= 0) return;
      // once the next statement lands this one settles back
      const next = i < LINES.length - 1 ? ease.inOutCubic(prog(t, at[i + 1]!, at[i + 1]! + 0.8)) : 0;
      const y = y0 + i * rowH + (1 - k) * 28 * u;
      c.save();
      c.globalAlpha = k * lerp(1, 0.38, next);
      c.filter = `blur(${((1 - k) * 14 * u).toFixed(1)}px)`;
      c.font = font(F.display(87.5, 800), size);
      c.fillStyle = rgba('fg');
      c.fillText(a, x0, y);
      const wa = c.measureText(a + ' ').width;
      c.font = font(F.display(87.5, 300), size);
      c.fillText(b, x0 + wa, y);
      c.restore();
      // the hairline under the newest statement
      const kr = ease.outExpo(prog(t, at[i]! + 0.35, at[i]! + 1.5));
      if (kr > 0) {
        c.font = font(F.display(87.5, 800), size);
        const wa = c.measureText(a + ' ').width;
        c.font = font(F.display(87.5, 300), size);
        const w = wa + c.measureText(b).width;
        const g = this.glow;
        const grad = g.createLinearGradient(x0, 0, x0 + w, 0);
        grad.addColorStop(0, HEX.accentBright);
        grad.addColorStop(0.5, HEX.accent);
        grad.addColorStop(1, HEX.accent2Bright);
        g.globalAlpha = 0.9 * lerp(1, 0.3, next);
        g.fillStyle = grad;
        g.fillRect(x0, y + 30 * u, w * kr, 2.5 * u);
        void glowInk;
      }
    });
  }
}
