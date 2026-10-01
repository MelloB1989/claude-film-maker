// The type of scene `merkle`: the counter, `visited 50 of 10,000`, and its footnote, `index is a pure cache · gitloom
// rebuild`, set in the frame's lower left over the dive. The counter's words are flat mono (the machine's readout) on
// the scene's 2D layer; its number is the line's hero, "50" in extruded Bricolage on a type stage of its own, satin bone
// with the moss diff glow along its seams (the fifty changed files are the `+`), slamming into its blank on "fifty.".
//
// The type stage looks straight at the plane z = 0 through a long lens from off the frame's lower left
// (engine/stage.ts aimTypeCamera), so at rest a glyph sits exactly where flat type at the same size would, and each
// shows its walls on its left and its foot, where the moss seam glows against the shadow.
import * as THREE from 'three';
import { Stage, aimTypeCamera, initAreaLights, typePxPerUnit } from '../engine/stage';
import { Mat, Type3D } from '../engine/type3d';
import { GLOW_LEVEL } from '../engine/look';
import { slam } from '../engine/motion';
import { F, font, glyphX, measure } from '../engine/type';
import { rgba } from '../engine/palette';
import { clamp, ease, lerp, prog, pulse } from '../engine/util';

// ------------------------------------------------------------------------------------------------ layout (1080p px)

/** The counter's left end and baseline, its words' mono, and the hero's size (px per em). */
export const COUNTER = { x: 150, y: 902, size: 34, fam: F.mono(500), heroPx: 168, heroFam: F.display(100, 800) } as const;
/** The footnote: a line under the counter (its baseline inside the title-safe 96 px). */
export const NOTE = { y: 966, size: 23, fam: F.mono(400) } as const;

/** The counter split about its number: `visited`, `50`, `of 10,000`. */
export function counterParts(text: string) {
  const m = /^(\D+?)\s+(\d+)\s+(.+)$/.exec(text);
  if (!m) throw new Error(`merkle: the counter has no number: ${text}`);
  return { pre: m[1]!, num: m[2]!, post: m[3]! };
}

/** Where each part of the counter stands (left ends, px), the hero's width, and the space between parts. */
export function counterLayout(text: string) {
  const { pre, num, post } = counterParts(text);
  const sp = measure(' ', COUNTER.fam, COUNTER.size);
  const xPre = COUNTER.x, xNum = xPre + measure(pre, COUNTER.fam, COUNTER.size) + 1.1 * sp;
  const numW = measure(num, COUNTER.heroFam, COUNTER.heroPx);
  const xPost = xNum + numW + 1.1 * sp;
  return { pre, num, post, xPre, xNum, numW, xPost, end: xPost + measure(post, COUNTER.fam, COUNTER.size) };
}

// ------------------------------------------------------------------------------------------------ the hero

const FOV = 7;
const CAM_D = 30;
const PX_PER_UNIT = typePxPerUnit(FOV, CAM_D);
/** Where the hero's camera stands (logical px of the frame: off its lower left). */
const CAM_AT = { x: -900, y: 1350 };
/** How deep a glyph launches from (em), how far it tips back (rad), the stagger between glyphs (s). */
const DEPTH_EM = 6;
const TIP = 0.55;
const STAGGER = 0.03;

/** The number, extruded, slamming in from depth on its hit; its moss seam lights as it lands, and a band runs across it. */
export class HeroNumber {
  readonly stage: Stage;
  readonly word: Type3D;
  private mat: THREE.MeshPhysicalMaterial;
  private strip: THREE.RectAreaLight;
  private home = new THREE.Vector3();

  /** `text` in `family` at `emPx` logical px per em, its origin (left end, baseline) at logical px (x, y). */
  constructor(renderer: THREE.WebGLRenderer, text: string, family: string, emPx: number, x: number, y: number) {
    this.stage = new Stage(renderer, { fov: FOV, near: 1, far: 80, envIntensity: 0.3 });
    aimTypeCamera(this.stage.camera, { fov: FOV, distance: CAM_D, eye: CAM_AT });
    this.mat = Mat.accent('moss', 0);
    this.word = new Type3D(text, { family, size: emPx / PX_PER_UNIT }, this.mat);
    this.word.group.position.set((x - 960) / PX_PER_UNIT, (540 - y) / PX_PER_UNIT, 0);
    this.home.copy(this.word.group.position);
    const s = this.stage.scene;
    s.add(this.word.group);
    // neutral light (lit bone stays out of the bloom): a near-frontal key, a long softbox above along the top bevels, a
    // rim from behind, and a narrow strip whose reflection runs across the faces as the number lands
    initAreaLights();
    const key = new THREE.DirectionalLight(0xffffff, 3.2);
    key.position.set(-3, 4, 9);
    const [x0, x1, ym] = this.span();
    const box = new THREE.RectAreaLight(0xffffff, 3, (x1 - x0) * 1.4, 0.5);
    box.position.set((x0 + x1) / 2, ym + 3.2, 2.2);
    box.lookAt((x0 + x1) / 2, ym, 0);
    const rim = new THREE.DirectionalLight(0xffffff, 2);
    rim.position.set(2, 3, -6);
    this.strip = new THREE.RectAreaLight(0xffffff, 0, 0.14, 3.2);
    s.add(key, box, rim, this.strip);
  }

  /** The number's left and right ends and its middle height (world), at rest. */
  private span(): [number, number, number] {
    const g = this.word.glyphs, p = this.home, size = this.word.size;
    return [p.x + g[0]!.x, p.x + g[g.length - 1]!.x + g[g.length - 1]!.w, p.y + 0.36 * size];
  }

  /** Pose for time t: each digit slams in from depth on `hit`, a hair apart. Returns whether any of it shows. */
  update(t: number, hit: number): boolean {
    const size = this.word.size;
    let any = false;
    this.word.glyphs.forEach((g, k) => {
      const s = slam(t, hit + STAGGER * k);
      const m = g.mesh;
      m.visible = s > 1e-3;
      any ||= m.visible;
      m.position.copy(g.home);
      m.position.z += (s - 1) * DEPTH_EM * size;
      m.rotation.set((1 - s) * TIP, 0, 0);
      m.scale.setScalar(size);
    });
    // the diff glow comes up as it lands, flares on the impact and settles
    this.mat.emissiveIntensity = GLOW_LEVEL * 1.15 * clamp(slam(t, hit + 0.04, { freq: 3 })) * (1 + 0.4 * pulse(t, hit + 0.05, 0.2));
    // the sweep: a strip mirrored in the faces, running across the number as it lands
    const u = prog(t, hit + 0.02, hit + 0.42, ease.inOutQuad);
    const [x0, x1, ym] = this.span();
    const zs = 4, k = (CAM_D + zs) / CAM_D, xc = this.stage.camera.position.x, yc = this.stage.camera.position.y;
    const xs = lerp(x0 - 0.4 * size, x1 + 0.4 * size, u);
    this.strip.position.set(xc + (xs - xc) * k, yc + (ym - yc) * k, zs);
    this.strip.lookAt(xs, ym, 0);
    this.strip.intensity = u > 0 && u < 1 ? 24 * Math.sin(Math.PI * u) ** 2 : 0;
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

/** Mono text typed in from `at`, `cps` characters a second on the frame grid, each piece in its own colour. */
function typed(c: CanvasRenderingContext2D, t: number, at: number, pieces: readonly { text: string; color: string }[],
  family: string, size: number, x: number, y: number, cps: number, alpha = 1) {
  if (t < at || alpha <= 0) return;
  const n = Math.floor(Math.round((t - at) * 30) * (cps / 30)) + 1;
  c.font = font(family, size);
  c.textBaseline = 'alphabetic';
  const all = pieces.map((p) => p.text).join('');
  let i = 0;
  c.globalAlpha = alpha;
  for (const p of pieces) {
    const chars = Array.from(p.text), shown = chars.slice(0, Math.max(0, Math.min(chars.length, n - i))).join('');
    if (shown) {
      c.fillStyle = p.color;
      c.fillText(shown, x + glyphX(all, i, family, size), y);
    }
    i += chars.length;
  }
  c.globalAlpha = 1;
}

/**
 * The counter's words and the blank its number lands in, from `open` (the walk sets out): `visited` types in, a hairline
 * blank draws out after it, and `of 10,000` types in beyond; on `hit` the number fills the blank (its rule flashes moss
 * and is gone). The footnote types in under it from `note`.
 */
export function drawCounter(c: CanvasRenderingContext2D, t: number, text: string, footnote: string, open: number, note: number, hit: number) {
  const L = counterLayout(text);
  if (t < open) return;
  typed(c, t, open, [{ text: L.pre, color: rgba('boneDim') }], COUNTER.fam, COUNTER.size, L.xPre, COUNTER.y, 45);
  // the blank: a hairline under where the number will stand
  const draw = prog(t, open + 0.1, open + 0.3, ease.outCubic), gone = prog(t, hit + 0.02, hit + 0.2);
  if (draw > 0 && gone < 1) {
    const x0 = L.xNum + 4, x1 = L.xNum + L.numW - 4, flash = pulse(t, hit, 0.06) * (t >= hit ? 1 : 0);
    c.strokeStyle = flash > 0.05 ? rgba('moss', 0.5 + 0.5 * flash) : rgba('boneFaint', 0.9);
    c.lineWidth = 1.5;
    c.globalAlpha = 1 - gone;
    c.beginPath();
    c.moveTo(x0, COUNTER.y + 6);
    c.lineTo(lerp(x0, x1, draw), COUNTER.y + 6);
    c.stroke();
    c.globalAlpha = 1;
  }
  typed(c, t, open + 0.16, [{ text: L.post, color: rgba('boneDim') }], COUNTER.fam, COUNTER.size, L.xPost, COUNTER.y, 45);
  // the footnote: deadpan; the command in it bone
  const cmd = footnote.lastIndexOf('·');
  typed(c, t, note, [
    { text: footnote.slice(0, cmd + 2), color: rgba('boneFaint') },
    { text: footnote.slice(cmd + 2), color: rgba('boneDim') },
  ], NOTE.fam, NOTE.size, COUNTER.x, NOTE.y, 75);
}
