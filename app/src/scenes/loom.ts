// Scene 05 `loom`: "Facts I keep." / "Incidents… I let go." / "Rules I never break." / "Skills, only when you need
// them." GitLoom's four memory tiers, woven (Plan 2 Task 15; spec §4 05).
//
// The picture is Blender shot B05 (blender/shots/b05_loom.py): a real loom, low on its cloth side, in a macro tour
// along the fell that holds on each tier while she names it and snaps across to the next on a beat, the plate's motion
// blur streaking the snap like a whip. Four warp lanes (facts, incidents, rules, skills)
// run from under the lens through the woven cloth to the fell and stretch away into the dark; a glass shuttle carrying
// the diff thread flies across on every beat, the reed beats its row in on the beat (its moss strand flaring: the
// commit) and the cloth is taken up toward the camera. The incidents' three oldest rows fray and let go on "let go",
// their blood strands burning; the rules warps hang slack until she names them and snap tight, then ring on "break";
// the skills warps lie dim and unwoven until the shuttle first flies into their lane, and light.
//
// This module composites that plate and sets the type over it, every time from the data (loom-time.ts):
//   - the labels, on their lanes (tracked: lbl_<tier>), `facts/ · long-term`, `incidents/ · ttl 30d`,
//     `rules/ · loaded whole`, `skills/ · lazy`: each draws on as she names its tier, the skills label dim until the
//     shuttle reaches the lane;
//   - L11–L14, flat Bricolage at the top left, one line at a time, the tier word lighting as she says it and then
//     behaving as its tier does (loom-type.ts);
//   - the stamp `gc: expire 3 incidents`, mono in blood, landing on "let go" by the expiring rows (tracked: gc).
import type * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { Layer2D, clearRT } from '../engine/gl';
import { LIN, rgba } from '../engine/palette';
import { Plate } from '../engine/plates';
import { Track } from '../engine/track';
import { F, font, layout, measure } from '../engine/type';
import { clamp, ease, lerp, prog, pulse } from '../engine/util';
import { TIERS, loomTimes, reachTime, type LoomTimes, type Tier } from './loom-time';
import { labelOn, letGo, lightWipe, reveal, rulesPull, stamp } from './loom-type';
import S from './loom.strings.json';

const SHOT = 'b05_loom';
const LINES = S.slice(0, 4) as [string, string, string, string];
const LABELS = Object.fromEntries(TIERS.map((k, i) => [k, S[4 + i]!])) as Record<Tier, string>;
const GC = S[8]!;

// ------------------------------------------------------------------------------------------------ the layout (1080p)

/** Her lines: top left, inside title safe. */
const LINE = { x: 150, y: 196, px: 60, fam: F.display(100, 500) };
/** Alpha of a spoken word, of a tier word before it lights (Skills dimmer: it waits), and lit. */
const SPOKEN = 0.7, UNLIT = 0.55, UNLIT_SKILLS = 0.36;
/** The labels: mono on a hairline leader rising from the lane. */
const LBL = { px: 22, fam: F.mono(500), lead: 54, dot: 3.4, padX: 10, padY: 7 };
/** The stamp: by the expiring rows, up and to the right of them, a little askew. */
const STAMP = { px: 26, fam: F.mono(500), dx: 40, dy: -118, tilt: -0.045, padX: 14, padY: 10 };

export default class Loom extends Scene {
  private plate!: Plate;
  private track!: Track;
  private layer = new Layer2D();
  private T!: LoomTimes;
  /** The shuttle first flies into the skills lane (the plate's track). */
  private reach = 0;

  override async init() {
    const { vo, audio, start, end } = this.ctx;
    this.track = await Track.load(SHOT);
    this.plate = new Plate(SHOT, this.track.f0, { count: this.track.frames });
    this.T = loomTimes(vo, audio, start, end);
    this.T.lines.forEach((ws, i) => {
      if (ws.length !== LINES[i]!.split(' ').length) throw new Error(`loom: line ${i + 1} has ${ws.length} spoken words`);
    });
    this.reach = reachTime(this.track, this.T.tier.skills);
  }

  override async prepare(t: number) {
    await this.plate.prepare(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx;
    const t = f.t;
    clearRT(renderer, out, LIN.ink);
    this.plate.draw(renderer, comp, out, t);

    const L = this.layer, c = L.ctx;
    L.clear();
    c.textBaseline = 'alphabetic';
    for (const tier of TIERS) this.label(c, t, tier);
    this.stamp(c, t);
    this.lines(c, t);
    comp.draw(renderer, L.upload(), out);

    // a breath of a punch on each downbeat (the reed's heaviest strokes)
    let punch = 0;
    for (const d of this.T.downbeats) punch += pulse(t, d, 0.11);
    return { zoom: 1 + 0.005 * punch };
  }

  // ---------------------------------------------------------------------------------------------- her lines

  private lines(c: CanvasRenderingContext2D, t: number) {
    const T = this.T;
    T.lines.forEach((words, li) => {
      const first = words[0]!.start;
      const next = T.lines[li + 1]?.[0]!.start;
      const out = next === undefined ? 1 : 1 - prog(t, next - 0.22, next - 0.04, ease.inOutCubic); // the last holds
      if (t < first - 0.03 || out <= 0) return;
      this.line(c, t, li, out);
    });
  }

  private line(c: CanvasRenderingContext2D, t: number, li: number, fade: number) {
    const T = this.T;
    const text = LINES[li]!, words = T.lines[li]!;
    const { fam, px } = LINE;
    const lay = layout(text, fam, px);
    c.font = font(fam, px);
    const tierOnset = words[0]!.start;
    const pull = li === 2 ? rulesPull(t, tierOnset, T.brk) : { track: 0, jolt: 0 };
    const lit = li === 3 ? lightWipe(t, this.reach) : lightWipe(t, tierOnset);
    let start = 0, shift = 0;
    text.split(' ').forEach((w, wi) => {
      const n = Array.from(w).length;
      const glyphs = lay.glyphs.slice(start, start + n);
      start += n + 1;
      const r = reveal(t, words[wi]!.start);
      const x0 = glyphs[0]!.x, wW = glyphs[n - 1]!.x + glyphs[n - 1]!.w - x0;
      glyphs.forEach((g, k) => {
        let x = LINE.x + g.x + shift, y = LINE.y + r.dy, a = SPOKEN * r.a, rot = 0, blur = 0;
        if (wi === 0) {
          // the tier word: lights left to right as she says it (Skills: when the shuttle reaches them)
          const u = (g.x + g.w / 2 - x0) / wW;
          const on = clamp((lit * 1.3 - 0.15 - u) / 0.3 + 0.5);
          a = lerp(li === 3 ? UNLIT_SKILLS : UNLIT, 1, on) * r.a;
          if (li === 2) x += pull.track * px * k;
          if (li === 1) {
            const g2 = letGo(t, k, n, T.release);
            x += g2.dx * px;
            y += g2.dy * px;
            rot = g2.rot;
            blur = g2.blur;
            a *= g2.a;
          }
        }
        if (li === 2) y += pull.jolt;
        a *= fade;
        if (!(a > 0.003)) return;
        c.save();
        c.globalAlpha = a;
        c.fillStyle = rgba('bone');
        if (blur > 0.25) c.filter = `blur(${blur.toFixed(2)}px)`;
        if (rot) {
          c.translate(x + g.w / 2, y - px * 0.35);
          c.rotate(rot);
          c.fillText(g.ch, -g.w / 2, px * 0.35);
        } else c.fillText(g.ch, x, y);
        c.restore();
      });
      if (wi === 0 && li === 2) shift = pull.track * px * (n - 1); // the rest of the line moves with "Rules"
    });
  }

  // ---------------------------------------------------------------------------------------------- the labels

  private label(c: CanvasRenderingContext2D, t: number, tier: Tier) {
    const at = this.T.tier[tier];
    if (t < at - 0.02) return;
    const p = this.track.at(`lbl_${tier}`, t);
    if (p.visible <= 0) return;
    const text = LABELS[tier];
    const head = text.slice(0, text.indexOf(' '));
    const on = labelOn(t, at, Array.from(text).length);
    const lit = tier === 'skills' ? lightWipe(t, this.reach) : 1;
    const { px, fam, lead, dot, padX, padY } = LBL;
    const w = measure(text, fam, px);
    const chipX = p.x - padX, chipH = px + 2 * padY, chipB = p.y - 7 - lead;
    // fade out at the frame's edges, as the slide carries the lane away
    const edge = clamp((chipX - 40) / 90) * clamp((1920 - 40 - (chipX + w + 2 * padX)) / 90) * clamp((chipB - chipH - 60) / 60);
    if (edge <= 0) return;
    c.save();
    c.globalAlpha = edge;
    // the dot on the lane, and the leader rising from it to the tag
    c.fillStyle = rgba('bone', lerp(0.45, 0.95, lit));
    c.beginPath();
    c.arc(p.x, p.y, dot * on.dot, 0, Math.PI * 2);
    c.fill();
    const top = p.y - 7 - lead * on.leader;
    c.fillStyle = rgba('boneDim', lerp(0.4, 0.75, lit));
    c.fillRect(p.x - 0.75, top, 1.5, (p.y - 7) - top);
    // the tag: a dark chip that grows as the path types in, the path bright and the property dim
    const typed = Array.from(text).slice(0, on.typed).join('');
    if (typed && on.leader >= 1) {
      c.font = font(fam, px);
      const tw = measure(typed, fam, px);
      roundRect(c, chipX, chipB - chipH, tw + 2 * padX, chipH, 4);
      c.fillStyle = rgba('panel', 0.9);
      c.fill();
      c.lineWidth = 1;
      c.strokeStyle = rgba('ruleStrong', 0.9);
      c.stroke();
      const by = chipB - padY - px * 0.2;
      const h = typed.slice(0, head.length), rest = typed.slice(head.length);
      c.fillStyle = rgba('bone', lerp(0.42, 1, lit));
      c.fillText(h, p.x, by);
      if (rest) {
        c.fillStyle = rgba('boneDim', lerp(0.5, 0.9, lit));
        c.fillText(rest, p.x + measure(head, fam, px), by);
      }
    }
    c.restore();
  }

  // ---------------------------------------------------------------------------------------------- the stamp

  private stamp(c: CanvasRenderingContext2D, t: number) {
    const at = this.T.release[0]!;
    const gone = this.T.tier.rules;
    if (t < at - 0.05 || t > gone) return;
    const p = this.track.at('gc', t);
    const st = stamp(t, at);
    const a = st.a * (1 - prog(t, gone - 0.55, gone - 0.2, ease.inOutCubic));
    if (!(a > 0.003)) return;
    const { px, fam, dx, dy, tilt, padX, padY } = STAMP;
    c.save();
    c.font = font(fam, px);
    const w = measure(GC, fam, px);
    c.translate(p.x + dx, p.y + dy);
    c.rotate(tilt);
    c.scale(st.s, st.s);
    c.globalAlpha = a;
    roundRect(c, -padX, -px * 0.8 - padY, w + 2 * padX, px + 2 * padY, 4);
    c.fillStyle = rgba('panel', 0.92);
    c.fill();
    c.strokeStyle = rgba('blood', 0.95);
    c.lineWidth = 1.5;
    c.stroke();
    c.fillStyle = rgba('bloodBright');
    c.fillText(GC, 0, 0);
    c.restore();
  }

  override dispose() {
    this.plate?.dispose();
    disposeLayer(this.layer);
  }
}

/** A rounded rectangle's path (Canvas2D's roundRect, spelled out for the older typings). */
function roundRect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}
