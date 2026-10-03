// Scene 09 `merkle`: "Fifty things changed? I only look at fifty." (Plan 2 Task 19; spec §4 09.) GitLoom indexes
// incrementally: a directory whose hash did not move is skipped whole, so a commit of fifty files reads fifty files.
//
// One world, every time from the data (her onsets, the score's beats and downbeats; merkle-time.ts):
// - The tree (merkle-tree.ts, drawn by merkle-gl.ts): a Merkle tree of 10,000 files, ten children a node, four levels,
//   as a cone tree in hairlines, the root high, each node's children on a ring under it, the files in rosettes on the
//   floor; every internal node carries its hash (merkle-labels.ts, on engine/glyphs.ts), legible where the lens brings
//   it. The cut lands low at its edge, looking up into the vault, as a band of light rises through it from the files to
//   the root (each hash covers its children's), landing on "Fifty"; the crane rises and pulls back over it, and the
//   fifty changed files twinkle in bone on "things".
// - "changed?": the fifty pulse moss and the moss climbs their paths, every hash above them split-flapping to its new
//   value as it passes, until the root's flips on the downbeat.
// - "I only look at fifty.": the walk goes down the lit paths one level a word, a comet on each; as it reaches a node,
//   each child whose hash did not move folds shut like an umbrella and draws up into its node, which seals, darkens and
//   takes the stamp `= hash · skipped` (a directory of files only its `=`). The crane comes in over the apex and all but
//   holds through "I only" while the top two levels fold and stamp around it (still enough to read them), then plunges
//   down outside the lit branch on "look at", landing low beside its file as she says "fifty.", looking up into the
//   same vault with only the fifty paths left in it.
// - The counter (merkle-type.ts): `visited ___ of 10,000` types in as the walk sets out, and on "fifty." the 50 slams
//   into its blank in extruded Bricolage with the moss diff glow; the footnote, `index is a pure cache · gitloom
//   rebuild`, types in under it, deadpan.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage } from '../engine/stage';
import { LIN } from '../engine/palette';
import { ease, keys, lerp, prog, pulse } from '../engine/util';
import { onBeat } from '../engine/motion';
import { nodeTimes, timesOf, type Times } from './merkle-time';
import { SHAPE, type Tree } from './merkle-tree';
import { aimAt, divePath, rigKeys } from './merkle-camera';
import { TreeDraw } from './merkle-gl';
import { LabelField, labelChars } from './merkle-labels';
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
    ({ tree: this.tree, path: this.path, P: this.P } = divePath());
    const times = nodeTimes(this.tree, T);
    this.draw = new TreeDraw(this.tree, times, new Set(this.path));
    this.draw.u.uScreen.value.set(W, H, SCALE);
    this.draw.u.uTwinkle.value.x = T.things - T.start;
    this.stage.scene.add(this.draw.group);
    this.atlas = new GlyphAtlas(labelChars(STAMP_TEXT), F.mono(500));
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
    this.rig = new CameraRig(rigKeys(this.T, this.P));
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
      [T.walk[2]! - 0.04, inv(P[1]!)],
      [T.walk[3]! - 0.04, inv(P[3]!), ease.inQuad],
      [T.walk[3]! + 0.08, inv(P[4]!), ease.linear],
      [T.end, inv(P[4]!)],
    ]);
    const fstop = keys(t, [[T.start, 5.6], [T.root, 8], [T.walk[2]!, 8], [T.land, 16, ease.inOutCubic], [T.end, 16]]);
    return { focus: 1 / D, fstop };
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, u = this.draw.u;
    aimAt(st.camera, this.rig, t, T, this.P[4]!);
    u.uT.value = t - T.start;
    // the index as the cut finds it: a band of light rises through the tree from the files to the root, landing on the
    // beat she says "Fifty" on (each node's hash covers its children's); a breath on every beat after
    const rise = prog(t, T.start + 0.02, T.fifty, ease.inOutCubic);
    u.uSweep.value.set(0, 1, 0, lerp(-0.06, SHAPE.y[0]! + 0.04, rise));
    u.uSweepK.value.set(0.055, 0.85 * Math.sin(Math.PI * Math.min(1, rise * 1.08)));
    u.uLight.value.y = t > T.fifty ? 0.035 * onBeat(f, 0.3) : 0;
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
