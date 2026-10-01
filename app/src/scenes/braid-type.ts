// The type of scene `braid`, on its 2D layer over the B08 plate and the card. Pure functions of time and the tracked
// anchors (data/track/b08_braid.json).
//
// - The query, `what camera did I buy`, typed into the top right as the scene opens (the input the three arms search
//   for), a hairline under it and a caret.
// - The labels, JetBrains Mono on hairline leaders from their arms (tracked: lbl_<arm>), each drawn on as its arm lands
//   on her first word for it: `lexical · your words`, `body · what you meant`, `cues · how you’d ask`. The arm's name
//   is bright; the rest of the phrase lights word by word as she says it.
// - "braided": each label lets its arm's name go. The chip, the leader and the phrase fade, and the name flies to the
//   plait's head (tracked: head) and rides it toward the camera, the three names stacked beside it; on the downbeat of
//   "answer" they slide into their cells of the card's `matched: lexical · cue · body` row (the card's own geometry,
//   Panel.cellOrigin, projected), `cues` dropping its s on the way, and hand over to the row as it lands: the row
//   shows the three words in the keyword tone the names fly in.
// - The footnote, `Ranked memories, no model call. Milliseconds.`, typed under the card once it hangs open.
import type { Anchor, Track } from '../engine/track';
import { F, font, measure } from '../engine/type';
import { rgba } from '../engine/palette';
import { spring } from '../engine/motion';
import { clamp, ease, frameIdx, lerp, prog } from '../engine/util';
import type { Word } from '../engine/vo';
import { ARMS, type Arm } from './braid-time';

/** The labels: mono on a hairline leader from the arm to a dark chip (loom's labels). */
export const LBL = { px: 22, fam: F.mono(500), padX: 10, padY: 7, dot: 3.4 };
/** Where each chip hangs from its anchor (px): the leader runs from the dot to (dx, dy), the chip's `side` edge there. */
export const CHIP: Record<Arm, { dx: number; dy: number; side: 'left' | 'right' }> = {
  lexical: { dx: -26, dy: 66, side: 'right' },
  body: { dx: -46, dy: 12, side: 'right' },
  cues: { dx: -22, dy: -72, side: 'right' },
};
/** The query: mono, right-aligned to the title-safe edge, at the top. */
export const QUERY = { px: 30, fam: F.mono(500), right: 1824, base: 158, cps: 48 };
/** The footnote: mono, bone-dim, under the card; typing speed. */
export const NOTE = { px: 24, fam: F.mono(400), below: 64, cps: 100 };

/** The anchor `name` smoothed over ±0.12 s (9 samples of the track): where a label's chip hangs. */
export function steadyAt(track: Track, name: string, t: number): { x: number; y: number } {
  let x = 0, y = 0;
  for (let k = -4; k <= 4; k++) {
    const a = track.at(name, t + k * 0.03);
    x += a.x;
    y += a.y;
  }
  return { x: x / 9, y: y / 9 };
}

/** A label's draw-on from its arm's landing: the dot (0..1+ spring), the leader (0..1), the characters typed. */
export function labelOn(t: number, at: number, chars: number) {
  return {
    dot: spring(t - at, 6, 0.55),
    leader: prog(t, at, at + 0.14, ease.outExpo),
    typed: clamp(Math.floor((t - at - 0.08) * 70) + 1, 0, chars),
  };
}

/** How lit a phrase word is (0 dim .. 1 bone): it lights as she says it. */
export const wordLit = (t: number, w: Word) => prog(t, w.start - 0.02, w.start + 0.16, ease.outCubic);

/** The label's text split: the arm's name (head), the separator, and the phrase's words (as the label spells them). */
export function splitLabel(text: string): { head: string; sep: string; words: string[] } {
  const i = text.indexOf(' · ');
  if (i < 0) throw new Error(`braid: label "${text}" has no " · "`);
  return { head: text.slice(0, i), sep: ' · ', words: text.slice(i + 3).split(' ') };
}

/** Where a chip's text starts (its baseline's left end) for an anchor at p, its text `w` px wide. */
export function chipText(arm: Arm, p: { x: number; y: number }, w: number) {
  const c = CHIP[arm];
  const ax = p.x + c.dx, ay = p.y + c.dy;
  const x = c.side === 'left' ? ax + LBL.padX : ax - LBL.padX - w;
  return { x, base: ay + 0.36 * LBL.px, attach: { x: ax, y: ay } };
}

// ------------------------------------------------------------------------------------------------ the names' flight

/** The three names beside the plait's head as it flies (px from the head anchor, baseline's left end): stacked from the
 * card's matched row down (its baseline is about 10 px above the hinge), so each slides straight across into its cell,
 * clear of the path's row above, and body and cues trade places on the way (the card ranks them lexical · cue · body). */
export const RIDE: Record<Arm, { dx: number; dy: number }> = {
  lexical: { dx: 40, dy: -10 },
  body: { dx: 40, dy: 22 },
  cues: { dx: 40, dy: 54 },
};

export interface Flight {
  /** 0..1: the name slides from its chip down its arm into P0, fading into the braid as it gets there. */
  absorb: number;
  /** 0..1: it comes out of the plait's head beside it (once the head has pulled clear of P0) into its place. */
  emerge: number;
  /** 0 while it rides the head, 1 as it lands in the card's row. */
  land: number;
}

/**
 * The names' flight, word for word with the threads: on "braided" each slides down its arm into P0 and is taken into
 * the plait (a 32nd apart, in the order she named them); they come out of its head together as it flies at the lens,
 * ride beside it, and land in the matched row on its downbeat.
 */
export function flight(t: number, arm: Arm, zip: number, matched: number): Flight {
  const i = ARMS.indexOf(arm);
  const go = zip + 0.02 + i * 0.075;
  const out = zip + 0.46 + i * 0.05;
  const into = matched - 0.2 + i * 0.02;
  return {
    absorb: prog(t, go, go + 0.3, ease.inOutCubic),
    emerge: prog(t, out, out + 0.24, ease.outCubic),
    land: prog(t, into, matched, ease.inOutCubic),
  };
}

type P = { x: number; y: number };

/**
 * A name along its flight and how much of it shows: from its chip (`chip`) to its arm's dot (`dot`) and down the arm to
 * P0 (`p0`), fading as it is taken in; then out of the plait's head (`head`) into its place beside it (`ride`); then into
 * the row (`cell`).
 */
export function flightPoint(f: Flight, chip: P, dot: P, p0: P, head: P, ride: P, cell: P): P & { alpha: number } {
  if (f.emerge <= 0) {
    const a = f.absorb;
    const k = a < 0.35 ? a / 0.35 : 1, j = a < 0.35 ? 0 : (a - 0.35) / 0.65;
    const x = lerp(lerp(chip.x, dot.x, k), p0.x, j), y = lerp(lerp(chip.y, dot.y, k), p0.y, j);
    return { x, y, alpha: 1 - prog(a, 0.5, 1) };
  }
  const e = f.emerge;
  const from = { x: head.x + 6, y: ride.y };
  const p = { x: lerp(from.x, ride.x, e), y: lerp(from.y, ride.y, e) };
  return { x: lerp(p.x, cell.x, f.land), y: lerp(p.y, cell.y, f.land), alpha: prog(e, 0, 0.45) };
}

/** The label's name for an arm, as the card's row spells it: `cues` lands as `cue`. */
export function rowWord(head: string, row: string): { word: string; col: number } {
  for (const w of [head, head.replace(/s$/, '')]) {
    const re = new RegExp(`(^|[^a-z])${w}([^a-z]|$)`);
    const m = re.exec(row);
    if (m) return { word: w, col: m.index + m[1]!.length };
  }
  throw new Error(`braid: "${head}" is not in the card's row "${row}"`);
}

// ------------------------------------------------------------------------------------------------ drawing

type Ctx = CanvasRenderingContext2D;

/** A rounded rectangle's path. */
export function roundRect(c: Ctx, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

/**
 * A label at time t: dot, leader, chip and text, drawn on from `at` (its arm's landing). The dot rides the thread (`p`,
 * its anchor, twang and all); the chip hangs from `steady`, the anchor smoothed, so it does not shake with the string.
 * `words` are her words for the phrase (they light the label's words as she says them). `fade` (1..0) takes the label
 * away when its name leaves; `keepHead` false hides the name in the chip (it is flying). Returns where the name's text
 * starts, for the flight.
 */
export function drawLabel(c: Ctx, t: number, arm: Arm, text: string, p: Anchor, steady: { x: number; y: number }, at: number, words: Word[], fade: number, keepHead: boolean) {
  const { head, sep, words: lw } = splitLabel(text);
  const { px, fam, padX, padY, dot } = LBL;
  c.font = font(fam, px);
  const w = measure(text, fam, px);
  const pos = chipText(arm, steady, w);
  const on = labelOn(t, at, Array.from(text).length);
  const a0 = fade * clamp(p.visible);
  if (t < at - 0.02 || a0 <= 0.003) return { x: pos.x, base: pos.base };
  c.save();
  c.globalAlpha = a0;
  // the dot on the thread and the leader to the chip
  c.fillStyle = rgba('bone', 0.9);
  c.beginPath();
  c.arc(p.x, p.y, dot * on.dot, 0, Math.PI * 2);
  c.fill();
  const lx = lerp(p.x, pos.attach.x, on.leader), ly = lerp(p.y, pos.attach.y, on.leader);
  c.strokeStyle = rgba('boneDim', 0.75);
  c.lineWidth = 1.25;
  c.beginPath();
  c.moveTo(p.x, p.y);
  c.lineTo(lx, ly);
  c.stroke();
  if (on.leader >= 1 && on.typed > 0) {
    const typed = Array.from(text).slice(0, on.typed).join('');
    const tw = measure(typed, fam, px);
    roundRect(c, pos.x - padX, pos.base - px * 0.8 - padY + 2, tw + 2 * padX, px + 2 * padY, 4);
    c.fillStyle = rgba('panel', 0.9);
    c.fill();
    c.lineWidth = 1;
    c.strokeStyle = rgba('ruleStrong', 0.9);
    c.stroke();
    // the name bright, the separator faint, each of her words lighting as she says it
    let x = pos.x, n = 0;
    const parts: { s: string; color: string }[] = [{ s: head, color: keepHead ? rgba('bone') : 'transparent' }, { s: sep, color: rgba('boneFaint') }];
    lw.forEach((s, i) => {
      const lit = words[i] ? wordLit(t, words[i]!) : 1;
      parts.push({ s: (i ? ' ' : '') + s, color: rgba(lit > 0.5 ? 'bone' : 'boneDim', lerp(0.55, 1, lit)) });
    });
    for (const part of parts) {
      const chars = Array.from(part.s);
      const show = chars.slice(0, Math.max(0, on.typed - n)).join('');
      n += chars.length;
      if (show) {
        c.fillStyle = part.color;
        c.fillText(show, x, pos.base);
      }
      x += measure(part.s, fam, px);
    }
  }
  c.restore();
  return { x: pos.x, base: pos.base };
}

/**
 * A flying name at its place along the flight, at size `px`, its last `drop` characters fading (`cues` -> `cue`). It is
 * the label's name and the card row's word alike (JetBrains Mono 500, bone: the row shows its arms' words in the keyword
 * tone), so the hand-over to the row is seamless.
 */
export function drawName(c: Ctx, name: string, at: { x: number; y: number }, px: number, alpha: number, drop: number, dropFade: number) {
  if (alpha <= 0.003) return;
  const fam = LBL.fam;
  c.save();
  c.font = font(fam, px);
  const keep = Array.from(name).slice(0, name.length - drop).join('');
  c.globalAlpha = alpha;
  c.fillStyle = rgba('bone');
  c.fillText(keep, at.x, at.y);
  if (drop > 0 && dropFade < 1) {
    c.globalAlpha = alpha * (1 - dropFade);
    c.fillText(name.slice(keep.length), at.x + measure(keep, fam, px), at.y);
  }
  c.restore();
}

/** The query, typed into the top right from `at`, with a hairline under it and a caret (on the output frame grid). */
export function drawQuery(c: Ctx, t: number, text: string, at: number, alpha: number) {
  const { px, fam, right, base, cps } = QUERY;
  if (t < at - 0.02 || alpha <= 0.003) return;
  c.save();
  c.font = font(fam, px);
  const w = measure(text, fam, px);
  const x0 = right - w;
  const n = clamp(Math.floor((t - at) * cps) + 1, 0, Array.from(text).length);
  const typed = Array.from(text).slice(0, n).join('');
  c.globalAlpha = alpha;
  c.fillStyle = rgba('bone', 0.92);
  c.fillText(typed, x0, base);
  // the field's hairline, drawn out with the typing
  const rule = prog(t, at - 0.05, at + 0.25, ease.outCubic);
  c.fillStyle = rgba('ruleStrong');
  c.fillRect(right - (w + 18) * rule, base + 16, (w + 18) * rule, 1.5);
  // a block caret: solid while typing, then blinking 16 frames on and off
  const done = at + (Array.from(text).length - 1) / cps;
  const blinkOn = t < done + 0.03 || Math.floor((frameIdx(t) - frameIdx(done)) / 16) % 2 === 1;
  if (blinkOn) {
    c.fillStyle = rgba('bone', 0.8);
    c.fillRect(x0 + measure(typed, fam, px) + 4, base - 0.78 * px, 0.6 * px, px);
  }
  c.restore();
}

/**
 * A sheen crossing the card as the answer lands: a soft diagonal band of bone light (at most 9%: a glint on the panel,
 * nowhere near the bloom), clipped to the card's face as it hangs (`quad`, its corners on screen), `u` 0..1 across it.
 */
export function drawSheen(c: Ctx, quad: { x: number; y: number }[], u: number) {
  const level = Math.sin(Math.PI * clamp(u));
  if (level <= 0.002) return;
  const xs = quad.map((q) => q.x), ys = quad.map((q) => q.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), yMid = (Math.min(...ys) + Math.max(...ys)) / 2;
  const cx = lerp(x0 - 160, x1 + 160, u), half = 110, dx = Math.cos(-0.35), dy = Math.sin(-0.35);
  c.save();
  c.beginPath();
  quad.forEach((q, i) => (i ? c.lineTo(q.x, q.y) : c.moveTo(q.x, q.y)));
  c.closePath();
  c.clip();
  const g = c.createLinearGradient(cx - half * dx, yMid - half * dy, cx + half * dx, yMid + half * dy);
  g.addColorStop(0, rgba('bone', 0));
  g.addColorStop(0.5, rgba('bone', 0.09 * level));
  g.addColorStop(1, rgba('bone', 0));
  c.fillStyle = g;
  c.fillRect(x0 - 4, Math.min(...ys) - 4, x1 - x0 + 8, Math.max(...ys) - Math.min(...ys) + 8);
  c.restore();
}

/** The footnote, typed in from `at` with its left end at (x, base). */
export function drawNote(c: Ctx, t: number, text: string, at: number, x: number, base: number) {
  const n = clamp(Math.floor((t - at) * NOTE.cps + 1), 0, Array.from(text).length);
  if (n <= 0) return;
  c.save();
  c.font = font(NOTE.fam, NOTE.px);
  c.fillStyle = rgba('boneDim');
  c.fillText(Array.from(text).slice(0, n).join(''), x, base);
  c.restore();
}
