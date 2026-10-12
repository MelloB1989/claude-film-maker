// ProgressBar: how far through the film (or the overlay's window) we are, as a thin bar along an edge with a glowing
// head. Transparent.
//
// Params: position 'bottom' ('top' | 'bottom'), thickness 4 (reference px), color 'accent', track 0.14 (the unfilled
// bar's alpha, in fg), inset 0 (fraction of W in from each side), marks (film times to tick, e.g. chapter starts),
// glow (Scene2D).
import { Scene2D, glowInk, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { clamp } from '../../engine/util';

export class ProgressBar extends Scene2D {
  protected override defaultBackground: Background = 'none';

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const u = this.u;
    const th = this.p('thickness', 4) * u;
    const inset = this.p('inset', 0) * W;
    const y = this.p<'top' | 'bottom'>('position', 'bottom') === 'top' ? 0 : H - th;
    const x0 = inset, w = W - 2 * inset;
    const k = clamp((f.t - this.ctx.start) / Math.max(1e-6, this.ctx.end - this.ctx.start));
    const color = this.p('color', 'accent');
    c.fillStyle = rgba('fg', this.p('track', 0.14));
    c.fillRect(x0, y, w, th);
    for (const m of this.p<number[]>('marks', [])) {
      const mk = (m - this.ctx.start) / (this.ctx.end - this.ctx.start);
      if (mk <= 0 || mk >= 1) continue;
      c.fillStyle = rgba('bg', 0.9);
      c.fillRect(x0 + w * mk - u, y, 2 * u, th);
    }
    c.fillStyle = rgba(color);
    c.fillRect(x0, y, w * k, th);
    if (this.glowLevel > 0) {
      // the head: a short bright run at the bar's end
      const g = this.glow, hw = Math.min(w * k, 60 * u);
      const grad = g.createLinearGradient(x0 + w * k - hw, 0, x0 + w * k, 0);
      grad.addColorStop(0, glowInk(color, 0));
      grad.addColorStop(1, glowInk(color, 0.9));
      g.fillStyle = grad;
      g.fillRect(x0 + w * k - hw, y, hw, th);
    }
  }
}

export default ProgressBar;
