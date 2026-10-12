// A film: one folder, films/<id>/, whose film.ts default-exports defineFilm({...}). The spec says what the film is (its
// format, frame rate, theme, fonts, audio and voiceover, from film.json) and what plays when: its shots in order, each
// for a length in seconds, beats or bars, each coming in from the one before by a transition; overlays over them; the
// film-wide look. filmTimeline() resolves it into the engine's timeline (scene windows back to back), filmTransitions()
// into transition specs at the cuts. Pure: no DOM, no three.js, so bun tests it and scripts/timeline.ts runs it.
import type { AudioData } from './audio';
import { configure, type FormatSpec } from './config';
import { setTheme, type ThemeSpec } from './palette';
import type { PostOverrides, SceneClass } from './scene';
import type { TransitionKind, TransitionSpec } from './transition';
import { registerFonts, resetFonts, type FontDef } from './type';
import type { CaptionLine, SceneSpan, VO } from './vo';
import type { SceneCues } from '../sfx/cue';
import type { TransitionSounds } from '../sfx/transitions';

/** A scene: its class (a kit scene, say), or a lazy import of a module whose default export is one. */
export type SceneSource = SceneClass | (() => Promise<{ default: SceneClass }>);

/** A length: seconds, or beats or bars of the film's grid (the analysed score's, or the synthetic grid's). */
export type Length = number | { beats: number } | { bars: number };

/**
 * How a shot comes in from the one before it: a kind, or a spec without its pair (the shots give it). `pre` and
 * `post` default to 0.25 s (0 for a 'cut').
 */
export type TransitionIn = TransitionKind | (Omit<TransitionSpec, 'from' | 'to' | 'pre' | 'post'> & { pre?: number; post?: number });

export interface ShotSpec {
  /** Unique within the film (timeline ids, --only, the player's marks). */
  id: string;
  scene: SceneSource;
  /** How long it plays. Not needed when `end` is given, nor in 'vo' timing. */
  length?: Length;
  /** An absolute window, song seconds (the shot after it then starts at `end`). */
  start?: number;
  end?: number;
  /** Handed to the scene as ctx.params. */
  params?: Record<string, unknown>;
  /** This shot's post overrides (the scene's own win over them). */
  post?: PostOverrides;
  /** Cap on adaptive motion-blur sub-frames while this shot is on screen. */
  maxSamples?: number;
  /** How this shot comes in from the one before it (none: a hard cut). */
  transition?: TransitionIn;
}

export interface OverlaySpec {
  id: string;
  scene: SceneSource;
  /** Default: the whole film. */
  start?: number;
  end?: number;
  params?: Record<string, unknown>;
  post?: PostOverrides;
}

/** A face of the film's own: as FontDef, its url relative to the film's folder. */
export type FilmFont = Omit<FontDef, 'url'> & { url: string };

export interface FilmSpec {
  /** The folder name under films/. */
  id: string;
  title?: string;
  format?: FormatSpec;
  fps?: number;
  theme?: ThemeSpec;
  fonts?: { faces: FilmFont[]; replace?: string[] };
  /** All optional: a silent film plays on a synthetic grid at `bpm` (default 120). Paths relative to the film. */
  audio?: { mix?: string; analysis?: string; bpm?: number; offset?: number; beatsPerBar?: number };
  /** A word-timed voiceover (a path to vo.json), or captions written here. */
  vo?: string | CaptionLine[];
  /** 'sequence' (default): shots play back to back by their lengths. 'vo': their windows are vo.json's scenes. */
  timing?: 'sequence' | 'vo';
  /** When the first shot starts (s, default 0). */
  start?: number;
  scenes: ShotSpec[];
  overlays?: OverlaySpec[];
  /** Transitions between adjacent shots, besides those the shots give inline. */
  transitions?: TransitionSpec[];
  /** The film's look: every frame starts from DEFAULT_POST with these over it. */
  post?: PostOverrides;
  /** Total length (default: the end of the last shot). */
  duration?: number;
  /** No word may start inside a transition's window (default true; only matters with a voiceover). */
  wordGuard?: boolean;
  /**
   * Sound design (app/scripts/cues.ts → data/sfx.json → tools/ film-sfx): cue modules by shot id, the palette
   * (default data/sfx_palette.json) and the sounds transitions make at their cuts.
   */
  sfx?: { cues?: Record<string, SceneCues>; palette?: string; transitions?: TransitionSounds };
  /** Anything else film.json carries (the pipeline's settings): the engine ignores it. */
  [k: string]: unknown;
}

/** Type-checks a film spec (and is where a film's defaults would go). */
export function defineFilm(f: FilmSpec): FilmSpec {
  return f;
}

/** One timeline entry as the engine takes it (engine.ts TimelineEntry). */
export interface FilmEntry {
  id: string;
  load: () => Promise<{ default: SceneClass }>;
  start: number;
  end: number;
  params?: Record<string, any>;
  post?: PostOverrides;
  maxSamples?: number;
  kind?: 'scene' | 'overlay';
}

const isClass = (s: SceneSource): s is SceneClass => typeof s === 'function' && !!s.prototype && typeof s.prototype.render === 'function';

/** The loader for a scene source. */
export function loaderOf(s: SceneSource): () => Promise<{ default: SceneClass }> {
  return isClass(s) ? () => Promise.resolve({ default: s }) : (s as () => Promise<{ default: SceneClass }>);
}

/** Where a length that starts at `start` ends. Beats and bars count on the grid from wherever `start` falls on it. */
export function lengthEnd(l: Length, start: number, audio?: Pick<AudioData, 'beatAt' | 'timeOfBeat' | 'barAt' | 'timeOfBar'>): number {
  if (typeof l === 'number') {
    if (!(l > 0)) throw new Error(`a length is positive, got ${l}`);
    return start + l;
  }
  if (!audio) throw new Error('a length in beats or bars needs the film\'s beat grid');
  if ('beats' in l) {
    if (!(l.beats > 0)) throw new Error(`a length is positive, got ${l.beats} beats`);
    return audio.timeOfBeat(audio.beatAt(start) + l.beats);
  }
  if (!(l.bars > 0)) throw new Error(`a length is positive, got ${l.bars} bars`);
  return audio.timeOfBar(audio.barAt(start) + l.bars);
}

/** Round to the microsecond: windows built from sums of float lengths compare equal where they meet. */
const us = (x: number) => Math.round(x * 1e6) / 1e6;

/**
 * The shots' windows. 'sequence': back to back from `film.start`, each for its length, or over its own start/end. 'vo':
 * each shot's window is the vo.json scene of the same id (every shot needs one). Throws on a shot with no length, a
 * duplicate id, or a window that runs backwards.
 */
export function shotWindows(film: Pick<FilmSpec, 'scenes' | 'timing' | 'start'>, audio?: AudioData, vo?: Pick<VO, 'scenes'>): { id: string; start: number; end: number }[] {
  const ids = new Set<string>();
  let t = film.start ?? 0;
  return film.scenes.map((s) => {
    if (ids.has(s.id)) throw new Error(`shot id '${s.id}' is used twice`);
    ids.add(s.id);
    let start: number, end: number;
    if (film.timing === 'vo') {
      const v = vo?.scenes.find((x) => x.id === s.id);
      if (!v) throw new Error(`shot ${s.id}: no scene '${s.id}' in vo.json (timing 'vo' takes every window from it)`);
      ({ start, end } = v);
    } else {
      start = s.start ?? t;
      if (s.end !== undefined) end = s.end;
      else if (s.length !== undefined) end = lengthEnd(s.length, start, audio);
      else throw new Error(`shot ${s.id} needs a length (seconds, { beats }, { bars }) or an end`);
    }
    start = us(start);
    end = us(end);
    if (!(end > start)) throw new Error(`shot ${s.id}: its window [${start}, ${end}) is empty`);
    t = end;
    return { id: s.id, start, end };
  });
}

/** The engine's timeline for a film: its shots in their windows, then its overlays (default: the whole film). */
export function filmTimeline(film: FilmSpec, audio?: AudioData, vo?: VO): FilmEntry[] {
  const win = shotWindows(film, audio, vo);
  const shots: FilmEntry[] = film.scenes.map((s, i) => ({
    id: s.id, load: loaderOf(s.scene), start: win[i]!.start, end: win[i]!.end,
    params: { ...(s.params ?? {}), shot: s.id, n: i + 1 }, post: s.post, maxSamples: s.maxSamples,
  }));
  const dur = filmDuration(film, shots);
  const overlays: FilmEntry[] = (film.overlays ?? []).map((o) => {
    if (win.some((w) => w.id === o.id)) throw new Error(`overlay id '${o.id}' is also a shot's`);
    return { id: o.id, load: loaderOf(o.scene), start: o.start ?? 0, end: o.end ?? dur, params: { ...(o.params ?? {}), shot: o.id }, post: o.post, kind: 'overlay' as const };
  });
  return [...shots, ...overlays];
}

/** The film's length: `duration`, else the end of its last shot. */
export function filmDuration(film: Pick<FilmSpec, 'duration'>, entries: readonly { start: number; end: number; kind?: string }[]): number {
  return film.duration ?? Math.max(0, ...entries.filter((e) => e.kind !== 'overlay').map((e) => e.end));
}

/** The default window either side of a cut (s). */
export const DEFAULT_SIDE = 0.25;

/** The film's transitions: each shot's inline `transition` (from the shot before it), then film.transitions. */
export function filmTransitions(film: Pick<FilmSpec, 'scenes' | 'transitions'>): TransitionSpec[] {
  const out: TransitionSpec[] = [];
  film.scenes.forEach((s, i) => {
    if (!s.transition || i === 0) {
      if (s.transition && i === 0) throw new Error(`shot ${s.id} is the first: there is nothing to transition from`);
      return;
    }
    const from = film.scenes[i - 1]!.id;
    const t = typeof s.transition === 'string' ? { kind: s.transition } : s.transition;
    const side = t.kind === 'cut' ? 0 : DEFAULT_SIDE;
    out.push({ ...t, from, to: s.id, pre: t.pre ?? side, post: t.post ?? side } as TransitionSpec);
  });
  return [...out, ...(film.transitions ?? [])];
}

/** Scene spans for the transition validator (transition.ts transitionEntries): the shots, in order. */
export function sceneSpans(entries: readonly FilmEntry[]): SceneSpan[] {
  return entries.filter((e) => e.kind !== 'overlay').map((e) => ({ id: e.id, act: '', start: e.start, end: e.end }));
}

/**
 * Put the film's format, frame rate, folder, theme and fonts in force. Call it before anything is built: the engine's
 * render targets take the format, shaders bake the theme's palette when they compile, layout measures with the fonts.
 */
export function applyFilm(film: Pick<FilmSpec, 'id' | 'format' | 'fps' | 'theme' | 'fonts'>, base = `films/${film.id}/`) {
  configure({ format: film.format ?? 'landscape', fps: film.fps ?? 30, film: film.id, base });
  setTheme(film.theme ?? 'noir');
  resetFonts();
  if (film.fonts) registerFonts(film.fonts.faces.map((f) => ({ ...f, url: /^([a-z]+:|\/)/i.test(f.url) ? f.url : base + f.url })), { replace: film.fonts.replace });
}
