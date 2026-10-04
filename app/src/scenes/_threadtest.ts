// Dev harness for the thread (render.ts stills --module _threadtest --t 0.5,2). A 3-ply bone/blood/moss thread (the
// diff thread: the bone 3-ply with the blood and moss strands laid in its grooves) on a gentle S-curve that recedes in
// depth, lit by a neutral key and a hard rim in the stage's studio, focused on its middle at f/2. It draws on from 0 to
// 1 over 2 s (outCubic: the tip races out and settles), holds, and frays in the middle (3.5–5 s). Then checks, one
// segment each:
//   6–10 s   macro close-up of the fray (f/8: at 25 cm the depth of field is thinner than the thread)
//   10 s     the all-bone 3-ply, wide (the opening's thread, the one Blender's B01 renders); 11–13 s macro
//   13–15 s  the snap: the diff thread drawn to its middle and frayed there, so the broken end splays
//   15 s on  a single bone strand above a 2-ply blood/moss thread
import * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { CameraRig, Stage } from '../engine/stage';
import { Thread } from '../engine/thread3d';
import { ease, keys, prog } from '../engine/util';

const FOV = 18; // a 64 mm lens on the full-frame gate
const FSTOP = 2;
const RADIUS = 0.012;
const S_CURVE: [number, number, number][] = [
  [-0.64, -0.07, 0.3],
  [-0.32, 0.05, 0.13],
  [0, 0, 0],
  [0.31, -0.05, -0.15],
  [0.64, 0.07, -0.36],
];
const MACRO = 6, BONE = 10, SNAP = 13, PLIES = 15;
const curve = (dy = 0) => S_CURVE.map(([x, y, z]) => new THREE.Vector3(x, y + dy, z));

export default class ThreadTest extends Scene {
  private stage!: Stage;
  private diff!: Thread;
  private bone!: Thread;
  private single!: Thread;
  private pair!: Thread;
  private wide = new CameraRig([
    { t: 0, pos: [-0.1, 0.075, 1.3], target: [0.02, 0, -0.03], fov: FOV },
    { t: MACRO, pos: [0.02, 0.05, 1.12], target: [0.03, -0.004, -0.03], ease: ease.linear },
  ]);
  private macro = new CameraRig([
    { t: 0, pos: [-0.12, 0.05, 0.27], target: [0.0, 0.0, 0.0], fov: FOV },
    { t: 4, pos: [-0.06, 0.035, 0.22], target: [0.01, 0.0, -0.005], ease: ease.linear },
  ]);
  private medium = new CameraRig([
    { t: 0, pos: [-0.2, 0.06, 0.55], target: [-0.02, 0.0, 0.0], fov: FOV },
    { t: 2, pos: [-0.16, 0.05, 0.5], target: [-0.01, 0.0, 0.0], ease: ease.linear },
  ]);

  override init() {
    this.stage = new Stage(this.ctx.renderer, { fov: FOV });
    const s = this.stage.scene;
    this.diff = new Thread(curve(), { radius: RADIUS, plies: 3, colors: ['bone', 'blood', 'moss'] });
    this.bone = new Thread(curve(), { radius: RADIUS, plies: 3, colors: ['bone', 'bone', 'bone'] });
    this.single = new Thread(curve(0.07), { radius: RADIUS * 0.6, plies: 1, colors: ['bone'] });
    this.pair = new Thread(curve(-0.07), { radius: RADIUS * 0.8, plies: 2, colors: ['blood', 'moss'] });
    for (const th of [this.diff, this.bone, this.single, this.pair]) s.add(th.mesh);
    // neutral light (the bloom's chroma gate keeps lit bone out of the glow): a key from the upper left and in front,
    // a hard rim from behind on the right that sculpts the plies and lights the fuzz
    const key = new THREE.DirectionalLight(0xffffff, 3.4);
    key.position.set(-1.6, 2.8, 0.5);
    const rim = new THREE.DirectionalLight(0xffffff, 5);
    rim.position.set(2.4, 1.4, -3.2);
    s.add(key, key.target, rim, rim.target);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const st = this.stage, t = f.t;
    const seg = t >= PLIES ? 'plies' : t >= SNAP ? 'snap' : t >= BONE ? 'bone' : t >= MACRO ? 'macro' : 'wide';
    const th = seg === 'bone' ? this.bone : seg === 'plies' ? this.single : this.diff;
    this.diff.mesh.visible = seg === 'wide' || seg === 'macro' || seg === 'snap';
    this.bone.mesh.visible = seg === 'bone';
    this.single.mesh.visible = this.pair.mesh.visible = seg === 'plies';
    let fstop = FSTOP, u = 0.5;
    if (seg === 'wide') {
      this.wide.apply(st.camera, t);
      th.setDraw(0, prog(t, 0, 2, ease.outCubic));
      th.setFray(0.5, keys(t, [[3.5, 0], [5, 1, ease.inOutCubic]]));
    } else if (seg === 'macro') {
      this.macro.apply(st.camera, t - MACRO);
      th.setDraw(0, 1);
      th.setFray(0.5, 1);
      [fstop, u] = [8, 0.47];
    } else if (seg === 'bone') {
      if (t < BONE + 1) this.wide.apply(st.camera, 2);
      else {
        this.macro.apply(st.camera, t - (BONE + 1));
        [fstop, u] = [8, 0.47];
      }
      th.setDraw(0, 1);
      th.setFray(0.5, 0);
    } else if (seg === 'snap') {
      this.medium.apply(st.camera, t - SNAP);
      th.setDraw(0, 0.5);
      th.setFray(0.5, 1);
      [fstop, u] = [5.6, 0.48];
    } else {
      this.wide.apply(st.camera, 2);
      for (const p of [this.single, this.pair]) p.setDraw(0, 1);
    }
    // focus on the thread's near surface (at macro distance the depth of field is thinner than the thread); setDraw
    // above comes first, and the window never changes the centreline, so pointAt reads the same either way
    const focus = st.depthOf(th.pointAt(u)) - RADIUS;
    st.render(out, { dof: { focus, fstop } });
  }

  override dispose() {
    for (const th of [this.diff, this.bone, this.single, this.pair]) th.dispose();
    this.stage.dispose();
  }
}
