// Scene 15 `weave`: "GitLoom." / "I don't forget." / "I commit." The film's last image (Plan 2 Task 12; spec §4 15).
//
// The picture is Blender shot B15 (blender/shots/b15_weave.py): the film's threads arcing out of the dark and weaving
// the GitLoom mark, the last pass locking on the first downbeat after the cut in a 0.5x ramp, then a slow push-in, a
// light sweep across the satin and the mark settling square to the camera on the left third. The engine composites
// that plate and sets the type beside the mark, every time from the data:
//   L30  "GitLoom."          no type: the mark completes.
//   L31  "I don't forget."   flat Bricolage, word by word on her onsets ("forget." lands on the lock).
//   L32  "I commit."         "I" flat; "commit." extruded, satin bone with the moss diff glow, slamming in from depth
//                            on its onset: the callback to the headline in `her` (weave-hero.ts).
//   the settle (the last downbeat): the site's wordmark, `gitloom 3f9a1c2`, types in as a git log entry under a
//   hairline, and on the next beat `gitloom.cloud` and the call to action; on the beat after that settles, the
//   signature, "Created by MelloB", fades up small in light Bricolage at the frame's bottom right (inside title-safe,
//   fixed to the screen like a filmmaker's credit, not the column); then a clean hold.
// The type column is anchored to the mark's tracked corner and scales with the mark's tracked size, so type and plate
// move as one world through the camera's truck and push.
import type * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { Layer2D, clearRT } from '../engine/gl';
import { LIN, rgba } from '../engine/palette';
import { Plate } from '../engine/plates';
import { Track } from '../engine/track';
import { F, font, glyphX, measure } from '../engine/type';
import { clamp, ease, prog, pulse } from '../engine/util';
import { Hero, PX_PER_UNIT } from './weave-hero';
import { WORDMARK_LEAD, timesOf, wordmarkShown } from './weave-time';
import S from './weave.strings.json';

export { timesOf };

const [FORGET, COMMIT_LINE, WORDMARK, URL, CTA, CREDIT_LINE] = S as [string, string, string, string, string, string];
const SHOT = 'b15_weave';

// ------------------------------------------------------------------------------------------------ the layout
// Logical px in the final frame, where the mark's tracked top-right corner is the reference: the column starts GAP
// right of the mark and spans its height, the hero line's baseline and the call to action's aligned to its parts.
const GAP = 102;
const SETUP = { fam: F.display(100, 500), px: 62, base: 88 }; // "I don't forget.": baseline, px below the mark's top
const HERO = { fam: F.display(75, 600), px: 300, base: 352 }; // "I commit."
const RULE = { y: 404, w: 596 };
const MARK = { fam: F.mono(500), px: 42, base: 470 }; // the wordmark
const FOOT = { fam: F.mono(400), px: 28, base: 546, dot: 22 }; // gitloom.cloud · start free — no card
/** The signature: screen px, its right end on title-safe's right edge, its baseline just inside title-safe's bottom
 * (descenders too), and its fade (s). */
export const CREDIT = { fam: F.display(100, 300), px: 24, right: 1824, base: 1010, track: 0.6, fade: 0.6 } as const;
/** When the signature comes up: the beat after the call to action has settled. */
export const creditAt = (T: { credit: number }) => T.credit;

export default class Weave extends Scene {
  private plate!: Plate;
  private track!: Track;
  private layer = new Layer2D();
  private hero!: Hero;
  private T!: ReturnType<typeof timesOf>;
  /** The mark's top-right corner and width in the final frame (logical px). */
  private ref = { x: 0, y: 0, w: 1 };
  /** The hero word's origin (left end, baseline) in the final frame (logical px). */
  private home = { x: 0, y: 0 };

  override async init() {
    const { vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.track = await Track.load(SHOT);
    this.plate = new Plate(SHOT, this.track.f0, { count: this.track.frames });
    const tEnd = end - 1 / 30;
    const tr = this.track.at('mark_tr', tEnd), tl = this.track.at('mark_tl', tEnd);
    this.ref = { x: tr.x, y: tr.y, w: tr.x - tl.x };
    const [, word] = COMMIT_LINE.split(' ') as [string, string];
    this.home = { x: this.ref.x + GAP + glyphX(COMMIT_LINE, COMMIT_LINE.indexOf(word), HERO.fam, HERO.px), y: this.ref.y + HERO.base };
    this.hero = new Hero(this.ctx.renderer, word, HERO.fam, HERO.px, this.home.x, this.home.y);
    this.hero.stage.compile(); // no first-slam shader hitch: its programs, built for the stage's own target
  }

  override async prepare(t: number) {
    await this.plate.prepare(t);
  }

  /** The column's frame at t: where the final layout's reference corner is now, and its scale (the camera's push). */
  private frame(t: number) {
    const tr = this.track.at('mark_tr', t), tl = this.track.at('mark_tl', t);
    return { x: tr.x, y: tr.y, k: (tr.x - tl.x) / this.ref.w };
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx;
    const t = f.t, T = this.T;
    clearRT(renderer, out, LIN.ink);
    this.plate.draw(renderer, comp, out, t);

    // the hero word, in the column's frame (moved and scaled with the mark)
    const fr = this.frame(t);
    if (t >= T.commit - 0.3) {
      const g = this.hero.word.group, home = this.home;
      g.scale.setScalar(fr.k);
      g.position.set((fr.x + (home.x - this.ref.x) * fr.k - 960) / PX_PER_UNIT, (540 - (fr.y + (home.y - this.ref.y) * fr.k)) / PX_PER_UNIT, 0);
      if (this.hero.update(t, T.commit)) this.hero.render(out);
    }

    // the flat type
    const L = this.layer, c = L.ctx;
    L.clear();
    c.save();
    c.translate(fr.x, fr.y);
    c.scale(fr.k, fr.k);
    c.translate(-this.ref.x, -this.ref.y);
    const x0 = this.ref.x + GAP, y0 = this.ref.y;
    c.textBaseline = 'alphabetic';
    this.setup(c, t, x0, y0);
    this.heroI(c, t, x0, y0);
    this.wordmark(c, t, x0, y0);
    c.restore();
    this.credit(c, t);
    comp.draw(renderer, L.upload(), out);

    // a camera punch on the lock and on the slam
    return { zoom: 1 + 0.011 * pulse(t, T.lock, 0.12) + 0.006 * pulse(t, T.commit + 0.02, 0.1) };
  }

  /** "I don't forget.", a word at a time on her onsets; it steps back to bone-dim as "I commit." takes over. */
  private setup(c: CanvasRenderingContext2D, t: number, x0: number, y0: number) {
    const T = this.T;
    c.font = font(SETUP.fam, SETUP.px);
    const dim = prog(t, T.commit - 0.05, T.commit + 0.35, ease.inOutCubic);
    const col = mixRGB(LIN.bone, LIN.boneDim, dim);
    let i = 0;
    FORGET.split(' ').forEach((w, k) => {
      const at = T.forget[k]!;
      const u = prog(t, at - 0.05, at + 0.2, ease.outExpo);
      const x = x0 + glyphX(FORGET, i, SETUP.fam, SETUP.px);
      i += Array.from(w).length + 1;
      if (u <= 0) return;
      c.fillStyle = cssLin(col, u);
      c.fillText(w, x, y0 + SETUP.base + (1 - u) * 12);
    });
  }

  /** The flat "I" of "I commit.", on its onset. */
  private heroI(c: CanvasRenderingContext2D, t: number, x0: number, y0: number) {
    const u = prog(t, this.T.i - 0.05, this.T.i + 0.2, ease.outExpo);
    if (u <= 0) return;
    c.font = font(HERO.fam, HERO.px);
    c.fillStyle = cssLin(LIN.bone, u);
    c.fillText(COMMIT_LINE.split(' ')[0]!, x0, y0 + HERO.base + (1 - u) * 18);
  }

  /** The settle: a hairline draws on, the wordmark types in behind a block cursor; then the address and the call. */
  private wordmark(c: CanvasRenderingContext2D, t: number, x0: number, y0: number) {
    const T = this.T;
    const r = prog(t, T.settle, T.settle + 0.42, ease.outExpo);
    if (r > 0) {
      c.fillStyle = rgba('ruleStrong');
      c.fillRect(x0, y0 + RULE.y, RULE.w * r, 1.5);
    }
    // the wordmark: one character a frame from the settle, the name in bone and the hash faint, as the site's nav
    const chars = Array.from(WORDMARK), space = WORDMARK.indexOf(' ');
    const n = wordmarkShown(t, T.settle, chars.length);
    c.font = font(MARK.fam, MARK.px);
    const y = y0 + MARK.base;
    if (n > 0) {
      c.fillStyle = rgba('bone');
      c.fillText(chars.slice(0, Math.min(n, space)).join(''), x0, y);
      if (n > space + 1) {
        c.fillStyle = rgba('boneFaint');
        c.fillText(chars.slice(space + 1, n).join(''), x0 + glyphX(WORDMARK, space + 1, MARK.fam, MARK.px), y);
      }
    }
    // the block cursor: rides the typing, blinks twice, and is gone well before the end (the last frame is clean)
    const typed = T.settle + WORDMARK_LEAD + chars.length / 30;
    const on = t >= T.settle && t < T.end - 1.1 && (t < typed || Math.floor((t - typed) / 0.36) % 2 === 1);
    if (on) {
      const cx = x0 + glyphX(WORDMARK, n, MARK.fam, MARK.px) + (n > 0 ? 3 : 0);
      c.fillStyle = rgba('bone', 0.85);
      c.fillRect(cx, y - MARK.px * 0.74, MARK.px * 0.56, MARK.px * 0.92);
    }
    // the address and the call to action, on the next beat
    c.font = font(FOOT.fam, FOOT.px);
    const a = prog(t, T.after - 0.03, T.after + 0.28, ease.outExpo);
    const b = prog(t, T.after + 0.1, T.after + 0.41, ease.outExpo);
    const fy = y0 + FOOT.base;
    if (a > 0) {
      c.fillStyle = cssLin(LIN.boneDim, a);
      c.fillText(URL, x0, fy + (1 - a) * 8);
    }
    if (b > 0) {
      const ux = x0 + measure(URL, FOOT.fam, FOOT.px);
      c.fillStyle = cssLin(LIN.boneFaint, b);
      c.beginPath();
      c.arc(ux + FOOT.dot, fy - FOOT.px * 0.3, 2.2, 0, Math.PI * 2);
      c.fill();
      c.fillStyle = cssLin(LIN.bloodBright, b);
      c.fillText(CTA, ux + FOOT.dot * 2, fy + (1 - b) * 8);
    }
  }

  /** The signature, bottom right: "Created by" faint, the name a step up in dim bone; a slow fade, no motion. */
  private credit(c: CanvasRenderingContext2D, t: number) {
    const u = prog(t, creditAt(this.T), creditAt(this.T) + CREDIT.fade, ease.inOutCubic);
    if (u <= 0) return;
    const sp = CREDIT_LINE.lastIndexOf(' ');
    const by = CREDIT_LINE.slice(0, sp + 1), name = CREDIT_LINE.slice(sp + 1);
    c.save();
    c.font = font(CREDIT.fam, CREDIT.px);
    c.letterSpacing = `${CREDIT.track}px`;
    c.textAlign = 'right';
    c.textBaseline = 'alphabetic';
    c.fillStyle = cssLin(LIN.boneDim, 0.8 * u);
    c.fillText(name, CREDIT.right, CREDIT.base);
    c.fillStyle = cssLin(LIN.boneFaint, 0.8 * u);
    c.fillText(by, CREDIT.right - c.measureText(name).width, CREDIT.base);
    c.restore();
  }

  override dispose() {
    this.plate?.dispose();
    disposeLayer(this.layer);
    this.hero?.dispose();
  }
}

/** A linear palette colour as a CSS colour at alpha a (Canvas2D takes sRGB). */
function cssLin(c: readonly [number, number, number], a = 1) {
  const s = (x: number) => Math.round(255 * clamp(x < 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055));
  return `rgba(${s(c[0])}, ${s(c[1])}, ${s(c[2])}, ${a})`;
}

function mixRGB(a: readonly number[], b: readonly number[], k: number): [number, number, number] {
  return [a[0]! + (b[0]! - a[0]!) * k, a[1]! + (b[1]! - a[1]!) * k, a[2]! + (b[2]! - a[2]!) * k];
}
