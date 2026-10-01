// The clock of `proof`: every time the scene keys on, from the data (her measured onsets, the score's sections, beats
// and downbeats). Nothing here is a hard-coded second.
//
// - "Forty-four…" is spoken in the room tone the score left behind in `honest`: 44 is revealed by light as she says it.
// - The slam: the score comes back on a downbeat (the start of its section inside the scene's window). The odometer's
//   rounds roll one per beat from there: each round is kicked on its beat (the drums tear into motion with the hit) and
//   clicks home an eighth note later, on the "and", so 91.4 lands as she says "four.".
// - The next downbeat flashes the per-category bars; the `%`, the last drum, flips up into its window on "bad".
import { wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';
import type { AudioData } from '../engine/audio';

/** How much of a beat a round's roll takes, kick to click: an eighth note. */
export const ROLL_BEATS = 0.5;

export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'proof').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`proof: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const forty = word('fortyfour'), four = word('four'), not = word('not'), bad = word('bad');
  // the slam: where the score comes back in, a section starting inside the window on a downbeat (else the first
  // downbeat after "Forty-four" begins)
  const back = audio.sections.find((s) => s.start > start + 1e-6 && s.start < end);
  const onDown = (t: number) => audio.downbeats.some((d) => Math.abs(d - t) < 1e-6);
  const slam = back && onDown(back.start) ? back.start : audio.downbeats.find((d) => d > forty.start + 1e-6);
  if (slam === undefined) throw new Error('proof: no downbeat for the slam');
  // the rounds: kicked on the slam and the three beats after it, each clicking home an eighth note later
  const after = audio.beats.filter((b) => b > slam + 1e-6).slice(0, 3);
  if (after.length < 3) throw new Error('proof: the rounds need three beats after the slam');
  const kicks = [slam, ...after];
  const lands = kicks.map((k) => k + ROLL_BEATS * beat);
  // the bars flash on the first downbeat after the last round lands
  const bars = audio.downbeats.find((d) => d > lands[3]! + 1e-6);
  if (bars === undefined || bars > not.start) throw new Error('proof: the bars need a downbeat between the landing and "Not"');
  return {
    start, end, beat,
    /** "Forty-four…": the 44 is lit as she says it. */
    forty: forty.start,
    slam, kicks, lands,
    /** She says "four." as 91.4 lands. */
    four: four.start,
    bars,
    /** "Not bad…": the % flips up on "bad". */
    not: not.start, bad: bad.start,
    /** The beat after "bad": the quote types in from there. */
    quote: audio.beats.find((b) => b > bad.start + 0.2) ?? bad.start + beat,
    /** The last downbeat in the window (a shine across the figure before the cut), if one falls after the quote. */
    shine: audio.downbeats.find((d) => d > bad.start + 0.5 && d < end - 0.25) ?? null,
  };
}
export type Times = ReturnType<typeof timesOf>;
