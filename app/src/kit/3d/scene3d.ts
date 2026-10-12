// Scene3D: the base of every 3D kit block. It owns a Stage (engine/stage.ts: the dim studio, depth of field, rotated-grid
// supersampling) and a light rig built from palette roles, frames the block's subject for the live aspect (landscape,
// vertical, square: the subject is fitted to whichever side is tighter), moves the camera by params, pulls focus onto
// the subject, clears the frame to the block's `background` and plays the common exits.
//
// A block implements build() (make its meshes, add them to this.stage.scene, call this.frame() with its subject's box)
// and update(f) (pose everything for the frame; return the world point to focus on). Everything is a pure function of
// the frame: no state carried between renders. Register what it makes with this.own(x) and dispose() frees it.
//
// Params every Scene3D reads (all optional; sizes are reference px of a 1080 px short side, angles degrees):
//   background 'theme'  'theme' | 'none' (transparent, alpha = the sharp render's coverage: stack it over another block
//                       or play it as an overlay) | a role | #hex | { from, to, angle } (common.ts)
//   spot 0.35           a soft lift of the backdrop behind the subject toward `surface` (0: flat); spotAt [0.5, 0.45]
//   camera              'static' | 'push' | 'pull' | 'orbit' | 'drift' | 'dolly' | 'crane' (camera.ts), or keys
//                       [{ t (s from the shot's start), pos [x,y,z], target [x,y,z], fov?, roll? }] in the block's world
//   cameraAmount 1      scales the move (2 is bold); cameraEase 'inOutCubic' (a util.ts ease name)
//   drift true          a slow breathing drift under any named move (false: none)
//   az, el              the framing's angle on the subject (each block has its own default)
//   fov 30              vertical field of view; a narrower one is a longer lens (shallower focus)
//   whip                'left' | 'right' | 'up' | 'down': the camera whips out over the last 110 ms (a cut on the grid
//                       lands it on the beat); pair it with a 'whip' transition into the next shot
//   dof true            depth of field; fstop 2.8; focus 'auto' (on the block's subject) or a distance (world units);
//                       maxBlur 40 (logical px)
//   key 1, rim 1, fill 1, softbox 1   the light rig's levels (multiples of the house's); keyColor 'fg', rimColor 'fg'
//                       (a role or #hex: light is neutral by default, so lit fg never blooms); env 1 (the studio)
//   glow 3              the accents' emissive level (look.ts glow levels; 0: no glow)
//   exit 'none'         'fade' | 'rise' | 'sink' over exitDur (0.4 s) at the shot's end (blocks add their own)
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { CameraRig, Stage, initAreaLights, type CamKey } from '../../engine/stage';
import { FSPass, H, Layer2D, W, clearRT, makeRT } from '../../engine/gl';
import { GLOW_LEVEL } from '../../engine/look';
import { lin } from '../../engine/palette';
import type { Handles } from '../../engine/transition';
import { ease } from '../../engine/util';
import { clearBackground, need, p, type Background } from '../common';
import { exitState, resolveTime, type Exit, type TimeRef } from '../text/fx';
import { refUnit } from '../scene2d';
import { basis, combine, fitDistance, moveAt, moved, orbitPos, whipOut, type CameraMove, type Orbit, type V3, type WhipDir } from './camera';

export type { Frame };

/** A camera key as a film gives it: `t` in seconds from the shot's start. */
export interface ShotCamKey { t: number; pos: V3; target: V3; fov?: number; roll?: number; ease?: keyof typeof ease }

/** What a block frames: its box's centre and size (world units, square to the view at rest). */
export interface Subject { centre: V3; w: number; h: number; margin?: number | [number, number]; dist?: number }

const easeOf = (name: string | undefined, fb: (x: number) => number) => (name ? (ease as Record<string, (x: number) => number>)[name] ?? fb : fb);

let spotPass: FSPass | null = null;

/** Add a soft radial lift (`amount` of the way from bg to `surface`) at (x, y) (fractions, y down) to `out`. */
function drawSpot(renderer: THREE.WebGLRenderer, out: THREE.WebGLRenderTarget, amount: number, at: [number, number]) {
  if (amount <= 0) return;
  spotPass ??= (() => {
    const pass = new FSPass(/* glsl */ `
      uniform vec3 lift; uniform vec2 at; uniform float aspect;
      void main() {
        vec2 d = (vUv - at) * vec2(aspect, 1.0) / max(aspect, 1.0);
        float k = exp(-dot(d, d) / 0.11);
        fragColor = vec4(lift * k, 0.0);
      }`, { lift: { value: new THREE.Vector3() }, at: { value: new THREE.Vector2() }, aspect: { value: 1 } }, { blending: THREE.CustomBlending, transparent: true });
    const m = pass.mat;
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = m.blendDst = THREE.OneFactor;
    m.blendSrcAlpha = THREE.ZeroFactor;
    m.blendDstAlpha = THREE.OneFactor;
    return pass;
  })();
  const a = lin('surface'), b = lin('bg');
  (spotPass.u.lift!.value as THREE.Vector3).set(...([0, 1, 2].map((i) => Math.max(0, a[i]! - b[i]!) * amount) as [number, number, number]));
  (spotPass.u.at!.value as THREE.Vector2).set(at[0], 1 - at[1]);
  spotPass.u.aspect!.value = W / H;
  spotPass.render(renderer, out);
}

/** A colour for a light: the role's (or #hex's) hue at full strength (its brightest channel 1). */
export function lightColor(key: string): THREE.Color {
  const c = lin(key), m = Math.max(c[0], c[1], c[2], 1e-6);
  return new THREE.Color().setRGB(c[0] / m, c[1] / m, c[2] / m, THREE.LinearSRGBColorSpace);
}

export abstract class Scene3D extends Scene {
  protected stage!: Stage;
  /** The framing at rest (frame() sets it): every move offsets it. */
  protected base: Orbit = { target: [0, 0, 0], az: 0, el: 0, dist: 5, fov: 30 };
  /** A block's own defaults for any param (the film's params win). */
  protected defaults: Record<string, unknown> = {};
  /** Exits the block plays itself (the base then leaves the frame alone). */
  protected ownExits: readonly string[] = [];
  /** A flat layer drawn over the 3D (a tagline, a label): make it with this.flatLayer(), draw on it in update(). */
  protected flat: Layer2D | null = null;
  override handles: Handles = { head: 0.5, tail: 0.5 };
  protected lights!: { key: THREE.DirectionalLight; rim: THREE.DirectionalLight; fill: THREE.DirectionalLight; box: THREE.RectAreaLight };
  private rig: CameraRig | null = null;
  private layerRT: THREE.WebGLRenderTarget | null = null;
  private owned: { dispose(): void }[] = [];

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  /** Make the block's meshes, add them to this.stage.scene and frame the subject (this.frame). */
  protected abstract build(): Promise<void> | void;

  /** Pose everything for the frame; return the world point to focus on (default: the framing's target). */
  protected abstract update(f: Frame): THREE.Vector3 | void;

  /** A param: the film's, else the block's default, else `fallback`. */
  protected p<T>(key: string, fallback: T): T {
    const v = this.ctx.params[key];
    if (v !== undefined) return v as T;
    const d = this.defaults[key];
    return d === undefined ? fallback : (d as T);
  }

  protected need<T>(key: string): T {
    return need(this.ctx, key);
  }

  /** Logical px per reference px. */
  protected get u(): number {
    return refUnit();
  }

  /** The shot's id (for wordTimes). */
  protected get shot(): string {
    return (this.ctx.params.shot as string | undefined) ?? this.ctx.id;
  }

  /** The accents' emissive level (param `glow`). */
  protected get glowLevel(): number {
    return this.p('glow', GLOW_LEVEL);
  }

  /** Song time of a TimeRef in this shot. */
  protected at(ref: TimeRef): number {
    return resolveTime(ref, this.ctx.start, this.ctx.audio);
  }

  /** Keep `x` to dispose with the block. */
  protected own<T extends { dispose(): void }>(x: T): T {
    this.owned.push(x);
    return x;
  }

  /** The flat layer (made on first ask, cleared each frame by the base before update()). */
  protected flatLayer(): Layer2D {
    this.flat ??= new Layer2D();
    return this.flat;
  }

  override async init() {
    this.stage = new Stage(this.ctx.renderer, { fov: this.p('fov', 30), envIntensity: 0.4 * this.p('env', 1) });
    this.buildLights();
    await this.build();
    const keys = this.p<ShotCamKey[] | CameraMove>('camera', 'drift');
    if (Array.isArray(keys)) {
      if (!keys.length) throw new Error(`shot ${this.ctx.id}: camera keys are empty`);
      this.rig = new CameraRig(keys.map((k, i): CamKey => ({ t: this.ctx.start + k.t, pos: k.pos, target: k.target, fov: k.fov ?? (i === 0 ? this.base.fov : undefined), roll: k.roll, ease: k.ease ? easeOf(k.ease, ease.inOutCubic) : undefined })));
    } else moveAt(keys, 0, 0); // a typo fails in init
    this.placeLights();
    this.stage.compile();
  }

  /**
   * Frame a subject: the framing's target at its centre, looking from the block's az and el (params, else `angle`), at
   * the distance that fits its box to the frame's live aspect with `margin` clear (or `dist`, when the block knows it).
   */
  protected frame(s: Subject, angle: { az?: number; el?: number } = {}) {
    const fov = this.p('fov', 30);
    const dist = s.dist ?? fitDistance(s.w, s.h, fov, W / H, s.margin ?? 0.1);
    this.base = { target: [...s.centre], az: this.p('az', angle.az ?? 0), el: this.p('el', angle.el ?? 0), dist, fov };
    this.subjectSize = Math.max(s.w, s.h);
  }

  protected subjectSize = 1;

  private buildLights() {
    initAreaLights();
    const key = new THREE.DirectionalLight(lightColor(this.p('keyColor', 'fg')), 0);
    const rim = new THREE.DirectionalLight(lightColor(this.p('rimColor', 'fg')), 0);
    const fill = new THREE.DirectionalLight(lightColor('fg'), 0);
    const box = new THREE.RectAreaLight(lightColor('fg'), 0, 1, 1);
    this.stage.scene.add(key, key.target, rim, rim.target, fill, fill.target, box);
    this.lights = { key, rim, fill, box };
  }

  /**
   * The rig round the subject, scaled to its size: a key from the upper left in front, a hard rim from behind on the
   * right that draws the edges, a low fill from the front, and a long softbox above and in front whose reflection runs
   * along top bevels and panel edges. Neutral by default.
   */
  protected placeLights() {
    const { key, rim, fill, box } = this.lights;
    const c = new THREE.Vector3(...this.base.target), s = this.subjectSize;
    const { right, up, back } = basis(this.base.az, 0);
    const at = (r: number, u: number, b: number) => c.clone().addScaledVector(new THREE.Vector3(...right), r * s).addScaledVector(new THREE.Vector3(...up), u * s).addScaledVector(new THREE.Vector3(...back), b * s);
    key.position.copy(at(-0.8, 1.2, 1.0));
    key.target.position.copy(c);
    key.intensity = 0.55 * this.p('key', 1);
    rim.position.copy(at(0.9, 0.9, -1.6));
    rim.target.position.copy(c);
    rim.intensity = 2.4 * this.p('rim', 1);
    fill.position.copy(at(0.4, -0.5, 1.2));
    fill.target.position.copy(c);
    fill.intensity = 0.12 * this.p('fill', 1);
    box.width = 1.5 * s;
    box.height = 0.28 * s;
    box.position.copy(at(0, 0.65, 0.4));
    box.lookAt(at(0, 0, -0.05));
    box.intensity = 6 * this.p('softbox', 1);
    for (const l of [key, rim, fill]) l.target.updateMatrixWorld();
  }

  /** Place the camera for t: the keys, or the framing moved by the named move (plus the drift), then the whip out. */
  protected placeCamera(f: Frame) {
    const cam = this.stage.camera;
    if (this.rig) this.rig.apply(cam, f.t);
    else {
      const move = this.p<CameraMove>('camera', 'drift');
      const amount = this.p('cameraAmount', 1);
      let m = moveAt(move, f.p, f.lt, amount, easeOf(this.p<string | undefined>('cameraEase', undefined), move === 'drift' ? ease.linear : ease.inOutCubic));
      if (move !== 'drift' && move !== 'static' && this.p('drift', true)) m = combine(m, moveAt('drift', f.p, f.lt, 0.6 * amount));
      const o = moved(this.base, m);
      cam.position.set(...orbitPos(o));
      cam.up.set(0, 1, 0);
      cam.lookAt(...o.target);
      if (o.roll) cam.rotateZ(THREE.MathUtils.degToRad(o.roll));
      cam.fov = o.fov;
      cam.updateProjectionMatrix();
    }
    const dir = this.p<WhipDir | false>('whip', false);
    if (dir) {
      const w = whipOut(f.t, f.end, dir);
      if (w.yaw) cam.rotateY(THREE.MathUtils.degToRad(w.yaw));
      if (w.pitch) cam.rotateX(THREE.MathUtils.degToRad(w.pitch));
    }
    cam.updateMatrixWorld();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const r = this.ctx.renderer;
    this.flat?.clear();
    const focusAt = this.update(f) ?? new THREE.Vector3(...this.base.target);
    this.placeCamera(f);
    const dofOn = this.p('dof', true);
    const fixed = this.p<number | 'auto'>('focus', 'auto');
    const dof = dofOn ? { focus: typeof fixed === 'number' ? fixed : Math.max(0.05, this.stage.depthOf(focusAt)), fstop: this.p('fstop', 2.8), maxBlurPx: this.p('maxBlur', 40) } : null;
    const bg = this.p<Background>('background', 'theme');
    const exit = this.p<Exit | string>('exit', 'none');
    const ex = this.ownExits.includes(exit) ? null : exitState(exit as Exit, f.t, f.end, this.p('exitDur', 0.4));
    const opacity = ex ? ex.alpha : 1;
    const offset: [number, number] = ex ? [0, ex.dy * 0.1] : [0, 0];
    const layered = opacity < 1 || offset[1] !== 0;
    const spot = this.p('spot', 0.35), spotAt = this.p<[number, number]>('spotAt', [0.5, 0.45]);
    const backdrop = (rt: THREE.WebGLRenderTarget) => {
      if (bg === 'none') return clearRT(r, rt, [0, 0, 0], 0);
      clearBackground(r, rt, bg);
      drawSpot(r, rt, spot, spotAt);
    };
    if (!layered) {
      backdrop(out);
      if (opacity > 0.001) this.stage.render(out, { dof, clear: false, alpha: bg === 'none' });
    } else {
      this.layerRT ??= makeRT(W, H, { depthBuffer: false });
      backdrop(this.layerRT);
      this.stage.render(this.layerRT, { dof, clear: false, alpha: bg === 'none' });
      backdrop(out);
      if (opacity > 0.001) this.ctx.comp.draw(r, this.layerRT.texture, out, { mode: 'normal', premult: false, opacity, offset });
    }
    if (this.flat && opacity > 0.001) this.ctx.comp.draw(r, this.flat.upload(), out, { opacity, offset });
  }

  override dispose() {
    for (const x of this.owned.splice(0)) x.dispose();
    for (const l of Object.values(this.lights ?? {})) (l as THREE.Light).dispose?.();
    this.stage?.dispose();
    this.layerRT?.dispose();
    this.layerRT = null;
    if (this.flat) disposeLayer(this.flat);
    this.flat = null;
  }
}
