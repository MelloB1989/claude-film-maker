// outcome: three statements on the voice: "Faster results." "Consistent marking." "Complete control." Each lands large
// and centred, alone, sliding in with a motion-blurred streak on its first word and out the same way as the next one
// arrives; then all three resolve stacked and centred, each over a hairline in the brand gradient. In a Stack over the
// aurora (film.ts); on its own it lights its own indigo field.
import { Scene2D, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { HEX, rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, lerp, prog } from '@engine/util';
import { spoken } from './common';

const LINES: [string, string][] = [
  ['Faster', 'results.'],
  ['Consistent', 'marking.'],
  ['Complete', 'control.'],
];

/** A statement's pose: its centre x and baseline y, size, alpha, blur, the streak behind it (px, signed: where it came from). */
interface Pose { x: number; y: number; size: number; alpha: number; blur: number; streak: number; line: number }

export default class Outcome extends Scene2D {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const u = this.u, t = f.t, st = this.ctx.start;
    const words = spoken(this.ctx);
    // each statement is two spoken words: it lands on the first
    const at = LINES.map((_, i) => words[i * 2]?.at ?? st + 0.7 + i * 1.9);
    // the resolve: all three, stacked, once the last has been said
    const R = at[2]! + 1.25;

    if (this.p<string>('background', 'theme') !== 'none') {
      const gx = W * lerp(0.4, 0.55, f.p), gy = H * 0.5;
      const bg = c.createRadialGradient(gx, gy, 0, gx, gy, W * 0.75);
      bg.addColorStop(0, rgba('surface2', 0.85));
      bg.addColorStop(0.55, rgba('bg2', 0.7));
      bg.addColorStop(1, rgba('bg', 0));
      c.fillStyle = bg;
      c.fillRect(0, 0, W, H);
    }

    const solo = 176 * u, stacked = 104 * u, rowH = 150 * u;
    const ySolo = H * 0.5 + solo * 0.34, yRow = (i: number) => H * 0.5 + stacked * 0.34 + (i - 1) * rowH;
    const kR = ease.inOutCubic(prog(t, R, R + 0.75));

    LINES.forEach((_, i) => {
      const a = at[i]!, next = at[i + 1];
      // alone: in from the right on its word, out to the left as the next one lands
      // the handoff: the old one is gone (out fast, to the left) by the time the new one is in the middle
      const kin = ease.outExpo(prog(t, a - 0.08, a + 0.55));
      const kout = next === undefined ? 0 : ease.inCubic(prog(t, next - 0.26, next - 0.04));
      const poses: Pose[] = [];
      if (kin > 0 && kout < 1 && (i === 2 || t < R)) {
        const travel = W * 0.2;
        const x = W / 2 + (1 - kin) * travel - kout * travel * 1.2;
        // the streak: how fast it is moving (the derivative of the eases), as a trail behind it
        const vin = (1 - kin) * travel * 0.55, vout = kout * (1 - kout) * travel * 1.6;
        const p: Pose = {
          x, y: ySolo, size: solo * lerp(1.035, 1, kin), alpha: Math.min(1, kin * 1.4) * (1 - kout) ** 2, line: kin * (1 - kout),
          blur: (1 - kin) * 6 * u + kout * 16 * u, streak: vin - vout,
        };
        // the last one, at the resolve, moves into its row
        if (i === 2 && kR > 0) {
          p.y = lerp(ySolo, yRow(2), kR);
          p.size = lerp(solo, stacked, kR);
        }
        poses.push(p);
      }
      // the first two come back into their rows at the resolve, softly
      if (i < 2) {
        const kb = ease.outCubic(prog(t, R + 0.2 + i * 0.1, R + 1.0 + i * 0.1));
        if (kb > 0) poses.push({ x: W / 2, y: yRow(i) + (1 - kb) * 16 * u, size: stacked, alpha: kb, blur: (1 - kb) * 12 * u, streak: 0, line: kb });
      }
      for (const p of poses) this.statement(c, LINES[i]!, p);
    });
  }

  /** One statement centred on p.x: the heavy first word, the light second, a streak behind it and a hairline under it. */
  private statement(c: CanvasRenderingContext2D, [a, b]: [string, string], p: Pose) {
    const u = this.u, track = -0.012 * p.size;
    c.save();
    c.textBaseline = 'alphabetic';
    c.letterSpacing = `${track.toFixed(1)}px`;
    const fa = font(F.display(87.5, 800), p.size), fb = font(F.display(87.5, 300), p.size);
    c.font = fa;
    const wa = c.measureText(a + ' ').width;
    c.font = fb;
    const w = wa + c.measureText(b).width, x0 = p.x - w / 2;
    const draw = (cx: CanvasRenderingContext2D, dx: number, alpha: number) => {
      cx.globalAlpha = alpha;
      cx.font = fa;
      cx.fillText(a, x0 + dx, p.y);
      cx.font = fb;
      cx.fillText(b, x0 + wa + dx, p.y);
    };
    c.fillStyle = rgba('fg');
    // the streak: fainter copies smeared back along its path, blurred
    if (Math.abs(p.streak) > 2 * u) {
      c.filter = `blur(${(Math.abs(p.streak) * 0.05 + 2 * u).toFixed(1)}px)`;
      const n = 6;
      for (let j = n; j >= 1; j--) draw(c, (p.streak * j) / n, p.alpha * 0.16 * (1 - j / (n + 1)));
    }
    c.filter = p.blur > 0.3 ? `blur(${p.blur.toFixed(1)}px)` : 'none';
    draw(c, 0, p.alpha);
    c.restore();
    // the hairline: the brand gradient, drawn out from the centre, on the glow layer
    if (p.line > 0.02) {
      const g = this.glow, hw = (w / 2) * ease.outExpo(p.line);
      const grad = g.createLinearGradient(p.x - w / 2, 0, p.x + w / 2, 0);
      grad.addColorStop(0, HEX.accentBright);
      grad.addColorStop(0.5, HEX.accent);
      grad.addColorStop(1, HEX.accent2Bright);
      g.save();
      g.globalAlpha = 0.9 * p.alpha;
      g.fillStyle = grad;
      g.fillRect(p.x - hw, p.y + p.size * 0.2, hw * 2, Math.max(2 * u, p.size * 0.018));
      g.restore();
    }
  }
}
