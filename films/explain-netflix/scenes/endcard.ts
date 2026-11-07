// End card: the film's line in two beats, a play mark, the series tag. 1.5 s, so everything lands in the first half.
// params: line1, line2, tag
import { NfScene, rev, land, text, kicker, rgba, glowInk, H, W, TAU, clamp, ease, F, font, type Frame } from './lib';

export default class EndCard extends NfScene {
  protected nominal = 2;

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const cx = W / 2;
    const k0 = land(t, 0.0, 0.5);
    // play mark
    const R = 54 * clamp(k0);
    c.strokeStyle = rgba('accentBright'); c.lineWidth = 4; c.beginPath(); c.arc(cx, 300, R, 0, TAU); c.stroke();
    g.strokeStyle = glowInk('accent', 0.8); g.lineWidth = 7; g.beginPath(); g.arc(cx, 300, R, 0, TAU); g.stroke();
    c.fillStyle = rgba('fg', clamp(k0));
    c.beginPath(); c.moveTo(cx - 15 * k0, 300 - 22 * k0); c.lineTo(cx + 25 * k0, 300); c.lineTo(cx - 15 * k0, 300 + 22 * k0); c.closePath(); c.fill();
    const l1 = rev(t, 0.08, 0.45, ease.outQuint), l2 = rev(t, 0.3, 0.45, ease.outQuint);
    text(c, this.p('line1', 'The cloud decides.'), cx, 520 + (1 - l1) * 36, { size: 96, weight: 800, face: 'display', width: 87.5, align: 'center', alpha: l1 });
    const s2 = this.p('line2', 'The box next door delivers.');
    text(c, s2, cx, 640 + (1 - l2) * 36, { size: 96, weight: 800, face: 'display', width: 87.5, align: 'center', color: 'accentBright', alpha: l2 });
    c.font = font(F.display(87.5, 800), 96);
    g.save(); g.globalAlpha *= l2 * 0.3; g.font = c.font; g.textAlign = 'center'; g.fillStyle = glowInk('accent'); g.fillText(s2, cx, 640 + (1 - l2) * 36); g.restore();
    const k3 = rev(t, 0.5, 0.4);
    c.fillStyle = rgba('accent', k3); c.fillRect(cx - 40, 760, 80, 3);
    kicker(c, this.p('tag', 'System design in 60 seconds'), cx, 820, k3, 'fgDim', 'center');
    void H; void f;
  }
}
