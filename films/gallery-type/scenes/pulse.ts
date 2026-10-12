// A scene of the film's own on the kit's Scene2D: a word, and a ring that blooms on every beat. The base clears the
// background, owns the layers and composites them; the scene only draws.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { onBeat } from '@engine/motion';

export default class Pulse extends Scene2D {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const r = (150 + 60 * onBeat(f, 0.3)) * this.u, k = onBeat(f, 0.25);
    c.strokeStyle = rgba('accent', 0.35 + 0.65 * k);
    c.lineWidth = 6 * this.u;
    c.beginPath();
    c.arc(W / 2, H / 2, r, 0, Math.PI * 2);
    c.stroke();
    c.font = font(F.display(87.5, 800), 64 * this.u);
    c.textAlign = 'center';
    c.fillStyle = rgba('fg');
    c.fillText(this.p('word', 'Pulse'), W / 2, H / 2 + 22 * this.u);
    const g = this.glow; // added as light: the ring blooms
    g.strokeStyle = glowInk('accent', k);
    g.lineWidth = 6 * this.u;
    g.beginPath();
    g.arc(W / 2, H / 2, r, 0, Math.PI * 2);
    g.stroke();
  }
}
