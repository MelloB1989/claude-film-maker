// The flat type and hairlines of scene `honest`, on its 2D layer over the stage. Pure functions of time and of where
// the stage's camera puts things on screen (logical 1080p px).
//
// - The question, `what's my sister's name?`: braid's query (JetBrains Mono 500, typed, a block caret), centred at the
//   top this time. Its caret blinks through the search and the silence, waiting; it goes when the answer comes.
// - The evidence floor: a hairline across the dark at the floor's level, drawn out from the middle as she says "And",
//   fading off at both ends like a horizon. Where a tip comes up under it the line lifts a little, quietly, as if it
//   felt the touch; it never gives.
// - I don't know.: quiet, centred, flat Bricolage Light in bone, coming into focus on "say" (no slam, no glow).
// - The footnote, verbatim, in mono under the card.
// - The embers: the faint blood light that runs down each arm as it lets go, drawn on the scene's glow layer.
import { F, font, measure } from '../engine/type';
import { rgba } from '../engine/palette';
import { clamp, ease, frameIdx, lerp, prog } from '../engine/util';

type Ctx = CanvasRenderingContext2D;

/** The question: braid's query metrics, centred; its typing speed comes from the times. */
export const QUERY = { px: 30, fam: F.mono(500), base: 172 };
/**
 * The floor's hairline: its weight (px), strength, how far in from each edge it fades up (px); the lift above a tip
 * (strength, reach either side, and how near a tip must come, px); and the faint tone on its far side, as if it were the
 * edge of a dark pane seen from under it (strength, height px).
 */
export const FLOOR = { w: 1.25, alpha: 0.75, fade: 330, lift: 0.85, reach: 130, near: 64, above: 0.22, aboveH: 180 };
/** I don't know.: her voice, quiet (Bricolage at its lightest weight). Baseline (px). */
export const KNOW = { px: 112, fam: F.display(100, 300), base: 560 };
/** The footnote under the card. */
export const NOTE = { px: 22, fam: F.mono(400), cps: 120 };

/** The question at t: typed from `at` at `cps`, its caret solid while typing then blinking, gone after `until`. */
export function drawQuery(c: Ctx, t: number, text: string, at: number, cps: number, alpha: number, until: number) {
  if (t < at - 0.02 || alpha <= 0.003) return;
  const { px, fam, base } = QUERY;
  const chars = Array.from(text);
  c.save();
  c.font = font(fam, px);
  const w = measure(text, fam, px);
  const x0 = 960 - w / 2;
  const n = clamp(Math.floor((t - at) * cps) + 1, 0, chars.length);
  const typed = chars.slice(0, n).join('');
  c.globalAlpha = alpha;
  c.fillStyle = rgba('bone', 0.92);
  c.fillText(typed, x0, base);
  // a block caret: solid while the keys land, then blinking 16 frames on and off, from the frame the typing ends
  const done = at + (chars.length - 1) / cps;
  const on = t < done + 0.03 || Math.floor((frameIdx(t) - frameIdx(done)) / 16) % 2 === 1;
  const caret = 1 - prog(t, until - 0.04, until + 0.08);
  if (on && caret > 0) {
    c.globalAlpha = alpha * caret;
    c.fillStyle = rgba('bone', 0.8);
    c.fillRect(x0 + measure(typed, fam, px) + 4, base - 0.78 * px, 0.6 * px, px);
  }
  c.restore();
}

/**
 * The evidence floor at height y (px): drawn out from the middle by `draw` (0..1), at `alpha`. `tips` are the arms'
 * tips on screen with how close each is to the line (0 far, 1 touching): the line lifts above each as it comes up.
 */
export function drawFloor(c: Ctx, y: number, draw: number, alpha: number, tips: { x: number; near: number }[]) {
  if (draw <= 0 || alpha <= 0.003) return;
  const half = 960 * ease.inOutCubic(clamp(draw));
  const x0 = 960 - half, x1 = 960 + half;
  c.save();
  const g = c.createLinearGradient(0, 0, 1920, 0);
  const f = FLOOR.fade / 1920;
  g.addColorStop(0, rgba('boneFaint', 0));
  g.addColorStop(f, rgba('boneFaint', FLOOR.alpha * alpha));
  g.addColorStop(1 - f, rgba('boneFaint', FLOOR.alpha * alpha));
  g.addColorStop(1, rgba('boneFaint', 0));
  // the far side: a breath of tone over the line, a flat dome fading up into the dark and off to both sides
  c.save();
  c.beginPath();
  c.rect(x0, y - FLOOR.aboveH, x1 - x0, FLOOR.aboveH);
  c.clip();
  c.translate(960, y);
  c.scale(1, FLOOR.aboveH / 900);
  const v = c.createRadialGradient(0, 0, 0, 0, 0, 900);
  v.addColorStop(0, rgba('panel', FLOOR.above * alpha));
  v.addColorStop(1, rgba('panel', 0));
  c.fillStyle = v;
  c.fillRect(-960, -900, 1920, 900);
  c.restore();
  c.fillStyle = g;
  c.fillRect(x0, y - FLOOR.w / 2, x1 - x0, FLOOR.w);
  // where a tip presses up under it, the line lifts toward bone over a short reach either side
  for (const tip of tips) {
    const k = FLOOR.lift * alpha * clamp(tip.near);
    if (k <= 0.004) continue;
    const a = Math.max(x0, tip.x - FLOOR.reach), b = Math.min(x1, tip.x + FLOOR.reach);
    if (b <= a) continue;
    const h = c.createLinearGradient(tip.x - FLOOR.reach, 0, tip.x + FLOOR.reach, 0);
    h.addColorStop(0, rgba('bone', 0));
    h.addColorStop(0.5, rgba('bone', k));
    h.addColorStop(1, rgba('bone', 0));
    c.fillStyle = h;
    c.fillRect(a, y - FLOOR.w / 2, b - a, FLOOR.w);
  }
  c.restore();
}

/** How close a tip `gapPx` under the floor is to it: 0 from FLOOR.near px down, 1 touching. */
export const nearness = (gapPx: number) => 1 - clamp(gapPx / FLOOR.near);

/**
 * I don't know., centred, coming into focus from `at`: from a soft blur and a few px low to sharp and in place (outCubic,
 * under half a second). `alpha` dims it.
 */
export function drawKnow(c: Ctx, t: number, text: string, at: number, alpha = 1) {
  const u = prog(t, at - 0.02, at + 0.44, ease.outCubic);
  if (u <= 0 || alpha <= 0.003) return;
  const { px, fam, base } = KNOW;
  c.save();
  c.font = font(fam, px);
  c.fontKerning = 'normal';
  c.textAlign = 'center';
  const blur = 7 * (1 - u);
  if (blur > 0.05) c.filter = `blur(${blur.toFixed(2)}px)`;
  c.globalAlpha = alpha * clamp(u * 1.25);
  c.fillStyle = rgba('bone');
  c.fillText(text, 960, base + 9 * (1 - u));
  c.restore();
}

/** The footnote, typed in from `at`, centred on x (it does not move as it types: it is laid out whole). */
export function drawNote(c: Ctx, t: number, text: string, at: number, x: number, base: number, alpha = 1) {
  const chars = Array.from(text);
  const n = clamp(Math.floor((t - at) * NOTE.cps + 1), 0, chars.length);
  if (n <= 0 || alpha <= 0.003) return;
  c.save();
  c.font = font(NOTE.fam, NOTE.px);
  const w = measure(text, NOTE.fam, NOTE.px);
  c.globalAlpha = alpha;
  c.fillStyle = rgba('boneDim');
  c.fillText(chars.slice(0, n).join(''), x - w / 2, base);
  c.restore();
}

/** A linear ramp from a to b over [t0, t1] (eased), for dims. */
export const dim = (t: number, t0: number, t1: number, a: number, b: number) => lerp(a, b, prog(t, t0, t1, ease.inOutCubic));

/**
 * The ember: a short soft run of light along a thread on screen (`pts`, its centreline projected, even in arc length),
 * centred at arc fraction `u`, `w` its half-width, `k` its strength; drawn in white on the glow layer, which the scene
 * composites as blood light (look.ts glow). Brightest at its centre, fading either way.
 */
export function drawEmber(c: Ctx, pts: { x: number; y: number }[], u: number, w: number, k: number) {
  if (k <= 0.004 || pts.length < 2) return;
  const n = pts.length - 1;
  const at = (s: number) => {
    const x = clamp(s, 0, 1) * n, i = Math.min(n - 1, Math.floor(x)), f = x - i;
    return { x: lerp(pts[i]!.x, pts[i + 1]!.x, f), y: lerp(pts[i]!.y, pts[i + 1]!.y, f) };
  };
  const steps = 28, s0 = u - 2.2 * w, ds = (4.4 * w) / steps;
  c.save();
  c.lineCap = 'round';
  for (const [width, gain] of [[6, 0.22], [2, 0.85]] as const) {
    c.lineWidth = width;
    for (let j = 0; j < steps; j++) {
      const a = s0 + j * ds, b = a + ds;
      if (b < 0 || a > 1) continue;
      const m = (a + b) / 2 - u;
      const alpha = k * gain * Math.exp(-((m / w) ** 2));
      if (alpha <= 0.004) continue;
      const p = at(a), q = at(b);
      c.strokeStyle = `rgba(255,255,255,${Math.min(1, alpha).toFixed(4)})`;
      c.beginPath();
      c.moveTo(p.x, p.y);
      c.lineTo(q.x, q.y);
      c.stroke();
    }
  }
  c.restore();
}
