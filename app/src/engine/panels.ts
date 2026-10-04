// 2.5D UI panels: a terminal, an editor, a JSON response, a chat or a card, painted by Canvas2D into a texture on a
// plane that scenes place on the Stage, plus the restrained syntax highlighter that colours their code.
//
// The look is monochrome with hierarchy: code is bone at five strengths (keywords brightest and a weight heavier,
// comments faint and italic, punctuation faintest), and colour is only ever semantic: the prompt's `$` in bright
// blood; in the diff gutters `+` in moss and `−` in bright blood (blood proper reads darker than moss on the panel),
// with a 6% moss or blood wash across their rows; a deletion struck through in bright blood; ✔ in moss. JetBrains
// Mono has no ✔, so it is drawn as a path (in the panel's shader, sharp at any zoom); every other glyph comes from the
// three families (a missing one is reported when the panel is built).
//
// Everything is a pure function of time. Lines type in by `at` and `cps` on the output frame grid (frameIdx), so a
// frame shows one state across its whole motion-blur shutter; the canvas is repainted and re-uploaded only when that
// state changes, not once per sub-frame. The mesh is a plane of w/1000 by h/1000 world units, so a panel 2 m from a
// 30° camera shows at about 1 panel px per 1080p px. Its rounded corners and 1 px edge are cut in the fragment shader
// from a signed distance, anti-aliased by its screen-space rate, so they stay clean at any tilt, distance or output
// scale; the canvas behind them is painted at pxScale× (2 by default: 1:1 at 4K, supersampled at 1080p), mipmapped
// and anisotropically filtered.
import * as THREE from 'three';
import { Layer2D } from './gl';
import { HEX, LIN, rgba } from './palette';
import { F, font, ot } from './type';
import { FPS, frameIdx, smootherstep } from './util';

// ---------------------------------------------------------------------------------------------------- tokenizer

export type Lang = 'bash' | 'ts' | 'python' | 'go' | 'rust' | 'json' | 'yaml' | 'md' | 'plain';
export type TokenClass = 'kw' | 'id' | 'str' | 'num' | 'com' | 'punc' | 'prompt' | 'ok';
export interface Token { text: string; cls: TokenClass }

const set = (s: string) => new Set(s.split(' '));
interface CLang { kw: Set<string>; lit: Set<string>; line: string; block: boolean; quotes: string; ident: RegExp; py?: boolean; rust?: boolean }
const IDENT = /[A-Za-z_][\w]*/y;
const C_LANGS: Record<'ts' | 'python' | 'go' | 'rust', CLang> = {
  ts: {
    kw: set('break case catch class const continue debugger default delete do else enum export extends finally for function if implements import in instanceof interface let new of private protected public return static super switch this throw try typeof var void while yield async await as from type declare readonly keyof satisfies'),
    lit: set('true false null undefined NaN Infinity'),
    line: '//', block: true, quotes: '\'"`', ident: /[A-Za-z_$][\w$]*/y,
  },
  python: {
    kw: set('and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'),
    lit: set('True False None'),
    line: '#', block: false, quotes: '\'"', ident: IDENT, py: true,
  },
  go: {
    kw: set('break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var'),
    lit: set('true false nil iota'),
    line: '//', block: true, quotes: '"\'`', ident: IDENT,
  },
  rust: {
    kw: set('as async await break const continue crate dyn else enum extern fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait type unsafe use where while'),
    lit: set('true false'),
    line: '//', block: true, quotes: '"', ident: IDENT, rust: true,
  },
};

const WS = /\s+/y;
const C_NUM = /(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)[\w]*/y;
const JSON_NUM = /-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/y;

/** The match of sticky `re` at i, or null. */
function at(re: RegExp, s: string, i: number): string | null {
  re.lastIndex = i;
  const m = re.exec(s);
  return m ? m[0] : null;
}

/** The code point at i (a surrogate pair whole). */
const cpAt = (s: string, i: number) => String.fromCodePoint(s.codePointAt(i)!);

/** Append a token, merging it into the last one of the same class (never a prompt or a check mark). */
function add(out: Token[], text: string, cls: TokenClass) {
  if (!text) return;
  const last = out[out.length - 1];
  if (last && last.cls === cls && cls !== 'ok' && cls !== 'prompt') last.text += text;
  else out.push({ text, cls });
}

/** End (exclusive) of the quoted string opening at i; to the end of the line if it isn't closed there. */
function endQuote(s: string, i: number, q: string, escapes = true): number {
  const triple = q !== '`' && s.startsWith(q + q + q, i) ? q + q + q : '';
  if (triple) {
    const e = s.indexOf(triple, i + 3);
    return e < 0 ? s.length : e + 3;
  }
  for (let j = i + 1; j < s.length; j++) {
    if (escapes && s[j] === '\\') j++;
    else if (s[j] === q) return j + 1;
  }
  return s.length;
}

function scanC(s: string, L: CLang): Token[] {
  const out: Token[] = [];
  let i = 0, m: string | null;
  while (i < s.length) {
    const ch = s[i]!;
    if ((m = at(WS, s, i))) { add(out, m, 'punc'); i += m.length; continue; }
    if (s.startsWith(L.line, i)) { add(out, s.slice(i), 'com'); break; }
    if (L.block && s.startsWith('/*', i)) {
      const e = s.indexOf('*/', i + 2), j = e < 0 ? s.length : e + 2;
      add(out, s.slice(i, j), 'com'); i = j; continue;
    }
    if (L.py && (m = at(/[rRbBuUfF]{1,2}(?=['"])/y, s, i))) {
      const j = endQuote(s, i + m.length, s[i + m.length]!);
      add(out, s.slice(i, j), 'str'); i = j; continue;
    }
    if (L.rust && ch === "'") { // a char literal, or the tick of a lifetime
      m = at(/'(?:\\.|[^\\'])'/y, s, i);
      if (m) add(out, m, 'str'); else add(out, "'", 'punc');
      i += m ? m.length : 1; continue;
    }
    if (L.quotes.includes(ch)) { const j = endQuote(s, i, ch); add(out, s.slice(i, j), 'str'); i = j; continue; }
    if ((m = at(C_NUM, s, i))) { add(out, m, 'num'); i += m.length; continue; }
    if ((m = at(L.ident, s, i))) { add(out, m, L.kw.has(m) ? 'kw' : L.lit.has(m) ? 'num' : 'id'); i += m.length; continue; }
    const cp = cpAt(s, i);
    add(out, cp, 'punc');
    i += cp.length;
  }
  return out;
}

const BASH_OP = /\|\||&&|>>|[|;&<>()]/y;
const BASH_WORD = /[^\s'"|&;<>()]+/y;

/**
 * A shell line. `$ ` at its start is the prompt; the word in command position (the line's first, and the first after
 * a pipe, `&&`, `||` or `;`) is the keyword; flags recede to the string tone; `#` opens a comment only where a word
 * starts. An indented line is a continuation, with no command word.
 */
function scanBash(s: string): Token[] {
  const out: Token[] = [];
  let i = 0, m: string | null;
  const lead = at(WS, s, 0) ?? '';
  add(out, lead, 'punc');
  i = lead.length;
  let cmd = lead.length === 0;
  if (s.startsWith('$ ', i) || s.slice(i) === '$') { add(out, '$', 'prompt'); i += 1; cmd = true; }
  while (i < s.length) {
    const ch = s[i]!;
    if ((m = at(WS, s, i))) { add(out, m, 'punc'); i += m.length; continue; }
    if (ch === '#' && (i === 0 || /\s/.test(s[i - 1]!))) { add(out, s.slice(i), 'com'); break; }
    if (ch === '"' || ch === "'") { const j = endQuote(s, i, ch, ch === '"'); add(out, s.slice(i, j), 'str'); i = j; cmd = false; continue; }
    if ((m = at(BASH_OP, s, i))) { add(out, m, 'punc'); i += m.length; if (m !== '>' && m !== '<' && m !== '>>' && m !== '(' && m !== ')') cmd = true; continue; }
    if ((m = at(BASH_WORD, s, i))) {
      i += m.length;
      const eq = /^([A-Za-z_]\w*)=(.*)$/s.exec(m);
      if (m === '\\') add(out, m, 'punc');
      else if (eq) { add(out, eq[1]!, 'id'); add(out, '=', 'punc'); add(out, eq[2]!, 'str'); }
      else if (cmd) { add(out, m, 'kw'); cmd = false; }
      else if (m.startsWith('-')) add(out, m, 'str');
      else if (/^\d+(?:\.\d+)?$/.test(m)) add(out, m, 'num');
      else add(out, m, 'id');
      continue;
    }
    const cp = cpAt(s, i);
    add(out, cp, 'punc');
    i += cp.length;
  }
  return out;
}

function scanJson(s: string): Token[] {
  const out: Token[] = [];
  let i = 0, m: string | null;
  while (i < s.length) {
    if ((m = at(WS, s, i))) { add(out, m, 'punc'); i += m.length; continue; }
    if (s[i] === '"') {
      const j = endQuote(s, i, '"');
      add(out, s.slice(i, j), at(/\s*:/y, s, j) ? 'id' : 'str'); // a key is a string followed by a colon
      i = j; continue;
    }
    if ((m = at(JSON_NUM, s, i)) || (m = at(/(?:true|false|null)\b/y, s, i))) { add(out, m, 'num'); i += m.length; continue; }
    const cp = cpAt(s, i);
    add(out, cp, 'punc');
    i += cp.length;
  }
  return out;
}

const YAML_KEY = /(?:"[^"]*"|'[^']*'|[^\s#:'"\-[\]{},][^:#]*?|-[^\s:#][^:#]*?)(?=\s*:(?:\s|$))/y;
const YAML_SCALAR = /(?:[^\s[\]{},#]|(?<=\S)#)+(?:\s+(?:[^\s[\]{},#]|(?<=\S)#)+)*/y;

function yamlScalar(v: string): TokenClass {
  if (/^[-+]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(v)) return 'num';
  if (/^\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+Z?)?$/.test(v)) return 'num';
  if (/^(?:true|false|null|~)$/i.test(v)) return 'num';
  return 'str';
}

function yamlValue(out: Token[], s: string, i: number) {
  let m: string | null;
  while (i < s.length) {
    if ((m = at(WS, s, i))) { add(out, m, 'punc'); i += m.length; continue; }
    if (s[i] === '#' && (i === 0 || /\s/.test(s[i - 1]!))) { add(out, s.slice(i), 'com'); return; }
    if ((m = at(/[[\]{},]/y, s, i))) { add(out, m, 'punc'); i += m.length; continue; }
    if (s[i] === '"' || s[i] === "'") { const j = endQuote(s, i, s[i]!); add(out, s.slice(i, j), 'str'); i = j; continue; }
    if ((m = at(YAML_SCALAR, s, i))) { add(out, m, yamlScalar(m)); i += m.length; continue; }
    const cp = cpAt(s, i);
    add(out, cp, 'punc');
    i += cp.length;
  }
}

/** A YAML line: `key:` in the identifier tone, values by type (numbers and dates as numbers), comments; prose otherwise. */
function scanYaml(s: string): Token[] {
  const out: Token[] = [];
  let i = 0, m: string | null;
  if ((m = at(WS, s, 0))) { add(out, m, 'punc'); i = m.length; }
  const rest = s.slice(i);
  if (rest.startsWith('#')) { add(out, rest, 'com'); return out; }
  if (/^(?:---|\.\.\.)\s*$/.test(rest)) { add(out, rest, 'punc'); return out; }
  while ((m = at(/-(?:\s+|$)/y, s, i))) { add(out, m, 'punc'); i += m.length; } // list items
  const key = at(YAML_KEY, s, i);
  if (key) {
    add(out, key, 'id');
    i += key.length;
    const colon = at(/\s*:/y, s, i)!;
    add(out, colon, 'punc');
    yamlValue(out, s, i + colon.length);
  } else if (i < s.length) add(out, s.slice(i), 'id'); // a line without a key reads as prose
  return out;
}

const MD_INLINE = /\[\[([^\]]+)\]\]|\[([^\]]*)\]\(([^)]*)\)|`([^`]+)`|\*\*([^*]+)\*\*/g;

function mdInline(out: Token[], s: string, base: TokenClass) {
  let last = 0;
  for (const m of s.matchAll(MD_INLINE)) {
    add(out, s.slice(last, m.index), base);
    if (m[1] !== undefined) { add(out, '[[', 'punc'); add(out, m[1], 'str'); add(out, ']]', 'punc'); }
    else if (m[3] !== undefined) { add(out, '[', 'punc'); add(out, m[2]!, base); add(out, '](', 'punc'); add(out, m[3], 'str'); add(out, ')', 'punc'); }
    else if (m[4] !== undefined) { add(out, '`', 'punc'); add(out, m[4], 'str'); add(out, '`', 'punc'); }
    else { add(out, '**', 'punc'); add(out, m[5]!, 'kw'); add(out, '**', 'punc'); }
    last = m.index + m[0].length;
  }
  add(out, s.slice(last), base);
}

/** Markdown: headings carry the weight (their marks recede), wikilinks and code read as strings, prose as identifiers. */
function scanMd(s: string): Token[] {
  const out: Token[] = [];
  const h = /^(\s{0,3}#{1,6})(\s+)(.*)$/s.exec(s);
  if (h) { add(out, h[1]!, 'punc'); add(out, h[2]!, 'punc'); mdInline(out, h[3]!, 'kw'); return out; }
  if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(s)) { add(out, s, 'punc'); return out; }
  const lead = /^(\s*(?:[-*+]|\d+[.)])\s+|\s*>+\s?)?/.exec(s)![0];
  add(out, lead, 'punc');
  mdInline(out, s.slice(lead.length), 'id');
  return out;
}

/** Split every check mark out into its own `ok` token: the font has no ✔, so it is drawn as a path. */
function splitOk(toks: Token[]): Token[] {
  const out: Token[] = [];
  for (const t of toks) {
    if (!/[✔✓]/u.test(t.text)) { out.push(t); continue; }
    for (const part of t.text.split(/([✔✓])/u)) if (part) out.push({ text: part, cls: part === '✔' || part === '✓' ? 'ok' : t.cls });
  }
  return out;
}

/**
 * One line of code as tokens that put back together are exactly the line. Restrained: keywords, identifiers,
 * strings, numbers (and literal constants), comments and punctuation (whitespace included); `prompt` for a shell
 * line's leading `$`, `ok` for a check mark.
 */
export function tokenize(line: string, lang: Lang): Token[] {
  let toks: Token[];
  switch (lang) {
    case 'bash': toks = scanBash(line); break;
    case 'ts': case 'python': case 'go': case 'rust': toks = scanC(line, C_LANGS[lang]); break;
    case 'json': toks = scanJson(line); break;
    case 'yaml': toks = scanYaml(line); break;
    case 'md': toks = scanMd(line); break;
    default: toks = line ? [{ text: line, cls: 'id' }] : [];
  }
  return splitOk(toks);
}

// ---------------------------------------------------------------------------------------------------- timing

export interface PanelLine {
  text: string;
  /**
   * cmd: typed input (in a terminal, at a `$ ` prompt); out: output; add/del: a diff's insertion and deletion (the
   * gutter draws their `+`/`−`, so the text leaves the mark out); ctx: an unchanged line; com: a whole-line comment.
   */
  kind?: 'cmd' | 'out' | 'add' | 'del' | 'ctx' | 'com';
  /** When the line's first character appears (s, song time). Without it the line is there from the start. */
  at?: number;
  /** Characters per second from `at`; without it the line appears whole at `at`. A `del` line is struck instead. */
  cps?: number;
  /**
   * Tones over runs of the line's characters, over the highlighter's look: `fatal: … commits yet` with "commits" in
   * blood. Character indices are code points, as the line types; a later span wins where spans overlap. A check mark
   * stays the panel's moss path.
   */
  spans?: readonly PanelSpan[];
  /** Bands painted on the canvas under the row's text (cite's highlighted lines): see PanelMark. */
  highlight?: PanelMark | readonly PanelMark[];
}

/**
 * A band painted on the canvas under a row's text, as tall as the row: the whole row edge to edge, or (with `from` or
 * `to`) the cells of characters [from, to) (fractional is fine; from defaults to 0, to to the line's end). Bone (a
 * quiet lift of the face), moss or blood (a wash), `alpha` strong (default 0.07 for bone, 0.1 for moss and blood). There
 * throughout, or coming up over `fade` s (default 0.12) from `at` and gone by `until`, on the frame grid.
 */
export interface PanelMark {
  from?: number;
  to?: number;
  tone?: 'bone' | 'moss' | 'blood';
  alpha?: number;
  at?: number;
  until?: number;
  fade?: number;
}

/** A mark's default strength per tone, the selection's (Panel.select), and a timed mark's fade (s). */
const MARK_ALPHA = { bone: 0.07, moss: 0.1, blood: 0.1 } as const;
const SELECT_ALPHA = 0.14;
const MARK_FADE = 0.12;

/**
 * A span's tone: a token class's look (its family and colour: `kw` the brightest and a weight heavier, `com` faint and
 * italic, `prompt` bright blood, …), or an accent on the character's own family: `blood` (the panel's bright blood, as
 * its prompt and its `−`: blood proper reads darker than moss on the panel) or `moss`.
 */
export type PanelTone = Exclude<TokenClass, 'ok'> | 'blood' | 'moss';

/** Characters [from, to) of a line, in a tone. */
export interface PanelSpan {
  from: number;
  to: number;
  tone: PanelTone;
}

export interface PanelSpec {
  kind: 'terminal' | 'editor' | 'json' | 'chat' | 'card';
  title?: string;
  /** Size in panel px: the mesh is w/1000 by h/1000 world units. */
  w: number;
  h: number;
  lang?: Lang;
  gutter?: 'numbers' | 'diff' | 'none';
  lines: PanelLine[];
  /** The number of the first line in a `numbers` gutter (default 1). */
  firstLine?: number;
  /** Code size in panel px (default 28); the chrome scales with it. */
  size?: number;
  /**
   * A window `rows` rows tall (an editor's viewport on a longer file), from under the top padding: rows outside it are
   * not drawn and a row across its edge is cut there, so at rest (a whole number of rows scrolled) no row is ever cut
   * through its glyphs. A panel built without an `h` is as tall as the window and the chrome round it.
   */
  rows?: number;
  /**
   * Rows scrolled up out of the top of the panel (fractional: a smooth scroll), a constant or a pure function of song
   * time (called at the frame grid's time, one state per output frame). A terminal scrolls its newest row into view on
   * its own; this adds to that.
   */
  scroll?: number | ((t: number) => number);
  /**
   * Drawn with the solid objects (three's opaque list) instead of the transparent ones, so glass in front of it (a bead,
   * the needle) refracts it: three's transmission pass copies only the opaque list. Its rounded edge keeps blending as a
   * transparent panel's does (the Stage supersamples rather than multisampling, so alpha-to-coverage would cut it hard).
   * It writes depth like any solid: while it fades (opacity), what lies behind it and draws after it does not show
   * through. Off by default: glass sees through a transparent panel to whatever is behind it.
   */
  opaque?: boolean;
}

/** What a Panel is built from: a PanelSpec whose `h` may be left out when it has `rows` (it is then sized by them). */
export type PanelInput = Omit<PanelSpec, 'h'> & { h?: number };

const EPS = 1e-6;
const glyphs = (s: string) => Array.from(s);
const typing = (l: PanelLine) => l.cps !== undefined && l.cps > 0 && Number.isFinite(l.cps);
/** A typed line's `$ `, shown whole when the terminal is ready rather than typed: 2 characters, or 0. */
const promptLen = (l: PanelLine) => (l.kind === 'cmd' && (l.text.startsWith('$ ') || l.text === '$') ? Math.min(2, l.text.length) : 0);

/**
 * When a line is complete (s): its last character typed (a `$ ` prompt is not typed), its whole text shown, or a
 * deletion's strike through; -Infinity for a line that is there from the start. Chain lines with it.
 */
export function lineEnd(l: PanelLine): number {
  if (l.at === undefined) return -Infinity;
  if (!typing(l)) return l.at;
  const n = glyphs(l.text).length;
  if (l.kind === 'del') return l.at + n / l.cps!;
  return l.at + Math.max(0, n - promptLen(l) - 1) / l.cps!;
}

/** The frame-grid time every panel state is computed at: one state per output frame, whatever the shutter samples. */
const frameT = (t: number) => frameIdx(t) / FPS;

/**
 * Characters of a line typed by song time t (pure; on the frame grid, as Panel.revealed shows them): a typed line's
 * first character lands on `at` and each next one 1/cps later; its `$ ` prompt is shown whole, not typed, and is not
 * counted. 0 for a deletion (it is struck, not typed) and for a line with no `at` (there from the start); all of a
 * line shown whole at `at`.
 */
export function typedCount(l: PanelLine, t: number): number {
  return typedAt(l, frameT(t));
}

/** typedCount at frame time tq. */
function typedAt(l: PanelLine, tq: number): number {
  if (l.kind === 'del' || l.at === undefined || tq < l.at) return 0;
  const n = glyphs(l.text).length, p = promptLen(l);
  return typing(l) ? Math.min(n, p + Math.floor((tq - l.at) * l.cps! + EPS) + 1) - p : n - p;
}

interface LineState {
  /** Characters of the text shown. */
  n: number;
  /** Characters struck through (a deletion; fractional, the strike runs smoothly). */
  struck: number;
  /** When the line starts: its prompt appears, or its first character. */
  start: number;
  /** 0..1: how far its row has opened (a row opens just before its line starts, pushing the rows below down). */
  open: number;
}

const OPEN_S = 0.14;

/** Each line's state at frame time tq; `terminal`: typed input waits at its prompt from when the line before it is done. */
function lineStates(lines: PanelLine[], tq: number, terminal: boolean): LineState[] {
  const out: LineState[] = [];
  let prevEnd = -Infinity;
  for (const l of lines) {
    const n = glyphs(l.text).length;
    let shown = n, struck = 0, start = -Infinity;
    if (l.kind === 'del') {
      struck = l.at === undefined ? n : tq < l.at ? 0 : typing(l) ? Math.min(n, (tq - l.at) * l.cps!) : n;
    } else if (l.at !== undefined) {
      const p = promptLen(l);
      // a terminal's typed input starts (its prompt appears) as soon as the line before it is complete: ready for
      // input. Anywhere else a line starts at `at`: a chat's user turn opens its row as its text starts typing
      start = terminal && l.kind === 'cmd' ? Math.min(l.at, prevEnd) : l.at;
      shown = p && tq >= start ? p : 0;
      if (tq >= l.at) shown = p + typedAt(l, tq);
    }
    const open = start === -Infinity ? 1 : smootherstep(start - OPEN_S, start, tq);
    out.push({ n: shown, struck, start, open });
    prevEnd = lineEnd(l);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------- style

/** Font and colour for each class: bone at five strengths, and the two semantic accents. */
const STYLE: Record<Exclude<TokenClass, 'ok'>, { family: string; color: string }> = {
  kw: { family: F.mono(500), color: rgba('bone', 1) },
  id: { family: F.mono(400), color: rgba('bone', 0.88) },
  num: { family: F.mono(400), color: rgba('bone', 0.95) },
  str: { family: F.mono(400), color: rgba('boneDim') },
  com: { family: F.mono(400, true), color: rgba('boneFaint') },
  punc: { family: F.mono(400), color: rgba('boneFaint') },
  prompt: { family: F.mono(500), color: rgba('bloodBright') },
};

/** The accents a span can tone characters in (on their own family). */
const ACCENT: Record<'blood' | 'moss', string> = { blood: rgba('bloodBright'), moss: rgba('moss') };

/** The design size the chrome is drawn for; the chrome scales with the code size. */
const BASE_PX = 28;
/** Cursor blink: this many frames on, as many off (about 0.53 s each), restarting on each keystroke. */
const BLINK = 16;
/** Check-mark slots drawn by the shader (further ones, and one in a row under the title bar, fall back to a canvas path). */
const CHECKS = 4;
/** The check mark in em, from its cell's left end of the baseline, y up: the short arm, the heel, the long arm. */
const CHECK_PTS: [number, number][] = [[0.05, 0.37], [0.225, 0.075], [0.565, 0.7]];
const CHECK_W = 0.12; // stroke width (em): a heavy check, a little bolder than the 500 weight's stems

const VERT = /* glsl */ `
  uniform vec2 uSize;
  varying vec2 vPx;
  void main() {
    vPx = vec2(uv.x, 1.0 - uv.y) * uSize; // panel px, from the top left, y down
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;

const FRAG = /* glsl */ `
  uniform sampler2D uMap;
  uniform bool uHasMap;
  uniform vec2 uSize;
  uniform float uRadius, uOpacity;
  uniform vec3 uFace, uEdge, uEdgeHi, uMoss;
  uniform vec4 uChecks[${CHECKS}]; // x, y (cell's left end of the baseline, px), size (px), on (0..1)
  uniform float uHalo;
  varying vec2 vPx;

  float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
  }
  float sdSeg(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    return length(pa - ba * clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0));
  }
  // coverage of the region d < 0, ramped over the screen pixel just inside it: the plane's own edge (d = 0 on its
  // straight sides) is never a hard polygon edge
  float inside(float d, float aa) { return clamp(-d / aa, 0.0, 1.0); }

  void main() {
    vec2 half_ = 0.5 * uSize;
    float d = sdRoundRect(vPx - half_, half_, uRadius);
    float aa = max(fwidth(d), 1e-4);
    float cov = inside(d, aa);
    if (cov <= 0.0) discard;
    vec3 face = uFace;
    if (gl_FrontFacing && uHasMap) face = texture2D(uMap, vec2(vPx.x / uSize.x, 1.0 - vPx.y / uSize.y)).rgb;
    // check marks: two capsules each, in moss, with a faint halo of moss light around them
    for (int i = 0; i < ${CHECKS}; i++) {
      vec4 k = uChecks[i];
      if (!gl_FrontFacing || k.w <= 0.0) continue; // uniform control flow: fwidth below stays defined
      vec2 q = (vPx - k.xy) / k.z * vec2(1.0, -1.0);
      float e = (min(sdSeg(q, vec2(${CHECK_PTS[0]!.join(', ')}), vec2(${CHECK_PTS[1]!.join(', ')})),
                     sdSeg(q, vec2(${CHECK_PTS[1]!.join(', ')}), vec2(${CHECK_PTS[2]!.join(', ')}))) - ${(CHECK_W / 2).toFixed(4)}) * k.z;
      float c = clamp(0.5 - e / max(fwidth(e), 1e-4), 0.0, 1.0) * k.w; // centred: a stroke keeps its weight
      vec2 mid = (q - vec2(0.3, 0.38)) * k.z;
      face += uMoss * uHalo * k.w * exp(-dot(mid, mid) / (k.z * k.z * 0.45));
      face = mix(face, uMoss, c);
    }
    // the 1 px edge: the band 0 > d > -1, lit a little along the top as if by a key from above
    float inner = inside(d + 1.0, aa);
    vec3 edge = mix(uEdge, uEdgeHi, 1.0 - smoothstep(0.0, 2.0 * uRadius, vPx.y));
    vec3 col = (face * inner + edge * (cov - inner)) / cov;
    gl_FragColor = vec4(col, cov * uOpacity);
  }`;

/**
 * The drop shadow: a soft darkening around the panel's shape, a little below it, on a quad just behind the panel. It
 * writes no depth, so the DoF reads the surfaces it falls on, and it sorts between a panel and whatever lies behind
 * it: on the void it only deepens the ink, on a panel further back it separates the two.
 */
const SHADOW_VERT = /* glsl */ `
  uniform vec2 uSize;
  uniform float uPad;
  varying vec2 vPx;
  void main() {
    vPx = vec2(uv.x, 1.0 - uv.y) * (uSize + 2.0 * uPad) - uPad;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;

const SHADOW_FRAG = /* glsl */ `
  uniform vec2 uSize, uOffset;
  uniform float uRadius, uBlur, uOpacity;
  varying vec2 vPx;
  float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
  }
  void main() {
    vec2 half_ = 0.5 * uSize;
    float d = sdRoundRect(vPx - half_ - uOffset, half_, uRadius);
    float a = 1.0 - smoothstep(-0.35 * uBlur, uBlur, d);
    gl_FragColor = vec4(0.0, 0.0, 0.0, a * a * uOpacity);
  }`;

/** Shadow: its offset (px, down), softness (px) and strength. */
const SHADOW = { offset: 12, blur: 64, opacity: 0.6 };

/** sRGB-space mix of two palette colours, as linear RGB (the edge highlight: ruleStrong lifted toward bone). */
function mixLin(a: keyof typeof HEX, b: keyof typeof HEX, k: number) {
  const pa = parseInt(HEX[a].slice(1), 16), pb = parseInt(HEX[b].slice(1), 16);
  const ch = (sh: number) => {
    const s = (((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k) / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return new THREE.Vector3(ch(16), ch(8), ch(0));
}

// ---------------------------------------------------------------------------------------------------- panel

/**
 * A panel's layout in panel px (from its top left, y down): the code's metrics and the chrome's, all fixed by its spec.
 * Rows of `lineH` start under the title bar and `padTop`; a row's text starts at `textX` (after the side padding, the
 * numbers gutter and the diff's sign column) on the mono grid of `adv`, its baseline half a row plus 0.365 em down
 * from the row's top (the cap height centred in the row).
 */
export interface PanelLayout {
  /** The chrome's scale: the code size over the 28 px it is designed at. */
  s: number;
  /** Code size (panel px per em). */
  size: number;
  /** One mono cell's advance: 0.6 em (JetBrains Mono's every advance). */
  adv: number;
  /** A row's height: 1.6 em, to the half px. */
  lineH: number;
  /** The title bar's height (a card's label; a card without a title has none). */
  bar: number;
  /** The side padding, and the padding above the first row and below the last. */
  padX: number;
  padTop: number;
  padBottom: number;
  /** The numbers gutter's width and the diff's sign column's (0 without them). */
  numW: number;
  signW: number;
  /** Where a row's text starts: padX + numW + signW. */
  textX: number;
}

/** What a panel's layout depends on: its kind, code size, title (a card's label), gutter and lines (their count and kinds). */
export type PanelLayoutSpec = Pick<PanelSpec, 'kind' | 'title' | 'gutter' | 'firstLine' | 'size'> & { lines: readonly Pick<PanelLine, 'kind'>[] };

/** The gutter a spec draws: as given, or an editor's line numbers. */
const gutterOf = (spec: Pick<PanelSpec, 'kind' | 'gutter'>) => spec.gutter ?? (spec.kind === 'editor' ? 'numbers' : 'none');

/**
 * The layout a panel of this spec has (Panel.layout), before there is one: it needs neither w nor h, so a scene can
 * size a panel by its rows (an editor's window of N rows is bar + padTop + N·lineH + its bottom margin tall).
 */
export function panelLayout(spec: PanelLayoutSpec): PanelLayout {
  const size = spec.size ?? BASE_PX, s = size / BASE_PX;
  const adv = size * 0.6; // JetBrains Mono: every advance is 600 of 1000 units
  const lineH = Math.round(size * 1.6 * 2) / 2;
  const bar = spec.kind === 'card' ? (spec.title ? Math.round(58 * s) : 0) : Math.round(52 * s);
  const gutter = gutterOf(spec);
  const hasDiff = spec.lines.some((l) => l.kind === 'add' || l.kind === 'del');
  const last = (spec.firstLine ?? 1) + spec.lines.length - 1;
  const numW = gutter === 'numbers' ? Math.max(2, String(last).length) * adv + Math.round(22 * s) : 0;
  const signW = gutter === 'diff' || (gutter === 'numbers' && hasDiff) ? 2 * adv : 0;
  const padX = Math.round(28 * s);
  return { s, size, adv, lineH, bar, padX, padTop: Math.round(20 * s), padBottom: Math.round(22 * s), numW, signW, textX: padX + numW + signW };
}

export interface PanelFrame {
  tq: number;
  st: LineState[];
  /** Row tops (px), after the terminal's scroll. */
  top: number[];
  /** Line numbers in a `numbers` gutter (0: none). */
  num: number[];
  /** Whether each line shows anything: text, or the prompt it waits at. */
  started: boolean[];
  cursor: { i: number; col: number; on: boolean; block: boolean } | null;
  /** Check marks (each cell's left end of the baseline, px): in the shader's slots, and on the canvas. */
  checks: { slot: [number, number][]; canvas: [number, number][] };
  /**
   * The bands painted under rows' text, in order (highlights, then the selection): line i's row from x0 to x1 (px), in
   * a CSS colour; `cells`: a run of characters (its corners rounded), else the whole row.
   */
  marks: { i: number; x0: number; x1: number; color: string; cells: boolean }[];
  key: string;
}

export class Panel {
  mesh: THREE.Mesh;
  /** The soft drop shadow, a child of the mesh (hide it, or set its material's uOpacity, per shot). */
  shadow: THREE.Mesh;
  /** 0..1: the panel's opacity (fades; the shadow follows). */
  opacity = 1;
  private mat: THREE.ShaderMaterial;
  private shadowMat: THREE.ShaderMaterial;
  private layer: Layer2D | null = null;
  private g: PanelLayout;
  private chars: string[][];
  private cls: TokenClass[][];
  /** Each character's span tone, if a span tones it. */
  private tones: (PanelTone | undefined)[][];
  /** Each line's highlights. */
  private hl: PanelMark[][];
  /** The selection a scene set for this frame (select()). */
  private selection: { line: number; from: number; to: number; alpha: number } | null = null;
  /** A terminal's typed line with no `$ ` of its own gets one drawn before it (not a continuation after a `\`). */
  private chromePrompt: boolean[];
  private key = '';

  /** The spec, its `h` resolved (from `rows`, when it was left out). */
  readonly spec: PanelSpec;

  constructor(input: PanelInput, private pxScale = 2) {
    this.g = panelLayout(input);
    if (input.rows !== undefined && !(input.rows > 0 && Number.isFinite(input.rows))) throw new RangeError(`Panel: rows must be a count > 0, not ${input.rows}`);
    if (input.h === undefined && input.rows === undefined) throw new Error('Panel: needs an h, or rows to be sized by');
    const spec = (this.spec = input.h === undefined ? { ...input, h: this.g.bar + this.g.padTop + input.rows! * this.g.lineH + this.g.padBottom } : (input as PanelSpec));
    const { w, h } = spec;
    const lines = spec.lines;
    this.chars = lines.map((l) => glyphs(l.text));
    this.cls = lines.map((l, i) => {
      const lang = this.langOf(i);
      const toks = l.kind === 'com' ? [{ text: l.text, cls: 'com' as const }] : tokenize(l.text, lang);
      return toks.flatMap((t) => glyphs(t.text).map(() => t.cls));
    });
    this.tones = lines.map((l, i) => {
      const n = this.chars[i]!.length, tones: (PanelTone | undefined)[] = [];
      for (const sp of l.spans ?? []) {
        if (!Number.isInteger(sp.from) || !Number.isInteger(sp.to) || sp.from < 0 || sp.to > n || sp.from >= sp.to) {
          throw new RangeError(`Panel: line ${i}'s span [${sp.from}, ${sp.to}) is not a run of its ${n} characters`);
        }
        for (let k = sp.from; k < sp.to; k++) tones[k] = sp.tone;
      }
      return tones;
    });
    this.hl = lines.map((l, i) => {
      const n = this.chars[i]!.length, marks = l.highlight === undefined ? [] : Array.isArray(l.highlight) ? [...l.highlight] : [l.highlight as PanelMark];
      for (const m of marks) {
        const from = m.from ?? 0, to = m.to ?? n;
        if (!(from >= 0 && from <= to && to <= n)) throw new RangeError(`Panel: line ${i}'s highlight [${m.from}, ${m.to}) is not a run of its ${n} characters`);
      }
      return marks;
    });
    this.chromePrompt = lines.map((l, i) => {
      const prev = lines[i - 1];
      const continues = prev?.kind === 'cmd' && /\\\s*$/.test(prev.text);
      return spec.kind === 'terminal' && l.kind === 'cmd' && !promptLen(l) && !continues;
    });
    this.mat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: {
        uMap: { value: null }, uHasMap: { value: false }, uSize: { value: new THREE.Vector2(w, h) },
        uRadius: { value: 16 }, uOpacity: { value: 1 },
        uFace: { value: new THREE.Vector3(...LIN.panel) }, uEdge: { value: new THREE.Vector3(...LIN.ruleStrong) },
        uEdgeHi: { value: mixLin('ruleStrong', 'bone', 0.22) }, uMoss: { value: new THREE.Vector3(...LIN.moss) },
        uChecks: { value: Array.from({ length: CHECKS }, () => new THREE.Vector4()) }, uHalo: { value: 0.035 },
      },
      transparent: true,
      side: THREE.DoubleSide,
    });
    if (spec.opaque) {
      // in the opaque list, with the blend NormalBlending gives a transparent panel (three turns blending off for an
      // opaque material only when it is NormalBlending)
      const m = this.mat;
      m.transparent = false;
      m.blending = THREE.CustomBlending;
      m.blendEquation = THREE.AddEquation;
      m.blendSrc = THREE.SrcAlphaFactor;
      m.blendDst = THREE.OneMinusSrcAlphaFactor;
      m.blendSrcAlpha = THREE.OneFactor;
      m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
    }
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(w / 1000, h / 1000), this.mat);
    this.verifyGlyphs();
    const pad = SHADOW.blur + SHADOW.offset;
    this.shadowMat = new THREE.ShaderMaterial({
      vertexShader: SHADOW_VERT,
      fragmentShader: SHADOW_FRAG,
      uniforms: {
        uSize: { value: new THREE.Vector2(w, h) }, uPad: { value: pad }, uOffset: { value: new THREE.Vector2(0, SHADOW.offset) },
        uRadius: { value: 16 }, uBlur: { value: SHADOW.blur }, uOpacity: { value: SHADOW.opacity },
      },
      transparent: true,
      depthWrite: false,
    });
    this.shadow = new THREE.Mesh(new THREE.PlaneGeometry((w + 2 * pad) / 1000, (h + 2 * pad) / 1000), this.shadowMat);
    this.shadow.position.z = -0.004; // just behind the face
    this.mesh.add(this.shadow);
  }

  /** Characters shown per line at t (pure). A deletion's text is always shown: `at`/cps time its strike instead. */
  revealed(t: number): number[] {
    return lineStates(this.spec.lines, frameT(t), this.spec.kind === 'terminal').map((s) => s.n);
  }

  /** Characters struck through per line at t (pure): a `del` line's strike, fractional; 0 for other lines. */
  struck(t: number): number[] {
    return lineStates(this.spec.lines, frameT(t), this.spec.kind === 'terminal').map((s) => s.struck);
  }

  // ------------------------------------------------------------------------------------------------ geometry
  //
  // Where things are on the panel, in panel px from its top left (y down), so a scene can put light, a caret, a glyph
  // actor or a chip on a row without copying the layout. Without t, the layout with every row open (no row opening, no
  // scroll): where a row sits once the rows above it have opened. With t, where the panel draws it in the frame at t
  // (rows opening as their lines start, a terminal scrolling its newest row into view), one state per output frame as
  // draw(t) paints it. A line index the panel doesn't have throws.

  /** The panel's layout (its code's metrics and its chrome's). */
  get layout(): Readonly<PanelLayout> {
    return this.g;
  }

  /** One mono cell's advance (px). */
  get adv() {
    return this.g.adv;
  }

  /** A row's height (px). */
  get lineH() {
    return this.g.lineH;
  }

  /** Line `line`'s row top (px): with every row above it open, or as drawn at t. */
  rowTop(line: number, t?: number): number {
    this.checkLine(line);
    if (t !== undefined) return this.topsAt(t)[line]!;
    const g = this.g;
    let y = 0;
    for (let i = 0; i < line; i++) y += g.lineH;
    return g.bar + g.padTop + y;
  }

  /**
   * Where line `line`'s own text starts on its baseline (px): after the gutter (or, in a terminal, after the `$ ` it
   * draws before a typed line without one; a chat's user turn on the right). With t, as drawn at t.
   */
  textOrigin(line: number, t?: number): { x: number; baseline: number } {
    const top = this.rowTop(line, t), g = this.g;
    return { x: this.textX(line) + (this.chromePrompt[line] ? 2 * g.adv : 0), baseline: top + g.lineH / 2 + 0.365 * g.size };
  }

  /**
   * The left end of the baseline of character `col` of line `line` (px): where the panel draws it, on the mono grid.
   * `col` may be fractional (a caret between cells, a typing head) or past the text's end. With t, as drawn at t.
   */
  cellOrigin(line: number, col: number, t?: number): { x: number; baseline: number } {
    const o = this.textOrigin(line, t);
    return { x: o.x + col * this.g.adv, baseline: o.baseline };
  }

  /**
   * The band rows are drawn in (px from the top): with `rows`, the window from under the top padding, rows·lineH tall;
   * without, the face under the title bar.
   */
  get viewport(): { top: number; bottom: number } {
    const g = this.g, rows = this.spec.rows;
    return rows === undefined ? { top: g.bar, bottom: this.spec.h } : { top: g.bar + g.padTop, bottom: g.bar + g.padTop + rows * g.lineH };
  }

  /** Whether a row whose top is at `top` reaches into the band rows are drawn in (paint draws it, cut at its edges). */
  private inView(top: number) {
    const g = this.g;
    if (this.spec.rows === undefined) return !(top > this.spec.h || top + g.lineH < g.bar);
    const v = this.viewport;
    return top < v.bottom && top + g.lineH > v.top;
  }

  /** Whether a row whose top is at `top` lies whole in that band (no edge cuts it). */
  private wholeInView(top: number) {
    if (this.spec.rows === undefined) return top >= this.g.bar;
    const v = this.viewport;
    return top >= v.top && top + this.g.lineH <= v.bottom;
  }

  private checkLine(line: number) {
    if (!Number.isInteger(line) || line < 0 || line >= this.spec.lines.length) {
      throw new RangeError(`Panel: no line ${line} (it has ${this.spec.lines.length})`);
    }
  }

  /** The last frame's row tops the geometry read, by frame time (a scene asks for several rows a frame). */
  private tops: { tq: number; top: number[] } | null = null;

  private topsAt(t: number): number[] {
    const tq = frameT(t);
    if (this.tops?.tq !== tq) this.tops = { tq, top: this.rows(tq).top };
    return this.tops.top;
  }

  /** Repaint for time t: lines typed in by `at`/cps, the cursor blinking on the frame grid. Cheap when nothing changed. */
  draw(t: number) {
    this.mat.uniforms.uOpacity!.value = this.opacity;
    this.shadowMat.uniforms.uOpacity!.value = SHADOW.opacity * this.opacity;
    const fr = this.frame(t);
    if (fr.key === this.key && this.layer) return;
    this.key = fr.key;
    this.paint(fr);
    this.layer!.upload();
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.mat.dispose();
    this.shadow.geometry.dispose();
    this.shadowMat.dispose();
    this.layer?.dispose();
    this.layer = null;
  }

  // ------------------------------------------------------------------------------------------------ layout

  private langOf(i: number): Lang {
    const { kind, lines } = this.spec;
    const l = lines[i]!;
    if (kind === 'terminal') return l.kind === 'cmd' ? this.spec.lang ?? 'bash' : 'plain';
    if (kind === 'chat') return 'plain';
    const lang = this.spec.lang ?? (kind === 'json' ? 'json' : 'plain');
    if (lang === 'md') { // YAML front matter: from a first `---` line to the next
      if (lines[0]?.text.trim() === '---' && i > 0) {
        const close = lines.findIndex((x, j) => j > 0 && x.text.trim() === '---');
        if (close < 0 || i < close) return 'yaml';
      }
    }
    return lang;
  }

  /** Each line's state at frame time tq, and its row's top: each row as tall as it has opened, a terminal scrolled. */
  private rows(tq: number): { st: LineState[]; top: number[] } {
    const { spec, g } = this;
    const st = lineStates(spec.lines, tq, spec.kind === 'terminal');
    // rows: each as tall as it has opened; a terminal scrolls to keep its newest row in view
    const y0 = g.bar + g.padTop, avail = spec.rows !== undefined ? spec.rows * g.lineH : spec.h - y0 - g.padBottom;
    const top: number[] = [];
    let y = 0;
    for (const s of st) { top.push(y); y += g.lineH * s.open; }
    let scroll = spec.kind === 'terminal' ? Math.max(0, y - avail) : 0;
    if (spec.scroll !== undefined) scroll += (typeof spec.scroll === 'function' ? spec.scroll(tq) : spec.scroll) * g.lineH;
    for (let i = 0; i < top.length; i++) top[i] = y0 + top[i]! - scroll;
    return { st, top };
  }

  /** Everything the canvas shows at t (pure), and a key that changes exactly when it does. */
  frame(t: number): PanelFrame {
    const tq = frameT(t);
    const { spec, g } = this;
    const lines = spec.lines;
    const { st, top } = this.rows(tq);
    // line numbers (a `numbers` gutter) count the rows that are open; a deletion gives its number up once its strike
    // begins (it is no longer in the file), and the rows below renumber
    const num: number[] = [];
    let n = (spec.firstLine ?? 1) - 1;
    const numbered = gutterOf(spec) === 'numbers';
    for (let i = 0; i < lines.length; i++) {
      const counted = numbered && !(lines[i]!.kind === 'del' && st[i]!.struck > 0) && st[i]!.open > 0.5;
      if (counted) n++;
      num.push(counted ? n : 0);
    }
    const started = st.map((s, i) => this.started(i, s, tq));
    // check marks, in line order. A shader slot draws over the whole face, so it takes a check whose row is wholly below
    // the title bar (the first CHECKS of them); the rest, and a check in a row scrolled up under the bar, are drawn on the
    // canvas inside the rows' clip, cut at the bar as the row's text is
    const slot: [number, number][] = [], canvas: [number, number][] = [];
    lines.forEach((_, i) => {
      const s = st[i]!, rowTop = top[i]!;
      if (s.open <= 0 || !this.inView(rowTop)) return; // a row paint() skips
      const base = rowTop + g.lineH / 2 + 0.365 * g.size, x = this.textX(i) + (this.chromePrompt[i] ? 2 * g.adv : 0);
      for (let k = 0; k < s.n; k++) {
        if (this.cls[i]![k] === 'ok') (this.wholeInView(rowTop) && slot.length < CHECKS ? slot : canvas).push([x + k * g.adv, base]);
      }
    });
    const cursor = this.cursor(st, tq);
    const marks = this.marks(st, top, tq);
    // the key is what paint() reads, exact (numbers print as the shortest string that reads back the same double): two
    // states a rounded key took for one (a row 1e-4 open and a shut one) would repaint in any order, not in sequence
    const key = JSON.stringify([st.map((s) => [s.n, s.struck, s.open]), top, num, started, cursor, slot, canvas, marks]);
    return { tq, st, top, num, started, cursor, checks: { slot, canvas }, marks, key };
  }

  /** Whether line i shows anything at the frame: text, or the prompt it waits at. */
  private started(i: number, s: LineState, tq: number) {
    return s.n > 0 || ((promptLen(this.spec.lines[i]!) > 0 || this.chromePrompt[i]!) && tq >= s.start);
  }

  /**
   * The cursor. A terminal's block sits after the newest line if it is typed input; elsewhere a bar follows the
   * newest typed line (and leaves when streamed output is done). Solid while keys land, then blinking.
   */
  private cursor(st: LineState[], tq: number): PanelFrame['cursor'] {
    const lines = this.spec.lines, term = this.spec.kind === 'terminal';
    let i = -1;
    for (let j = 0; j < lines.length; j++) {
      const l = lines[j]!;
      if (term ? this.started(j, st[j]!, tq) : typing(l) && l.kind !== 'del' && tq >= l.at!) i = j;
    }
    if (i < 0) return null;
    const l = lines[i]!, s = st[i]!;
    if (term && l.kind !== 'cmd') return null;
    const end = lineEnd(l);
    if (!term && l.kind === 'out' && tq > end) return null;
    const anchor = l.at !== undefined && tq >= l.at ? Math.min(tq, end) : Number.isFinite(s.start) ? s.start : 0;
    const phase = frameIdx(tq) - frameIdx(anchor);
    const on = ((phase % (2 * BLINK)) + 2 * BLINK) % (2 * BLINK) < BLINK;
    return { i, col: (this.chromePrompt[i] ? 2 : 0) + s.n, on, block: term };
  }

  // ------------------------------------------------------------------------------------------------ paint

  private canvas(): CanvasRenderingContext2D {
    if (!this.layer) {
      this.layer = new Layer2D(this.spec.w, this.spec.h, this.pxScale);
      const tex = this.layer.texture;
      tex.generateMipmaps = true;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      tex.anisotropy = 16; // three clamps it to what the GPU offers
      this.mat.uniforms.uMap!.value = tex;
      this.mat.uniforms.uHasMap!.value = true;
    }
    return this.layer.ctx;
  }

  private paint(fr: PanelFrame) {
    const c = this.canvas();
    const { spec, g } = this;
    const { w } = spec;
    this.layer!.clear(HEX.panel);
    c.textBaseline = 'alphabetic';
    c.textAlign = 'left';

    c.save();
    c.beginPath();
    const view = this.viewport;
    c.rect(0, view.top, w, view.bottom - view.top);
    c.clip();
    spec.lines.forEach((l, i) => {
      const s = fr.st[i]!, top = fr.top[i]!, rowH = g.lineH * s.open;
      if (s.open <= 0 || !this.inView(top)) return;
      const base = top + g.lineH / 2 + 0.365 * g.size; // the cap height centred in the row
      const struckOn = l.kind === 'del' && s.struck > 0;
      // the diff: a wash across the row and the mark in the gutter
      if (l.kind === 'add' || struckOn) {
        const key = l.kind === 'add' ? 'moss' : 'blood';
        c.fillStyle = rgba(key, 0.06);
        c.fillRect(0, top, w, rowH);
        if (g.signW && s.open > 0.5) {
          c.font = font(F.mono(500), g.size);
          c.fillStyle = rgba(key === 'moss' ? 'moss' : 'bloodBright'); // blood proper reads darker than moss on the panel
          c.fillText(l.kind === 'add' ? '+' : '−', g.padX + g.numW, base);
        }
      }
      // highlights and the selection, under the text
      for (const m of fr.marks) {
        if (m.i !== i) continue;
        c.fillStyle = m.color;
        if (!m.cells) c.fillRect(m.x0, top, m.x1 - m.x0, rowH);
        else {
          c.beginPath();
          c.roundRect(m.x0, top, m.x1 - m.x0, rowH, Math.min(Math.round(3 * g.s), rowH / 2, (m.x1 - m.x0) / 2));
          c.fill();
        }
      }
      if (fr.num[i]) {
        c.font = font(F.mono(400), g.size);
        c.fillStyle = rgba('boneFaint', 0.85);
        c.textAlign = 'right';
        c.fillText(String(fr.num[i]), g.padX + g.numW - Math.round(22 * g.s), base);
        c.textAlign = 'left';
      }
      const x0 = this.textX(i);
      if (this.bubble(i) && s.n > 0) { // a chat's user turn: a quiet bubble on the right, the text typing inside it
        const pad = Math.round(16 * g.s), inset = Math.round(4 * g.s);
        c.fillStyle = HEX.panel2;
        c.beginPath();
        c.roundRect(x0 - pad, top + inset, this.chars[i]!.length * g.adv + 2 * pad, g.lineH - 2 * inset, Math.round(12 * g.s));
        c.fill();
      }
      if (this.chromePrompt[i] && fr.started[i]) {
        c.font = font(STYLE.prompt.family, g.size);
        c.fillStyle = STYLE.prompt.color;
        c.fillText('$', x0, base);
      }
      const xt = x0 + (this.chromePrompt[i] ? 2 * g.adv : 0);
      this.text(c, i, s.n, xt, base, l.kind === 'del' ? s.struck : 0);
      if (struckOn) {
        const lead = this.chars[i]!.findIndex((ch) => !/\s/.test(ch));
        const from = Math.max(0, lead), to = Math.min(s.struck, this.chars[i]!.length);
        if (to > from) {
          c.fillStyle = rgba('bloodBright');
          c.fillRect(xt + from * g.adv, base - 0.3 * g.size - g.s, (to - from) * g.adv, 2 * g.s);
        }
      }
    });
    this.canvasChecks(c, fr.checks.canvas);
    c.restore();

    if (fr.cursor) {
      const { i, col, on, block } = fr.cursor;
      const base = fr.top[i]! + g.lineH / 2 + 0.365 * g.size;
      if (on && (this.spec.rows === undefined ? base > g.bar : this.wholeInView(fr.top[i]!))) {
        c.fillStyle = rgba('bone', block ? 0.82 : 0.95);
        const x = this.textX(i) + col * g.adv, y = base - 0.98 * g.size, ch = 1.25 * g.size;
        c.fillRect(x, y, block ? g.adv : Math.max(2, 0.08 * g.size), ch);
      }
    }
    this.chrome(c);
    this.setChecks(fr.checks);
  }

  /** Whether line i is a chat's user turn, drawn in a bubble on the right. */
  private bubble(i: number) {
    return this.spec.kind === 'chat' && this.spec.lines[i]!.kind === 'cmd';
  }

  /** Where line i's text (or its drawn prompt) starts. */
  private textX(i: number) {
    const g = this.g;
    if (this.bubble(i)) return this.spec.w - g.padX - Math.round(16 * g.s) - this.chars[i]!.length * g.adv;
    return g.textX;
  }

  /** Line i's first n characters from x at the baseline, one glyph at a time on the mono grid (no ligatures). */
  private text(c: CanvasRenderingContext2D, i: number, n: number, x: number, base: number, struck: number) {
    const g = this.g, chars = this.chars[i]!, cls = this.cls[i]!;
    let cur = '';
    for (let k = 0; k < n; k++) {
      const ch = chars[k]!, kc = cls[k]!, cx = x + k * g.adv;
      if (kc === 'ok') continue; // a check mark: frame() placed it
      if (/\s/.test(ch)) continue;
      const st = this.styleOf(i, k);
      if (cur !== st.family) { c.font = font(st.family, g.size); cur = st.family; }
      c.fillStyle = st.color;
      c.globalAlpha = k < struck ? 0.62 : 1; // the struck part of a deletion recedes
      c.fillText(ch, cx, base);
    }
    c.globalAlpha = 1;
  }

  /**
   * The selection for the frames drawn from now on: characters [from, to) of line `line` (fractional is fine: a
   * selection running across the line), painted under the text in bone at `alpha`; `select(null)` clears it. A scene
   * sets it from t every frame, before draw(t), as it sets `opacity`.
   */
  select(line: number | null, from = 0, to?: number, alpha = SELECT_ALPHA) {
    if (line === null) {
      this.selection = null;
      return;
    }
    this.checkLine(line);
    const end = to ?? this.chars[line]!.length;
    if (!(from >= 0 && from <= end && end <= this.chars[line]!.length)) throw new RangeError(`Panel: no run [${from}, ${to}) on line ${line}`);
    this.selection = { line, from, to: end, alpha };
  }

  /** The bands under the rows' text at frame time tq: each drawn row's highlights at their strength then, and the selection. */
  private marks(st: LineState[], top: number[], tq: number): PanelFrame['marks'] {
    const out: PanelFrame['marks'] = [], g = this.g;
    const run = (i: number, from: number, to: number) => {
      const x = this.textX(i) + (this.chromePrompt[i] ? 2 * g.adv : 0);
      return { x0: x + from * g.adv, x1: x + to * g.adv };
    };
    const strength = (a: number) => Math.round(a * 1e4) / 1e4; // (far under 8-bit alpha: a fade's frames key alike)
    this.hl.forEach((marks, i) => {
      if (!marks.length || st[i]!.open <= 0 || !this.inView(top[i]!)) return;
      for (const m of marks) {
        const tone = m.tone ?? 'bone', fade = m.fade ?? MARK_FADE;
        let a = m.alpha ?? MARK_ALPHA[tone];
        if (m.at !== undefined) a *= smootherstep(m.at, m.at + fade, tq);
        if (m.until !== undefined) a *= 1 - smootherstep(m.until - fade, m.until, tq);
        a = strength(a);
        if (a <= 0) continue;
        const cells = m.from !== undefined || m.to !== undefined;
        const { x0, x1 } = cells ? run(i, m.from ?? 0, m.to ?? this.chars[i]!.length) : { x0: 0, x1: this.spec.w };
        if (x1 > x0) out.push({ i, x0, x1, color: rgba(tone, a), cells });
      }
    });
    const sel = this.selection;
    if (sel && sel.to > sel.from && st[sel.line]!.open > 0 && this.inView(top[sel.line]!)) {
      out.push({ i: sel.line, ...run(sel.line, sel.from, sel.to), color: rgba('bone', strength(sel.alpha)), cells: true });
    }
    return out;
  }

  /**
   * The family and colour the panel draws character `col` of line `line` in: its span's tone over the highlighter's
   * look. Null for one it doesn't draw as text (a blank; a check mark, drawn as a moss path).
   */
  charStyle(line: number, col: number): { family: string; color: string } | null {
    this.checkLine(line);
    const chars = this.chars[line]!;
    if (!Number.isInteger(col) || col < 0 || col >= chars.length) throw new RangeError(`Panel: line ${line} has no character ${col}`);
    if (this.cls[line]![col] === 'ok' || /\s/.test(chars[col]!)) return null;
    const { family, color } = this.styleOf(line, col);
    return { family, color };
  }

  /** Character k of line i's look (not a check mark): its token class's, or its span's tone. */
  private styleOf(i: number, k: number): { family: string; color: string } {
    const kc = this.cls[i]![k] as Exclude<TokenClass, 'ok'>, tone = this.tones[i]![k];
    if (tone === undefined) return STYLE[kc];
    if (tone === 'blood' || tone === 'moss') return { family: STYLE[kc].family, color: ACCENT[tone] };
    return STYLE[tone];
  }

  /**
   * Report every character a line would draw from a family that has no glyph for it (the browser would fill it from
   * a fallback font, outside the film's three families). Once, at construction: parsing a font is slow.
   */
  private verifyGlyphs() {
    const seen = new Set<string>();
    this.chars.forEach((chars, i) => chars.forEach((ch, k) => {
      const kc = this.cls[i]![k]!;
      if (kc === 'ok' || /\s/.test(ch)) return;
      const family = this.styleOf(i, k).family;
      if (seen.has(family + ch)) return;
      seen.add(family + ch);
      try {
        if (ot(family).charToGlyphIndex(ch) === 0) console.warn(`panels: ${family} has no glyph for ${JSON.stringify(ch)} (U+${ch.codePointAt(0)!.toString(16).toUpperCase()})`);
      } catch { /* the fonts are not loaded (bun tests): nothing to check against */ }
    }));
  }

  /** Title bar (three muted dots, a centred title, a hairline) or a card's label. */
  private chrome(c: CanvasRenderingContext2D) {
    const { spec, g } = this;
    if (!g.bar) return;
    c.fillStyle = HEX.panel;
    c.fillRect(0, 0, spec.w, g.bar);
    c.fillStyle = HEX.rule;
    c.fillRect(0, g.bar - 1, spec.w, 1);
    if (spec.kind === 'card') {
      if (spec.title) { // a card's label is copy (TypeScript, Go, …): never under the 16 px floor for mono labels
        const size = Math.max(16, Math.round(0.72 * g.size));
        c.font = font(F.ui(500), size);
        c.fillStyle = rgba('boneDim');
        c.fillText(spec.title, g.padX, g.bar / 2 + 0.36 * size);
      }
      return;
    }
    c.fillStyle = HEX.ruleStrong;
    for (let k = 0; k < 3; k++) {
      c.beginPath();
      c.arc(Math.round(24 * g.s) + k * Math.round(20 * g.s), g.bar / 2, 6 * g.s, 0, Math.PI * 2);
      c.fill();
    }
    if (spec.title) {
      const size = Math.max(16, Math.round(18 * g.s));
      c.font = font(F.ui(500), size);
      c.fillStyle = rgba('boneDim', 0.9);
      c.textAlign = 'center';
      c.fillText(spec.title, spec.w / 2, g.bar / 2 + 0.36 * size);
      c.textAlign = 'left';
    }
  }

  /** Check marks to the shader's slots (sharp at any zoom). */
  private setChecks(checks: PanelFrame['checks']) {
    const u = this.mat.uniforms.uChecks!.value as THREE.Vector4[];
    const size = this.g.size;
    u.forEach((v, k) => {
      const p = checks.slot[k];
      if (p) v.set(p[0], p[1], size, 1); else v.set(0, 0, 0, 0);
    });
  }

  /** Check marks without a slot, as canvas paths (paint() draws them inside the rows' clip). */
  private canvasChecks(c: CanvasRenderingContext2D, pts: [number, number][]) {
    if (!pts.length) return;
    const size = this.g.size;
    c.strokeStyle = rgba('moss');
    c.lineWidth = CHECK_W * size;
    c.lineCap = c.lineJoin = 'round';
    for (const [x, y] of pts) {
      c.beginPath();
      CHECK_PTS.forEach(([px, py], j) => (j ? c.lineTo : c.moveTo).call(c, x + px * size, y - py * size));
      c.stroke();
    }
  }
}
