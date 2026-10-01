// The clock of scene 13 `connect` (Plan 2 Task 23): every moment it keys on, from the data (her measured onsets, the
// score's beats and downbeats), and the pure motion those moments drive: the ✔'s pen stroke and the carousel's turn and
// flips. Nothing here is a hard-coded second, and everything is a pure function of its inputs.
//
// "One command... and I'm in Claude Code." / "Or any agent, in any language."
// - "One" (on its beat): the Claude Code command (spec §11.1) starts typing; it is typed by the end of "command…".
// - The downbeat in her pause: Enter. `$ claude mcp list` types in the rest of the pause and is entered.
// - "I'm": the server answers. "in" (on its beat): the ✔ is drawn, a moss pen stroke that lands on the beat. I'm in.
// - "Claude Code.": the camera pulls back off the ✔ and the terminal is one face of a carousel.
// - From the beat on "Code." to the last beat before the cut, six beats: one card flips in on each (L27).
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { ease, prog } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';

/** The cards that flip in after the terminal (the MCP config, `gitloom install`, the four SDKs): one a beat. */
export const CARDS = 6;
/** The carousel's faces: the terminal and the cards. */
export const FACES = CARDS + 1;
/** One face's turn (radians). */
export const STEP = (2 * Math.PI) / FACES;

/** The breath at each `\` line break of the command (s). */
export const BREAK = 0.05;
/** How long the ✔'s pen takes to draw it (s): it lands on the beat. */
export const TICK_DRAW = 0.17;

/** A window of song time (s). */
export interface Span {
  at: number;
  end: number;
}

/** Every time the scene keys on (song seconds), from her onsets and the score's grid. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'connect').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`connect: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const one = word('one'), command = word('command'), and = word('and'), im = word('im'), inn = word('in');
  const claude = word('claude'), code = word('code'), or = word('or'), agent = word('agent'), language = word('language');
  // L26: Enter on the downbeat in her pause after "command…" (the new prompt prints on it; the rows open just before,
  // as a terminal's do); the command types from "One" to a moment before
  const enter = audio.downbeats.find((d) => d > command.end - 0.1 && d < and.start);
  if (enter === undefined) throw new Error('connect: no downbeat between "command…" and "and" for the Enter');
  const type: Span = { at: one.start, end: enter - 0.2 };
  if (!(type.end > command.end - 0.25)) throw new Error('connect: the command would be typed long before "command…" ends');
  // `$ claude mcp list` types in the rest of the pause; its answer prints as she says "I'm" (its row opening once the
  // typing is done); the ✔ lands on the beat she says "in" on (or on "in" itself)
  const tick = audio.beats.find((b) => Math.abs(b - inn.start) < beat / 4) ?? inn.start;
  const list: Span = { at: enter + 0.06, end: enter + 0.26 };
  const out = list.end + 0.15;
  if (!(out + 0.01 < tick - TICK_DRAW && Math.abs(out - im.start) < 0.15)) throw new Error('connect: no room for `claude mcp list` and its answer before the ✔');
  // L27: the six beats from "Code." to the last before the cut, a card on each
  const cards = audio.beats.filter((b) => b > tick + beat / 2 && b < end - beat / 4);
  if (cards.length !== CARDS) throw new Error(`connect: the carousel needs ${CARDS} beats between the ✔ and the cut, the grid has ${cards.length}`);
  // the camera pulls back off the ✔ on "Claude", and the first card lands on the next beat
  const reveal: Span = { at: claude.start + 0.04, end: cards[0]! - 0.05 };
  return {
    start, end, beat,
    one: one.start, command: command.end, and: and.start, im: im.start, in: inn.start,
    claude: claude.start, code: code.start, or: or.start, agent: agent.start, language: language.start,
    type, enter, list, out, tick, reveal, cards,
  };
}
export type Times = ReturnType<typeof timesOf>;

// ------------------------------------------------------------------------------------------------ the ✔

/**
 * How far the ✔'s pen is along its path at t (0..1), landing on the beat: it sets down and runs the short arm, then
 * flicks up the long one faster (its speed rises the whole way, as a hand's does).
 */
export function penAt(t: number, tick: number): number {
  const u = prog(t, tick - TICK_DRAW, tick);
  return 0.3 * u + 0.7 * u * u;
}

/** The pen's heat (0..1): hot while it draws, cooling fast after it lands. */
export function penHeat(t: number, tick: number): number {
  if (t < tick - TICK_DRAW) return 0;
  if (t <= tick) return 1;
  return Math.exp(-(t - tick) / 0.09);
}

/**
 * The ✔'s own light (its stroke's glow level, glow('moss', ·)): lit while it is drawn, flaring as it lands, settling
 * to a level that still blooms a little (it stays the frame's one lit mark through the hold), and dimming as the
 * terminal turns away into the carousel.
 */
export function tickLevel(t: number, T: Pick<Times, 'tick' | 'cards'>): number {
  if (t < T.tick - TICK_DRAW) return 0;
  if (t < T.tick) return TICK_LIGHT.drawing;
  const away = 1 - 0.3 * prog(t, T.cards[0]! - 0.1, T.cards[1]!);
  return TICK_LIGHT.rest * away + TICK_LIGHT.flare * Math.exp(-(t - T.tick) / TICK_LIGHT.decay);
}

/** The ✔'s light (glow levels): the stroke behind the pen as it draws, the flare as it lands and its decay (s), at rest. */
export const TICK_LIGHT = { drawing: 2.1, flare: 1.1, decay: 0.16, rest: 1.1 };

// ------------------------------------------------------------------------------------------------ the carousel

/**
 * The carousel's turn on each card's beat: it whips round a face and decelerates into the beat (outQuart over `dur`),
 * so a card lands still and sharp on its beat and holds there for the rest of it. (A spring landing on the beat would
 * still be moving fast on it: a face a beat is a long way to turn, and every landing would be a smear.)
 */
export const TURN = { dur: 0.26 };
/**
 * A card's flip: it starts once the turn has it nearly round (its back to the camera still), turns over through its
 * middle (inOutCubic, fastest edge-on) and lands face up on the beat with the turn.
 */
export const FLIP = { dur: 0.2 };

/** A turn's progress (0..1) at t, landing on `hit`. */
export const turnStep = (t: number, hit: number) => prog(t, hit - TURN.dur, hit, ease.outQuart);
/** A flip's progress (0..1) at t, landing on `hit`. */
export const flipStep = (t: number, hit: number) => prog(t, hit - FLIP.dur, hit, ease.inOutCubic);

/** The carousel's turn at t (radians): a face's turn on each card's beat, so card k (1-based) is in front from its beat. */
export function turnAt(t: number, cards: readonly number[]): number {
  let a = 0;
  for (const c of cards) a += turnStep(t, c);
  return a * STEP;
}

/**
 * Face k's flip at t (radians about its own upright axis; 0: face up). The terminal (face 0) is face up throughout; a
 * card lies face down (π: its back to the world) until it flips in as its turn ends, landing face up on its beat. It
 * turns the way the ring does, so it comes round showing its back and shows its face only as it lands.
 */
export function flipAt(t: number, k: number, cards: readonly number[]): number {
  if (k === 0) return 0;
  return Math.PI * (1 - flipStep(t, cards[k - 1]!));
}

/** Face k's place round the carousel at turn `turn` (radians; 0: in front, + to the right as the camera sees it). */
export const faceAngle = (k: number, turn: number) => k * STEP - turn;
