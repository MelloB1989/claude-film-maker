// Text layout for the 2D kit blocks (Canvas2D measuring, so call it from init() or render(), after the fonts load):
// a face by role, width and weight; a face's vertical metrics (cap height, x-height, descender) as fractions of its
// size; a line laid out glyph by glyph with its words' spans (type.ts layout(): kerned, tracked); balanced wrapping and
// fitting to a measure; and drawing a run with tracking.
import { F, font, layout, measure } from '../../engine/type';
import { fitScale, wordsOf, wrapBalanced } from './fx';

/** Which face: a role ('display', 'mono', 'ui', or a film's own), and for display faces a width (% of normal). */
export interface FaceSpec {
  role?: string;
  /** Display faces: width in % of normal (the defaults are cut at 75, 87.5 and 100). */
  width?: number;
  weight?: number;
  italic?: boolean;
}

/** The registered family for a face spec. */
export function family(f: FaceSpec): string {
  const role = f.role ?? 'display';
  if (role === 'display') return F.display(f.width ?? 100, f.weight ?? 800);
  if (role === 'mono') return F.mono(f.weight ?? 500, f.italic ?? false);
  if (role === 'ui') return F.ui(f.weight ?? 500);
  return F.role(role, f.weight ?? 400, f.italic);
}

/** A face's vertical metrics as fractions of its size: cap height, x-height, descender, ascender. */
export interface FaceMetrics { cap: number; x: number; desc: number; asc: number }

const metricsCache = new Map<string, FaceMetrics>();
let mc: CanvasRenderingContext2D | null = null;

/** The vertical metrics of a family (measured once, from the ink of H, x and g). */
export function metrics(fam: string): FaceMetrics {
  const hit = metricsCache.get(fam);
  if (hit) return hit;
  mc ??= document.createElement('canvas').getContext('2d')!;
  mc.font = font(fam, 100);
  const H = mc.measureText('H'), x = mc.measureText('x'), g = mc.measureText('gjpqy');
  const m: FaceMetrics = {
    cap: (H.actualBoundingBoxAscent || 70) / 100,
    x: (x.actualBoundingBoxAscent || 50) / 100,
    desc: (g.actualBoundingBoxDescent || 22) / 100,
    asc: (H.fontBoundingBoxAscent || 95) / 100,
  };
  metricsCache.set(fam, m);
  return m;
}

/** A glyph of a laid line: its character, left edge and advance (px, from the line's left). */
export interface LGlyph { ch: string; x: number; w: number }
/** A word of a laid line: its text, its glyphs [i0, i1), its left and right edges (px). */
export interface LWord { w: string; i0: number; i1: number; x0: number; x1: number }

/** A line set in one face and size: its glyphs and words (kerned, tracked), width and metrics. */
export interface LaidLine {
  text: string;
  family: string;
  size: number;
  /** Tracking, px. */
  track: number;
  width: number;
  glyphs: LGlyph[];
  words: LWord[];
  m: FaceMetrics;
}

/** Lay out a line: kerned glyph positions (type.ts layout), with `track` px between glyphs, and its words' spans. */
export function layLine(text: string, fam: string, size: number, track = 0): LaidLine {
  const lay = layout(text, fam, size, track);
  const glyphs = lay.glyphs.map((g) => ({ ch: g.ch, x: g.x, w: g.w }));
  const words = wordsOf(text).map(({ w, i0, i1 }) => ({ w, i0, i1, x0: glyphs[i0]!.x, x1: glyphs[i1 - 1]!.x + glyphs[i1 - 1]!.w }));
  return { text, family: fam, size, track, width: lay.width, glyphs, words, m: metrics(fam) };
}

/**
 * A text set to a measure: wrapped into balanced lines no wider than `maxW` at `size` (when `wrap`), then every line
 * shrunk alike so the widest fits ('shrink'), or grown or shrunk to fill it ('fill', at most `maxSize`), or left
 * ('none'). Tracking is in em and scales with the size. Returns the lines' texts and the size they are set at.
 */
export function setToMeasure(text: string, fam: string, size: number, maxW: number, o: { tracking?: number; wrap?: boolean; fit?: 'shrink' | 'fill' | 'none'; maxSize?: number } = {}): { lines: string[]; size: number } {
  const tr = o.tracking ?? 0;
  const widthAt = (s: string, px: number) => measure(s, fam, px, tr * px);
  const words = wordsOf(text).map((w) => w.w);
  const lines = o.wrap === false || words.length <= 1 ? [text.trim()] : wrapBalanced(words, (s) => widthAt(s, size), maxW);
  const widest = Math.max(1, ...lines.map((l) => widthAt(l, size)));
  const fit = o.fit ?? 'shrink';
  let px = size;
  if (fit === 'shrink') px = size * fitScale(widest, maxW);
  else if (fit === 'fill') px = Math.min(o.maxSize ?? size * 3, (size * maxW) / widest);
  return { lines, size: px };
}

/** Draw `text` with `track` px of letter spacing at (x, y), left aligned (tracking follows the context's transform). */
export function fillTracked(c: CanvasRenderingContext2D, text: string, x: number, y: number, track: number) {
  if (Math.abs(track) > 1e-3) c.letterSpacing = `${track}px`;
  c.fillText(text, x, y);
  if (Math.abs(track) > 1e-3) c.letterSpacing = '0px';
}

/** Width of a run drawn with fillTracked (no trailing spacing). */
export const trackedWidth = (text: string, fam: string, size: number, track: number) => measure(text, fam, size, track);
