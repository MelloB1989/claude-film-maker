// Scene 09 `merkle`: "Fifty things changed? I only look at fifty." (Plan 2 Task 19; spec §4 09.)
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, type CamKey, type V3 } from '../engine/stage';
import { LIN } from '../engine/palette';
import { ease, hash, keys, lerp, prog, pulse } from '../engine/util';
import { onBeat } from '../engine/motion';
import { nodeTimes, timesOf, type Times } from './merkle-time';
import { SEED, SHAPE, buildTree, diveLeaf, pickChanged, pathTo, type Tree } from './merkle-tree';
import { TreeDraw } from './merkle-gl';
import { LABEL_CHARS, LabelField, STAMP } from './merkle-labels';
import { GlyphAtlas } from '../engine/glyphs';
import { F } from '../engine/type';
import { H, Layer2D, SCALE, W, makeRT } from '../engine/gl';
import { COUNTER, HeroNumber, counterLayout, drawCounter } from './merkle-type';
import { cocScale, lensFov } from '../engine/dof';
import S from './merkle.strings.json';

const [STAMP_TEXT, COUNTER_TEXT, FOOTNOTE] = S as [string, string, string];

const INK = new THREE.Color().setRGB(...LIN.ink);
const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

export default class Merkle extends Scene {
  private T!: Times;
  private stage!: Stage;
  private tree!: Tree;
  private draw!: TreeDraw;
  private atlas!: GlyphAtlas;
  private labels!: LabelField;
  private hero!: HeroNumber;
  private layer = new Layer2D();
  private rig!: CameraRig;
  /** The dive: the root down to its file, and where they stand. */
  private path: number[] = [];
  private P: THREE.Vector3[] = [];

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    const T = (this.T = timesOf(vo, audio, start, end));
    this.stage = new Stage(renderer, { fov: 34, near: 0.004, far: 20 });
    this.tree = buildTree(pickChanged(SEED));
    this.path = pathTo(diveLeaf(this.tree));
    this.P = this.path.map((id) => v(this.tree.pos[id * 3]!, this.tree.pos[id * 3 + 1]!, this.tree.pos[id * 3 + 2]!));
    const times = nodeTimes(this.tree, T);
    this.draw = new TreeDraw(this.tree, times, new Set(this.path));
    this.draw.u.uScreen.value.set(W, H, SCALE);
    this.stage.scene.add(this.draw.group);
    if (STAMP_TEXT !== STAMP) throw new Error('merkle: the stamp is not the strings file\'s');
    this.atlas = new GlyphAtlas(LABEL_CHARS, F.mono(500));
    this.labels = new LabelField(this.tree, times, this.atlas, this.draw.u, STAMP_TEXT);
    this.stage.scene.add(this.labels.mesh);
    const L = counterLayout(COUNTER_TEXT);
    this.hero = new HeroNumber(renderer, L.num, COUNTER.heroFam, COUNTER.heroPx, L.xNum, COUNTER.y);
    this.buildRig();
    this.warmUp();
  }

  /**
   * Draw everything once before the first frame: the shaders compile for the stages' targets, and the atlas (with its
   * mips) and the instance buffers upload, so no first-use stall or first-frame difference lands on a frame. Nothing it
   * sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const T = this.T, st = this.stage, rt = makeRT(W, H);
    st.compile();
    this.hero.stage.compile();
    this.ctx.renderer.initTexture(this.atlas.texture);
    this.rig.apply(st.camera, T.root);
    this.draw.u.uT.value = T.root - T.start;
    st.render(rt, { dof: { focus: 1, fstop: 8 } });
    this.hero.update(T.land + 1, T.land);
    this.hero.render(rt);
    rt.dispose();
  }

  // ---------------------------------------------------------------------------------------------- the camera

  private buildRig() {
    const T = this.T, [, P1, P2, P3, P4] = this.P as [THREE.Vector3, THREE.Vector3, THREE.Vector3, THREE.Vector3, THREE.Vector3];
    const key = (t: number, pos: THREE.Vector3, target: THREE.Vector3, fov?: number, e?: (x: number) => number): CamKey =>
      ({ t, pos: pos.toArray() as V3, target: target.toArray() as V3, fov, ease: e });
    // one side of the tree, the dive's file's (`out`, from the trunk through the file): the crane cuts in low there,
    // looking up into the vault, rises over it as the moss climbs, and drops back down outside the lit branch to land
    // low beside the file, looking up into the same vault with only the fifty paths left in it
    const out = v(P4.x, 0, P4.z).normalize();
    const az = Math.atan2(out.x, out.z);
    const at = (a: number, r: number, y: number) => v(r * Math.sin(az + a), y, r * Math.cos(az + a));
    const d = THREE.MathUtils.degToRad;
    const Y = v(0, 1, 0);
    // out from a node of the path and up, and a point in from it and up
    const outside = (p: THREE.Vector3, r: number, h: number) => p.clone().addScaledVector(out, r).addScaledVector(Y, h);
    const inside = (p: THREE.Vector3, r: number, h: number) => p.clone().addScaledVector(out, -r).addScaledVector(Y, h);
    this.rig = new CameraRig([
      // low at the tree's edge, looking up into the vault; the crane rises and pulls back over it
      key(T.start, at(d(-12), 0.86, 0.04), v(0, 0.46, 0), 44),
      key(T.fifty + 0.55, at(d(10), 1.3, 0.62), v(0, 0.25, 0), 34, ease.inOutQuad),
      // high over the lit tree as the moss reaches the root, then easing in for the walk
      key(T.root, at(d(4), 1.04, 1.06), v(0, 0.31, 0), 34, ease.inOutCubic),
      key(T.walk[0]!, at(d(1), 0.9, 1.0), v(0, 0.32, 0.0), 36, ease.inOutCubic),
      // the dive: down outside the lit branch, lagging the walk (the comet leads), slow while the top-level folds close,
      // then faster, level by level, tipping up from the drop to the vault as it lands with "fifty."
      key(T.walk[1]! + 0.06, outside(P1, 0.34, 0.16), inside(P1, 0.06, -0.13), 40, ease.inQuad),
      key(T.walk[2]! + 0.04, outside(P2, 0.2, 0.05), inside(P3, 0.0, 0.0), 44, ease.linear),
      key(T.walk[3]! + 0.06, outside(P3, 0.13, 0.012), inside(P4, 0.12, 0.08), 48, ease.linear),
      key(T.land + 0.01, outside(P4, 0.1, 0.016), inside(P4, 0.4, 0.075), 60, ease.outCubic),
      key(T.end, outside(P4, 0.094, 0.018), inside(P4, 0.4, 0.08), 60, ease.linear),
    ]);
  }

  /** Focus (m) and stop: the tree, the root, the walk's next node, the file. */
  private focus(t: number) {
    const T = this.T, st = this.stage, P = this.P;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.01, st.depthOf(p));
    const D = keys(t, [
      [T.start, inv(v(0, 0.3, 0))],
      [T.root - 0.3, inv(v(0, 0.3, 0))],
      [T.root, inv(P[0]!), ease.inOutCubic],
      [T.walk[0]!, inv(P[1]!), ease.inOutCubic],
      [T.walk[1]! + 0.06, inv(P[2]!), ease.linear],
      [T.walk[2]! + 0.04, inv(P[3]!), ease.linear],
      [T.walk[3]! + 0.06, inv(P[4]!), ease.linear],
      [T.end, inv(P[4]!)],
    ]);
    const fstop = keys(t, [[T.start, 5.6], [T.root, 8], [T.walk[0]!, 8], [T.land, 16, ease.inOutCubic], [T.end, 16]]);
    return { focus: 1 / D, fstop };
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, u = this.draw.u;
    this.rig.apply(st.camera, t);
    u.uT.value = t - T.start;
    // the index as the cut finds it: a band of light rises through the tree from the files to the root, landing on the
    // beat she says "Fifty" on (each node's hash covers its children's); a breath on every beat after
    const rise = prog(t, T.start + 0.02, T.fifty, ease.inOutCubic);
    u.uSweep.value.set(0, 1, 0, lerp(-0.06, SHAPE.y[0]! + 0.04, rise));
    u.uSweepK.value.set(0.055, 0.85 * Math.sin(Math.PI * Math.min(1, rise * 1.08)) + 0.5 * pulse(t, T.fifty, 0.08) * (rise >= 1 ? 0 : 1));
    u.uLight.value.y = t > T.fifty ? 0.035 * onBeat(f, 0.3) : 0;
    u.uTwinkle.value.x = T.things - T.start;
    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    const dof = this.focus(t);
    // the far side of the tree falls away into the dark: from a little past the focus
    u.uFar.value.set(dof.focus * 1.8, dof.focus * 9, 0.3);
    // labels go where the lens throws them out of focus
    this.labels.u.uDefocus.value.x = 1 / dof.focus;
    this.labels.u.uDefocus.value.y = cocScale(dof, lensFov(st.camera), H);
    st.render(out, { dof });
    r.setClearColor(cc, ca);

    // the counter's number, then its words and the footnote
    if (this.hero.update(t, T.land)) this.hero.render(out);
    this.layer.clear();
    drawCounter(this.layer.ctx, t, COUNTER_TEXT, FOOTNOTE, T.walk[0]!, T.walk[0]! + 0.26, T.land);
    this.ctx.comp.draw(r, this.layer.upload(), out);

    // the root's hash changes on the downbeat, and the number lands: the frame punches in a hair, and jolts on the slam
    const dl = t - T.land;
    const shake = dl > 0 ? 3.5 * Math.exp(-dl * 22) * Math.cos(dl * 2 * Math.PI * 11) : 0;
    return { zoom: 1 + 0.006 * pulse(t, T.root, 0.1) + 0.009 * pulse(t, T.land + 0.02, 0.09), shake: [0, shake] };
  }

  override dispose() {
    this.hero?.dispose();
    disposeLayer(this.layer);
    this.labels?.dispose();
    this.atlas?.dispose();
    this.draw?.dispose();
    this.stage?.dispose();
  }
}
