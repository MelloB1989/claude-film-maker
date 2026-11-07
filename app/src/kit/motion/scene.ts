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
import type { Frame, PostOverrides } from '../../engine/scene';
import { clamp, ease, noise1 } from '../../engine/util';
import { Scene3D } from '../3d/scene3d';
import { pulse } from './fns';
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

  /** The camera pose at shot time t (before the arrive and the drift). */
  protected abstract cam(t: number): CamPose;
  /** Pose the shot at time t; return the focus point (world), or nothing for the framing's target. */
  protected abstract pose(t: number, f: Frame): THREE.Vector3 | void;

  /** Builds the environment; call from build() after this.frame(), or let the base call it (it does if you don't). */
  private envBuilt = false;
  protected buildEnv() {
    if (this.envBuilt) return;
    this.envBuilt = true;
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
    const ws = (this.ctx.params.words as { w: string; f: number }[] | undefined ?? []).filter((w) => norm(w.w) === norm(word));
    const w = ws[nth];
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

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    super.render(f, out);
    return this.post(f.lt);
  }
}
