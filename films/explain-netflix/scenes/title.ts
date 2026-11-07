// Title: a buffering spinner that resolves into a play mark, then the title lands line by line, "300 million"
// counting up in the accent, under a playback bar whose buffer runs well ahead of the playhead (the film's motif).
// params: kicker, line1, count (300), countSuffix (' million'), line2tail (' people'), line3
import { NfScene, rev, land, text, kicker, rgba, glowInk, W, H, TAU, clamp, ease, lerp, F, font, type Frame } from './lib';

export default class Title extends NfScene {
  protected nominal = 2.8;

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number) {
    const cx = 330, cy = H * 0.46;
    // spinner → play
    const morph = rev(t, 0.22, 0.35, ease.inOutCubic);
    const spinA = 1 - morph;
    if (spinA > 0) {
      for (let i = 0; i < 12; i++) {
        const ang = (i / 12) * TAU + t * 5.5;
        const fadeI = ((i / 12) + 1) % 1;
        const r = 64;
        c.fillStyle = rgba('fg', (0.12 + 0.6 * fadeI) * spinA * rev(t, 0, 0.12));
        c.beginPath(); c.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, 6, 0, TAU); c.fill();
      }
    }
    const pk = land(t, 0.28, 0.6);
    if (pk > 0) {
      const R = 92 * pk;
      g.strokeStyle = glowInk('accent', 0.9); g.lineWidth = 6;
      g.beginPath(); g.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + TAU * clamp(morph)); g.stroke();
      c.strokeStyle = rgba('accentBright'); c.lineWidth = 5;
      c.beginPath(); c.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + TAU * clamp(morph)); c.stroke();
      c.fillStyle = rgba('fg', pk);
      c.beginPath(); c.moveTo(cx - 26 * pk, cy - 36 * pk); c.lineTo(cx + 40 * pk, cy); c.lineTo(cx - 26 * pk, cy + 36 * pk); c.closePath(); c.fill();
    }
    // title
    const x = 520;
    const k0 = rev(t, 0.3, 0.4);
    kicker(c, this.p('kicker', 'System design in 60 seconds'), x, 300 + (1 - k0) * 12, k0, 'accent2');
    const lines = [
      { s: this.p('line1', 'How Netflix streams to'), at: 0.36 },
      { s: '', at: 0.48 },
      { s: this.p('line3', 'without buffering.'), at: 0.6 },
    ];
    const size = 104, lh = 120;
    for (let i = 0; i < 3; i++) {
      const L = lines[i]!, k = rev(t, L.at, 0.55, ease.outQuint);
      const y = 420 + i * lh + (1 - k) * 46;
      if (i === 1) {
        // "300 million people": the number counts up and glows
        const n = Math.round(this.p('count', 300) * ease.outExpo(clamp((t - 0.48) / 0.9)));
        const num = `${n}${this.p('countSuffix', '+ million')}`;
        c.save(); c.globalAlpha *= k;
        c.font = font(F.display(87.5, 800), size);
        const wNum = c.measureText(`${this.p('count', 300)}${this.p('countSuffix', '+ million')}`).width;
        text(c, num, x, y, { size, weight: 800, width: 87.5, face: 'display', color: 'accentBright' });
        g.save(); g.globalAlpha *= k * 0.35; g.font = c.font; g.fillStyle = glowInk('accent'); g.fillText(num, x, y); g.restore();
        text(c, this.p('line2tail', ' members'), x + wNum, y, { size, weight: 800, width: 87.5, face: 'display' });
        c.restore();
      } else {
        text(c, L.s, x, y, { size, weight: 800, width: 87.5, face: 'display', alpha: k });
      }
    }
    // the underline under "without buffering."
    const ku = rev(t, 0.95, 0.5, ease.inOutCubic);
    if (ku > 0) {
      c.font = font(F.display(87.5, 800), size);
      const wl = c.measureText(lines[2]!.s).width;
      c.fillStyle = rgba('accent'); c.fillRect(x, 420 + 2 * lh + 22, wl * ku, 6);
      g.fillStyle = glowInk('accent', 0.7); g.fillRect(x, 420 + 2 * lh + 20, wl * ku, 10);
    }
    // playback bar: buffered range far ahead of the playhead
    const kb = rev(t, 0.7, 0.6);
    if (kb > 0) {
      const bx = 520, by = 860, bw = W - bx - 160;
      const play = 0.08 + 0.05 * clamp((t - 0.7) / 2);
      const buf = lerp(play, 0.86, ease.outCubic(clamp((t - 0.8) / 1.2)));
      c.save(); g.save(); c.globalAlpha *= kb; g.globalAlpha *= kb;
      c.fillStyle = 'rgba(255,230,210,0.12)'; c.fillRect(bx, by, bw * kb, 6);
      c.fillStyle = 'rgba(255,230,210,0.35)'; c.fillRect(bx, by, bw * buf * kb, 6);
      c.fillStyle = rgba('accent'); c.fillRect(bx, by, bw * play * kb, 6);
      g.fillStyle = glowInk('accent', 0.6); g.fillRect(bx, by - 2, bw * play * kb, 10);
      c.beginPath(); c.arc(bx + bw * play * kb, by + 3, 11, 0, TAU); c.fillStyle = rgba('accentBright'); c.fill();
      text(c, 'buffered ahead', bx + bw * buf * kb - 6, by - 18, { size: 22, color: 'fgDim', align: 'right', alpha: rev(t, 1.3, 0.4) });
      c.restore(); g.restore();
    }
  }
}
export type { Frame };
