// Dev harness for glass over panels (render.ts stills --module _glasstest --t 0.5,1.5). A commit bead hangs a few
// centimetres in front of an editor panel, the camera close on it. Before t = 1 the panel is the default (transparent:
// three's transmission pass leaves it out, so the glass refracts only the ink behind it); from t = 1 the same panel is
// built `opaque` (in the opaque list the pass copies), and the bead shows the panel's face and code bent through it.
import * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { Stage, freeTransmission, initAreaLights } from '../engine/stage';
import { Panel, type PanelLine } from '../engine/panels';
import { Bead } from '../engine/bead';
import { LIN } from '../engine/palette';

const LINES: PanelLine[] = [
  { text: '---' }, { text: 'tier: facts' }, { text: 'tags: [user, prefs]' }, { text: 'confidence: 0.9' }, { text: '---' },
  { text: '' }, { text: '## Editor' }, { text: '' }, { text: 'Uses neovim. Has since 2019.' }, { text: '' }, { text: '## Timezone' },
];
/** World units per panel px ×1000 (diff's editor scale): the panel is 26 cm wide. */
const SCALE = 0.4;
const INK = new THREE.Color().setRGB(...LIN.ink);

export default class GlassTest extends Scene {
  private stage!: Stage;
  private panels: Panel[] = [];
  private bead!: Bead;

  override init() {
    this.stage = new Stage(this.ctx.renderer, { fov: 24, near: 0.01, far: 30, envIntensity: 0.22 });
    const s = this.stage.scene;
    for (const opaque of [false, true]) {
      const p = new Panel({ kind: 'editor', title: 'facts/people/user.md', w: 640, lang: 'md', size: 24, rows: LINES.length, lines: LINES, opaque });
      const g = new THREE.Group();
      g.scale.setScalar(SCALE);
      g.add(p.mesh);
      s.add(g);
      p.draw(0);
      this.panels.push(p);
    }
    // the bead 4 cm in front of `Uses neovim. Has since 2019.`, its bore across, its face to the camera
    this.bead = new Bead({ radius: 0.024, bore: 0.0055, chamfer: 0.003, text: '3f9a1c2' });
    this.bead.place(new THREE.Vector3(0.0, -0.045, 0.04), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 1));
    s.add(this.bead.mesh);
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 0.5, 1.2, 0.4);
    box.position.set(-0.5, 0.55, 0.7);
    box.lookAt(0, 0, 0);
    const key = new THREE.DirectionalLight(0xffffff, 0.35);
    key.position.set(-1.2, 1.6, 1.4);
    const rim = new THREE.DirectionalLight(0xffffff, 4);
    rim.position.set(1, 1.1, -1.6);
    s.add(box, key, rim);
    this.stage.camera.position.set(0.05, -0.01, 0.26);
    this.stage.camera.lookAt(0, -0.045, 0.04);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const opaque = f.t >= 1;
    this.panels.forEach((p, i) => (p.mesh.visible = (i === 1) === opaque));
    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1); // what the glass sees through the transmission pass
    this.stage.render(out, { dof: { focus: this.stage.depthOf(this.bead.mesh.position), fstop: 5.6 } });
    r.setClearColor(cc, ca);
  }

  override dispose() {
    freeTransmission(this.ctx.renderer, this.bead.material);
    for (const p of this.panels) p.dispose();
    this.bead.dispose();
    this.stage.dispose();
  }
}
