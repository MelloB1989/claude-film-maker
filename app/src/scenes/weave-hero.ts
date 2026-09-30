// The hero word of `weave`: L32's "commit." as extruded Bricolage (satin bone with the moss diff glow, the callback to
// the headline in `her`), slamming in from depth on its spoken onset, on a stage of its own that renders over the
// plate. The camera looks straight at the type's plane, so at rest a glyph sits exactly where the flat 2D line sets it:
// a world point (x, y, 0) shows at logical px (960 + x * PX_PER_UNIT, 540 - y * PX_PER_UNIT).
//
// Light: a key from the upper left, a rim from behind, the stage's studio, and a narrow strip whose reflection runs
// across the faces left to right as the word lands (the specular sweep of motion language v2 §5).
import * as THREE from 'three';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import { Stage } from '../engine/stage';
import { Mat, Type3D } from '../engine/type3d';
import { GLOW_LEVEL } from '../engine/look';
import { slam } from '../engine/motion';
import { clamp, ease, lerp, prog, pulse } from '../engine/util';

/** A long lens: at rest the type is nearly square to the viewer across the whole column (the far right glyph shows
 * a few px of wall), and a slam from depth still reads as a push toward camera. */
export const FOV = 7;
export const CAM_D = 30;
/** Logical px per world unit on the type's plane (z = 0). */
export const PX_PER_UNIT = 1080 / (2 * CAM_D * Math.tan((FOV * Math.PI) / 360));
/** Where (logical px) the camera stands across the frame. */
const CAM_X_PX = 300;

/** How far behind its rest a glyph launches (em), how far it tips back (rad), and the stagger between glyphs (s). */
const DEPTH_EM = 7;
const TIP = 0.6;
const STAGGER = 0.016;
/** The sweep: when it starts after the onset and how long it takes to cross (s). */
const SWEEP_AT = 0.03;
const SWEEP_DUR = 0.5;

export class Hero {
  readonly stage: Stage;
  readonly word: Type3D;
  private mat: THREE.MeshPhysicalMaterial;
  private strip: THREE.RectAreaLight;
  private key: THREE.DirectionalLight;
  private rim: THREE.DirectionalLight;

  /** `text` set in `family` at `emPx` logical px per em, its origin (left end, baseline) at logical px (x, y). */
  constructor(renderer: THREE.WebGLRenderer, text: string, family: string, emPx: number, x: number, y: number) {
    this.stage = new Stage(renderer, { fov: FOV, near: 5, far: 80, envIntensity: 0.3 });
    // the camera stands left of the column (over the mark) looking straight ahead, its film shifted so the type's
    // plane still maps to the frame as if it were centred: every glyph shows the wall on its right, turned from the
    // key, where the moss seam glows against shadow (the headline's look in `her`)
    const cam = this.stage.camera;
    const xc = (CAM_X_PX - 960) / PX_PER_UNIT;
    cam.position.set(xc, 0, CAM_D);
    cam.lookAt(xc, 0, 0);
    cam.filmOffset = (-xc * cam.getFilmWidth()) / CAM_D;
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this.mat = Mat.accent('moss', 0);
    this.word = new Type3D(text, { family, size: emPx / PX_PER_UNIT }, this.mat);
    this.word.group.position.set((x - 960) / PX_PER_UNIT, (540 - y) / PX_PER_UNIT, 0);
    const s = this.stage.scene;
    s.add(this.word.group);

    // neutral light: a near-frontal key that sets the faces at bone (albedo 0.85 x 3.4 x N.L 0.87 / pi = 0.8), a long
    // softbox above whose reflection runs along the top bevels, a rim from behind and above along the top edges
    RectAreaLightUniformsLib.init();
    this.key = new THREE.DirectionalLight(0xffffff, 3.4);
    this.key.position.set(-3, 4, 9);
    const [x0, x1, ym] = this.span();
    const box = new THREE.RectAreaLight(0xffffff, 3, (x1 - x0) * 1.3, 0.5);
    box.position.set((x0 + x1) / 2, ym + 3.2, 2.2);
    box.lookAt((x0 + x1) / 2, ym, 0);
    this.rim = new THREE.DirectionalLight(0xffffff, 2);
    this.rim.position.set(2, 3, -6);
    this.strip = new THREE.RectAreaLight(0xffffff, 0, 0.14, 3.2);
    s.add(this.key, box, this.rim, this.strip);
  }

  /** The word's left and right ends and its middle height, in world units (for the sweep and framing). */
  private span(): [number, number, number] {
    const g = this.word.glyphs, p = this.word.group.position, k = this.word.group.scale.x, size = this.word.size * k;
    return [p.x + g[0]!.x * k, p.x + (g[g.length - 1]!.x + g[g.length - 1]!.w) * k, p.y + 0.36 * size];
  }

  /** Pose everything for time t; `onset` is the word's spoken onset. Returns whether any of it shows. */
  update(t: number, onset: number): boolean {
    const size = this.word.size;
    let any = false;
    this.word.glyphs.forEach((g, k) => {
      const s = slam(t, onset + STAGGER * k);
      const m = g.mesh;
      m.visible = s > 1e-3;
      any ||= m.visible;
      m.position.copy(g.home);
      m.position.z += (s - 1) * DEPTH_EM * size;
      m.rotation.set((1 - s) * TIP, 0, 0);
      m.scale.setScalar(size);
    });
    // the diff glow comes up as it lands, flares on the impact and settles to the film's level
    this.mat.emissiveIntensity = GLOW_LEVEL * clamp(slam(t, onset + 0.05, { freq: 3 })) * (1 + 0.3 * pulse(t, onset + 0.06, 0.2));
    // the sweep: a strip mirrored in the faces, running across the word
    const u = prog(t, onset + SWEEP_AT, onset + SWEEP_AT + SWEEP_DUR, ease.inOutQuad);
    const [x0, x1, ym] = this.span();
    // a point x on the face mirrors a strip at xc + (x - xc) * k, k = (D + zs) / D (the camera at xc)
    const zs = 4, k = (CAM_D + zs) / CAM_D, xc = this.stage.camera.position.x;
    const xs = lerp(x0 - 0.4 * size, x1 + 0.4 * size, u);
    this.strip.position.set(xc + (xs - xc) * k, ym * k, zs);
    this.strip.lookAt(xs, ym, 0);
    this.strip.intensity = u > 0 && u < 1 ? 26 * Math.sin(Math.PI * u) ** 2 : 0;
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
