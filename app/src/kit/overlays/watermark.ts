// Watermark: a corner bug, a small mono label and/or a logo image, inside the action-safe area. Transparent; fades in
// over the overlay's first half second and out over its last.
//
// Params: text (mono, uppercase, tracked), image (a path in the film's folder: 'assets/logo.svg'), corner 'br' ('tl' |
// 'tr' | 'bl' | 'br'), size 22 (text, reference px; the image is 1.6x as tall), opacity 0.7, dot true (an accent dot
// breathing on the beat before the text), color 'fgDim'.
import { Scene2D, glowInk, isTall, safeRect, type Frame } from '../scene2d';
import type { Background } from '../common';
import { filmUrl } from '../../engine/config';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { onBeat } from '../../engine/motion';
import { ease, prog } from '../../engine/util';
import { family, layLine, type LaidLine } from '../text/layout';

export class Watermark extends Scene2D {
  protected override defaultBackground: Background = 'none';
  private text: LaidLine | null = null;
  private img: HTMLImageElement | null = null;

  override async init() {
    const u = this.u;
    const size = this.p('size', isTall() ? 26 : 22) * u;
    const text = this.p<string>('text', '');
    this.text = text ? layLine(text.toUpperCase(), family({ role: 'mono', weight: 500 }), size, 0.2 * size) : null;
    const path = this.p<string | null>('image', null);
    if (path) {
      const img = new Image();
      img.src = filmUrl(path);
      try {
        await img.decode();
      } catch {
        throw new Error(`overlay ${this.ctx.id}: image ${filmUrl(path)} did not load`);
      }
      this.img = img;
    }
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const T = this.text, u = this.u;
    const size = this.p('size', isTall() ? 26 : 22) * u;
    const a = this.p('opacity', 0.7) * Math.min(prog(f.t, this.ctx.start, this.ctx.start + 0.5, ease.outCubic), 1 - prog(f.t, this.ctx.end - 0.5, this.ctx.end));
    if (a <= 0.002) return;
    const corner = this.p<'tl' | 'tr' | 'bl' | 'br'>('corner', 'br');
    const safe = safeRect('action');
    const ih = this.img ? 1.6 * size : 0, iw = this.img ? (ih * this.img.naturalWidth) / Math.max(1, this.img.naturalHeight) : 0;
    const dot = this.p('dot', true) && T ? 0.62 * size : 0;
    const gap = 0.6 * size;
    const w = iw + (this.img && T ? gap : 0) + dot + (T ? T.width : 0);
    const h = Math.max(ih, T ? T.m.cap * size : 0);
    const x = corner[1] === 'l' ? safe.x0 : safe.x1 - w;
    const y = corner[0] === 't' ? safe.y0 : safe.y1 - h; // the bug's top
    c.globalAlpha = a;
    let cx = x;
    if (this.img) {
      c.drawImage(this.img, cx, y + (h - ih) / 2, iw, ih);
      cx += iw + (T ? gap : 0);
    }
    if (T) {
      const base = y + h / 2 + (T.m.cap * size) / 2;
      if (dot) {
        const r = 0.17 * size, dx = cx + r, dy = base - (T.m.cap * size) / 2;
        c.fillStyle = rgba('accent');
        c.beginPath();
        c.arc(dx, dy, r, 0, Math.PI * 2);
        c.fill();
        if (this.glowLevel > 0) {
          const g = this.glow;
          g.fillStyle = glowInk('accent', a * (0.35 + 0.4 * onBeat(f, 0.3)));
          g.beginPath();
          g.arc(dx, dy, r, 0, Math.PI * 2);
          g.fill();
        }
        cx += dot;
      }
      c.font = font(T.family, T.size);
      c.letterSpacing = `${T.track}px`;
      c.fillStyle = rgba(this.p('color', 'fgDim'));
      c.fillText(T.text, cx, base);
      c.letterSpacing = '0px';
    }
  }
}

export default Watermark;
