// The clock of scene 14 `anywhere` (Plan 2 Task 24): every moment it keys on, from the data (her measured onsets, the
// score's beats and downbeats), and the pure arithmetic of the namespaces doubling. Nothing here is a hard-coded second,
// and everything is a pure function of its inputs.
//
// "On your machine... or in my cloud." / "One memory for every user you have."
// - The cut in (a downbeat): the terminal waits, its prompt breathing. On "On" (its beat) the install line types in
//   with her, done as "machine…" ends; "machine" slams in on its onset over the terminal.
// - The four chips are dealt out of the machine on sixteenths, the first on the beat in her pause, the last a sixteenth
//   before the split; Enter goes a sixteenth before the first.
// - The split, on the downbeat between "or" and "in": the camera pulls back to both pages, the cloud's three console
//   cards deal in on sixteenths, "cloud" slams in on its onset; the Playground's tool calls land on the beats from
//   "cloud.", retrieve (moss) then remember (blood); the Memory Graph settles into its tier regions from its deal.
// - "One": the first namespace, user-0001, in the Namespaces card.
// - The downbeat on "for": a cut (half a frame before it, so no frame mixes the two shots) to user-0001 alone, and on
//   the sixteenths after it the namespaces double eleven times, 1 to 2,048, as she says "for every user you have."
// - The label types in on "user"; the footnote on the beat on "have.".
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { FPS } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';

/** Doublings from one namespace to 2,048 (2^11). */
export const DOUBLINGS = 11;
export const NAMESPACES = 2 ** DOUBLINGS;
/** The chips under the terminal (the facts sheet's line, split at its dots). */
export const CHIPS = 4;

/** A window of song time (s). */
export interface Span {
  at: number;
  end: number;
}

/** Every time the scene keys on (song seconds), from her onsets and the score's grid. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'anywhere').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`anywhere: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm, q = beat / 4;
  const on = word('on'), your = word('your'), machine = word('machine'), or = word('or'), inn = word('in'), my = word('my'), cloud = word('cloud');
  const one = word('one'), memory = word('memory'), forr = word('for'), every = word('every'), user = word('user'), you = word('you'), have = word('have');
  const beats = audio.beats.filter((b) => b >= start - 1e-6 && b < end);
  const downs = audio.downbeats.filter((d) => d >= start - 1e-6 && d < end);

  // L28. The split: the downbeat in her pause between "machine…" and "in"
  const split = downs.find((d) => d > machine.end && d < inn.start);
  if (split === undefined) throw new Error('anywhere: no downbeat between "machine…" and "in" for the split');
  // the chips: one a sixteenth from the first beat in her pause after "machine…", the last a sixteenth before the split
  const chip0 = beats.find((b) => b > machine.end + q / 2);
  if (chip0 === undefined) throw new Error('anywhere: no beat after "machine…" for the chips');
  const chips = Array.from({ length: CHIPS }, (_, k) => chip0 + k * q);
  if (!(chips[CHIPS - 1]! < split - q / 2)) throw new Error('anywhere: the chips would run into the split');
  // the install line types with "On your machine…", from "On"; Enter (the new prompt) a sixteenth before the first chip
  const enter = chip0 - q;
  const type: Span = { at: on.start, end: enter - 0.03 };
  if (!(type.end > machine.end - 0.1 && type.end - type.at > 0.5)) throw new Error('anywhere: the install line would not type with "On your machine…"');
  // the cloud's cards deal in on sixteenths from the split: the Playground, the Memory Graph, Namespaces
  const deal = [split, split + q, split + 2 * q];
  // the Playground's tool calls land on the beat on "cloud." and the next: it checks what it knows, then remembers
  const retrieve = beats.find((b) => b > cloud.start - q && b < cloud.end + q);
  if (retrieve === undefined) throw new Error('anywhere: no beat on "cloud." for the first tool call');
  const remember = retrieve + beat;
  // the Memory Graph settles into its tier regions from its deal; its relations draw on as she says "memory"
  const settle: Span = { at: deal[1]!, end: memory.end };

  // L29. "One": the first namespace's row
  const first = one.start;
  // the downbeat on "for": the cut to the field, half a frame before that downbeat's frame (no frame's shutter, a
  // quarter frame either side of its time, reaches it)
  const down = downs.find((d) => d > memory.start && Math.abs(d - forr.start) < q);
  if (down === undefined) throw new Error('anywhere: no downbeat on "for" for the cut');
  const cut = (Math.round(down * FPS) - 0.5) / FPS;
  // eleven doublings, one a sixteenth from the one after the downbeat: user-0001 alone for a sixteenth, then 2, 4, …
  const doublings = Array.from({ length: DOUBLINGS }, (_, k) => down + (k + 1) * q);
  // the label types in on "user"; the footnote on the beat on "have."
  const label = user.start - 0.02;
  const note = beats.find((b) => Math.abs(b - have.start) < q) ?? have.start;
  if (!(doublings[DOUBLINGS - 1]! < end - beat)) throw new Error('anywhere: the doublings need a beat\'s hold before the cut');
  return {
    start, end, beat,
    on: on.start, your: your.start, machine: machine.start, machineEnd: machine.end, or: or.start, in: inn.start, my: my.start,
    cloud: cloud.start, cloudEnd: cloud.end,
    one: one.start, memory: memory.start, for: forr.start, every: every.start, user: user.start, you: you.start, have: have.start,
    type, enter, chips, split, deal, retrieve, remember, settle, first, down, cut, doublings, label, note,
  };
}
export type Times = ReturnType<typeof timesOf>;

// ------------------------------------------------------------------------------------------------ the namespaces

/** A namespace's name: user-0001 for the first (index 0) … user-2048. */
export const nsName = (i: number) => `user-${String(i + 1).padStart(4, '0')}`;

/**
 * Where namespace i sits in the field (column, row, from the first's corner): its index's bits dealt alternately to x
 * and to y (a Morton order), so the first 2^k namespaces always fill one block, and each doubling copies the whole block
 * beside itself: along x, then y, then x… Eleven doublings make 64 columns by 32 rows.
 */
export function cellOf(i: number): { x: number; y: number } {
  let x = 0, y = 0;
  for (let b = 0; b < DOUBLINGS; b++) {
    const bit = (i >> b) & 1;
    if (b % 2 === 0) x |= bit << (b >> 1);
    else y |= bit << (b >> 1);
  }
  return { x, y };
}

/** The doubling (0-based) that brings namespace i in; -1 for the first, which is there before any. */
export const levelOf = (i: number) => (i <= 0 ? -1 : Math.floor(Math.log2(i) + 1e-9));

/** The block of namespaces after n doublings: its columns and rows. */
export function blockAfter(n: number): { cols: number; rows: number } {
  return { cols: 2 ** Math.ceil(n / 2), rows: 2 ** Math.floor(n / 2) };
}

/**
 * Where namespace i comes from: the one it is a copy of (the block's same place before the doubling that brings it), as
 * a (column, row) offset back to it. Doubling k copies along x when k is even, along y when it is odd, by the block's
 * extent along that axis before the doubling.
 */
export function copyOffset(i: number): { dx: number; dy: number } {
  const k = levelOf(i);
  if (k < 0) return { dx: 0, dy: 0 };
  const b = blockAfter(k);
  return k % 2 === 0 ? { dx: b.cols, dy: 0 } : { dx: 0, dy: b.rows };
}
