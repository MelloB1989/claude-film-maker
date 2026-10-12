// Typography: font registry (Canvas2D via FontFace + outlines via opentype.js),
// glyph layout, text outlines as Path2D, and point sampling of text for particle effects.
import * as opentype from 'opentype.js';

/**
 * A font face the engine loads: its family name (what Canvas2D and opentype.js know it by), its file, and what it is
 * for. `role` groups faces F picks from: 'display' (headlines; F.display picks by width and weight), 'mono' (code and
 * machine text), 'ui' (chrome), or any role of a film's own (F.role). `url` is relative to the page (the engine's
 * defaults are in public/fonts/; a film's are films/<id>/fonts/..., see film.ts). `features`: OpenType feature settings
 * for the face (Canvas2D has no font-feature-settings of its own).
 */
export interface FontDef {
  family: string;
  url: string;
  role: string;
  weight: number;
  /** Width in % of normal (display faces cut at several widths animate width in steps). */
  width?: number;
  italic?: boolean;
  features?: string;
}

/**
 * Mono text is verbatim: JetBrains Mono's ligatures and contextual alternates would join `--scope` into one long rule,
 * `//` into a single glyph, `->` into an arrow. They are off for every mono face.
 */
export const MONO_FEATURES = '"calt" 0, "liga" 0';

/**
 * The engine's default faces (SIL OFL, docs/CREDITS.md): Bricolage Grotesque in static instances at widths 75, 87.5
 * and 100 % and weights 300/500/600/800 (cut by tools/ film-fonts), JetBrains Mono 400/500/700 and italic 400, Geist
 * 400/500/600.
 */
export function defaultFonts(): FontDef[] {
  const d: FontDef[] = [];
  for (const w of [750, 875, 1000]) for (const wt of [300, 500, 600, 800]) d.push({ family: `Bricolage-${w}-${wt}`, url: `fonts/Bricolage-w${w}-${wt}.ttf`, role: 'display', weight: wt, width: w / 10 });
  for (const wt of [400, 500, 700]) d.push({ family: `JBMono-${wt}`, url: `fonts/JetBrainsMono-${wt}.ttf`, role: 'mono', weight: wt, features: MONO_FEATURES });
  d.push({ family: 'JBMonoItalic-400', url: 'fonts/JetBrainsMonoItalic-400.ttf', role: 'mono', weight: 400, italic: true, features: MONO_FEATURES });
  for (const wt of [400, 500, 600]) d.push({ family: `Geist-${wt}`, url: `fonts/Geist-${wt}.ttf`, role: 'ui', weight: wt });
  return d;
}

let DEFS: FontDef[] = defaultFonts();

/**
 * Add a film's faces (before loadFonts: Engine.init does it from the film's `fonts`). A role the film gives faces for
 * replaces the default faces of that role when `replace` names it ('display', say, to set every headline in the
 * film's own face); otherwise the faces join the role's. A family registered twice is an error.
 */
export function registerFonts(defs: readonly FontDef[], o: { replace?: readonly string[] } = {}) {
  const drop = new Set(o.replace ?? []);
  DEFS = [...DEFS.filter((d) => !drop.has(d.role)), ...defs];
  const seen = new Set<string>();
  for (const d of DEFS) {
    if (seen.has(d.family)) throw new Error(`font family ${d.family} is registered twice`);
    seen.add(d.family);
  }
}

/** Back to the default faces (tests). */
export function resetFonts() {
  DEFS = defaultFonts();
}

/** The faces of a role, or throws naming the roles there are. */
function facesOf(role: string, italic?: boolean): FontDef[] {
  let faces = DEFS.filter((d) => d.role === role);
  if (!faces.length) throw new Error(`no fonts for role '${role}' (roles: ${[...new Set(DEFS.map((d) => d.role))].join(', ')})`);
  if (italic !== undefined) {
    const it = faces.filter((d) => !!d.italic === italic);
    if (it.length) faces = it;
  }
  return faces;
}

/** The face of `faces` nearest the asked width (when given), then weight. */
function pick(faces: FontDef[], weight: number, width?: number): string {
  let best = faces[0]!;
  const score = (d: FontDef) => (width === undefined ? 0 : Math.abs((d.width ?? 100) - width) * 1000) + Math.abs(d.weight - weight);
  for (const d of faces) if (score(d) < score(best)) best = d;
  return best.family;
}

/** Family names by role: the registered face nearest the asked width and weight. */
export const F = {
  /** Headlines: the display face nearest `width` (% of normal) and `weight`. */
  display(width = 100, weight = 600): string {
    return pick(facesOf('display'), weight, width);
  },
  /** Code and machine text: the mono face nearest `weight`, italic when asked (if the role has one). */
  mono(weight = 400, italic = false): string {
    return pick(facesOf('mono', italic), weight);
  },
  /** UI chrome. */
  ui(weight = 400): string {
    return pick(facesOf('ui'), weight);
  },
  /** Any role, a film's own included (`F.role('serif', 400)`). */
  role(role: string, weight = 400, italic?: boolean): string {
    return pick(facesOf(role, italic), weight);
  },
};

/** CSS font string for Canvas2D. */
export const font = (family: string, sizePx: number) => `${sizePx}px "${family}"`;

const otCache = new Map<string, opentype.Font>();
const bufCache = new Map<string, ArrayBuffer>();

/** Every registered family name. */
export const fontFamilies = () => DEFS.map((d) => d.family);
/** Every registered face. */
export const fontDefs = (): readonly FontDef[] => DEFS;

/** The FontFace descriptors loadFonts gives a family (undefined: the font's own defaults). */
export function fontFaceDescriptors(family: string): FontFaceDescriptors | undefined {
  const d = DEFS.find((x) => x.family === family);
  if (!d) throw new Error(`unknown font family: ${family}`);
  return d.features ? { featureSettings: d.features } : undefined;
}

export async function loadFonts(): Promise<void> {
  await Promise.all(
    DEFS.map(async (d) => {
      const r = await fetch(d.url);
      if (!r.ok) throw new Error(`font ${d.family}: ${d.url}: HTTP ${r.status}`);
      const buf = await r.arrayBuffer();
      bufCache.set(d.family, buf);
      const ff = new FontFace(d.family, buf, fontFaceDescriptors(d.family));
      await ff.load();
      document.fonts.add(ff);
    }),
  );
  await document.fonts.ready;
}

/** opentype.js Font for outline work (lazy-parsed). */
export function ot(family: string): opentype.Font {
  let f = otCache.get(family);
  if (!f) {
    const buf = bufCache.get(family);
    if (!buf) throw new Error(`font not loaded: ${family}`);
    f = opentype.parse(buf);
    otCache.set(family, f);
  }
  return f;
}

export interface Glyph {
  ch: string;
  i: number; // char index in string
  x: number; // left edge (px), relative to the text origin
  w: number; // advance width (px)
}
export interface TextLayout {
  text: string;
  family: string;
  size: number;
  width: number; // total advance width
  ascent: number;
  descent: number;
  glyphs: Glyph[];
}

let measureCtx: CanvasRenderingContext2D | null = null;
function mctx() {
  if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d')!;
  return measureCtx;
}

/**
 * Per-glyph horizontal layout with the font's kerning, for drawing glyphs one by one.
 * Glyph i sits at the width of text[0..i] minus its own advance, so the kerning between it and the
 * previous glyph moves *it* (the width of text[0..i) alone leaves that pair out: every kern would land
 * one glyph late, e.g. the Y–o kern of "Your" pushing the u into the o). `w` is the glyph's own advance.
 * `tracking` is extra letter spacing in px.
 */
export function layout(text: string, family: string, size: number, tracking = 0): TextLayout {
  const c = mctx();
  c.font = font(family, size);
  const glyphs: Glyph[] = [];
  const chars = Array.from(text);
  let prefix = '';
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i]!;
    prefix += ch;
    const w = c.measureText(ch).width;
    glyphs.push({ ch, i, x: c.measureText(prefix).width - w + i * tracking, w });
  }
  const m = c.measureText(text || 'M');
  return {
    text, family, size,
    width: (text ? m.width : 0) + Math.max(0, chars.length - 1) * tracking,
    ascent: m.fontBoundingBoxAscent ?? size * 0.8,
    descent: m.fontBoundingBoxDescent ?? size * 0.2,
    glyphs,
  };
}

/**
 * x (px) of glyph `index` in `text` set as one kerned run — where to start drawing text[index..] when a
 * word is split into separately drawn pieces (sung/unsung colours, a clipped wipe). Measuring
 * text[0..index) instead would drop the kern between the two pieces. Past the end: the run's width.
 */
export function glyphX(text: string, index: number, family: string, size: number, tracking = 0): number {
  const chars = Array.from(text);
  if (index <= 0) return 0;
  if (index >= chars.length) return measure(text, family, size, tracking);
  const c = mctx();
  c.font = font(family, size);
  return c.measureText(chars.slice(0, index + 1).join('')).width - c.measureText(chars[index]!).width + index * tracking;
}

/**
 * Typographic punctuation for display text: curly apostrophes and quotes, the ellipsis character.
 * Leading elisions (’cause, ’til, ’em, ’90s) get an apostrophe, not an opening quote.
 */
export function smart(s: string): string {
  return s
    .replace(/\.\.\./g, '…')
    .replace(/(^|[\s([{—–-])'(?=(?:cause|cos|til|em|round|n|tis|twas|\d0s)\b)/gi, '$1’')
    .replace(/(^|[\s([{—–-])'/g, '$1‘')
    .replace(/'/g, '’')
    .replace(/(^|[\s([{—–-])"/g, '$1“')
    .replace(/"/g, '”');
}

/** Typewriter quotes back (mono UI text that shows a line as typed input or code). */
export const plain = (s: string) => s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/…/g, '...');

export function measure(text: string, family: string, size: number, tracking = 0) {
  const c = mctx();
  c.font = font(family, size);
  return c.measureText(text).width + Math.max(0, Array.from(text).length - 1) * tracking;
}

/** Largest font size (<= max) at which text fits in maxWidth. */
export function fitSize(text: string, family: string, maxWidth: number, max = 400, tracking = 0) {
  const w = measure(text, family, 100, tracking * 100 / max);
  return Math.min(max, (100 * maxWidth) / Math.max(1, w));
}

/**
 * Outline of text as opentype commands at (x, baselineY). Glyphs are placed one by one at the
 * Canvas2D-measured positions (so outlines line up with fillText) — this also sidesteps
 * opentype.js's unsupported GSUB lookups that crash font.getPath().
 */
export function textPathCommands(text: string, family: string, size: number, x = 0, y = 0, tracking = 0) {
  const f = ot(family);
  const lay = layout(text, family, size, tracking);
  const cmds: opentype.PathCommand[] = [];
  for (const g of lay.glyphs) cmds.push(...f.charToGlyph(g.ch).getPath(x + g.x, y, size).commands);
  return cmds;
}

/** Outline of text as a Path2D at (x, baselineY). */
export function textPath2D(text: string, family: string, size: number, x = 0, y = 0, tracking = 0): Path2D {
  const p = new opentype.Path();
  p.commands = textPathCommands(text, family, size, x, y, tracking);
  return new Path2D(p.toPathData(3));
}

/**
 * Sample points inside the filled text (rasterized at `size`) on a jittered grid with spacing `step`.
 * Returns points relative to the text origin (left, baseline). Great for "text made of atoms".
 */
export function textPoints(text: string, family: string, size: number, step = 6, seed = 1): { x: number; y: number }[] {
  const lay = layout(text, family, size);
  const pad = Math.ceil(size * 0.3);
  const W = Math.ceil(lay.width + pad * 2), H = Math.ceil(size * 1.6);
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const c = cv.getContext('2d', { willReadFrequently: true })!;
  c.font = font(family, size);
  c.fillStyle = '#fff';
  c.textBaseline = 'alphabetic';
  const base = Math.round(size * 1.15);
  c.fillText(text, pad, base);
  const data = c.getImageData(0, 0, W, H).data;
  const out: { x: number; y: number }[] = [];
  let s = seed >>> 0;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let y = 0; y < H; y += step) {
    for (let x = 0; x < W; x += step) {
      const jx = x + (rnd() - 0.5) * step * 0.8, jy = y + (rnd() - 0.5) * step * 0.8;
      const ix = Math.max(0, Math.min(W - 1, Math.round(jx))), iy = Math.max(0, Math.min(H - 1, Math.round(jy)));
      if (data[(iy * W + ix) * 4 + 3]! > 128) out.push({ x: jx - pad, y: jy - base });
    }
  }
  return out;
}
