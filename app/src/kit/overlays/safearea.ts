// SafeArea: development guides over the frame. Action-safe (93%) and title-safe (90%) rectangles, the centre cross and
// the thirds, and in a vertical frame a feed's UI zones (header, caption and buttons) shaded. Transparent; for
// checking a layout, never for a delivered render.
//
// Params: thirds true, social (default: in a vertical frame), labels true, opacity 0.8.
import { Scene2D, isTall, safeRect, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { family } from '../text/layout';

export class SafeArea extends Scene2D {
  protected override defaultBackground: Background = 'none';

  draw(c: CanvasRenderingContext2D, _f: Frame) {
    const u = this.u;
    c.globalAlpha = this.p('opacity', 0.8);
    c.lineWidth = Math.max(1, 1.5 * u);
    const labels = this.p('labels', true);
    const fs = 15 * u;
    c.font = font(family({ role: 'mono', weight: 500 }), fs);
    const box = (r: ReturnType<typeof safeRect>, color: string, label: string) => {
      c.strokeStyle = rgba(color, 0.85);
      c.setLineDash([10 * u, 6 * u]);
      c.strokeRect(r.x0, r.y0, r.w, r.h);
      c.setLineDash([]);
      if (labels) {
        c.fillStyle = rgba(color);
        c.fillText(label, r.x0 + 8 * u, r.y0 + fs + 6 * u);
      }
    };
    if (this.p('social', isTall())) {
      // a feed's UI: the header, the caption and buttons along the bottom, the button column on the right
      const s = safeRect('social');
      c.fillStyle = rgba('accent', 0.12);
      c.fillRect(0, 0, W, s.y0);
      c.fillRect(0, s.y1, W, H - s.y1);
      c.fillRect(s.x1, s.y0, W - s.x1, s.y1 - s.y0);
      box(s, 'accent', 'SOCIAL SAFE');
    }
    box(safeRect('action'), 'accent2', 'ACTION SAFE 93%');
    box(safeRect('title'), 'fgDim', 'TITLE SAFE 90%');
    c.strokeStyle = rgba('fgFaint', 0.9);
    if (this.p('thirds', true)) {
      c.beginPath();
      for (const k of [1 / 3, 2 / 3]) {
        c.moveTo(W * k, 0);
        c.lineTo(W * k, H);
        c.moveTo(0, H * k);
        c.lineTo(W, H * k);
      }
      c.stroke();
    }
    const cs = 24 * u;
    c.strokeStyle = rgba('fg', 0.8);
    c.beginPath();
    c.moveTo(W / 2 - cs, H / 2);
    c.lineTo(W / 2 + cs, H / 2);
    c.moveTo(W / 2, H / 2 - cs);
    c.lineTo(W / 2, H / 2 + cs);
    c.stroke();
  }
}

export default SafeArea;
