// The series lower third (GFX.md; placed top-left since r7): SYSTEM DESIGN IN 60 SECONDS in Geist 600 caps, tracked +8 %, over the topic line in
// Geist 400, on a soft plate, wiping in and out. An alpha overlay (tools/matte.sh: the explain-netflix-black and -grey passes).
// params: tag, topic
import { NfScene, rev, text, rgba, glowInk, clamp, ease, F, font, type Frame } from './lib';

export default class LowerThird extends NfScene {
  protected nominal = 3;

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const len = f.end - f.start;
    const kin = rev(t, 0.05, 0.5, ease.outQuart), kout = rev(t, len - 0.45, 0.4, ease.inQuad);
    const k = kin * (1 - kout);
    if (k <= 0) return;
    // top-left, inside title safe, the plate's right edge at x <= 680: at the bottom it sat over the presenter's gestures
    // in the MCU opening, and her head (hair included) starts at x ~704 there. Both lines wrap to fit.
    const x = 120, top = 90, maxW = 500;
    const tag = this.p('tag', 'SYSTEM DESIGN IN 60 SECONDS'), topic = this.p('topic', 'How Netflix streams to 300+ million members without buffering');
    // text() sets anything under 40 px a size up (28 -> 35): measure at the size it draws
    const tagL = wrap(c, tag, maxW, F.ui(600), 35, 2.1), topL = wrap(c, topic, maxW, F.ui(400), 40, 0);
    const h = 40 + tagL.length * 40 + 12 + topL.length * 50;
    const w = maxW + 60;
    // plate, wiping in from the left
    c.save();
    c.beginPath(); c.rect(x - 20, top - 10, (w + 20) * kin, h + 20); c.clip();
    const pl = c.createLinearGradient(x, 0, x + w, 0);
    pl.addColorStop(0, 'rgba(18,14,11,0.82)'); pl.addColorStop(0.7, 'rgba(18,14,11,0.6)'); pl.addColorStop(1, 'rgba(18,14,11,0)');
    c.globalAlpha *= 1 - kout;
    c.fillStyle = pl; c.fillRect(x - 20, top, w + 20, h);
    c.fillStyle = rgba('accent'); c.fillRect(x, top + 16, 5, h - 32);
    let y = top + 20;
    for (const l of tagL) text(c, l, x + 30, (y += 40) - 6, { size: 28, weight: 600, track: 2.1, alpha: clamp(kin * 1.4 - 0.2) });
    y += 12;
    for (const l of topL) text(c, l, x + 30, (y += 50) - 8, { size: 40, weight: 400, color: 'fg', alpha: clamp(kin * 1.4 - 0.35) });
    c.restore();
    g.save(); g.globalAlpha *= k * 0.6; g.fillStyle = glowInk('accent'); g.fillRect(x - 1, top + 16, 7, (h - 32) * kin); g.restore();
  }
}

/** Words of s in as few lines no wider than maxW as fit, at the given face, size and tracking, balanced (the narrowest
 * width that still needs no more lines), so no word is left alone on the last line. */
function wrap(c: CanvasRenderingContext2D, s: string, maxW: number, fam: string, size: number, track: number): string[] {
  c.save();
  c.font = font(fam, size);
  (c as any).letterSpacing = `${track}px`;
  const greedy = (w: number) => {
    const lines: string[] = [];
    let cur = '';
    for (const word of s.split(' ')) {
      const next = cur ? `${cur} ${word}` : word;
      if (cur && c.measureText(next).width > w) { lines.push(cur); cur = word; } else cur = next;
    }
    if (cur) lines.push(cur);
    return lines;
  };
  const n = greedy(maxW).length;
  let lo = 0, hi = maxW;
  while (hi - lo > 1) { const mid = (lo + hi) / 2; if (greedy(mid).length > n) lo = mid; else hi = mid; }
  const lines = greedy(hi);
  c.restore();
  return lines;
}
