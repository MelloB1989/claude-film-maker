// The clock of scene 04 `repo`: every time it keys on, from her onsets and the score's grid, and its terminal's two
// typed commands. Pure: repo.ts draws from it and the cue sheet (sfx/scenes/repo.ts) places its sounds from it.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import type { PanelLine } from '../engine/panels';
import { norm, type VO, type Word } from '../engine/vo';
import S from './repo.strings.json';

const [CD, LS, GITLOG, ...REST] = S as string[];
/** The log, newest first (spec §4): each a hash, a space, a message. */
export const LOG = REST.slice(0, 4).map((s) => ({ line: s, hash: s.slice(0, s.indexOf(' ')) }));
/** The listing: the four tiers' directories, the chips. */
export const DIRS = LS!.split(/\s+/).filter(Boolean);

/** Every time the scene keys on, from her onsets and the score's grid (song seconds). */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'repo').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`repo: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const im = word('im'), git = word('git'), repo = word('repo'), you = word('you'), read = word('read'), me = word('me');
  // the listing pops on the downbeat she reaches "git repo" on, its chips a 32nd note apart
  const pop = audio.downbeats.find((d) => d > im.start + 0.25 && d < repo.start) ?? git.start;
  const chips = DIRS.map((_, i) => pop + (i * beat) / 8);
  // `cd ~/memory && ls` types in with "I'm just a…", done just before the pop; `git log --oneline` types in the pause
  // after "repo." and is entered as the camera starts its dive
  const cd = { at: im.start, end: pop - 0.13 };
  const log = { at: repo.start + 0.1, end: Math.min(you.start - 0.32, repo.start + 0.5) };
  // the commits land on the beats from "You", one a beat
  const beads = audio.beats.filter((b) => b >= you.start - 0.06).slice(0, LOG.length);
  if (beads.length < LOG.length || beads[beads.length - 1]! > end - 0.9) throw new Error('repo: the commits need four beats from "You" with a second left for the file');
  // the footnote types in on "read"; the file swings in on the beat after the last commit
  const fileLand = beads[beads.length - 1]! + beat;
  return {
    start, end, beat, im: im.start, repo: repo.start, you: you.start, me: me.start,
    pop, chips, cd, log, enter: log.end + 0.05,
    /** The camera crosses the terminal's face. */
    cross: beads[0]! - 0.1,
    beads, note: read.start - 0.02, fileLand,
  };
}
export type Times = ReturnType<typeof timesOf>;

/** A command typed from `at`, its last key on `end` (the `$ ` prompt is there, not typed). */
const typed = (text: string, at: number, end: number): PanelLine => ({ text, kind: 'cmd', at, cps: (Array.from(text).length - 3) / (end - at) });

/**
 * The terminal's rows: `cd ~/memory && ls`, the listing's row (the chips are its output), `git log --oneline`, and the
 * dive's row, which opens on Enter.
 */
export function terminalLines(T: Pick<Times, 'cd' | 'log' | 'pop' | 'enter'>): PanelLine[] {
  return [typed(CD!, T.cd.at, T.cd.end), { text: '', kind: 'out', at: T.pop - 0.1 }, typed(GITLOG!, T.log.at, T.log.end), { text: '', kind: 'out', at: T.enter }];
}
