// KineticText: the hero type block. One or more lines of display type that land word by word (or glyph by glyph, or
// line by line) on a stagger, on the beat grid, at given times, or exactly on the shot's spoken words, with an optional
// mono kicker above and a sub line below. Each line has its own face, size (fitted and wrapped to the measure), colour
// and reveal; emphasis words land in the accent and glow; diff lines strike through (−) or glow in accent2 (+).
//
// Params (all optional but the text; sizes in reference px of a 1080 px short side, positions as fractions of the frame):
//   text | lines      the copy: a string ('\n' splits lines) or an array of strings / line specs { text, ...style }
//   style (block default, per line overridable):
//     role 'display'   face role ('display' | 'mono' | 'ui' | a film's own); width (display: 75 | 87.5 | 100), weight
//     size 132         font size; fit 'shrink' (to maxWidth) | 'fill' (grow or shrink to it) | 'none'
//     tracking         em (display default -0.02); leading (baseline step in em, display 1.0); uppercase
//     color 'fg'       a palette role or #hex
//     reveal 'rise'    'rise' | 'slam' | 'blur' | 'track' | 'typewriter' | 'scramble' | 'wipe' | 'fade' | 'ghost'
//     unit 'word'      'word' | 'glyph' | 'line'
//     stagger          s between units (word 0.075, glyph 0.03, line 0.16); every: beats between units instead
//     emphasis         words to land in the accent with a glow
//   per line only: at (when its first unit lands: s after the shot start, { beat }, { bar }), diff '-' | '+'
//   align 'center'     'left' | 'center' | 'right'; x, y (anchor, fractions of W and H); valign 'center' | 'top' | 'bottom'
//   maxWidth           fraction of W (0.84; 0.86 vertical); wrap true (balanced wrapping before shrinking)
//   sync 'stagger'     'stagger' | 'beats' (units on the grid, `every` beats apart) | 'vo' (on the shot's spoken words)
//   delay 0.1          when the first unit lands (TimeRef: s, { beat }, { bar }), for 'stagger' and 'beats'
//   cps 30             typewriter glyphs per second; caret true; seed (scramble)
//   emphasisColor 'accent' | 'accent2'; emphasisStyle 'glow' | 'marker' (a highlighter sweep) | 'underline'
//   kicker             a mono label above; kickerColor 'accent'; kickerReveal 'scramble'; kickerAt; kickerDot true
//   sub                a line below; subColor 'fgDim'; subSize; subRole 'ui'; subAt; subReveal 'fade'
//   exit 'none'        'fade' | 'rise' | 'blur' | 'sink' over exitDur (0.3 s) at the shot's end
//   push 0.025         a slow scale about the anchor over the shot (0: none)
//   background, glow   (Scene2D)
import { Scene2D, glowInk, isTall, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { font } from '../../engine/type';
import { onBeat, wordTimes } from '../../engine/motion';
import { clamp, ease, lerp, prog } from '../../engine/util';
import type { Spoken } from './fx';
import * as fx from './fx';
import { family, fillTracked, layLine, metrics, setToMeasure, type FaceSpec, type LaidLine } from './layout';

export type Unit = 'word' | 'glyph' | 'line';
export type Align = 'left' | 'center' | 'right';

/** How a line is set and revealed. Every field may be given for the whole block or for one line. */
export interface LineStyle extends FaceSpec {
  size?: number;
  fit?: 'shrink' | 'fill' | 'none';
  tracking?: number;
  leading?: number;
  uppercase?: boolean;
  color?: string;
  reveal?: fx.Reveal;
  unit?: Unit;
  stagger?: number;
  every?: number;
  emphasis?: string[];
}

export interface LineSpec extends LineStyle {
  text: string;
  at?: fx.TimeRef;
  diff?: '-' | '+';
}

export interface KineticParams extends LineStyle {
  text?: string;
  lines?: (string | LineSpec)[];
  align?: Align;
  x?: number;
  y?: number;
  valign?: 'center' | 'top' | 'bottom';
  maxWidth?: number;
  wrap?: boolean;
  sync?: 'stagger' | 'beats' | 'vo';
  delay?: fx.TimeRef;
  cps?: number;
  caret?: boolean;
  seed?: number;
  emphasisColor?: string;
  emphasisStyle?: 'glow' | 'marker' | 'underline';
  kicker?: string;
  kickerColor?: string;
  kickerReveal?: fx.Reveal;
  kickerAt?: fx.TimeRef;
  kickerDot?: boolean;
  sub?: string;
  subColor?: string;
  subSize?: number;
  subRole?: string;
  subAt?: fx.TimeRef;
  subReveal?: fx.Reveal;
  exit?: fx.Exit;
  exitDur?: number;
  push?: number;
}

/** A word on a set line: its span on the line, when it lands and when each of its glyphs does. */
interface SetWord { w: string; i0: number; i1: number; x0: number; x1: number; at: number; ga: number[]; emph: boolean }

/** A line as set: its layout, where it sits, how it reveals and its words' times. */
interface SetLine {
  kind: 'kicker' | 'main' | 'sub';
  lay: LaidLine;
  x: number;
  y: number;
  color: string;
  reveal: fx.Reveal;
  unit: Unit;
  words: SetWord[];
  diff?: '-' | '+';
  /** The spec line it was wrapped from (lines of one spec reveal as one). */
  spec: number;
  /** When its last unit lands. */
  last: number;
}

const DEFAULT_STAGGER: Record<Unit, number> = { word: 0.075, glyph: 0.03, line: 0.16 };

export class KineticText extends Scene2D {
  protected override ownExit = true;
  /** A subclass's defaults (TitleCard, Quote...): the film's params override them. */
  protected defaults: Partial<KineticParams> = {};
  protected setLines: SetLine[] = [];
  /** The block's anchor (logical px) and its box as set (before push). */
  protected anchor = { x: 0, y: 0 };
  protected box = { x0: 0, y0: 0, x1: 0, y1: 0 };
  /** When the main lines start and finish landing. */
  protected firstAt = 0;
  protected lastAt = 0;
  private glowFrame = -1;
  private frameNo = 0;

  /** A param: the film's, else the subclass's default, else `fallback`. */
  protected k<K extends keyof KineticParams>(key: K, fallback: NonNullable<KineticParams[K]>): NonNullable<KineticParams[K]> {
    const v = this.ctx.params[key as string] ?? this.defaults[key];
    return (v ?? fallback) as NonNullable<KineticParams[K]>;
  }

  override init() {
    this.layoutBlock();
  }

  /** The copy as line specs (a subclass may supply its own). */
  protected specs(): LineSpec[] {
    const lines = this.ctx.params.lines ?? this.defaults.lines;
    const text = (this.ctx.params.text ?? this.defaults.text) as string | undefined;
    const raw: (string | LineSpec)[] = lines ?? (text !== undefined ? text.split('\n') : []);
    if (!raw.length) throw new Error(`shot ${this.ctx.id}: KineticText needs \`text\` or \`lines\``);
    return raw.map((l) => (typeof l === 'string' ? { text: l } : l));
  }

  /** Style of a line: its own, else the block's, else the defaults for its role. */
  private style(l: LineSpec) {
    const pick = <K extends keyof LineStyle>(key: K, fb: NonNullable<LineStyle[K]>): NonNullable<LineStyle[K]> => (l[key] ?? this.k(key as keyof KineticParams, fb as never)) as NonNullable<LineStyle[K]>;
    const role = pick('role', 'display');
    const display = role === 'display';
    const reveal = pick('reveal', 'rise');
    let unit = pick('unit', 'word');
    if (reveal === 'track') unit = 'line';
    if (reveal === 'typewriter') unit = 'glyph';
    return {
      face: { role, width: pick('width', 87.5), weight: pick('weight', display ? 800 : 500), italic: l.italic ?? this.ctx.params.italic } as FaceSpec,
      size: pick('size', 132),
      fit: pick('fit', 'shrink'),
      tracking: pick('tracking', display ? -0.02 : 0),
      leading: pick('leading', display ? 1.0 : 1.25),
      uppercase: pick('uppercase', false),
      color: pick('color', 'fg'),
      reveal,
      unit,
      stagger: l.stagger ?? (this.ctx.params.stagger as number | undefined) ?? this.defaults.stagger ?? (reveal === 'typewriter' ? 1 / this.k('cps', 30) : DEFAULT_STAGGER[unit]),
      every: l.every ?? this.k('every', 0) ?? 0,
      emphasis: [...(this.k('emphasis', []) as string[]), ...(l.emphasis ?? [])],
    };
  }

  /** Lay the block out and time every unit (init: fonts are loaded, the format is set). */
  protected layoutBlock() {
    const u = this.u, tall = isTall();
    const align = this.k('align', 'center');
    const ax = this.k('x', align === 'center' ? 0.5 : align === 'left' ? (tall ? 0.08 : 0.1) : tall ? 0.92 : 0.9) * W;
    const ay = this.k('y', 0.5) * H;
    const maxW = this.k('maxWidth', align === 'center' ? (tall ? 0.86 : 0.84) : tall ? 0.84 : 0.8) * W;
    const wrap = this.k('wrap', true);
    this.anchor = { x: ax, y: ay };
    const out: SetLine[] = [];
    const specs = this.specs();

    // ---- the main lines, set to the measure
    const main: { lay: LaidLine; st: ReturnType<KineticText['style']>; spec: number; diff?: '-' | '+' }[] = [];
    specs.forEach((l, si) => {
      const st = this.style(l);
      const fam = family(st.face);
      const text = st.uppercase ? l.text.toUpperCase() : l.text;
      const gutter = l.diff ? 0.8 * st.size * u : 0;
      const set = setToMeasure(text, fam, st.size * u, maxW - gutter, { tracking: st.tracking, wrap, fit: st.fit, maxSize: st.size * u * 2.2 });
      for (const t of set.lines) main.push({ lay: layLine(t, fam, set.size, st.tracking * set.size), st, spec: si, diff: l.diff });
    });
    const mainSize = Math.max(...main.map((m) => m.lay.size));

    // ---- the kicker and the sub
    const kickerText = this.k('kicker', '');
    const kFam = family({ role: 'mono', weight: 500 });
    const kSize = clamp(0.2 * mainSize, 22 * u, 32 * u);
    const kicker = kickerText ? layLine(kickerText.toUpperCase(), kFam, kSize, 0.22 * kSize) : null;
    const subText = this.k('sub', '');
    const sFam = family({ role: this.k('subRole', 'ui'), weight: 400 });
    const sSize = this.k('subSize', 0) * u || clamp(0.34 * mainSize, 30 * u, 50 * u);
    const subs = subText ? setToMeasure(subText, sFam, sSize, Math.min(maxW, (tall ? 0.84 : 0.62) * W), { wrap: true, fit: 'shrink' }) : null;

    // ---- vertical: baselines from the top of the block (cap top of its first line)
    let y = 0;
    const ys: number[] = [];
    let kickerY = 0;
    const dotR = kicker && this.k('kickerDot', true) ? 0.26 * kSize : 0;
    if (kicker) {
      kickerY = kicker.m.cap * kSize;
      y = kickerY + Math.max(18 * u, 0.42 * mainSize);
    }
    main.forEach((m, i) => {
      const s = m.lay.size, cap = m.lay.m.cap * s;
      if (i === 0) y += cap;
      else {
        const p = main[i - 1]!.lay;
        y += Math.max(m.st.leading * s, p.m.desc * p.size + cap + 0.08 * s);
      }
      ys.push(y);
    });
    const subYs: number[] = [];
    if (subs) {
      const last = main[main.length - 1]!.lay;
      y += last.m.desc * last.size + Math.max(16 * u, 0.3 * last.size);
      const sm = metrics(sFam);
      subs.lines.forEach((_, i) => {
        y += i === 0 ? sm.cap * subs.size : 1.38 * subs.size;
        subYs.push(y);
      });
    }
    const h = y;
    const valign = this.k('valign', 'center');
    const top = valign === 'top' ? ay : valign === 'bottom' ? ay - h : ay - h / 2;
    const left = (w: number) => (align === 'center' ? ax - w / 2 : align === 'left' ? ax : ax - w);

    // ---- timing
    const { audio, vo } = this.ctx;
    const start = this.ctx.start;
    const sync = this.k('sync', 'stagger');
    // beats: the first unit on the shot's first beat (a shot cut on the beat lands its first word on the cut)
    const delay = this.k('delay', sync === 'beats' ? 0 : 0.1);
    const t0raw = fx.resolveTime(delay, start, audio);
    const t0 = sync === 'beats' ? audio.timeOfBeat(Math.ceil(audio.beatAt(t0raw) - 1e-6)) : t0raw;
    const kickerAt = kicker ? fx.resolveTime(this.k('kickerAt', delay), start, audio) : t0;
    let spoken: Spoken[] = [];
    if (sync === 'vo') {
      try {
        spoken = wordTimes(vo, this.shot).map((x) => x.w);
      } catch {
        spoken = [];
      }
    }
    const allWords = main.flatMap((m) => m.lay.words.map((w) => w.w));
    const spans = spoken.length ? fx.alignToVO(allWords, spoken, { fallback: t0 }) : null;
    let cursor = kicker && sync !== 'vo' ? Math.max(t0, kickerAt + 0.14) : t0;
    let wi = 0;
    const timed: SetWord[][] = main.map(() => []);
    // the spec lines in order: their visual lines share one run of units
    for (let si = 0; si < specs.length; si++) {
      const rows = main.map((m, i) => ({ m, i })).filter((r) => r.m.spec === si);
      if (!rows.length) continue;
      const st = rows[0]!.m.st;
      const grid = { stagger: st.stagger, every: sync === 'beats' ? st.every || 1 : st.every || undefined, grid: audio };
      const first = specs[si]!.at !== undefined ? fx.resolveTime(specs[si]!.at!, start, audio) : cursor;
      // units: words, glyphs or lines of this spec
      const n = st.unit === 'line' ? rows.length : rows.reduce((s, r) => s + (st.unit === 'glyph' ? r.m.lay.glyphs.filter((g) => !/\s/u.test(g.ch)).length : r.m.lay.words.length), 0);
      const times = fx.staggerTimes(n, first, grid);
      let ui = 0, last = first;
      rows.forEach((r, ri) => {
        for (const w of r.m.lay.words) {
          const nGlyph = w.i1 - w.i0;
          let at: number, ga: number[];
          if (spans) {
            const sp = spans[wi]!;
            const lineAt = spans[wi - r.m.lay.words.indexOf(w)]!.start;
            at = st.unit === 'line' ? lineAt : sp.start;
            const per = Math.min(fx.SCRAMBLE.per, Math.max(0.012, (sp.end - sp.start) / Math.max(1, nGlyph)));
            ga = st.reveal === 'scramble' ? Array.from({ length: nGlyph }, (_, j) => sp.start + j * per) : fx.glyphTimes(sp, nGlyph);
            if (st.unit === 'line') ga = ga.map(() => lineAt);
          } else if (st.unit === 'line') {
            at = times[ri]!;
            ga = Array.from({ length: nGlyph }, (_, j) => (st.reveal === 'scramble' ? at + j * fx.SCRAMBLE.per : at));
          } else if (st.unit === 'glyph') {
            ga = Array.from({ length: nGlyph }, () => times[Math.min(ui++, times.length - 1)]!);
            at = ga[0]!;
          } else {
            at = times[ui++]!;
            ga = Array.from({ length: nGlyph }, (_, j) => (st.reveal === 'scramble' ? at + j * fx.SCRAMBLE.per : at));
          }
          last = Math.max(last, ...ga, at);
          timed[r.i]!.push({ ...w, at, ga, emph: fx.isOneOf(w.w, st.emphasis) });
          wi++;
        }
      });
      cursor = sync === 'beats' ? audio.timeOfBeat(audio.beatAt(last) + (st.every || 1)) : last + Math.max(0.12, st.stagger * 2);
    }
    const allAt = timed.flat().map((w) => w.at);
    this.firstAt = Math.min(...allAt);
    this.lastAt = Math.max(...timed.flat().map((w) => Math.max(w.at, ...w.ga)));

    // ---- the set lines
    if (kicker) {
      const kw = kicker.width + (dotR ? dotR * 2 + 0.7 * kSize : 0);
      const x = left(kw) + (dotR ? dotR * 2 + 0.7 * kSize : 0);
      const kr = this.k('kickerReveal', 'scramble');
      out.push({
        kind: 'kicker', lay: kicker, x, y: top + kickerY, color: this.k('kickerColor', 'accent'), reveal: kr, unit: 'line', spec: -1,
        words: kicker.words.map((w) => ({ ...w, at: kickerAt, ga: Array.from({ length: w.i1 - w.i0 }, (_, j) => kickerAt + (kr === 'scramble' || kr === 'typewriter' ? (w.i0 + j) * 0.03 : 0)), emph: false })),
        last: kickerAt + kicker.glyphs.length * 0.03,
      });
    }
    main.forEach((m, i) => {
      const words = timed[i]!;
      out.push({ kind: 'main', lay: m.lay, x: left(m.lay.width), y: top + ys[i]!, color: m.st.color, reveal: m.st.reveal, unit: m.st.unit, words, diff: m.diff, spec: m.spec, last: Math.max(...words.map((w) => Math.max(w.at, ...w.ga))) });
    });
    if (subs) {
      const subAt = this.ctx.params.subAt !== undefined || this.defaults.subAt !== undefined ? fx.resolveTime(this.k('subAt', 0), start, audio) : this.lastAt + 0.3;
      const sr = this.k('subReveal', 'fade');
      let n = 0;
      subs.lines.forEach((t, i) => {
        const lay = layLine(t, sFam, subs.size, 0);
        const words = lay.words.map((w) => {
          const at = subAt + 0.035 * n++;
          return { ...w, at, ga: Array.from({ length: w.i1 - w.i0 }, () => at), emph: false };
        });
        out.push({ kind: 'sub', lay, x: left(lay.width), y: top + subYs[i]!, color: this.k('subColor', 'fgDim'), reveal: sr, unit: 'word', words, spec: -2, last: words[words.length - 1]?.at ?? subAt });
      });
    }
    this.setLines = out;
    const xs = out.map((l) => l.x), xe = out.map((l) => l.x + l.lay.width);
    this.box = { x0: Math.min(...xs), y0: top, x1: Math.max(...xe), y1: top + h };
  }

  /** The glow layer with this frame's push applied (set up on the first ask in a frame). */
  protected glowAt(push: number): CanvasRenderingContext2D | null {
    if (this.glowLevel <= 0) return null;
    const g = this.glow;
    if (this.glowFrame !== this.frameNo) {
      this.glowFrame = this.frameNo;
      this.pushOn(g, push);
    }
    return g;
  }

  private pushOn(c: CanvasRenderingContext2D, s: number) {
    if (s === 1) return;
    c.translate(this.anchor.x, this.anchor.y);
    c.scale(s, s);
    c.translate(-this.anchor.x, -this.anchor.y);
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    this.frameNo++;
    const push = 1 + this.k('push', 0.025) * clamp(f.p);
    this.pushOn(c, push);
    this.drawBefore(c, f, push);
    for (const l of this.setLines) this.drawLine(c, l, f, push);
    this.drawAfter(c, f, push);
  }

  /** Hooks for subclasses: drawn under and over the lines (in the pushed frame). */
  protected drawBefore(_c: CanvasRenderingContext2D, _f: Frame, _push: number) {}
  protected drawAfter(_c: CanvasRenderingContext2D, _f: Frame, _push: number) {}

  /** The block's exit state at t (per line: lines leave top first, 40 ms apart). */
  protected exitOf(l: SetLine, t: number): fx.UnitState {
    const style = this.k('exit', 'none');
    if (style === 'none') return fx.SHOWN;
    const idx = this.setLines.indexOf(l), n = this.setLines.length;
    const end = this.ctx.end - (n - 1 - idx) * 0.04;
    return fx.exitState(style, t, end, this.k('exitDur', 0.3));
  }

  protected drawLine(c: CanvasRenderingContext2D, l: SetLine, f: Frame, push: number) {
    const t = f.t, L = l.lay, size = L.size, m = L.m;
    const ex = this.exitOf(l, t);
    if (ex.alpha <= 0.002) return;
    const emphColor = this.k('emphasisColor', 'accent');
    const emphStyle = this.k('emphasisStyle', 'glow');
    const diffColor = l.diff === '-' ? 'accent' : l.diff === '+' ? 'accent2' : null;
    const strikeAt = l.last + fx.revealTail(l.reveal) + 0.12;
    const strike = l.diff === '-' ? fx.sweep(t, strikeAt, 0.32) : 0;
    const lineAlpha = lerp(1, 0.5, strike);
    c.save();
    c.font = font(L.family, size);
    c.textBaseline = 'alphabetic';
    // a rising line comes up behind its own mask
    if (l.reveal === 'rise') {
      c.beginPath();
      c.rect(-W, l.y - (m.cap + 0.32) * size, 3 * W, (m.cap + m.desc + 0.42) * size);
      c.clip();
    }
    // the kicker's dot, and a diff line's gutter mark
    if (l.kind === 'kicker' && this.k('kickerDot', true)) this.kickerDot(c, l, f, ex, push);
    if (l.diff) this.gutter(c, l, t, ex, push);

    if (l.reveal === 'track') this.drawTrack(c, l, t, ex, diffColor);
    else if (l.reveal === 'typewriter') this.drawTyped(c, l, t, ex, diffColor, push);
    else if (l.reveal === 'scramble') this.drawScramble(c, l, t, ex, diffColor);
    else {
      const cy = l.y - (m.cap * size) / 2;
      for (const w of l.words) {
        const color = w.emph && !diffColor ? emphColor : diffColor ?? l.color;
        // a marker or underline belongs to the word (it sweeps once the word is in)
        if (w.emph && emphStyle !== 'glow') this.mark(c, l, w, t, fx.compose(fx.revealState(l.reveal, t, w.at), ex), emphStyle, emphColor, l.x + (w.x0 + w.x1) / 2, cy, push);
        const ink = w.emph && emphStyle === 'marker' ? l.color : color;
        const glowColor = w.emph && emphStyle === 'glow' ? emphColor : diffColor ?? emphColor;
        // the pieces that move: the word, or each of its glyphs
        const pieces = l.unit === 'glyph'
          ? L.glyphs.slice(w.i0, w.i1).map((g, j) => ({ text: g.ch, x: g.x, w: g.w, at: w.ga[j]!, track: 0 })).filter((pc) => !/\s/u.test(pc.text))
          : [{ text: w.w, x: w.x0, w: w.x1 - w.x0, at: w.at, track: L.track }];
        for (const pc of pieces) {
          const st = fx.compose(fx.revealState(l.reveal, t, pc.at), ex);
          // a line wiped as one: one sweep across it, each word uncovered as the sweep passes it
          if (l.reveal === 'wipe' && l.unit === 'line') {
            const sweepX = prog(t, pc.at, pc.at + 0.45, ease.outCubic) * (L.width + 0.1 * size);
            st.clip = clamp((sweepX - pc.x) / Math.max(1, pc.w));
          }
          const cx = l.x + pc.x + pc.w / 2;
          this.run(c, L.family, pc.text, l.x + pc.x, l.y, size, pc.track, st, rgba(ink, lineAlpha), cx, cy, pc.w);
          // the glow: emphasis words flare as they land and keep a soft light; a + line glows a little throughout
          const gk = (w.emph && emphStyle === 'glow' ? fx.emphasisGlow(t, pc.at) : 0) + (l.diff === '+' ? 0.35 * clamp((t - pc.at) / 0.2) : 0);
          if (gk > 0.003) {
            const g = this.glowAt(push);
            if (g) this.run(g, L.family, pc.text, l.x + pc.x, l.y, size, pc.track, st, glowInk(glowColor, Math.min(1, gk) * 0.6), cx, cy, pc.w);
          }
        }
      }
    }
    if (strike > 0) {
      const sy = l.y - m.x * size * 0.52, th = Math.max(2 * this.u, 0.06 * size);
      const x0 = l.x - 0.06 * size, x1 = l.x + L.width + 0.06 * size;
      c.globalAlpha = ex.alpha;
      c.fillStyle = rgba('accent');
      c.fillRect(x0, sy - th / 2, (x1 - x0) * strike, th);
      const g = this.glowAt(push);
      if (g) {
        g.save();
        g.globalAlpha = ex.alpha * 0.7;
        g.fillStyle = glowInk('accent');
        g.fillRect(x0, sy - th / 2, (x1 - x0) * strike, th);
        g.restore();
      }
    }
    c.restore();
  }

  /** Draw a run (a word, a glyph) with a unit state: alpha, offset, scale about (cx, cy), blur, a left-to-right clip. */
  protected run(c: CanvasRenderingContext2D, fam: string, text: string, x: number, y: number, size: number, track: number, st: fx.UnitState, color: string, cx: number, cy: number, w: number) {
    if (st.alpha <= 0.002 || st.clip <= 0) return;
    c.save();
    c.globalAlpha *= st.alpha;
    if (st.blur * size > 0.05) c.filter = `blur(${(st.blur * size).toFixed(2)}px)`;
    c.translate(cx + st.dx * size, cy + st.dy * size);
    if (st.scale !== 1) c.scale(st.scale, st.scale);
    c.translate(-cx, -cy);
    if (st.clip < 1) {
      c.beginPath();
      c.rect(x - 0.1 * size, y - 1.3 * size, (w + 0.1 * size) * st.clip + 0.1 * size * st.clip, 1.8 * size);
      c.clip();
    }
    c.font = font(fam, size);
    c.fillStyle = color;
    fillTracked(c, text, x, y, track + st.track * size);
    c.restore();
    // a wipe's leading edge: a thin accent bar
    if (st.clip > 0 && st.clip < 1) {
      c.save();
      c.globalAlpha *= st.alpha * Math.sin(Math.PI * st.clip);
      c.fillStyle = rgba(this.k('emphasisColor', 'accent'));
      c.fillRect(x + (w + 0.1 * size) * st.clip, y - 0.95 * size * 0.78, Math.max(2, 0.035 * size), 1.05 * size * 0.78);
      c.restore();
    }
  }

  /** Track: the line's glyphs drawn apart and closing in (spread about the anchor's side of the line). */
  private drawTrack(c: CanvasRenderingContext2D, l: SetLine, t: number, ex: fx.UnitState, diffColor: string | null) {
    const L = l.lay, size = L.size, n = L.glyphs.length;
    const align = this.k('align', 'center');
    const st = fx.compose(fx.revealState('track', t, l.words[0]?.at ?? 0), ex);
    if (st.alpha <= 0.002) return;
    const pivot = align === 'center' ? (n - 1) / 2 : align === 'left' ? 0 : n - 1;
    c.save();
    c.globalAlpha *= st.alpha;
    if (st.blur * size > 0.05) c.filter = `blur(${(st.blur * size).toFixed(2)}px)`;
    const emph = this.k('emphasisColor', 'accent');
    for (const w of l.words) {
      c.fillStyle = rgba(w.emph && !diffColor ? emph : diffColor ?? l.color);
      for (let j = w.i0; j < w.i1; j++) {
        const g = L.glyphs[j]!;
        c.fillText(g.ch, l.x + g.x + (j - pivot) * st.track * size, l.y + st.dy * size);
      }
    }
    c.restore();
  }

  /** Typewriter: glyphs on the frame grid, a caret at the head while typing, blinking after. */
  private drawTyped(c: CanvasRenderingContext2D, l: SetLine, t: number, ex: fx.UnitState, diffColor: string | null, push: number) {
    const L = l.lay, size = L.size;
    const tq = fx.frameTime(t);
    let shown = -1, lastAt = -Infinity;
    for (const w of l.words) {
      for (let j = w.i0; j < w.i1; j++) {
        const at = w.ga[j - w.i0]!;
        lastAt = Math.max(lastAt, at);
        if (tq >= at - 1e-9) shown = Math.max(shown, j);
      }
    }
    c.save();
    c.globalAlpha *= ex.alpha;
    const emph = this.k('emphasisColor', 'accent');
    for (const w of l.words) {
      if (w.i0 > shown) break;
      const end = Math.min(w.i1, shown + 1);
      c.fillStyle = rgba(w.emph && !diffColor ? emph : diffColor ?? l.color);
      fillTracked(c, Array.from(L.text).slice(w.i0, end).join(''), l.x + w.x0, l.y + ex.dy * size, L.track);
    }
    // the caret: at the head, solid while the keys land, blinking after; gone at the line's exit
    const first = l.words[0]?.at ?? 0;
    const isLast = this.setLines.filter((x) => x.kind === l.kind && x.reveal === 'typewriter').at(-1) === l;
    if (this.k('caret', true) && tq >= first - 1e-9 && (isLast ? true : tq < lastAt + 0.05)) {
      const g = L.glyphs[Math.max(0, shown)];
      const hx = shown < 0 ? l.x : l.x + g!.x + g!.w + L.track;
      if (fx.caretOn(t, lastAt)) {
        const mono = /mono/i.test(L.family);
        const cw = mono ? 0.56 * size : Math.max(2, 0.07 * size);
        c.fillStyle = rgba(this.k('emphasisColor', 'accent'), 0.9);
        c.fillRect(hx + (mono ? 0.04 * size : 0.05 * size), l.y - L.m.cap * size * 1.12, cw, L.m.cap * size * 1.32);
        const gl = this.glowAt(push);
        if (gl) {
          gl.fillStyle = glowInk(this.k('emphasisColor', 'accent'), 0.5 * ex.alpha);
          gl.fillRect(hx + (mono ? 0.04 * size : 0.05 * size), l.y - L.m.cap * size * 1.12, cw, L.m.cap * size * 1.32);
        }
      }
    }
    c.restore();
  }

  /** Scramble: each glyph churns through seeded glyphs (accent) and settles to its own (left to right). */
  private drawScramble(c: CanvasRenderingContext2D, l: SetLine, t: number, ex: fx.UnitState, diffColor: string | null) {
    const L = l.lay, size = L.size;
    const seed = this.k('seed', 1) * 7919 + this.setLines.indexOf(l) * 131;
    const emph = this.k('emphasisColor', 'accent');
    c.save();
    c.globalAlpha *= ex.alpha;
    for (const w of l.words) {
      const color = rgba(w.emph && !diffColor ? emph : diffColor ?? l.color);
      for (let j = w.i0; j < w.i1; j++) {
        const g = L.glyphs[j]!;
        const settle = w.ga[j - w.i0]!;
        const ch = fx.scrambleGlyph(g.ch, j, t, w.at, settle, seed);
        if (!ch || /\s/u.test(ch)) continue;
        const settled = ch === g.ch && fx.frameTime(t) >= settle - 1e-9;
        c.fillStyle = settled ? color : rgba(l.kind === 'kicker' ? 'fgDim' : emph, 0.85);
        const dx = settled ? 0 : (g.w - c.measureText(ch).width) / 2;
        c.fillText(ch, l.x + g.x + dx, l.y + ex.dy * size);
      }
    }
    c.restore();
  }

  /** The kicker's dot: an accent light before the label, breathing on the beat. */
  private kickerDot(c: CanvasRenderingContext2D, l: SetLine, f: Frame, ex: fx.UnitState, push: number) {
    const size = l.lay.size, r = 0.26 * size;
    const k = fx.revealState('fade', f.t, l.words[0]?.at ?? 0).alpha * ex.alpha;
    if (k <= 0.002) return;
    const x = l.x - 0.7 * size - r, y = l.y - l.lay.m.cap * size * 0.5;
    const color = this.k('kickerColor', 'accent');
    c.save();
    c.globalAlpha *= k;
    c.fillStyle = rgba(color);
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fill();
    c.restore();
    const g = this.glowAt(push);
    if (g) {
      g.save();
      g.fillStyle = glowInk(color, k * (0.5 + 0.5 * onBeat(f, 0.35)));
      g.beginPath();
      g.arc(x, y, r * 1.05, 0, Math.PI * 2);
      g.fill();
      g.restore();
    }
  }

  /** A diff line's gutter mark (− or +), in mono, left of the line. */
  private gutter(c: CanvasRenderingContext2D, l: SetLine, t: number, ex: fx.UnitState, push: number) {
    const size = l.lay.size;
    const k = fx.revealState('fade', t, l.words[0]?.at ?? 0).alpha * ex.alpha;
    if (k <= 0.002) return;
    const role = l.diff === '-' ? 'accent' : 'accent2';
    const fam = family({ role: 'mono', weight: 700 });
    c.save();
    c.font = font(fam, size * 0.8);
    c.globalAlpha *= k;
    c.fillStyle = rgba(role);
    c.textAlign = 'center';
    const x = l.x - 0.55 * size;
    c.fillText(l.diff === '-' ? '−' : '+', x, l.y - 0.02 * size);
    c.restore();
    if (l.diff === '+') {
      const g = this.glowAt(push);
      if (g) {
        g.save();
        g.font = font(fam, size * 0.8);
        g.textAlign = 'center';
        g.fillStyle = glowInk(role, 0.6 * k);
        g.fillText('+', x, l.y - 0.02 * size);
        g.restore();
      }
    }
  }

  /** A word's marker (a highlighter swept behind it) or underline, after it lands. */
  private mark(c: CanvasRenderingContext2D, l: SetLine, w: SetWord, t: number, st: fx.UnitState, style: 'marker' | 'underline', color: string, cx: number, cy: number, push: number) {
    const size = l.lay.size, m = l.lay.m;
    const k = fx.sweep(t, w.at + 0.1, 0.36);
    if (k <= 0 || st.alpha <= 0.002) return;
    const x0 = l.x + w.x0 - 0.08 * size, ww = (w.x1 - w.x0 + 0.16 * size) * k;
    const [y0, hh] = style === 'marker' ? [l.y - (m.cap + 0.12) * size, (m.cap + 0.26) * size] : [l.y + 0.1 * size, Math.max(3 * this.u, 0.07 * size)];
    for (const [ctx, ink] of [[c, rgba(color, style === 'marker' ? 0.92 : 1)], [this.glowAt(push), glowInk(color, style === 'marker' ? 0.28 : 0.8)]] as const) {
      if (!ctx) continue;
      ctx.save();
      ctx.globalAlpha *= st.alpha;
      ctx.translate(cx + st.dx * size, cy + st.dy * size);
      ctx.scale(st.scale, st.scale);
      ctx.translate(-cx, -cy);
      ctx.fillStyle = ink;
      ctx.beginPath();
      ctx.roundRect(x0, y0, ww, hh, Math.min(hh / 2, 0.06 * size));
      ctx.fill();
      ctx.restore();
    }
  }
}

export default KineticText;
