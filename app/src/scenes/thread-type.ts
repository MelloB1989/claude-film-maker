// The flat type of scene `thread`: L01 "Your agent forgets." in the lower-left third, and L02's "back to" above the
// thread, right of centre. Bricolage, bone at 70% (spec §4 01), kerned glyph by glyph (layout()), drawn on the scene's
// 2D layer. Pure functions of time: every word appears on its spoken onset, and "forgets" comes apart as she says it:
// the gaps open letter by letter from the f as her voice reaches each one, then each letter drifts off, softens and
// lets go, like the fibres lifting off the fraying thread above it.
import { layout } from '../engine/type';
import { rgba } from '../engine/palette';
import { clamp, ease, hash, prog } from '../engine/util';
import { spring } from '../engine/motion';

export interface WordAt {
  text: string;
  at: number;
  end: number;
}

/** A word's entrance: it rises a few px into place and fades up on the house spring, landing on its onset. */
export function reveal(t: number, at: number): { a: number; dy: number } {
  const k = spring(t - at + 0.02);
  return { a: clamp(prog(t, at - 0.02, at + 0.14, ease.outCubic)), dy: (1 - k) * 12 };
}

export interface LineOpts {
  /** Opacity of the line (bone at 70%). */
  alpha?: number;
  /** Index of the word that comes apart as it is spoken. */
  loosen?: number;
  /** When the loosened word's letters have all let go, and when the rest of the line starts and ends fading. */
  gone?: number;
  fadeFrom?: number;
  fadeTo?: number;
}

/** How far each letter of a loosening word has come apart at t: extra x (em), drift (em), turn, blur (px), opacity. */
export function loosen(t: number, i: number, n: number, at: number, end: number, gone: number) {
  const ti = at + (i / n) * (end - at) * 0.9; // when her voice reaches the letter
  let dx = 0;
  for (let j = 1; j <= i; j++) {
    const tj = at + (j / n) * (end - at) * 0.9;
    dx += 0.3 * ease.outCubic(prog(t, tj, tj + 0.85)); // the gap before letter j opens as she reaches it
  }
  const d = ease.outQuad(prog(t, ti, gone)); // it lets go as her voice reaches it, then drifts slower and slower
  const h1 = hash(i, 11) - 0.5, h2 = hash(i, 23) - 0.5;
  return {
    dx: dx + d * (0.18 + 0.25 * h1),
    dy: d * (0.55 * h2 - 0.12),
    rot: d * h1 * 0.35,
    blur: d * 6,
    a: 1 - ease.inOutCubic(prog(t, ti + 0.35 + 0.1 * hash(i, 37), gone)),
  };
}

/**
 * Draw a line of words (each with its onset) at (x, baseline y), kerned as one run. Each word appears on its onset;
 * the word `loosen` comes apart as it is spoken (see loosen()), and the rest of the line fades out with it.
 */
export function drawLine(c: CanvasRenderingContext2D, t: number, words: WordAt[], family: string, size: number,
  x: number, y: number, o: LineOpts = {}) {
  const text = words.map((w) => w.text).join(' ');
  const lay = layout(text, family, size);
  const alpha = o.alpha ?? 0.7;
  const lineFade = 1 - prog(t, o.fadeFrom ?? Infinity, o.fadeTo ?? Infinity, ease.inOutCubic);
  c.font = `${size}px "${family}"`;
  c.textBaseline = 'alphabetic';
  c.fillStyle = rgba('bone');
  let start = 0;
  words.forEach((w, wi) => {
    const n = Array.from(w.text).length;
    const glyphs = lay.glyphs.slice(start, start + n);
    start += n + 1;
    const r = reveal(t, w.at);
    if (r.a <= 0) return;
    glyphs.forEach((g, i) => {
      let gx = x + g.x, gy = y + r.dy, rot = 0, blur = 0, a = alpha * r.a;
      if (o.loosen === wi) {
        const l = loosen(t, i, n, w.at, w.end, o.gone ?? w.end + 0.6);
        gx += l.dx * size;
        gy += l.dy * size;
        rot = l.rot;
        blur = l.blur;
        a *= l.a;
      } else a *= lineFade;
      if (a <= 0.002) return;
      c.save();
      c.globalAlpha = a;
      if (blur > 0.25) c.filter = `blur(${blur.toFixed(2)}px)`;
      if (rot) {
        c.translate(gx + g.w / 2, gy - size * 0.35);
        c.rotate(rot);
        c.fillText(g.ch, -g.w / 2, size * 0.35);
      } else c.fillText(g.ch, gx, gy);
      c.restore();
    });
  });
  return lay;
}
