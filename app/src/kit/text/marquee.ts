// Marquee: a ticker of big words scrolling across the frame, row against row, with a drawn star between words. Every
// other word is set in outline, emphasis words in the accent with a glow; the rows fade out at the frame's edges and
// the whole band can tilt.
//
// Params:
//   words (required)   an array of words or phrases (or a string split on ' · ')
//   rows 2             rows, alternating direction; speed 180 (reference px a second); size 150 (reference px)
//   outline true       every other word in outline; emphasis: words in the accent; sep 'spark' (a drawn mark) or ''
//   tilt -4            degrees; y 0.5; role 'display', width 75, weight 800; uppercase true; fade 0.12 (edge fade)
//   push               (a slow scale over the shot, default 0.03)
import { Scene2D, glowInk, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { mod } from '../../engine/util';
import * as fx from './fx';
import { family, layLine, type LaidLine } from './layout';
import { drawMark, type MarkKind } from './marks';

export class Marquee extends Scene2D {
  private items: { lay: LaidLine; emph: boolean; outline: boolean; x: number }[] = [];
  private period = 0;
  private size = 0;

  override init() {
    const u = this.u;
    const raw = this.need<string[] | string>('words');
    const words = Array.isArray(raw) ? raw : raw.split(/\s*·\s*/);
    const size = (this.size = this.p('size', 150) * u);
    const fam = family({ role: this.p('role', 'display'), width: this.p('width', 75), weight: this.p('weight', 800) });
    const upper = this.p('uppercase', true);
    const emph = this.p<string[]>('emphasis', []);
    const outline = this.p('outline', true);
    const gap = 0.9 * size;
    let x = 0;
    // repeat the run until it is wider than the frame, so a row always covers it
    const run = () => words.map((w, i) => {
      const lay = layLine(upper ? w.toUpperCase() : w, fam, size, -0.01 * size);
      const it = { lay, emph: fx.isOneOf(w, emph) || emph.includes(w), outline: outline && i % 2 === 1, x };
      x += lay.width + gap;
      return it;
    });
    this.items = run();
    this.period = x;
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const size = this.size, u = this.u;
    const rows = this.p('rows', 2), speed = this.p('speed', 180) * u;
    const tilt = (this.p('tilt', -4) * Math.PI) / 180;
    const push = 1 + this.p('push', 0.03) * f.p;
    const sep = this.p<MarkKind | ''>('sep', 'spark');
    const g = this.glowLevel > 0 ? this.glow : null;
    const step = 1.08 * size;
    const cy = this.p('y', 0.5) * H;
    for (const ctx of g ? [c, g] : [c]) {
      ctx.translate(W / 2, cy);
      ctx.rotate(tilt);
      ctx.scale(push, push);
      ctx.translate(-W / 2, -cy);
    }
    // the band covers the frame's diagonal when tilted
    const reach = Math.hypot(W, H) * 0.6;
    for (let r = 0; r < rows; r++) {
      const y = cy + (r - (rows - 1) / 2) * step + 0.36 * size;
      const dir = r % 2 === 0 ? -1 : 1;
      const off = mod(dir * (f.t - this.ctx.start) * speed + r * 0.37 * this.period, this.period);
      for (let rep = -2; rep <= Math.ceil((2 * reach) / this.period) + 1; rep++) {
        for (const it of this.items) {
          const x = W / 2 - reach + it.x + rep * this.period - off;
          if (x > W / 2 + reach || x + it.lay.width < W / 2 - reach) continue;
          c.font = font(it.lay.family, it.lay.size);
          c.letterSpacing = `${it.lay.track}px`;
          const color = it.emph ? 'accent' : 'fg';
          if (it.outline && !it.emph) {
            c.strokeStyle = rgba(color, 0.9);
            c.lineWidth = Math.max(1.5, 0.018 * size);
            c.strokeText(it.lay.text, x, y);
          } else {
            c.fillStyle = rgba(color);
            c.fillText(it.lay.text, x, y);
          }
          if (it.emph && g) {
            g.font = c.font;
            g.letterSpacing = c.letterSpacing;
            g.fillStyle = glowInk('accent', 0.45);
            g.fillText(it.lay.text, x, y);
          }
          if (sep) {
            const sx = x + it.lay.width + 0.45 * size, sy = y - 0.36 * size;
            drawMark(c, sep, sx, sy, 0.34 * size, 1, rgba('accent'));
            if (g) drawMark(g, sep, sx, sy, 0.34 * size, 1, glowInk('accent', 0.6));
          }
        }
      }
    }
    c.letterSpacing = '0px';
    // fade the rows out at the frame's edges (on any background: the layer's own alpha is cut away)
    const fade = this.p('fade', 0.12) * W;
    if (fade > 0) {
      for (const ctx of g ? [c, g] : [c]) {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.globalCompositeOperation = 'destination-out';
        for (const [x0, x1] of [[0, fade], [W, W - fade]] as const) {
          const grad = ctx.createLinearGradient(x0, 0, x1, 0);
          grad.addColorStop(0, 'rgba(0,0,0,1)');
          grad.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = grad;
          ctx.fillRect(Math.min(x0, x1), 0, fade, H);
        }
        ctx.globalCompositeOperation = 'source-over';
      }
    }
  }
}

export default Marquee;
