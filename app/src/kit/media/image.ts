// Image: a picture from the film's folder, full frame or framed: fit 'cover' or 'contain', a slow Ken Burns push or pan,
// rounded corners, a soft shadow, a hairline border, an entry (fade, rise, scale, wipe) and a parallax drift. Video is
// the same block playing a clip's frames.
//
// Params (frame.ts Framed lists them all; sizes in reference px of a 1080 px short side, positions fractions):
//   src               'assets/shot.png' (required)
//   x 0.5, y 0.5, w 1, h 1, fit 'cover'
//   from { zoom: 1 }, to { zoom: 1.06 }   Ken Burns keys { zoom, x, y } (pan -1..1, y down) over the shot
//   radius 0, shadow 0, border, entry 'fade', delay 0, entryDur 0.8, drift [0, 0], float 0
//   exit 'none', background 'theme', glow
//
//   { id: 'hero', scene: Image, length: 4, params: { src: 'assets/hero.jpg', from: { zoom: 1.12, x: -0.4 }, to: { zoom: 1, x: 0.3 } } }
//   { id: 'card', scene: Image, length: 4, params: { src: 'assets/ui.png', fit: 'contain', w: 0.7, h: 0.7, radius: 18, shadow: 1, entry: 'rise' } }
import type { Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { cropRect, kenBurns, layoutBox, Framed, type Fit, type KB } from './frame';

export class Image extends Framed {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const m = this.media;
    if (!m) return;
    const fit = this.k<Fit>('fit', 'cover');
    const box = layoutBox({ cx: this.k('x', 0.5), cy: this.k('y', 0.5), w: this.k('w', 1), h: this.k('h', 1), fit, aspect: m.width / Math.max(1, m.height), W, H });
    const kb = kenBurns(this.k<KB>('from', { zoom: 1 }), this.k<KB>('to', { zoom: 1.06 }), f.p);
    const mo = this.motion(f);
    if (mo.alpha <= 0.001 || mo.wipe <= 0) return;
    const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
    c.save();
    c.globalAlpha = mo.alpha;
    c.translate(cx + mo.dx, cy + mo.dy);
    c.scale(mo.scale, mo.scale);
    c.translate(-cx, -cy);
    if (mo.wipe < 1) {
      c.beginPath();
      const pad = 200 * this.u; // (room for the shadow)
      c.rect(box.x - pad, box.y - pad, (box.w + 2 * pad) * mo.wipe, box.h + 2 * pad);
      c.clip();
    }
    const aspect = box.w / box.h;
    this.drawPicture(c, box, (mw, mh) => cropRect(mw, mh, aspect, kb.zoom, kb.x, kb.y), f.t, {
      radius: this.k('radius', 0) * this.u, shadow: this.k('shadow', 0), border: this.k<string | undefined>('border', undefined),
    });
    c.restore();
  }
}

export default Image;
