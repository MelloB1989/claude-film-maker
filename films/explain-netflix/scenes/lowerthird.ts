// The series lower third (GFX.md): SYSTEM DESIGN IN 60 SECONDS in Geist 600 caps, tracked +8 %, over the topic line in
// Geist 400, on a soft plate, wiping in and out. An alpha overlay (render with VITE_NF_MATTE).
// params: tag, topic
import { NfScene, rev, text, rgba, glowInk, clamp, ease, F, font, type Frame } from './lib';

export default class LowerThird extends NfScene {
  protected nominal = 3;

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const len = f.end - f.start;
    const kin = rev(t, 0.05, 0.5, ease.outQuart), kout = rev(t, len - 0.45, 0.4, ease.inQuad);
    const k = kin * (1 - kout);
    if (k <= 0) return;
    const x = 120, y = 790;
    const tag = this.p('tag', 'SYSTEM DESIGN IN 60 SECONDS'), topic = this.p('topic', 'How Netflix streams without buffering');
    c.font = font(F.ui(400), 40);
    const wTopic = c.measureText(topic).width;
    const w = Math.max(wTopic, 560) + 80;
    // plate, wiping in from the left
    c.save();
    c.beginPath(); c.rect(x - 20, y - 70, (w + 40) * kin, 170); c.clip();
    const pl = c.createLinearGradient(x, 0, x + w, 0);
    pl.addColorStop(0, 'rgba(18,14,11,0.82)'); pl.addColorStop(1, 'rgba(18,14,11,0)');
    c.globalAlpha *= 1 - kout;
    c.fillStyle = pl; c.fillRect(x - 20, y - 60, w + 40, 150);
    c.fillStyle = rgba('accent'); c.fillRect(x, y - 44, 5, 112);
    text(c, tag, x + 30, y - 6, { size: 26, weight: 600, track: 2.1, alpha: clamp(kin * 1.4 - 0.2) });
    text(c, topic, x + 30, y + 48, { size: 40, weight: 400, color: 'fg', alpha: clamp(kin * 1.4 - 0.35) });
    c.restore();
    g.save(); g.globalAlpha *= k * 0.6; g.fillStyle = glowInk('accent'); g.fillRect(x - 1, y - 44, 7, 112 * kin); g.restore();
  }
}
