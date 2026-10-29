// Words: a few lines of type for a title card or an end card, each fading up and drifting a little into place, tracked
// out as it lands. Transparent by default: stack it over a picture.
//
// Params:
//   lines: [{ text, x 0.5, y 0.5, size 40, role 'serif', weight 500, tracking 0.12, color '#f2ede3', align 'center',
//             at 0, dur 1.2, rise 12 }]       (x, y shares of the frame; size and rise reference px; at s from the shot)
//   fadeOut 0                                  s before the shot's end everything fades out
import { Scene2D, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { F, font } from '../../engine/type';

export interface WordLine {
  text: string; x?: number; y?: number; size?: number; role?: string; weight?: number; tracking?: number;
  color?: string; align?: CanvasTextAlign; at?: number; dur?: number; rise?: number;
}

const outCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export class Words extends Scene2D {
  protected override defaultBackground: Background = 'none';

  private family(role: string, weight: number): string {
    try {
      return F.role(role, weight);
    } catch {
      return F.ui(weight >= 500 ? 500 : 400);
    }
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const lines = this.p<WordLine[]>('lines', []);
    const lt = f.t - this.ctx.start, fo = this.p('fadeOut', 0), rest = this.ctx.end - f.t;
    const out = fo > 0 ? Math.min(1, Math.max(0, rest / fo)) : 1;
    for (const l of lines) {
      const k = Math.min(1, Math.max(0, (lt - (l.at ?? 0)) / (l.dur ?? 1.2)));
      if (k <= 0) continue;
      const e = outCubic(k), size = (l.size ?? 40) * this.u;
      c.save();
      c.globalAlpha = e * out;
      c.font = font(this.family(l.role ?? 'serif', l.weight ?? 500), size);
      c.letterSpacing = `${(l.tracking ?? 0.12) * size * (1.4 - 0.4 * e)}px`;
      c.textAlign = l.align ?? 'center';
      c.textBaseline = 'middle';
      c.fillStyle = l.color ?? '#f2ede3';
      c.fillText(l.text, (l.x ?? 0.5) * W, (l.y ?? 0.5) * H + (1 - e) * (l.rise ?? 12) * this.u);
      c.restore();
    }
  }
}

export default Words;
