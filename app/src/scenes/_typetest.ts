// Dev harness for Type3D (render.ts stills --module _typetest --t 1). "every memory has a commit" as extruded satin-bone
// Bricolage with "commit" in the moss diff glow, lit on the Stage. Under it, in the same plane, the same line set flat by
// Canvas2D's own fillText, so the kerning can be checked glyph by glyph (the two are projected alike).
// Over t in [0, 1] the glyphs slam in from depth one after another (motion.slam: the house spring's tight overshoot on
// each glyph's own mesh, pivoted at its centre), all landed and settled well before t = 1, the acceptance frame. After
// it the flat line leaves and the camera comes round to a low three-quarter close-up on "commit", racking focus onto
// it, while the studio turns and sweeps its highlights over the faces.
import * as THREE from 'three';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import { Scene, type Frame } from '../engine/scene';
import { CameraRig, Stage, type V3 } from '../engine/stage';
import { LIN } from '../engine/palette';
import { F, font, layout } from '../engine/type';
import { Mat, Type3D } from '../engine/type3d';
import { slam } from '../engine/motion';
import { GLOW_LEVEL } from '../engine/look';
import { clamp, ease, keys } from '../engine/util';

const TEXT = 'every memory has a commit';
const ACCENT = 4; // the word "commit"
const EM = 0.1; // world units (metres) per em: the line is 1.24 m long, a tabletop piece
const FOV = 20; // a 57 mm lens (dof.ts)
const FSTOP = 2.8;
/** The flat line's baseline, in em below the 3D line's. */
const FLAT_DROP = 1.36;
/** How deep the glyphs start (em behind their rest) and when each lands (s): one after another, all down by 0.58. */
const FLY = 3.5;
const land = (k: number) => 0.2 + 0.019 * k;

export default class TypeTest extends Scene {
  private stage!: Stage;
  private line!: Type3D;
  private flat!: THREE.Mesh;
  private bone!: THREE.MeshPhysicalMaterial;
  private moss!: THREE.MeshPhysicalMaterial;
  /** The middle of "commit" (world), for the rack focus. */
  private commit = new THREE.Vector3();
  // at t = 1 the camera looks at the line from a little left of its middle and above it, so the walls it sees on
  // "commit" face away from the key; then it comes round to a low three-quarter close-up on "commit" from its right
  private rig = new CameraRig([
    { t: 0, pos: [-0.24, 0.32, 2.62], target: [-0.02, -0.035, 0], fov: FOV },
    { t: 1, pos: [-0.2, 0.27, 2.34], target: [-0.02, -0.035, 0], ease: ease.outCubic },
    { t: 1.6, pos: [-0.2, 0.27, 2.34], target: [-0.02, -0.035, 0] },
    { t: 4, pos: [0.98, 0.16, 0.72], target: [0.4, 0.02, 0], ease: ease.inOutCubic },
    { t: 7, pos: [0.86, 0.22, 0.66], target: [0.44, 0.03, 0], ease: ease.inOutQuad },
  ]);

  override init() {
    const fam = F.display(100, 600);
    this.stage = new Stage(this.ctx.renderer, { fov: FOV });
    const s = this.stage.scene;
    this.bone = Mat.satinBone();
    this.moss = Mat.accent('moss');
    this.line = new Type3D(TEXT, { family: fam, size: EM }, (g) => (g.word === ACCENT ? this.moss : this.bone));
    this.line.group.position.set(-this.line.width / 2, 0, 0);
    s.add(this.line.group);
    this.flat = flatLine(TEXT, fam, EM);
    this.flat.position.y = -FLAT_DROP * EM;
    this.line.group.add(this.flat);
    const cg = this.line.glyphs.filter((g) => g.word === ACCENT), last = cg[cg.length - 1]!;
    this.commit.set((cg[0]!.x + last.x + last.w) / 2 - this.line.width / 2, 0.3 * EM, 0);

    // neutral light only (a key warmer than ~4000 K would open the bloom's chroma gate on bone): a softbox high on the
    // left whose reflection runs along the bevels that turn to it, a soft spot from the upper right for the faces (a
    // pool that falls off towards the ends of the line), and a hard rim from above and behind along the top edges
    RectAreaLightUniformsLib.init();
    const box = new THREE.RectAreaLight(0xffffff, 4, 1.4, 0.5);
    box.position.set(-0.9, 1.1, 1.2);
    box.lookAt(0, 0, 0);
    const key = new THREE.SpotLight(0xffffff, 20, 0, 0.45, 1, 2);
    key.position.set(1.3, 1.9, 1.6);
    key.target.position.set(-0.06, -0.04, 0);
    const rim = new THREE.DirectionalLight(0xffffff, 5);
    rim.position.set(-0.6, 3, -2.2);
    s.add(box, key, key.target, rim, rim.target);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const st = this.stage, t = f.t;
    // the slam: each glyph from FLY em deep and tipped back, landing on its time with the house spring's overshoot
    this.line.glyphs.forEach((g, k) => {
      const s = slam(t, land(k));
      g.mesh.visible = s > 0;
      g.mesh.position.copy(g.home);
      g.mesh.position.z += (s - 1) * FLY * EM;
      g.mesh.rotation.set((1 - s) * 0.55, 0, 0);
      g.mesh.scale.setScalar(this.line.size);
    });
    // the diff glow comes up as "commit" lands
    this.moss.emissiveIntensity = GLOW_LEVEL * clamp(slam(t, land(this.line.glyphs.findIndex((g) => g.word === ACCENT))));
    // the flat line is there to check the kerning against at t = 1; it leaves as the camera comes round
    (this.flat.material as THREE.MeshBasicMaterial).opacity = 1 - clamp((t - 1.6) / 1.2);
    this.flat.visible = t < 2.8;

    this.rig.apply(st.camera, t);
    st.scene.environmentRotation.set(0, keys(t, [[1.6, 0], [7, 1.1, ease.inOutQuad]]), 0);
    // focus on the line's middle, then rack to "commit" as the camera comes round (in diopters, as a focus ring turns)
    const dLine = 1 / st.depthOf([0, 0.3 * EM, 0]), dCommit = 1 / st.depthOf(this.commit);
    const D = keys(t, [[1.6, dLine], [3.6, dCommit, ease.inOutCubic]]);
    st.render(out, { dof: { focus: 1 / D, fstop: FSTOP } });
  }

  override dispose() {
    this.line.dispose();
    this.flat.geometry.dispose();
    const fm = this.flat.material as THREE.MeshBasicMaterial;
    fm.map?.dispose();
    fm.dispose();
    this.bone.dispose();
    this.moss.dispose();
    this.stage.dispose();
  }
}

/**
 * The line set flat by Canvas2D (fillText shapes it with Chrome's own kerning) on a plane in the 3D line's face plane:
 * its text origin (left end, baseline) at the plane's local origin, `em` world units per em, in bone-faint.
 */
function flatLine(text: string, family: string, em: number): THREE.Mesh {
  const PX = 320; // texture px per em, over twice what t = 1 shows
  const lay = layout(text, family, PX);
  const pad = Math.ceil(0.3 * PX), w = Math.ceil(lay.width) + 2 * pad, h = Math.ceil(1.5 * PX), base = Math.round(1.1 * PX);
  const cv = document.createElement('canvas');
  cv.width = w;
  cv.height = h;
  const c = cv.getContext('2d')!;
  c.font = font(family, PX);
  c.textBaseline = 'alphabetic';
  c.fillStyle = '#fff';
  c.fillText(text, pad, base);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const mat = new THREE.MeshBasicMaterial({
    map: tex, color: new THREE.Color().setRGB(...(LIN.boneFaint as V3)), transparent: true, depthWrite: true, toneMapped: false,
  });
  const geo = new THREE.PlaneGeometry((w / PX) * em, (h / PX) * em);
  geo.translate(((w / 2 - pad) / PX) * em, ((base - h / 2) / PX) * em, 0); // canvas (pad, base) to the origin
  return new THREE.Mesh(geo, mat);
}
