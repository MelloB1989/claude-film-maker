// A scene written from scratch: a Canvas2D layer composited over the theme's background, a word that springs in on
// the shot's first downbeat and a rule that grows on the beat. Copy it to start a scene of your own.
import type { THREE } from '@engine/three';
import { Scene, disposeLayer, type Frame } from '@engine/scene';
import { Layer2D, W, H, clearRT } from '@engine/gl';
import { LIN, rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { onBeat, slam } from '@engine/motion';
import { lerp } from '@engine/util';

export default class Hello extends Scene {
  private layer = new Layer2D();

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp, audio } = this.ctx;
    clearRT(renderer, out, LIN.bg);
    const L = this.layer, c = L.ctx;
    L.clear();
    const title = (this.ctx.params.title as string) ?? 'Hello, film.';
    const k = slam(f.t, audio.nearestDownbeat(f.start + 0.5));
    c.textAlign = 'center';
    c.textBaseline = 'alphabetic';
    c.font = font(F.display(100, 800), 160);
    c.fillStyle = rgba('fg', Math.min(1, k));
    c.fillText(title, W / 2, H / 2 + lerp(80, 0, Math.min(1, k)));
    c.fillStyle = rgba('accent', 0.9);
    c.fillRect(W / 2 - 200 * k - 40 * onBeat(f), H / 2 + 60, 400 * k + 80 * onBeat(f), 4);
    comp.draw(renderer, L.upload(), out);
  }

  override dispose() {
    disposeLayer(this.layer);
  }
}
