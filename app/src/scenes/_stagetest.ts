// Dev harness for the stage (render.ts stills --module _stagetest --t 1). Three satin bone spheres at 2, 4 and 8 m down
// the view axis (exactly, at t = 1), lit by a neutral key and a hard rim in the dim studio, focused on the middle one
// at f/1.4. The near sphere overlaps the sharp one and the sharp one hides part of the far one, so both kinds of depth
// edge are on screen. After t = 1.6 the focus racks to the near sphere, then the far one, then back, on a slow push-in.
import * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { CameraRig, Stage, type V3 } from '../engine/stage';
import { LIN } from '../engine/palette';
import { ease, keys } from '../engine/util';

const FOV = 20; // a 57 mm lens on the full-frame gate (dof.ts)
const FSTOP = 1.4;

// view-space positions at t = 1 (the camera is at the origin looking down -z then): x, y, depth, radius
const SPHERES: [number, number, number, number][] = [
  [-0.2, -0.12, 2, 0.14], // near
  [0, 0, 4, 0.3], // in focus
  [0.85, 0.35, 8, 0.5], // far
];

export default class StageTest extends Scene {
  private stage!: Stage;
  private rig = new CameraRig([
    { t: 0, pos: [-0.06, 0.04, 0.3], target: [-0.02, 0, -4], fov: FOV },
    { t: 1, pos: [0, 0, 0], target: [0, 0, -4], ease: ease.linear },
    { t: 7, pos: [0.12, -0.02, -0.25], target: [0.05, 0.02, -4], ease: ease.outCubic },
  ]);
  private balls: THREE.Mesh[] = [];

  override init() {
    this.stage = new Stage(this.ctx.renderer, { fov: FOV });
    const s = this.stage.scene;
    const bone = new THREE.Color().setRGB(...LIN.bone);
    // satin bone, as Task 4's glyphs will wear it
    const satin = new THREE.MeshPhysicalMaterial({
      color: bone, roughness: 0.38, metalness: 0, clearcoat: 0.25, clearcoatRoughness: 0.12,
      sheen: 0.3, sheenRoughness: 0.6, sheenColor: bone,
    });
    const geo = new THREE.SphereGeometry(1, 160, 120);
    for (const [x, y, z, r] of SPHERES) {
      const m = new THREE.Mesh(geo, satin);
      m.position.set(x, y, -z);
      m.scale.setScalar(r);
      s.add(m);
      this.balls.push(m);
    }
    // neutral light only (a key warmer than ~4000 K would open the bloom's chroma gate on bone): a key from the upper
    // left and a little behind the subjects, so the spheres turn from lit to dark across the frame, and a hard rim from
    // behind on the right
    const key = new THREE.DirectionalLight(0xffffff, 2.8);
    key.position.set(-4, 3, -2.5);
    key.target.position.set(0, 0, -4);
    const rim = new THREE.DirectionalLight(0xffffff, 5);
    rim.position.set(3.2, 1.6, -11);
    rim.target.position.set(0, 0, -4);
    s.add(key, key.target, rim, rim.target);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const st = this.stage;
    this.rig.apply(st.camera, f.t);
    // rack focus in diopters (as a focus ring turns): the middle sphere, the near one, the far one, back
    const [dn, dm, df] = this.balls.map((b) => 1 / st.depthOf(b.position)) as V3;
    const D = keys(f.t, [[0, dm], [1.6, dm], [2.4, dn], [3.4, dn], [4.2, df], [5.2, df], [6, dm]]);
    st.render(out, { dof: { focus: 1 / D, fstop: FSTOP } });
  }

  override dispose() {
    this.balls[0]?.geometry.dispose();
    (this.balls[0]?.material as THREE.Material | undefined)?.dispose();
    this.stage.dispose();
  }
}
