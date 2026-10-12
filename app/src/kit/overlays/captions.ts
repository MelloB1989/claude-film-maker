// Captions: social-video captions from the film's voiceover (vo.json, or captions written in film.ts), a few words at a
// time, every word lit on its spoken onset. An overlay: transparent by default, drawn over whatever shot is on screen.
//
// Params:
//   style 'karaoke'    'karaoke' (the chunk shows whole, the current word lit on an accent pill that slides word to
//                      word), 'pop' (each word pops in on its onset, the current one in the accent), 'line' (the
//                      whole line, a fill sweeping through it as it is spoken)
//   position 'bottom'  'bottom' | 'center' | 'top' (clear of a vertical feed's UI; safe-area aware); y overrides (fraction)
//   maxWords           words a chunk holds (3 in a vertical frame, 6 otherwise; 'line': the whole line)
//   size               reference px (68 vertical, 50 otherwise); role 'display', width 100, weight 800; uppercase
//   color 'fg', highlight 'accent', dim 0.45 (alpha of words not yet spoken: karaoke), pill true
//   box false          a translucent plate behind the chunk; shadow true (a soft dark drop for footage)
//   scenes             only the lines of these shots (default: every line inside the overlay's window)
//   lead 0.06, hold 0.7, release 0.5 (s: before a chunk, after its last word, after a word for the highlight)
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { THEME, rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { spring } from '../../engine/motion';
import { VO } from '../../engine/vo';
import { clamp, ease, lerp, prog } from '../../engine/util';
import * as fx from '../text/fx';
import { family, layLine, type LaidLine } from '../text/layout';

export type CaptionStyle = 'karaoke' | 'pop' | 'line';

/** A chunk as set: its lines, and where each of its words sits. */
interface SetChunk {
  chunk: fx.Chunk;
  lines: LaidLine[];
  /** Per word: its line, left and right edges (px from the line's left). */
  at: { line: number; x0: number; x1: number }[];
  size: number;
}

export class Captions extends Scene2D {
  protected override defaultBackground: Background = 'none';
  private chunks: SetChunk[] = [];
  private fam = '';

  override init() {
    const tall = isTall(), u = this.u;
    const style = this.p<CaptionStyle>('style', 'karaoke');
    const size = this.p('size', tall ? 68 : 50) * u;
    const upper = this.p('uppercase', false);
    this.fam = family({ role: this.p('role', 'display'), width: this.p('width', 100), weight: this.p('weight', 800) });
    const maxW = this.p('maxWidth', tall ? 0.82 : 0.7) * W;
    const scenes = this.p<string[] | null>('scenes', null);
    const { start, end } = this.ctx;
    const lines = this.ctx.vo.lines.filter((l) => (scenes ? scenes.includes(l.scene) : l.start >= start - 1e-3 && l.start < end));
    const chunks = fx.captionChunks(lines.map((l) => ({ words: l.words.map((w) => ({ ...w, w: upper ? w.w.toUpperCase() : w.w })) })), {
      maxWords: this.p('maxWords', style === 'line' ? 99 : tall ? 3 : 6),
      maxChars: this.p('maxChars', style === 'line' ? 999 : tall ? 22 : 42),
      // a line caption keeps its line whole; the others break early at a phrase's end
      minWords: style === 'line' ? 999 : 2,
      lead: this.p('lead', 0.06),
      hold: this.p('hold', 0.7),
    });
    const track = this.p('tracking', -0.01) * size;
    this.chunks = chunks.map((chunk) => {
      const words = chunk.words.map((w) => w.w);
      // two balanced lines at most; shrunk if one word alone is too wide
      let rows = fx.wrapBalanced(words, (s) => layLine(s, this.fam, size, track).width, maxW);
      let px = size;
      if (rows.length > 2) rows = fx.wrapBalanced(words, (s) => layLine(s, this.fam, size, track).width, (maxW * rows.length) / 2);
      const widest = Math.max(...rows.map((r) => layLine(r, this.fam, size, track).width));
      if (widest > maxW) px = size * (maxW / widest);
      const laid = rows.map((r) => layLine(r, this.fam, px, (track * px) / size));
      const at: SetChunk['at'] = [];
      laid.forEach((l, li) => l.words.forEach((w) => at.push({ line: li, x0: w.x0, x1: w.x1 })));
      return { chunk, lines: laid, at, size: px };
    });
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const t = f.t;
    const i = fx.chunkAt(this.chunks.map((s) => s.chunk), t);
    if (i < 0) return;
    const S = this.chunks[i]!, ch = S.chunk, size = S.size;
    const tall = isTall();
    const style = this.p<CaptionStyle>('style', 'karaoke');
    const m = S.lines[0]!.m;
    const step = size * 1.12;
    const blockH = m.cap * size + (S.lines.length - 1) * step;
    const pos = this.p<'bottom' | 'center' | 'top'>('position', 'bottom');
    const yParam = this.p<number | null>('y', null);
    // the block's top (cap top of its first line)
    const top = yParam !== null ? yParam * H - blockH / 2
      : pos === 'top' ? (tall ? 0.15 : 0.09) * H
        : pos === 'center' ? H / 2 - blockH / 2
          : (tall ? 0.735 : 0.9) * H - blockH;
    const xs = S.lines.map((l) => W / 2 - l.width / 2);
    const ys = S.lines.map((_, li) => top + m.cap * size + li * step);
    // in and out: the chunk pops in at its start, and fades if nothing follows straight after
    const next = this.chunks[i + 1]?.chunk;
    const gapAfter = !next || next.start > ch.end + 1e-3;
    const inK = spring(t - ch.start, 6, 0.75);
    const outK = gapAfter ? 1 - prog(t, ch.end - 0.12, ch.end, ease.inCubic) : 1;
    const alpha = clamp(prog(t, ch.start, ch.start + 0.08)) * outK;
    if (alpha <= 0.002) return;
    const scale = style === 'pop' ? 1 : lerp(0.94, 1, clamp(inK));
    const cx = W / 2, cy = top + blockH / 2;
    c.save();
    c.translate(cx, cy);
    c.scale(scale, scale);
    c.translate(-cx, -cy);
    c.globalAlpha = alpha;
    c.font = font(this.fam, size);
    const fg = this.p('color', 'fg'), hi = this.p('highlight', 'accent');

    if (this.p('box', false)) {
      const padX = 0.42 * size, padY = 0.34 * size;
      const w = Math.max(...S.lines.map((l) => l.width));
      c.fillStyle = rgba('surface', 0.82);
      c.beginPath();
      c.roundRect(cx - w / 2 - padX, top - padY, w + 2 * padX, blockH + m.desc * size + 2 * padY, 0.28 * size);
      c.fill();
    }
    if (this.p('shadow', true)) {
      c.shadowColor = 'rgba(0,0,0,0.55)';
      c.shadowBlur = 0.22 * size;
      c.shadowOffsetY = 0.04 * size;
    }
    const words = ch.words;
    const cur = fx.currentWord(words, t, this.p('release', 0.5));
    const g = this.glowLevel > 0 ? this.glow : null;
    if (g) {
      g.translate(cx, cy);
      g.scale(scale, scale);
      g.translate(-cx, -cy);
      g.globalAlpha = alpha;
    }

    if (style === 'karaoke' && this.p('pill', true)) this.pill(c, g, S, xs, ys, t, cur, hi);

    words.forEach((w, k) => {
      const a = S.at[k]!, L = S.lines[a.line]!;
      const x = xs[a.line]! + a.x0, y = ys[a.line]!;
      if (style === 'line') {
        // dim, then filled as it is spoken
        const p = VO.wordProgress({ ...w, line: 0, index: k, gi: 0 }, t);
        c.fillStyle = rgba(fg, this.p('dim', 0.38));
        this.fill(c, w.w, x, y, L.track);
        if (p > 0) {
          c.save();
          c.beginPath();
          c.rect(x - 0.1 * size, y - 1.2 * size, 0.1 * size + (a.x1 - a.x0) * p + (p >= 1 ? 0.2 * size : 0), 1.6 * size);
          c.clip();
          c.fillStyle = rgba(fg);
          this.fill(c, w.w, x, y, L.track);
          c.restore();
        }
        return;
      }
      if (style === 'pop') {
        if (t < w.start - 0.02) return;
        const k2 = spring(t - (w.start - 0.02), 6, 0.6);
        const wx = x + (a.x1 - a.x0) / 2, wy = y - (L.m.cap * size) / 2;
        c.save();
        c.translate(wx, wy + (1 - clamp(k2)) * 0.18 * size);
        c.scale(lerp(0.55, 1, k2), lerp(0.55, 1, k2));
        c.translate(-wx, -wy);
        c.globalAlpha *= clamp(k2 * 2.5);
        c.fillStyle = rgba(k === cur ? hi : fg);
        this.fill(c, w.w, x, y, L.track);
        c.restore();
        if (g && k === cur) {
          g.save();
          g.font = c.font;
          g.translate(wx, wy);
          g.scale(lerp(0.55, 1, k2), lerp(0.55, 1, k2));
          g.translate(-wx, -wy);
          g.fillStyle = glowInk(hi, 0.4);
          this.fill(g, w.w, x, y, L.track);
          g.restore();
        }
        return;
      }
      // karaoke: spoken words full, the current one on its pill, the rest dim
      const onPill = k === cur && this.p('pill', true);
      const ink = onPill ? (THEME.kind === 'dark' ? fg : 'bg') : k === cur ? hi : fg;
      c.fillStyle = rgba(ink, t >= w.start ? 1 : this.p('dim', 0.45));
      this.fill(c, w.w, x, y, L.track);
    });
    c.restore();
  }

  /** The karaoke pill: an accent capsule behind the current word, sliding from the last word to this one. */
  private pill(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D | null, S: SetChunk, xs: number[], ys: number[], t: number, cur: number, hi: string) {
    if (cur < 0) return;
    const size = S.size, m = S.lines[0]!.m;
    const rect = (k: number) => {
      const a = S.at[k]!;
      const padX = 0.2 * size, padT = 0.2 * size, padB = 0.24 * size;
      return { x: xs[a.line]! + a.x0 - padX, y: ys[a.line]! - m.cap * size - padT, w: a.x1 - a.x0 + 2 * padX, h: m.cap * size + padT + padB };
    };
    const w = S.chunk.words[cur]!;
    const to = rect(cur);
    const from = cur > 0 && S.at[cur - 1]!.line === S.at[cur]!.line ? rect(cur - 1) : { ...to, x: to.x + to.w / 2, w: 0 };
    const k = clamp(spring(t - w.start, 7, 0.82), 0, 1.06);
    const r = { x: lerp(from.x, to.x, k), y: lerp(from.y, to.y, k), w: lerp(from.w, to.w, k), h: to.h };
    const radius = Math.min(r.h / 2, 0.22 * size);
    c.save();
    c.shadowColor = 'transparent';
    c.fillStyle = rgba(hi);
    c.beginPath();
    c.roundRect(r.x, r.y, Math.max(0, r.w), r.h, radius);
    c.fill();
    c.restore();
    if (g) {
      g.save();
      g.fillStyle = glowInk(hi, 0.26);
      g.beginPath();
      g.roundRect(r.x, r.y, Math.max(0, r.w), r.h, radius);
      g.fill();
      // the word on the pill stays crisp: no light where its letters are
      const a = S.at[cur]!, L = S.lines[a.line]!;
      g.globalCompositeOperation = 'destination-out';
      g.font = font(this.fam, size);
      g.fillStyle = '#000';
      this.fill(g, w.w, xs[a.line]! + a.x0, ys[a.line]!, L.track);
      g.restore();
    }
  }

  private fill(c: CanvasRenderingContext2D, text: string, x: number, y: number, track: number) {
    if (Math.abs(track) > 1e-3) c.letterSpacing = `${track}px`;
    c.fillText(text, x, y);
    if (Math.abs(track) > 1e-3) c.letterSpacing = '0px';
  }
}

export default Captions;
