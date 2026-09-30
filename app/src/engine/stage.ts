// The stage for 3D shots: a three.js scene and perspective camera in a dim studio (a PMREM of three's RoomEnvironment,
// neutral light), rendered as HDR linear colour with a depth texture, then through the depth of field (dof.ts) into
// the scene's `out` target. The scene adds its own key and rim lights; the studio gives glossy surfaces their sweeps
// while the background stays ink.
//
// Anti-aliasing is supersampling on the rotated grid of glsl rgss(): four passes, each rendering the scene shifted by
// one tap and running the DoF (on its quarter of the disc) on it, averaged into `out`. Colour and depth then always
// describe the same surface; MSAA would resolve an edge pixel's colour from two surfaces but keep one depth, and the
// DoF would stair-step sharp edges and leak them into the blur. Motion-blur sub-frames get all four taps as well
// instead of one each (SS_TAP): a one-tap sub-frame has hard edges, and the engine's adaptive sampler chases that
// aliasing as if it were motion (the stage test's push-in at t = 1 took 324 sub-frames to converge with one tap each,
// 36 with four: 324 passes against 144; a still frame takes 12 either way, 12 passes against 48).
//
// CameraRig moves the camera through keys: position and target along a smooth curve through the keys, fov and roll in
// step, each segment timed by the ease of the key it is heading to.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { FSPass, H, PH, PW, W, clearRT, makeRT } from './gl';
import { LIN } from './palette';
import { DofPass, type DofParams } from './dof';
import { ease } from './util';

export type V3 = [number, number, number];

export interface StageOpts {
  /** Vertical field of view (degrees). DoF follows it: a narrower fov is a longer lens (dof.ts, DOF_SENSOR_H). */
  fov?: number;
  near?: number;
  far?: number;
  /** The studio's strength, scene.environmentIntensity (default 0.4: glossy sweeps, black stays black). */
  envIntensity?: number;
  /** Linear RGB behind everything (default ink). */
  background?: V3;
}

/** The rotated-grid taps of glsl rgss(k), in px. */
const RGSS: readonly (readonly [number, number])[] = [[0.125, -0.375], [0.375, 0.125], [-0.125, 0.375], [-0.375, -0.125]];

/**
 * The studio: three's RoomEnvironment (a room with six softboxes) as a black box. Its walls and props are painted to
 * albedo 0.1 (from white), so at the default 0.4 the fill stays low: bone keeps a dark side, and glossy ink reads ink
 * (its body renders at or below the ink background) with crisp softbox highlights and a bright Fresnel rim. The room
 * is turned half round, so its largest softbox (it hung behind the camera, a flat frontal fill) lights the subjects
 * from behind and above instead. Scenes can move it: stage.scene.environmentRotation sweeps its highlights across
 * glossy surfaces.
 */
const STUDIO_WALLS = 0.1;
const STUDIO_TURN = Math.PI;

/**
 * What every Stage on a renderer shares: the studio's PMREM (a few MB, a moment to build) and the working buffers.
 * Stage renders never interleave (a scene renders a stage start to finish), so one set serves them all.
 */
interface Shared {
  studio: THREE.WebGLRenderTarget;
  /** One pass: HDR colour and its depth, at the output size. */
  color: THREE.WebGLRenderTarget;
  /** One pass after the DoF, before it is averaged into `out`. */
  pass: THREE.WebGLRenderTarget | null;
  /** `out` as it was, for clear: false. */
  backdrop: THREE.WebGLRenderTarget | null;
  dof: DofPass;
  copy: FSPass;
  /** Adds a pass into `out`, weighted (`add` blends, `put` replaces). */
  add: FSPass;
  put: FSPass;
  refs: number;
}
const SHARED = new WeakMap<THREE.WebGLRenderer, Shared>();

function buildStudio(renderer: THREE.WebGLRenderer) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  room.rotation.y = STUDIO_TURN;
  room.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
    if (m?.isMeshStandardMaterial) m.color.setScalar(STUDIO_WALLS);
  });
  // the room is a closed box, but pin the clear colour anyway: the PMREM must not depend on renderer state
  const cc = renderer.getClearColor(new THREE.Color()), ca = renderer.getClearAlpha();
  renderer.setClearColor(0x000000, 1);
  const rt = pmrem.fromScene(room, 0.04);
  renderer.setClearColor(cc, ca);
  room.dispose();
  pmrem.dispose();
  return rt;
}

function acquire(renderer: THREE.WebGLRenderer): Shared {
  let s = SHARED.get(renderer);
  if (!s) {
    const texel = `uniform sampler2D src; uniform float w; void main() { fragColor = texelFetch(src, ivec2(gl_FragCoord.xy), 0) * w; }`;
    const add = new FSPass(texel, { src: { value: null }, w: { value: 1 } }, { blending: THREE.CustomBlending, transparent: true });
    add.mat.blendEquation = THREE.AddEquation;
    add.mat.blendSrc = add.mat.blendDst = add.mat.blendSrcAlpha = add.mat.blendDstAlpha = THREE.OneFactor;
    s = {
      studio: buildStudio(renderer),
      color: makeRT(W, H, { depthTexture: new THREE.DepthTexture(PW, PH, THREE.FloatType) }),
      pass: null,
      backdrop: null,
      dof: new DofPass(),
      copy: new FSPass(`uniform sampler2D src; void main() { fragColor = texelFetch(src, ivec2(gl_FragCoord.xy), 0); }`, { src: { value: null } }),
      add,
      put: new FSPass(texel, { src: { value: null }, w: { value: 1 } }),
      refs: 0,
    };
    SHARED.set(renderer, s);
  }
  s.refs++;
  return s;
}

/**
 * What Stage.render can draw into: a target of the output size (PWxPH: the stage's buffers are, and its passes read
 * them texel for texel at gl_FragCoord), or the canvas. `clear: false` keeps what a target holds, so it needs one: the
 * canvas cannot be read back.
 */
export function stageTarget(out: { width: number; height: number } | null, clear?: boolean) {
  if (out && (out.width !== PW || out.height !== PH)) {
    throw new Error(`Stage.render: the target is ${out.width}x${out.height}; a stage renders at the output size, ${PW}x${PH} (render it there and draw that texture down)`);
  }
  if (!out && clear === false) throw new Error('Stage.render: clear: false keeps what the target holds, and the canvas (null) cannot be read back');
}

/**
 * Run `draw` for each rotated-grid tap (glsl rgss()), the camera shifted by the tap's offset in px of the output: of the
 * whole frame, or within a view offset the scene set on it (setViewOffset: a tile, a crop), which is then back as it
 * was, projection and all.
 */
export function eachTap(cam: THREE.PerspectiveCamera, draw: (tap: number) => void) {
  const v = cam.view?.enabled ? { ...cam.view } : null;
  try {
    RGSS.forEach(([dx, dy], tap) => {
      // (setViewOffset also updates the projection)
      if (v) cam.setViewOffset(v.fullWidth, v.fullHeight, v.offsetX + (dx * v.width) / PW, v.offsetY + (dy * v.height) / PH, v.width, v.height);
      else cam.setViewOffset(PW, PH, dx, dy, PW, PH);
      cam.updateMatrixWorld();
      draw(tap);
    });
  } finally {
    if (v) cam.setViewOffset(v.fullWidth, v.fullHeight, v.offsetX, v.offsetY, v.width, v.height);
    else cam.clearViewOffset();
  }
}

function release(renderer: THREE.WebGLRenderer) {
  const s = SHARED.get(renderer);
  if (!s || --s.refs > 0) return;
  s.studio.dispose();
  s.color.depthTexture?.dispose();
  for (const rt of [s.color, s.pass, s.backdrop]) rt?.dispose();
  s.dof.dispose();
  for (const p of [s.copy, s.add, s.put]) p.mat.dispose();
  SHARED.delete(renderer);
}

export class Stage {
  scene = new THREE.Scene();
  camera: THREE.PerspectiveCamera;
  private shared: Shared;
  private background: V3;
  private disposed = false;

  constructor(private renderer: THREE.WebGLRenderer, opts: StageOpts = {}) {
    this.camera = new THREE.PerspectiveCamera(opts.fov ?? 30, W / H, opts.near ?? 0.1, opts.far ?? 100);
    this.background = opts.background ?? LIN.ink;
    this.shared = acquire(renderer);
    this.scene.environment = this.shared.studio.texture;
    this.scene.environmentIntensity = opts.envIntensity ?? 0.4;
  }

  /**
   * Draw the scene with the camera into `out` (every pixel), a target of the output size or the canvas (stageTarget):
   * through the depth of field with `dof`, straight across without. `clear: false` starts each pass from what is already
   * in `out` instead of the background colour; the DoF then treats it as the far distance (the camera's far plane). A
   * view offset set on the camera is kept (eachTap).
   */
  render(out: THREE.WebGLRenderTarget | null, opts: { dof?: DofParams | null; clear?: boolean } = {}) {
    stageTarget(out, opts.clear);
    const r = this.renderer, cam = this.camera, s = this.shared;
    const autoClear = r.autoClear;
    r.autoClear = false;
    let backdrop: THREE.Texture | null = null;
    if (opts.clear === false && out) {
      s.backdrop ??= makeRT(W, H, { depthBuffer: false });
      s.copy.u.src!.value = out.texture;
      s.copy.render(r, s.backdrop);
      backdrop = s.backdrop.texture;
    }
    s.pass ??= makeRT(W, H, { depthBuffer: false });
    eachTap(cam, (tap) => {
      if (backdrop) {
        s.copy.u.src!.value = backdrop;
        s.copy.render(r, s.color);
        r.setRenderTarget(s.color);
        r.clear(false, true, true);
      } else clearRT(r, s.color, this.background);
      r.setRenderTarget(s.color);
      r.render(this.scene, cam);
      if (opts.dof) s.dof.render(r, s.color.texture, s.color.depthTexture!, cam, opts.dof, s.pass!, tap);
      else {
        s.copy.u.src!.value = s.color.texture;
        s.copy.render(r, s.pass!);
      }
      const acc = tap === 0 ? s.put : s.add;
      acc.u.src!.value = s.pass!.texture;
      acc.u.w!.value = 1 / RGSS.length;
      acc.render(r, out);
    });
    r.autoClear = autoClear;
  }

  /**
   * Compile the scene's shaders for the stage's colour target, where its frames draw them, and the stage's own passes
   * (copy, accumulate). three builds each program for the target bound when it compiles (its output colour space and
   * tone mapping): renderer.compile() with nothing bound builds the canvas's variant, and the first frame builds the
   * stage's all over again, the stall it was meant to spare.
   */
  compile() {
    const r = this.renderer, s = this.shared, prev = r.getRenderTarget();
    r.setRenderTarget(s.color);
    r.compile(this.scene, this.camera);
    for (const p of [s.copy, s.add, s.put]) r.compile(p.scene, p.cam);
    r.setRenderTarget(prev);
  }

  /** Depth of a world point along the camera's view axis: the distance DofParams.focus is measured in. */
  depthOf(p: THREE.Vector3 | V3): number {
    const cam = this.camera;
    cam.updateMatrixWorld();
    const v = Array.isArray(p) ? new THREE.Vector3(...p) : p.clone();
    return -v.applyMatrix4(cam.matrixWorldInverse).z;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.scene.environment = null;
    release(this.renderer);
  }
}

// ---------------------------------------------------------------------------------------------------- the rig

export interface CamKey {
  t: number;
  pos: V3;
  target: V3;
  /**
   * Vertical fov (degrees). The first key must give one; a key without one carries the previous key's. (So a rig sets
   * the fov at every time: a camera two rigs share never keeps whichever ran last.)
   */
  fov?: number;
  /** Degrees about the view axis, counter-clockwise as seen from behind the camera (the picture turns clockwise). */
  roll?: number;
  /** Shapes the segment that ends at this key (default ease.inOutCubic: the camera settles on the key). */
  ease?: (x: number) => number;
}

const sub = (a: V3, b: V3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const reflect = (a: V3, b: V3): V3 => [2 * a[0] - b[0], 2 * a[1] - b[1], 2 * a[2] - b[2]]; // b mirrored through a

/**
 * Centripetal Catmull-Rom (Barry-Goldman) between p1 and p2 at u in 0..1: no cusps or loops however unevenly the keys
 * are spaced. A missing or coincident neighbour is mirrored from the other side.
 */
function catmullRom(p0: V3 | undefined, p1: V3, p2: V3, p3: V3 | undefined, u: number): V3 {
  const d12 = sub(p1, p2);
  if (d12 < 1e-9) return [p1[0], p1[1], p1[2]];
  if (!p0 || sub(p0, p1) < 1e-9) p0 = reflect(p1, p2);
  if (!p3 || sub(p2, p3) < 1e-9) p3 = reflect(p2, p1);
  const t1 = Math.sqrt(sub(p0, p1)), t2 = t1 + Math.sqrt(d12), t3 = t2 + Math.sqrt(sub(p2, p3));
  const t = t1 + u * (t2 - t1);
  const out: V3 = [0, 0, 0];
  for (let i = 0; i < 3; i++) {
    const a1 = ((t1 - t) * p0[i]! + t * p1[i]!) / t1;
    const a2 = ((t2 - t) * p1[i]! + (t - t1) * p2[i]!) / (t2 - t1);
    const a3 = ((t3 - t) * p2[i]! + (t - t2) * p3[i]!) / (t3 - t2);
    const b1 = ((t2 - t) * a1 + t * a2) / t2;
    const b2 = ((t3 - t) * a2 + (t - t1) * a3) / (t3 - t1);
    out[i] = ((t2 - t) * b1 + (t - t1) * b2) / (t2 - t1);
  }
  return out;
}

/**
 * Keyframed camera. `apply(cam, t)` places the camera for time t: before the first key and after the last it holds
 * them, at a key time it is exactly that key; between keys, position and target follow a centripetal Catmull-Rom curve
 * through all the keys (a straight line with two), fov and roll interpolate, all on the segment's eased progress.
 */
export class CameraRig {
  private keys: (CamKey & { fovR: number; rollR: number })[];

  constructor(keys: CamKey[]) {
    if (!keys.length) throw new Error('CameraRig needs at least one key');
    const ks = [...keys].sort((a, b) => a.t - b.t);
    const first = ks[0]!;
    if (first.fov === undefined) {
      throw new Error(`CameraRig needs a fov on its first key (t = ${first.t}): without one it would leave the camera's own, and a camera two rigs share would keep whichever ran last`);
    }
    let fov = first.fov, roll = 0;
    this.keys = ks.map((k) => {
      fov = k.fov ?? fov;
      roll = k.roll ?? roll;
      return { ...k, fovR: fov, rollR: roll };
    });
  }

  apply(cam: THREE.PerspectiveCamera, t: number) {
    const ks = this.keys, n = ks.length;
    let pos: V3, target: V3, fov: number, roll: number;
    let i = 0;
    while (i < n && ks[i]!.t <= t) i++; // ks[i - 1].t <= t < ks[i].t
    if (i === 0 || i === n || ks[i - 1]!.t === t) {
      const k = ks[Math.max(0, i - 1)]!;
      ({ pos, target, fovR: fov, rollR: roll } = k);
    } else {
      const a = ks[i - 1]!, b = ks[i]!;
      const e = (b.ease ?? ease.inOutCubic)((t - a.t) / (b.t - a.t));
      pos = catmullRom(ks[i - 2]?.pos, a.pos, b.pos, ks[i + 1]?.pos, e);
      target = catmullRom(ks[i - 2]?.target, a.target, b.target, ks[i + 1]?.target, e);
      fov = a.fovR + (b.fovR - a.fovR) * e;
      roll = a.rollR + (b.rollR - a.rollR) * e;
    }
    cam.position.set(pos[0], pos[1], pos[2]);
    cam.up.set(0, 1, 0);
    cam.lookAt(target[0], target[1], target[2]);
    if (roll) cam.rotateZ(THREE.MathUtils.degToRad(roll));
    cam.fov = fov;
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
  }
}
