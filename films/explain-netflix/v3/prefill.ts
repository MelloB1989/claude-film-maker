// v3 pre-positioning ("Every night, Netflix predicts what your area will watch. And copies it to the box near you."):
// a moon rises behind "Every night" (the off-peak fill window); a fan of title cards flips up over the library and the
// ones your area will watch light red and lift; on "copies" they fly in arcs into the Open Connect box with a stream of
// packets, and the box's fill gauge rises.
// Panel mode (params.panel): the same scene in the presenter shot's card, type scaled up for its size.
// Facts (facts_netflix.json): OCAs are filled during a nightly off-peak fill window with content chosen by predicted
// popularity for the region.
import { Flow, Beam, accentSolid, spring, expo, smooth, win, antic, pulse, breathe, keyed } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, KineticText, Label, MotionScene, ServerBox, glowMat, surfaceMat, hdr, emFor, v, arc, playGeometry, RoundedBoxGeometry, type CamPose } from './lib';

const FOV = 30;
const LIB = v(-2.45, -0.1, 0), BOX = v(2.45, -0.1, 0);
const NT = 8, PICK = [1, 2, 5, 6];

export default class Prefill extends MotionScene {
  private D = 7.6;
  private S = 1;
  private moon!: THREE.Mesh;
  private moonMat!: THREE.MeshBasicMaterial;
  private hero!: KineticText;
  private tag!: Label;
  private lib!: ServerBox;
  private box!: ServerBox;
  private libLabel!: Label;
  private boxLabel!: Label;
  private tiles: THREE.Group[] = [];
  private tileMats: THREE.MeshPhysicalMaterial[] = [];
  private gauge!: THREE.Mesh;
  private gaugeMat!: THREE.MeshBasicMaterial;
  private flow!: Flow;
  private arcs: THREE.QuadraticBezierCurve3[] = [];
  private tileHome: THREE.Vector3[] = [];

  protected build() {
    const s = this.stage.scene;
    const P = this.panel;
    this.D = P ? 17.5 : 8.4;
    this.S = 1;
    this.defaults = { fstop: P ? 4 : 2.2 };
    this.env = { floor: { y: -0.95, pool: 'accent2', poolK: 0.05, reach: 6 }, haze: { y: 1.0, role2: 'accent2Dim', k2: 0.1 } };
    const tCopies = this.cue('copies', 4.6), tNight = this.cue('night', 0.8);
    this.hits = [{ t: tNight, kind: 'punch', amt: 0.6 }, { t: tCopies, kind: 'punch', amt: 0.7 }];
    const em = (px: number) => emFor(px * this.S, this.D, FOV);
    // the moon and the night line
    this.moonMat = glowMat('#ffd9a8', 1.4);
    this.moon = new THREE.Mesh(new THREE.SphereGeometry(0.42, 40, 24), this.moonMat);
    s.add(this.moon);
    this.hero = this.own(new KineticText('Every night', { size: em(P ? 84 : 110), align: 'center', accentWords: [1], accentMat: accentSolid('accent2', 1.1) }));
    this.hero.group.position.set(P ? -0.3 : -0.35, P ? 2.0 : 1.3, 0);
    this.tag = this.own(new Label('OFF-PEAK FILL WINDOW', { size: em(P ? 30 : 38), family: F.mono(500), role: 'accent2', k: 1.3, tracking: 0.08 }));
    this.tag.group.position.set(this.hero.group.position.x, this.hero.group.position.y - (P ? 0.55 : 0.36), 0);
    // the library (left) and the box near you (right)
    this.lib = this.own(new ServerBox(1.3, 0.28, 0.85, 4));
    this.lib.group.position.copy(LIB); this.lib.group.rotation.y = 0.35;
    this.box = this.own(new ServerBox(1.1, 0.26, 0.8, 2));
    this.box.group.position.copy(BOX).add(v(0, -0.15, 0)); this.box.group.rotation.y = -0.35;
    s.add(this.lib.group, this.box.group, this.hero.group, this.tag.group);
    this.libLabel = this.own(new Label(P ? 'library' : 'Netflix library', { size: em(P ? 44 : 52), role: 'fgDim' }));
    this.libLabel.group.position.set(LIB.x, LIB.y - 0.85, 0.3);
    this.boxLabel = this.own(new Label(P ? 'box near you' : 'the box near you', { size: em(P ? 44 : 52) }));
    this.boxLabel.group.position.set(BOX.x - (P ? 0.55 : 0.3), BOX.y - (P ? 0.85 : 0.72), 0.3);
    s.add(this.libLabel.group, this.boxLabel.group);
    // the fill gauge beside the box
    const gTrack = new THREE.Mesh(new RoundedBoxGeometry(0.12, 1.0, 0.12, 2, 0.04), surfaceMat('#2a211b'));
    gTrack.position.set(BOX.x + 0.85, BOX.y - 0.05, 0);
    this.gaugeMat = glowMat('accent', 3.5);
    this.gauge = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1, 0.14), this.gaugeMat);
    s.add(gTrack, this.gauge);
    // title cards: a fan over the middle, each a dark card with a play mark
    const cardGeo = new RoundedBoxGeometry(0.46, 0.64, 0.05, 2, 0.04);
    const play = playGeometry(0.1, 0.025);
    for (let i = 0; i < NT; i++) {
      const g = new THREE.Group();
      const m = accentSolid('#3a2a22', 0);
      m.color.copy(hdr('#2e231d', 1));
      const card = new THREE.Mesh(cardGeo, m);
      const pm = new THREE.Mesh(play, glowMat('#c8bdb0', 0.9));
      pm.position.z = 0.03;
      g.add(card, pm);
      const col = i % 4, row = Math.floor(i / 4);
      const home = v(-0.96 + col * 0.64, 0.22 - row * 0.78, 0.15);
      this.tileHome.push(home);
      this.tiles.push(g); this.tileMats.push(m); s.add(g);
      this.arcs.push(arc(home, v(BOX.x, BOX.y + 0.05, 0.1), 0.9 + 0.12 * col));
    }
    this.flow = this.own(new Flow(arc(v(LIB.x + 0.4, LIB.y + 0.3, 0.1), v(BOX.x - 0.4, BOX.y + 0.1, 0.1), 1.3), { rate: 22, speed: 4.2, radius: 0.024, length: 0.16, k: 5, spread: 0.12, max: 60 }));
    s.add(this.flow.mesh);
    this.frame({ centre: [0, 0.2, 0], w: 6.6, h: 3.4, dist: this.D });
  }

  protected cam(t: number): CamPose {
    const D = this.D, tCopies = this.cue('copies', 4.6);
    const k = smooth(t, tCopies - 0.3, 1.6);
    const m = this.panel ? 0.35 : 1;
    const az = THREE.MathUtils.degToRad(m * (-4 + 3 * Math.min(1, t / 4) + 3 * k));
    const d = D * (1 - m * (0.04 * Math.min(1, t / this.len) + 0.03 * k));
    const ty = this.panel ? -0.05 : 0.3;
    return { pos: [Math.sin(az) * d + 0.1 * k, ty + 0.55, Math.cos(az) * d], target: [0.1 * k, ty, 0], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const tEvery = this.cue('every', 0.4), tNight = this.cue('night', 0.8), tPred = this.cue('predicts', 1.85), tArea = this.cue('area', 2.8);
    const tWatch = this.cue('watch', 3.6), tCopies = this.cue('copies', 4.6), tBox = this.cue('box', 5.25), tNear = this.cue('near', 5.6);
    // moon rises behind the line
    const mk = expo(t, tEvery - 0.3, 1.2);
    const hp = this.hero.group.position;
    this.moon.position.set(hp.x + (this.panel ? 3.25 : 3.1), hp.y - 0.9 + mk * 0.95, -2.5);
    this.moon.scale.setScalar(Math.max(0.001, mk) * (this.panel ? 0.6 : 1));
    this.moonMat.color.copy(hdr('#ffd9a8', 1.1 + 0.3 * breathe(t, 0.4)));
    this.hero.enter(t, [tEvery, tNight], 'drop');
    this.hero.emphasis(t, tNight + 0.25, 0.7);
    this.tag.pose(t, tNight + 0.25, 'type');
    // library and box
    const lk = antic(t, tEvery + 0.1, { amt: 0, settle: 0.5, over: 0.1 });
    this.lib.group.scale.setScalar(Math.max(0.001, lk));
    this.lib.blink(t);
    this.libLabel.pose(t, tEvery + 0.25, 'rise');
    const bk = antic(t, tNight + 0.1, { amt: 0, settle: 0.5, over: 0.1 });
    this.box.group.scale.setScalar(Math.max(0.001, bk));
    this.box.blink(t, t > tCopies);
    this.boxLabel.pose(t, tNear - 0.05, 'rise');
    // the cards flip up on "predicts"; your area's picks light and lift on "area"
    this.tiles.forEach((g, i) => {
      const t0 = tPred + i * 0.07;
      const k = spring(t, t0, 0.5, 0.1);
      const picked = PICK.includes(i);
      const pk = picked ? spring(t, tArea + PICK.indexOf(i) * 0.08, 0.45, 0.15) : 0;
      const home = this.tileHome[i]!.clone().add(v(0, 0.12 * pk, 0.25 * pk));
      const m = this.tileMats[i]!;
      // the copy: picked cards fly along their arc into the box from "copies"
      const tf = tCopies + PICK.indexOf(i) * 0.14;
      if (picked && t > tf) {
        const u = expo(t, tf, 0.55);
        const p = this.arcs[i]!.getPointAt(Math.min(1, u));
        g.position.copy(p).lerp(home, 0);
        g.position.copy(u < 1 ? p : this.arcs[i]!.getPointAt(1));
        g.scale.setScalar(Math.max(0.001, 1 - u * 0.85));
        g.rotation.set(0, u * 1.2, u * -0.6);
        g.visible = u < 0.98;
      } else {
        g.position.copy(home);
        g.scale.setScalar(Math.max(0.001, k) * (1 + 0.08 * pk));
        g.rotation.set((1 - k) * -1.4, 0.08 * breathe(t, 0.4, i), 0);
        g.visible = k > 0.001;
      }
      // light: picks glow red, the rest dim back after "watch"
      m.color.copy(hdr('#2e231d', 1)).lerp(hdr('accent', 1), pk * 0.8);
      m.emissive.copy(hdr('accent', 1));
      m.emissiveIntensity = pk * (0.9 + 0.8 * pulse(t, tWatch, 0.04, 0.2));
      if (!picked) g.scale.multiplyScalar(1 - 0.12 * win(t, tWatch, 0.3));
    });
    // the stream and the gauge
    this.flow.pose(t, tCopies, Infinity);
    const fill = 0.05 + 0.9 * smooth(t, tCopies + 0.1, 1.7);
    this.gauge.scale.y = fill * 0.94;
    this.gauge.position.set(BOX.x + 0.85, BOX.y - 0.05 - 0.47 + (fill * 0.94) / 2, 0.01);
    this.gaugeMat.color.copy(hdr('accent', 3.5 * (1 + 0.6 * pulse(t, tBox, 0.05, 0.3))));
    return t < tCopies ? v(0, 0.1, 0.2) : v(0.6, -0.1, 0);
  }
}
