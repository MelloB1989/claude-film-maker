// Stands in for a product scene (scenes/product/<id>.ts) until the product agent's file exists: a floating frame and
// the scene's id. film.ts switches to the real file by itself once it is there.
import { Scene2D, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, prog } from '@engine/util';

export default class Placeholder extends Scene2D {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const u = this.u, k = ease.outCubic(prog(f.lt, 0, 0.9));
    const w = W * 0.66, h = w * 0.58, x = (W - w) / 2, y = (H - h) / 2 + (1 - k) * 30 * u;
    c.save();
    c.globalAlpha = k;
    c.shadowColor = 'rgba(0,0,0,0.55)';
    c.shadowBlur = 70 * u;
    c.shadowOffsetY = 28 * u;
    c.beginPath();
    c.roundRect(x, y, w, h, 18 * u);
    c.fillStyle = rgba('surface');
    c.fill();
    c.shadowBlur = 0;
    c.lineWidth = 1.5 * u;
    c.strokeStyle = rgba('ruleStrong');
    c.stroke();
    c.textAlign = 'center';
    c.fillStyle = rgba('fgFaint');
    c.font = font(F.mono(500), 26 * u);
    c.fillText(`${this.ctx.id} · product scene pending`, W / 2, y + h / 2);
    c.restore();
  }
}
