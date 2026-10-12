// Word-timed voiceover (films/<id>/data/vo.json, written by tools/ film-edit and film-snap) with queries for kinetic type.
// A film without a voiceover gets VO.empty(), or captions written in film.ts (VO.fromCaptions): lines with times and,
// optionally, each word's; words without times are spread over their line by length.
import { smart } from './type';
import { filmUrl } from './config';

/** A caption line authored in film.ts: its text and when it shows; words timed or spread over [start, end]. */
export interface CaptionLine {
  text: string;
  start: number;
  /** Default: 0.32 s a word after start. */
  end?: number;
  id?: string;
  /** The scene it belongs to (wordTimes(vo, scene) finds it); default: the scene on screen at `start`. */
  scene?: string;
  words?: { w: string; start: number; end: number }[];
}

export interface Word {
  w: string; // display token (punctuation attached, typographic: it’s, you…)
  start: number;
  end: number;
  syl?: [number, number][];
  /** filled in by VO: */
  line: number;
  index: number; // index within line
  gi: number; // global word index
}
export interface Line {
  i: number;
  id: string;
  scene: string;
  act: string;
  text: string;
  start: number;
  end: number;
  words: Word[];
}
export interface SceneSpan { id: string; act: string; start: number; end: number }
export interface ActSpan { id: string; name: string; start: number; end: number }

export class VO {
  lines: Line[];
  words: Word[];
  scenes: SceneSpan[];
  acts: ActSpan[];
  duration: number;

  constructor(j: { duration: number; lines: any[]; scenes: SceneSpan[]; acts: ActSpan[] }) {
    // display text gets curly apostrophes and the ellipsis; mono UI text that wants them straight uses plain()
    this.lines = j.lines.map((l, li) => ({
      ...l,
      i: li,
      text: smart(l.text),
      words: (l.words as any[]).map((w, wi) => ({ ...w, w: smart(w.w), line: li, index: wi, gi: 0 })),
    }));
    this.words = this.lines.flatMap((l) => l.words);
    this.words.forEach((w, i) => (w.gi = i));
    this.scenes = j.scenes;
    this.acts = j.acts;
    this.duration = j.duration;
  }

  /** Load a voiceover (default: the film's data/vo.json). */
  static async load(url = filmUrl('data/vo.json')): Promise<VO> {
    const r = await fetch(url);
    if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) throw new Error(`voiceover ${url}: HTTP ${r.status} (run tools/ film-edit, or leave the film's vo out)`);
    return new VO(await r.json());
  }

  /** No voiceover: no lines, no words, no scenes. */
  static empty(duration = 0): VO {
    return new VO({ duration, lines: [], scenes: [], acts: [] });
  }

  /**
   * Captions as a voiceover: each line's words timed as given, or spread over [start, end] in proportion to their
   * length (a word's share of the line's characters, a tenth of it held back as the gap after it). `sceneAt` names the
   * scene a line without `scene` belongs to.
   */
  static fromCaptions(lines: CaptionLine[], sceneAt: (t: number) => string = () => '', duration = 0): VO {
    const out = [...lines].sort((a, b) => a.start - b.start).map((l, i) => {
      const toks = l.text.split(/\s+/).filter(Boolean);
      const end = l.end ?? l.start + 0.32 * Math.max(1, toks.length);
      if (!(end > l.start)) throw new Error(`caption "${l.text}": end ${end} is not after start ${l.start}`);
      let words = l.words;
      if (!words) {
        const total = toks.reduce((s, w) => s + w.length + 1, 0);
        let at = l.start;
        words = toks.map((w) => {
          const span = ((w.length + 1) / total) * (end - l.start);
          const word = { w, start: +at.toFixed(4), end: +(at + span * 0.9).toFixed(4) };
          at += span;
          return word;
        });
      }
      return { id: l.id ?? `C${String(i + 1).padStart(2, '0')}`, scene: l.scene ?? sceneAt(l.start), act: '', text: l.text, start: l.start, end, words };
    });
    return new VO({ duration: Math.max(duration, ...out.map((l) => l.end)), lines: out, scenes: [], acts: [] });
  }

  /** The line being spoken at t (or null in gaps). */
  lineAt(t: number): Line | null {
    return this.lines.find((l) => t >= l.start && t < l.end) ?? null;
  }
  /** Most recent line that started at or before t. */
  lastLine(t: number): Line | null {
    let best: Line | null = null;
    for (const l of this.lines) if (l.start <= t) best = l;
    return best;
  }
  nextLine(t: number): Line | null {
    return this.lines.find((l) => l.start > t) ?? null;
  }
  linesIn(t0: number, t1: number): Line[] {
    return this.lines.filter((l) => l.end > t0 && l.start < t1);
  }
  /** The scene window containing t. */
  sceneAt(t: number): SceneSpan | null {
    return this.scenes.find((s) => t >= s.start && t < s.end) ?? null;
  }
  /** Lines whose text includes `s` (case-insensitive, straight or curly quotes). */
  find(s: string): Line[] {
    const q = fold(s);
    return this.lines.filter((l) => fold(l.text).includes(q));
  }
  /** First line containing `s`; throws if missing (fail loudly while authoring). */
  get(s: string, nth = 0): Line {
    const l = this.find(s)[nth];
    if (!l) throw new Error(`line not found: ${s}`);
    return l;
  }
  wordAt(t: number): Word | null {
    return this.words.find((w) => t >= w.start && t < w.end) ?? null;
  }
  lastWord(t: number): Word | null {
    let best: Word | null = null;
    for (const w of this.words) if (w.start <= t) best = w;
    return best;
  }
  /** Words whose normalized text matches (e.g. 'commit'). */
  findWords(s: string): Word[] {
    const q = norm(s);
    return this.words.filter((w) => norm(w.w) === q);
  }

  /** Spoken progress of a word at t: 0 before start, 1 after end, linear inside. */
  static wordProgress(w: Word, t: number): number {
    if (t <= w.start) return 0;
    if (t >= w.end) return 1;
    return (t - w.start) / Math.max(1e-3, w.end - w.start);
  }

  /** Progress through a whole line in characters (0..text.length), for per-glyph wipes. */
  static lineCharProgress(l: Line, t: number): number {
    let chars = 0;
    for (const w of l.words) {
      const p = VO.wordProgress(w, t);
      chars += p * w.w.length;
      if (p < 1) break;
      chars += 1; // the space
    }
    return Math.min(chars, l.text.length);
  }
}

export const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9()]/g, '');
const fold = (s: string) => s.toLowerCase().replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/…/g, '...');
