// MotionScene: the base of every v3 explainer shot (docs/STYLE_V3.md). A Scene3D (stage, DoF, supersampling, the light
// rig) with:
//   - a programmatic camera: cam(t) gives the pose on the shot clock; the base adds the arrive (the shot opens with the
//     camera decelerating into its first framing: the cut lands in motion) and an always-on drift;
//   - the environment: a haze far behind, a gridded floor, dust in front and behind (env options);
//   - hits: punch (post zoom), flash, shake and glitch (ca + shake) on times the scene registers, merged into the post
//     overrides with the shot's bloom;
//   - words: cue(word) is the time a VO word lands, from params.words (the EDL's words[].f on the shot's clock).
//
// A shot implements build() (make its objects, call this.frame() with the subject's box) and pose(t, f) (pose them;
// return the focus point, or nothing for the framing's target), and cam(t).
import * as THREE from 'three';
import { disposeLayer, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { H, Layer2D, W } from '../../engine/gl';
import { HEX } from '../../engine/palette';
import { clamp, ease, noise1 } from '../../engine/util';
import { clearBackground, type Background } from '../common';
import { Scene3D } from '../3d/scene3d';
import { pulse, spring } from './fns';
import { Dust, Floor, Haze } from './parts';

export interface CamPose { pos: [number, number, number]; target: [number, number, number]; fov?: number; roll?: number }

export type HitKind = 'punch' | 'flash' | 'shake' | 'glitch';
export interface Hit { t: number; kind: HitKind; amt?: number }

export interface EnvOpts {
  floor?: false | ConstructorParameters<typeof Floor>[0];
  haze?: false | ConstructorParameters<typeof Haze>[0];
  dust?: false | ConstructorParameters<typeof Dust>[0];
  /** Dust in front of the subject (big soft bokeh); default on when dust is. */
  nearDust?: false | ConstructorParameters<typeof Dust>[0];
}

export interface Arrive {
  /** Seconds of the settle (default 0.42: about 10 frames). */
  dur?: number;
  /** Extra distance at the cut, as a share of the camera-target distance (0.18 = starts 18 % further away). */
  dist?: number;
  /** Yaw and pitch offsets at the cut (degrees, about the target), and roll. */
  yaw?: number;
  pitch?: number;
  roll?: number;
}

const FPS = 24;

/**
 * The panel box of a presenter shot (px of 1920x1080, GFX.md): x 1010-1860, y 150-930, content above y 770 (the
 * captions own the rest). A panel shot (params.panel true, or params.layout 'panel') draws the frosted card there and
 * the 3D over it with no environment; the camera's principal point sits on the card's content centre (a view offset),
 * so the shot frames its subject as usual and it lands in the card. (From agent-13's WhatsApp base.)
 */
export const PANEL = { x0: 1010, x1: 1860, y0: 150, y1: 930, contentY1: 770 };

export abstract class MotionScene extends Scene3D {
  /** The environment; a shot overrides it in its constructor or build(). */
  protected env: EnvOpts = {};
  /** The camera arrive at the cut (false: none). */
  protected arrival: Arrive | false = { dur: 0.42, dist: 0.16, yaw: 7, roll: 1.2 };
  /** Hits merged into the post overrides. */
  protected hits: Hit[] = [];
  /** Base post for the shot (bloom etc). */
  protected basePost: PostOverrides = { bloom: 0.6, bloomThreshold: 1.2, bloomRadius: 0.7, halation: 0.18, vignette: 0.34, grain: 0.03, ca: 0.2 };
  /** The drift's strength (1: ±0.6 % position, ±0.3° roll). */
  protected driftAmt = 1;

  protected floor: Floor | null = null;
  protected haze: Haze | null = null;
  protected dust: Dust | null = null;
  protected nearDust: Dust | null = null;
  /** Shot-clock time of the current frame (s). */
  protected t = 0;
  private card: Layer2D | null = null;

  constructor(ctx: SceneCtx) {
    super(ctx);
    if (this.matte) this.basePost = { ...this.basePost, grain: 0, vignette: 0, ca: 0 };
    if (this.panel) {
      this.env = { floor: false, haze: false, dust: false };
      this.arrival = { dur: 0.42, dist: 0.1, yaw: -6, roll: 0 };
      this.basePost = { ...this.basePost, grain: 0, vignette: 0, ca: 0 };
    }
  }

  /** Panel mode: params.panel true or params.layout 'panel'. A shot that changes env in build() must keep it off. */
  /** A matte pass (params.matte set: the frame cleared to black or grey for an alpha pair, or the caption-band gate): no
   * environment, no grain or vignette, so only the graphic itself is in the frame. */
  protected get matte(): boolean {
    return !!this.ctx.params.matte;
  }

  protected get panel(): boolean {
    return this.ctx.params.panel === true || this.ctx.params.layout === 'panel';
  }

  /** The camera pose at shot time t (before the arrive and the drift). */
  protected abstract cam(t: number): CamPose;
  /** Pose the shot at time t; return the focus point (world), or nothing for the framing's target. */
  protected abstract pose(t: number, f: Frame): THREE.Vector3 | void;

  /** Builds the environment; call from build() after this.frame(), or let the base call it (it does if you don't). */
  private envBuilt = false;
  protected buildEnv() {
    if (this.envBuilt) return;
    this.envBuilt = true;
    if (this.panel || this.matte) return;
    const s = this.stage.scene;
    if (this.env.haze !== false) s.add(this.own(this.haze = new Haze(this.env.haze ?? {})).mesh);
    if (this.env.floor !== false) s.add(this.own(this.floor = new Floor(this.env.floor ?? {})).mesh);
    if (this.env.dust !== false) {
      s.add(this.own(this.dust = new Dust(this.env.dust ?? {})).points);
      if (this.env.nearDust !== false) {
        const c = this.base.target;
        this.nearDust = new Dust({ count: 26, box: [6, 3.5, 2], centre: [c[0], c[1], c[2] + this.base.dist * 0.55], size: 0.02, k: 0.35, seed: 5, ...(this.env.nearDust ?? {}) });
        s.add(this.own(this.nearDust).points);
      }
    }
  }

  override async init() {
    await super.init();
    this.buildEnv();
    this.stage.compile();
  }

  /** The shot clock time of a VO word (its `nth` occurrence; case and punctuation ignored) + `lag` frames; `fb` if absent. */
  protected cue(word: string, fb: number, nth = 0, lag = 2): number {
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9']/g, '');
    const all = (this.ctx.params.words as { w: string; f: number }[] | undefined) ?? [];
    for (const w of all) if (!Number.isFinite(w.f)) throw new Error(`shot ${this.ctx.id}: params.words[] need f (the frame on the shot's clock), got ${JSON.stringify(w)}`);
    const w = all.filter((x) => norm(x.w) === norm(word))[nth];
    return w ? (w.f + lag) / FPS : fb;
  }

  /** The shot's length (s). */
  protected get len(): number { return this.ctx.end - this.ctx.start; }

  protected update(f: Frame): THREE.Vector3 | void {
    this.t = f.lt;
    const focus = this.pose(f.lt, f);
    this.dust?.pose(f.t);
    this.nearDust?.pose(f.t);
    return focus;
  }

  protected override placeCamera(f: Frame) {
    const t = f.lt;
    const c = this.cam(t);
    const cam = this.stage.camera;
    const pos = new THREE.Vector3(...c.pos), tgt = new THREE.Vector3(...c.target);
    let roll = c.roll ?? 0;
    // the arrive: offsets that decay with outExpo over `dur` from the cut
    if (this.arrival) {
      const a = this.arrival, k = 1 - ease.outExpo(clamp(t / (a.dur ?? 0.42)));
      if (k > 0) {
        const off = pos.clone().sub(tgt);
        off.multiplyScalar(1 + (a.dist ?? 0) * k);
        off.applyAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad((a.yaw ?? 0) * k));
        const right = new THREE.Vector3().crossVectors(off, new THREE.Vector3(0, 1, 0)).normalize();
        off.applyAxisAngle(right, THREE.MathUtils.degToRad((a.pitch ?? 0) * k));
        pos.copy(tgt).add(off);
        roll += (a.roll ?? 0) * k;
      }
    }
    // the drift: never still
    const d = pos.distanceTo(tgt) * 0.006 * this.driftAmt;
    pos.x += d * noise1(f.t * 0.35, 11); pos.y += d * noise1(f.t * 0.31, 12) * 0.7; pos.z += d * noise1(f.t * 0.27, 13) * 0.5;
    roll += 0.3 * this.driftAmt * noise1(f.t * 0.2, 14);
    cam.position.copy(pos);
    cam.up.set(0, 1, 0);
    cam.lookAt(tgt);
    if (roll) cam.rotateZ(THREE.MathUtils.degToRad(roll));
    cam.fov = c.fov ?? this.p('fov', 30);
    if (this.panel) {
      const cx = ((PANEL.x0 + PANEL.x1) / 2 / 1920) * W, cy = ((PANEL.y0 + PANEL.contentY1) / 2 / 1080) * H;
      cam.setViewOffset(W, H, W / 2 - cx, H / 2 - cy, W, H);
    } else cam.clearViewOffset();
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this.haze?.pose(f.t, cam);
  }

  /** The post overrides at shot time t: the base, plus every hit. A shot may override and add its own. */
  protected post(t: number): PostOverrides {
    let zoom = 1, flash = 0, sx = 0, sy = 0, ca = this.basePost.ca ?? 0.25;
    for (const h of this.hits) {
      const a = h.amt ?? 1;
      if (h.kind === 'punch') {
        const x = t - h.t;
        if (x >= 0 && x < 0.6) zoom *= 1 + 0.035 * a * (x < 0.06 ? x / 0.06 : Math.exp(-(x - 0.06) / 0.1));
      } else if (h.kind === 'flash') flash += 0.12 * a * pulse(t, h.t, 0.02, 0.05);
      else if (h.kind === 'shake' || h.kind === 'glitch') {
        const p = pulse(t, h.t, 0.01, h.kind === 'glitch' ? 0.09 : 0.12) * a;
        if (p > 0.01) {
          const fr = Math.floor(t * FPS);
          sx += p * 14 * noise1(fr * 0.9, 21); sy += p * 9 * noise1(fr * 0.9, 22);
          if (h.kind === 'glitch') ca += p * 5;
        }
      }
    }
    return { ...this.basePost, zoom, flash, shake: [sx, sy], ca };
  }

  /** The panel card: frosted dark glass, an accent top edge, scaled up from 0.92 with an overshoot from the left. */
  private drawCard(t: number) {
    this.card ??= new Layer2D();
    const L = this.card, c = L.ctx, u = W / 1920;
    L.clear();
    const k = spring(t, 0, 0.5, 0.09), a = clamp(t / 0.12);
    const x0 = PANEL.x0 * u, x1 = PANEL.x1 * u, y0 = PANEL.y0 * u, y1 = PANEL.y1 * u;
    const s = 0.92 + 0.08 * k;
    c.save();
    c.globalAlpha = a;
    c.translate(x0, (y0 + y1) / 2);
    c.scale(s, s);
    c.translate(-x0 + (1 - k) * -30 * u, -(y0 + y1) / 2);
    c.shadowColor = 'rgba(0,0,0,0.4)'; c.shadowBlur = 50 * u; c.shadowOffsetY = 16 * u;
    c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 18 * u);
    c.fillStyle = 'rgba(26,20,16,0.78)'; c.fill();
    c.shadowColor = 'transparent';
    c.strokeStyle = '#3B3129'; c.lineWidth = Math.max(1, u); c.stroke();
    const e = ease.outExpo(clamp((t - 0.08) / 0.5));
    c.beginPath(); c.roundRect(x0 + 18 * u, y0 - 1.5 * u, (x1 - x0 - 36 * u) * e, 3 * u, 1.5 * u);
    c.fillStyle = HEX.accent; c.fill();
    c.restore();
    return L.upload();
  }

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    if (!this.panel) {
      super.render(f, out);
      return this.post(f.lt);
    }
    const r = this.ctx.renderer;
    this.flat?.clear();
    const focusAt = this.update(f) ?? new THREE.Vector3(...this.base.target);
    this.placeCamera(f);
    const dof = this.p('dof', true) ? { focus: Math.max(0.05, this.stage.depthOf(focusAt)), fstop: this.p('fstop', 2.8), maxBlurPx: this.p('maxBlur', 30) } : null;
    clearBackground(r, out, this.p<Background>('background', 'theme'));
    this.ctx.comp.draw(r, this.drawCard(f.lt), out, {});
    this.stage.render(out, { dof, clear: false });
    if (this.flat) this.ctx.comp.draw(r, this.flat.upload(), out, {});
    return this.post(f.lt);
  }

  override dispose() {
    if (this.card) disposeLayer(this.card);
    this.card = null;
    super.dispose();
  }
}
