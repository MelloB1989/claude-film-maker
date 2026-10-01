// The type of scene `ex`: L03's hero, "vector store", as extruded JetBrains Mono on a stage of its own, and the flat
// type and UI the scene draws on its 2D layer (L03's Bricolage, the file label, the query chips, the tooltip, the
// stamps). Everything is a pure function of the song time and the times it is given.
//
// The hero stage looks straight at the type's plane through a long lens, so at rest a glyph sits exactly where the flat
// 2D layout would set it: a world point (x, y, 0) shows at logical px (960 + x * PX_PER_UNIT, 540 - y * PX_PER_UNIT).
import * as THREE from 'three';
import { Stage, aimTypeCamera, initAreaLights, typePxPerUnit } from '../engine/stage';
import { Mat, Type3D } from '../engine/type3d';
import { GLOW_LEVEL } from '../engine/look';
import { slam, spring } from '../engine/motion';
import { F, font, glyphX, measure } from '../engine/type';
import { rgba } from '../engine/palette';
import { clamp, ease, hash, lerp, prog, pulse } from '../engine/util';

// ------------------------------------------------------------------------------------------------ the hero

const FOV = 7;
const CAM_D = 30;
/** Logical px per world unit on the hero's plane (z = 0). */
export const PX_PER_UNIT = typePxPerUnit(FOV, CAM_D);
/** Where the hero's camera stands (logical px of the frame: off its lower left). */
const CAM_AT = { x: -1300, y: 1150 };
/** How deep a glyph launches from (em), how far it tips back (rad), the stagger between glyphs (s). */
const DEPTH_EM = 7;
const TIP = 0.6;
const STAGGER = 0.018;

/**
 * "vector store": extruded mono, satin bone with the blood diff glow along its seams (the vector store is the film's
 * minus: the ex), each word slamming in from depth on its spoken onset; at the exit the whole word flies at the camera
 * and through it (the shot pushes into the cloud).
 */
export class HeroWord {
  readonly stage: Stage;
  readonly word: Type3D;
  private mat: THREE.MeshPhysicalMaterial;
  private strip: THREE.RectAreaLight;
  /** The word's resting position (world). */
  private home = new THREE.Vector3();

  /** `text` set in `family` at `emPx` logical px per em, its origin (left end, baseline) at logical px (x, y). */
  constructor(renderer: THREE.WebGLRenderer, text: string, family: string, emPx: number, x: number, y: number) {
    this.stage = new Stage(renderer, { fov: FOV, near: 1, far: 80, envIntensity: 0.3 });
    // the camera stands off the frame's lower left looking straight ahead, its view offset so the type's plane still maps
    // as if centred: every glyph shows the wall on its left and its foot, where the blood seam glows along the edge
    aimTypeCamera(this.stage.camera, { fov: FOV, distance: CAM_D, eye: CAM_AT });
    this.mat = Mat.accent('blood', 0);
    this.mat.transparent = true; // (it fades as it flies past the camera)
    this.word = new Type3D(text, { family, size: emPx / PX_PER_UNIT }, this.mat);
    this.word.group.position.set((x - 960) / PX_PER_UNIT, (540 - y) / PX_PER_UNIT, 0);
    this.home.copy(this.word.group.position);
    const s = this.stage.scene;
    s.add(this.word.group);
    // neutral light: a near-frontal key (faces at bone), a long softbox above along the top bevels, a rim from behind,
    // and a narrow strip whose reflection sweeps the faces as the word lands
    initAreaLights();
    const key = new THREE.DirectionalLight(0xffffff, 3.4);
    key.position.set(-3, 4, 9);
    const [x0, x1, ym] = this.span();
    const box = new THREE.RectAreaLight(0xffffff, 3, (x1 - x0) * 1.3, 0.5);
    box.position.set((x0 + x1) / 2, ym + 3.2, 2.2);
    box.lookAt((x0 + x1) / 2, ym, 0);
    const rim = new THREE.DirectionalLight(0xffffff, 2);
    rim.position.set(2, 3, -6);
    this.strip = new THREE.RectAreaLight(0xffffff, 0, 0.14, 3.2);
    s.add(key, box, rim, this.strip);
  }

  /** The word's left and right ends and its middle height (world), at rest. */
  private span(): [number, number, number] {
    const g = this.word.glyphs, p = this.home, size = this.word.size;
    return [p.x + g[0]!.x, p.x + g[g.length - 1]!.x + g[g.length - 1]!.w, p.y + 0.36 * size];
  }

  /**
   * Pose for time t: word w slams in on onsets[w]; from exit[0] to exit[1] the word flies at the camera and past it,
   * spreading from the frame point `zoomAt` (logical px: where the camera's push heads). Returns whether any of it shows.
   */
  update(t: number, onsets: readonly number[], exit: readonly [number, number], zoomAt: { x: number; y: number }): boolean {
    const size = this.word.size;
    let any = false;
    const wordStart = new Map<number, number>();
    this.word.glyphs.forEach((g, k) => {
      if (!wordStart.has(g.word)) wordStart.set(g.word, k);
      const at = onsets[g.word] ?? onsets[onsets.length - 1]!;
      const s = slam(t, at + STAGGER * (k - wordStart.get(g.word)!));
      const m = g.mesh;
      m.visible = s > 1e-3;
      any ||= m.visible;
      m.position.copy(g.home);
      m.position.z += (s - 1) * DEPTH_EM * size;
      m.rotation.set((1 - s) * TIP, 0, 0);
      m.scale.setScalar(size);
    });
    // the exit: the word comes at the camera along the line of sight through zoomAt, which stays put while everything
    // else spreads from it, accelerating, and is past the camera as the push lands
    const out = prog(t, exit[0], exit[1], ease.inCubic);
    const p0 = new THREE.Vector3((zoomAt.x - 960) / PX_PER_UNIT, (540 - zoomAt.y) / PX_PER_UNIT, 0);
    this.word.group.position.copy(this.home).addScaledVector(this.stage.camera.position.clone().sub(p0), 0.93 * out);
    this.mat.opacity = 1 - prog(out, 0.1, 0.6);
    if (this.mat.opacity <= 0) any = false;
    // the diff glow comes up as "store" lands, flares on the impact and settles
    const last = onsets[onsets.length - 1]!;
    this.mat.emissiveIntensity = GLOW_LEVEL * 0.9 * clamp(slam(t, last + 0.05, { freq: 3 })) * (1 + 0.35 * pulse(t, last + 0.06, 0.2));
    // the sweep: a strip mirrored in the faces, running across the word as "store" lands
    const u = prog(t, last + 0.03, last + 0.55, ease.inOutQuad);
    const [x0, x1, ym] = this.span();
    const zs = 4, k = (CAM_D + zs) / CAM_D, xc = this.stage.camera.position.x, yc = this.stage.camera.position.y;
    const xs = lerp(x0 - 0.4 * size, x1 + 0.4 * size, u);
    this.strip.position.set(xc + (xs - xc) * k, yc + (ym - yc) * k, zs);
    this.strip.lookAt(xs, ym, 0);
    this.strip.intensity = u > 0 && u < 1 ? 26 * Math.sin(Math.PI * u) ** 2 : 0;
    return any;
  }

  render(out: THREE.WebGLRenderTarget) {
    this.stage.render(out, { clear: false });
  }

  dispose() {
    this.word.dispose();
    this.mat.dispose();
    this.stage.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ flat type

export interface WordAt {
  text: string;
  at: number;
}

/**
 * A line of flat Bricolage, kerned as one run, each word appearing on its onset: it rises a few px into place and fades
 * up on the house spring. `alpha` scales the whole line.
 */
export function drawWords(c: CanvasRenderingContext2D, t: number, words: readonly WordAt[], family: string, size: number,
  x: number, y: number, color: string, alpha = 1) {
  const text = words.map((w) => w.text).join(' ');
  c.font = font(family, size);
  c.textBaseline = 'alphabetic';
  c.fillStyle = color;
  let i = 0;
  for (const w of words) {
    const gx = x + glyphX(text, i, family, size);
    i += Array.from(w.text).length + 1;
    const a = prog(t, w.at - 0.03, w.at + 0.12, ease.outCubic) * alpha;
    if (a <= 0.002) continue;
    const dy = (1 - spring(t - w.at + 0.03)) * 14;
    c.globalAlpha = a;
    c.fillText(w.text, gx, y + dy);
  }
  c.globalAlpha = 1;
}

/** Mono text typed in from `at`, `cps` characters a second on the frame grid, each piece in its own colour. */
export function drawTyped(c: CanvasRenderingContext2D, t: number, at: number, pieces: readonly { text: string; color: string }[],
  family: string, size: number, x: number, y: number, alpha = 1, cps = 30) {
  const n = Math.max(0, Math.floor(Math.round((t - at) * 30) * (cps / 30)) + 1);
  if (t < at || alpha <= 0) return;
  c.font = font(family, size);
  c.textBaseline = 'alphabetic';
  const all = pieces.map((p) => p.text).join('');
  let i = 0;
  c.globalAlpha = alpha;
  for (const p of pieces) {
    const len = Array.from(p.text).length;
    const shown = Array.from(p.text).slice(0, Math.max(0, Math.min(len, n - i))).join('');
    if (shown) {
      c.fillStyle = p.color;
      c.fillText(shown, x + glyphX(all, i, family, size), y);
    }
    i += len;
  }
  c.globalAlpha = 1;
}

// ------------------------------------------------------------------------------------------------ chips

/** A rounded rectangle path. */
function rrect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.roundRect(x, y, w, h, r);
}

export const CHIP = { size: 30, padX: 18, h: 52, r: 10 } as const;

/**
 * A query chip (`berlin?`, `why?`): mono in a hairline pill, its left end at (x, baseline y). `ghost`: dashed and
 * faint, a query that finds nothing. `k` 0..1 brings it in (it rises a little and fades up). Returns its width.
 */
export function drawQuery(c: CanvasRenderingContext2D, text: string, x: number, y: number, k: number, ghost: boolean) {
  const fam = F.mono(400), w = measure(text, fam, CHIP.size) + 2 * CHIP.padX;
  if (k <= 0) return w;
  const top = y - CHIP.size * 0.72 - (CHIP.h - CHIP.size * 0.72) / 2 + (1 - k) * 10;
  c.save();
  c.globalAlpha = k;
  rrect(c, x, top, w, CHIP.h, CHIP.r);
  c.fillStyle = rgba('panel', ghost ? 0.5 : 0.92);
  c.fill();
  c.lineWidth = 1.5;
  if (ghost) c.setLineDash([5, 5]);
  c.strokeStyle = ghost ? rgba('boneDim', 0.75) : rgba('ruleStrong');
  c.stroke();
  c.setLineDash([]);
  c.font = font(fam, CHIP.size);
  c.fillStyle = ghost ? rgba('boneDim') : rgba('bone');
  c.fillText(text, x + CHIP.padX, top + (CHIP.h + CHIP.size * 0.72) / 2);
  c.restore();
  return w;
}

/**
 * The tooltip: `cosine 0.8127`, its label dim and its score bright, in a panel with a hairline edge, its left end at
 * (x, baseline y), on a leader from (lx, ly). `k` brings it in.
 */
export function drawTooltip(c: CanvasRenderingContext2D, text: string, x: number, y: number, lx: number, ly: number, k: number) {
  if (k <= 0) return;
  const fam = F.mono(400), size = 26, sp = text.lastIndexOf(' ');
  const label = text.slice(0, sp + 1), score = text.slice(sp + 1);
  const w = measure(text, fam, size) + 36, h = 50, top = y - size * 0.72 - (h - size * 0.72) / 2;
  c.save();
  c.globalAlpha = k;
  // the leader: a hairline from the numeral to the tooltip's edge, drawn out as it opens
  const ex = lerp(lx, x, ease.outCubic(k)), ey = lerp(ly, top + h / 2, ease.outCubic(k));
  c.strokeStyle = rgba('boneFaint');
  c.lineWidth = 1.25;
  c.beginPath();
  c.moveTo(lx, ly);
  c.lineTo(ex, ey);
  c.stroke();
  const s = 0.94 + 0.06 * ease.outBack(clamp(k));
  c.translate(x, top + h / 2);
  c.scale(s, s);
  c.translate(-x, -(top + h / 2));
  rrect(c, x, top, w, h, 10);
  c.fillStyle = rgba('panel');
  c.fill();
  c.strokeStyle = rgba('ruleStrong');
  c.lineWidth = 1.5;
  c.stroke();
  c.font = font(fam, size);
  c.fillStyle = rgba('boneDim');
  c.fillText(label, x + 18, y);
  c.fillStyle = rgba('bone');
  c.fillText(score, x + 18 + measure(label, fam, size), y);
  c.restore();
}

/** Four corner ticks around a box (the lit numeral), drawn in as `k` rises. */
export function drawBrackets(c: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, k: number) {
  if (k <= 0) return;
  const arm = 9 * k, pad = lerp(14, 6, ease.outCubic(k));
  c.save();
  c.strokeStyle = rgba('bone', k);
  c.lineWidth = 1.5;
  for (const [x, y, sx, sy] of [[x0 - pad, y0 - pad, 1, 1], [x1 + pad, y0 - pad, -1, 1], [x0 - pad, y1 + pad, 1, -1], [x1 + pad, y1 + pad, -1, -1]] as const) {
    c.beginPath();
    c.moveTo(x, y + sy * arm);
    c.lineTo(x, y);
    c.lineTo(x + sx * arm, y);
    c.stroke();
  }
  c.restore();
}

// ------------------------------------------------------------------------------------------------ stamps

export const STAMP = { size: 46, padX: 22, h: 76, r: 9, border: 2.5 } as const;

export interface StampPose {
  /** Where its left end and baseline land (logical px). */
  x: number;
  y: number;
  /** Scale (1 at rest), turn (rad), opacity, drop (px, the collapse), and its edge's glow (0..). */
  s: number;
  rot: number;
  a: number;
  dy: number;
  glow: number;
}

/**
 * A stamp's pose at t: it comes down from above the frame's plane (large, turning, accelerating) and hits on `hit`, a
 * beat, squashing a little and ringing out; its edge flares on the impact. From `drop` (the collapse) it falls out of
 * the frame under gravity, turning away.
 */
export function stampPose(t: number, hit: number, drop: number, x: number, y: number, tilt: number, seed: number): StampPose {
  const u = prog(t, hit - 0.13, hit, ease.inQuad);
  let s = lerp(1.75, 1, u), rot = tilt + (1 - u) * 0.07 * (hash(seed, 3) < 0.5 ? -1 : 1);
  const a = clamp(u * 3.5);
  if (t >= hit) {
    const dt = t - hit;
    s = 1 - 0.05 * Math.exp(-dt * 20) * Math.cos(dt * 2 * Math.PI * 9);
    rot = tilt;
  }
  let dy = 0;
  if (t > drop) {
    const dt = t - drop;
    dy = 0.5 * 9000 * dt * dt;
    rot += dt * dt * 3.2 * (hash(seed, 5) - 0.5);
  }
  return { x, y, s, rot, a: t < hit - 0.13 ? 0 : a, dy, glow: t < hit ? 0 : pulse(t, hit, 0.09) };
}

/** Draw a stamp: `− …` in bright blood mono, in a blood-edged chip with a faint blood wash, at its pose. */
export function drawStamp(c: CanvasRenderingContext2D, text: string, p: StampPose) {
  if (p.a <= 0) return null;
  const fam = F.mono(500), w = measure(text, fam, STAMP.size) + 2 * STAMP.padX, h = STAMP.h;
  const top = p.y - STAMP.size * 0.36 - h / 2;
  const cx = p.x + w / 2, cy = top + h / 2 + p.dy;
  c.save();
  c.globalAlpha = p.a;
  c.translate(cx, cy);
  c.rotate(p.rot);
  c.scale(p.s, p.s);
  c.translate(-w / 2, -h / 2);
  rrect(c, 0, 0, w, h, STAMP.r);
  c.fillStyle = rgba('blood', 0.07);
  c.fill();
  c.lineWidth = STAMP.border;
  c.strokeStyle = rgba('bloodBright');
  c.stroke();
  c.font = font(fam, STAMP.size);
  c.textBaseline = 'alphabetic';
  c.fillStyle = rgba('bloodBright');
  c.fillText(text, STAMP.padX, h / 2 + STAMP.size * 0.36);
  c.restore();
  return { cx, cy, w, h };
}

/** The stamp's glow, for the additive glow layer: its edge in white (the layer's tint makes it blood light). */
export function drawStampGlow(c: CanvasRenderingContext2D, text: string, p: StampPose, level: number) {
  if (p.a <= 0 || level <= 0) return;
  const fam = F.mono(500), w = measure(text, fam, STAMP.size) + 2 * STAMP.padX, h = STAMP.h;
  const top = p.y - STAMP.size * 0.36 - h / 2;
  c.save();
  c.globalAlpha = p.a * Math.min(1, level);
  c.translate(p.x + w / 2, top + h / 2 + p.dy);
  c.rotate(p.rot);
  c.scale(p.s, p.s);
  c.translate(-w / 2, -h / 2);
  c.filter = 'blur(4px)';
  rrect(c, 0, 0, w, h, STAMP.r);
  c.lineWidth = STAMP.border * 1.6;
  c.strokeStyle = '#fff';
  c.stroke();
  c.restore();
}
