// The clock of scene 10 `graph`: every moment it keys on, from the data (her measured onsets, the score's beats and
// downbeats). Nothing here is a hard-coded second; the durations are the motion's own.
//
// "I connect the dots... and I learn your language."
// - The cut: in close on the file's last line, `Works with [[facts/orgs/acme.md]].`; a thread draws on under the link
//   in the bar's last beat, and tightens.
// - "I", on the downbeat: the link lifts off the page as the thread, which races out into the dark and lands in the
//   acme.md bead on the eighth, inside "connect": an edge.
// - "the dots…": the camera pulls back to the constellation of memories. A new memory, maya.md, hangs a thread to
//   [[facts/trips/lisbon-2026.md]], a file that doesn't exist yet: the thread dangles, blood dashes running down it,
//   pinging on the beat, unanswered.
// - The beat after "dots…": the trip is written. Its bead drops in where the link pointed, the loose end snaps up to it
//   and the edge heals: blood to moss. The moss runs on, the walk, a hop a sixteenth: trip, hotel, city.
// - "and I learn": a terminal rises into the foreground and `gitloom vocab add --term kubernetes --alias k8s` types in
//   with her; on the downbeat the answer, `k8s → kubernetes  ·  search finds either form`.
// - "your language.": `k8s` lifts off the answer as a thread (the link's rhyme) and searches up into the graph; on the
//   beat it finds acme.md, and the word it says, kubernetes, lights. The camera rides up the thread into acme.md's
//   close-up: one move from the link to the find, no cut.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';

/** The walk's hops after the heal: trip, hotel, city, one each this fraction of a beat apart (a sixteenth triplet). */
export const HOP = 1 / 6;
export const HOPS = 3;

export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'graph').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`graph: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const i1 = word('i'), connect = word('connect'), dots = word('dots'), and = word('and');
  const learn = word('learn'), your = word('your'), language = word('language');
  const inside = (t: number) => t > start + 1e-6 && t < end - 1e-6;
  const beats = audio.beats.filter(inside), downs = audio.downbeats.filter(inside);
  const next = (grid: number[], after: number, what: string) => {
    const b = grid.find((x) => x > after + 1e-6);
    if (b === undefined || !inside(b)) throw new Error(`graph: no ${what} after ${after} in the window`);
    return b;
  };

  // "I", on its downbeat: the lift-off; it lands in acme.md on the eighth after, inside "connect"
  const lift = downs.find((d) => Math.abs(d - i1.start) < 0.1) ?? i1.start;
  const land = lift + beat / 2;
  if (!(land > connect.start && land < connect.end + 0.05)) throw new Error('graph: the edge must land inside "connect"');
  // the underline draws on under the link in the beat before, and tightens
  const underline = { at: lift - 0.46, end: lift - 0.2 };
  // the dangling link pings on the beat in "the dots…", unanswered; the trip is written on the beat after "dots…"
  const ping = next(beats, land, 'beat');
  const heal = next(beats, dots.end - 0.05, 'beat');
  if (!(heal > ping)) throw new Error('graph: the heal must come after the ping');
  // the walk runs on from the heal: trip, hotel, city, a sixteenth apart
  const hops = Array.from({ length: HOPS }, (_, i) => heal + (i + 1) * HOP * beat);
  // the vocabulary: the terminal rises as the walk lands; the command types in with "and I learn", the answer lands on
  // the downbeat
  const answer = downs.find((d) => d > learn.start - 0.2 && d < your.start + 0.05);
  if (answer === undefined) throw new Error('graph: no downbeat for the vocabulary\'s answer');
  const rise = hops[HOPS - 1]! - 0.06;
  const type = { at: and.start + 0.06, end: answer - 0.09 };
  if (!(type.at > hops[HOPS - 1]!)) throw new Error('graph: the walk must land before the command types');
  // "your language.": k8s lifts off the answer and finds the memory on the beat inside "language."
  const seek = your.start - 0.03;
  const found = beats.find((b) => b > language.start && b < language.end) ?? language.start + 0.3;
  if (!(found - seek > 0.25)) throw new Error('graph: no time for the search to fly');
  // (no cut: the camera rides the search up into acme.md's close-up in one move, graph.ts flightKeys)
  return {
    start, end, beat,
    underline, lift, land,
    i1: i1.start, connect: connect.start, dots: dots.start, dotsEnd: dots.end,
    ping, heal, hops,
    and: and.start, rise, type, answer,
    your: your.start, language: language.start, seek, found,
  };
}
export type Times = ReturnType<typeof timesOf>;
