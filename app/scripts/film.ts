// A film outside the browser (bun): its spec (films/<id>/film.ts), its audio grid and voiceover read from disk, and the
// timeline and transitions the engine would resolve. scripts/timeline.ts and scripts/cues.ts build on it.
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { AudioData } from '../src/engine/audio';
import { applyFilm, filmDuration, filmTimeline, filmTransitions, sceneSpans, type FilmEntry, type FilmSpec } from '../src/engine/film';
import { transitionEntries, type TransitionEntry } from '../src/engine/transition';
import { VO } from '../src/engine/vo';

export const APP = path.resolve(import.meta.dir, '..');
export const ROOT = path.resolve(APP, '..');

/** The film id from --film, else $FILM, else showcase. */
export function filmArg(argv = process.argv.slice(2)): string {
  const i = argv.indexOf('--film');
  const id = (i >= 0 ? argv[i + 1] : undefined) ?? process.env.FILM ?? 'showcase';
  if (!/^[\w-]+$/.test(id)) throw new Error(`--film takes a film id (films/<id>/), got '${id}'`);
  return id;
}

export interface NodeFilm {
  film: FilmSpec;
  dir: string;
  audio: AudioData;
  vo: VO;
  timeline: FilmEntry[];
  transitions: TransitionEntry[];
  duration: number;
}

const readJson = (p: string) => JSON.parse(readFileSync(p, 'utf8'));

/** Load and resolve a film as Engine.init does, from files instead of fetches. */
export async function loadFilm(id: string): Promise<NodeFilm> {
  const dir = path.join(ROOT, 'films', id);
  if (!existsSync(path.join(dir, 'film.ts'))) throw new Error(`no film '${id}': ${path.relative(ROOT, dir)}/film.ts does not exist`);
  const film = ((await import(path.join(dir, 'film.ts'))) as { default: FilmSpec }).default;
  if (film.id !== id) throw new Error(`films/${id}/film.ts says its id is '${film.id}': the id is the folder's name`);
  applyFilm(film);
  const a = film.audio ?? {};
  const audio = a.analysis ? new AudioData(readJson(path.join(dir, a.analysis))) : AudioData.grid({ duration: film.duration ?? 3600, bpm: a.bpm, offset: a.offset, beatsPerBar: a.beatsPerBar });
  let vo = typeof film.vo === 'string' ? new VO(readJson(path.join(dir, film.vo))) : VO.empty();
  const timeline = filmTimeline(film, audio, vo);
  const duration = filmDuration(film, timeline);
  if (Array.isArray(film.vo)) vo = VO.fromCaptions(film.vo, (t) => timeline.find((e) => e.kind !== 'overlay' && t >= e.start && t < e.end)?.id ?? '', duration);
  const transitions = transitionEntries(filmTransitions(film), sceneSpans(timeline), film.wordGuard === false ? [] : vo.words);
  return { film, dir, audio, vo, timeline, transitions, duration };
}
