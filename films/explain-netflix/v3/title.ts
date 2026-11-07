// v3 title: a 3D play mark born from a buffering spinner (packets racing round a ring of red light) slams into place,
// the title builds glyph by glyph beside it with "300+" slammed in the accent, and a playback bar under it shows the
// buffer running far ahead of the playhead (the film's motif). The camera arrives swinging in from the right and keeps
// pushing in. Facts: "300+ million" (facts_netflix.json, the script's softening).
import { Flow } from '@kit/motion';
import { spring, expo, win, pulse, antic, breathe } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, Mat, Circle, hdr, KineticText, Label, MotionScene, glowMat, surfaceMat, playGeometry, emFor, v, type CamPose } from './lib';

const DIST = 6.2, FOV = 30;

export default class Title extends MotionScene {
  private ring!: Circle;
  private spin!: Flow;
  private ringMesh!: THREE.Mesh;
  private ringMat!: THREE.MeshBasicMaterial;
  private play!: THREE.Mesh;
  private kicker!: Label;
  private l1!: KineticText;
  private hero!: KineticText;
  private l2b!: KineticText;
  private l3!: KineticText;
  private bar!: THREE.Group;
  private buf!: THREE.Mesh;
  private head!: THREE.Mesh;
  private knob!: THREE.Mesh;
  private P = v(-2.05, 0.1, 0.2);

  protected build() {
    const s = this.stage.scene;
    this.env = { floor: { y: -1.45, pool: 'accent', poolK: 0.14, centre: [-2, 0], reach: 5 }, haze: { role2: 'accentDim', k2: 0.22 } };
    const tSnap = this.cue('but', 0.36, 0, 4), tHero = this.cue('video', 0.6, 0, 1);
    this.hits = [{ t: tSnap, kind: 'punch', amt: 0.8 }, { t: tSnap, kind: 'flash', amt: 0.6 }, { t: tHero + 0.1, kind: 'punch', amt: 1 }];
    const P = this.P;
    // the ring: a torus of red light, and packets racing round it (the spinner)
    this.ringMat = glowMat('accent', 3.2);
    this.ringMesh = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.022, 12, 120), this.ringMat);
    this.ringMesh.position.copy(P);
    s.add(this.ringMesh);
    this.ring = new Circle(P, 0.62, 1);
    this.spin = this.own(new Flow(this.ring, { rate: 26, speed: 9, radius: 0.028, length: 0.22, k: 5, hotShare: 0.4, vary: 0.1, max: 40 }));
    s.add(this.spin.mesh);
    this.play = new THREE.Mesh(playGeometry(0.36, 0.16), surfaceMat('#f2ece4', { rough: 0.3, coat: 0.9 }));
    this.play.position.copy(P).add(v(0.05, 0, 0));
    s.add(this.play);
    // the type
    const x0 = -1.18;
    this.kicker = this.own(new Label('SYSTEM DESIGN IN 60 SECONDS', { size: emFor(34, DIST, FOV), family: F.mono(500), role: 'accent2', k: 1.2, align: 'left', tracking: 0.06 }));
    this.kicker.group.position.set(x0, 0.98, 0);
    const em1 = emFor(80, DIST, FOV);
    this.l1 = this.own(new KineticText('How Netflix streams to', { size: em1, align: 'left' }));
    this.l1.group.position.set(x0, 0.42, 0);
    this.hero = this.own(new KineticText('300+', { size: emFor(150, DIST, FOV), align: 'left', accentWords: [0], accentMat: Mat.accent('accent', 4), depth: 0.22 }));
    this.hero.group.position.set(x0, -0.36, 0);
    this.l2b = this.own(new KineticText('million people', { size: em1, align: 'left' }));
    this.l2b.group.position.set(x0 + this.hero.width + 0.12, -0.36, 0);
    this.l3 = this.own(new KineticText('without buffering.', { size: em1, align: 'left' }));
    this.l3.group.position.set(x0, -0.98, 0);
    for (const k of [this.kicker.group, this.l1.group, this.hero.group, this.l2b.group, this.l3.group]) s.add(k);
    // the playback bar under the play mark: track, buffer (warm grey) racing ahead, playhead (red) and knob
    this.bar = new THREE.Group();
    const W = 1.5;
    const track = new THREE.Mesh(new THREE.BoxGeometry(W, 0.03, 0.03), surfaceMat('#3b3129'));
    track.position.x = W / 2;
    this.buf = new THREE.Mesh(new THREE.BoxGeometry(1, 0.034, 0.034), glowMat('#8a7d70', 1));
    this.head = new THREE.Mesh(new THREE.BoxGeometry(1, 0.04, 0.04), glowMat('accent', 4));
    this.knob = new THREE.Mesh(new THREE.SphereGeometry(0.05, 20, 12), glowMat('accentBright', 5));
    this.bar.add(track, this.buf, this.head, this.knob);
    this.bar.position.set(P.x - W / 2, P.y - 0.98, P.z);
    s.add(this.bar);
    this.frame({ centre: [0, 0, 0], w: 5.8, h: 3.2, dist: DIST });
  }

  protected cam(t: number): CamPose {
    // a slow push and a few degrees of orbit through the shot
    const k = Math.min(1, t / this.len);
    const az = THREE.MathUtils.degToRad(-6 + 9 * k), d = DIST * (1.0 - 0.07 * k);
    return { pos: [Math.sin(az) * d - 0.1, 0.25 - 0.15 * k, Math.cos(az) * d], target: [-0.1, -0.02, 0], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const P = this.P;
    const tSnap = this.cue('but', 0.36, 0, 4); // the spinner resolves on "But"
    // ring: appears scaling up, spinner packets race until the snap, then the ring is whole and pulses
    const rk = spring(t, 0.0, 0.45, 0.12);
    this.ringMesh.scale.setScalar(Math.max(0.001, rk));
    this.ringMesh.rotation.z = 0;
    const lit = t < tSnap ? 0.35 : 1 + 1.5 * pulse(t, tSnap, 0.02, 0.18);
    this.ringMat.color.copy(hdr('accent', 3.2 * lit));
    this.spin.pose(t, -0.4, tSnap, 1, 1 + 0.6 * win(t, 0, tSnap));
    // play mark: slams from the camera into the ring at the snap
    const pk = antic(t, tSnap, { amt: 0, settle: 0.45, over: 0.14 });
    this.play.scale.setScalar(Math.max(0.001, pk));
    this.play.position.set(P.x + 0.05, P.y, P.z + (1 - expo(t, tSnap, 0.25)) * 2.5);
    this.play.rotation.set(0.25 * breathe(t, 0.4), 0.35 * breathe(t, 0.3, 1) + (1 - Math.min(1, pk)) * 1.2, 0);
    this.play.visible = t >= tSnap;
    // the type, on the VO's rhythm (it is a title over "But the video doesn't come from the cloud")
    this.kicker.pose(t, 0.12, 'type');
    this.l1.enter(t, tSnap + 0.08, 'rise', 1 / 24);
    const tHero = this.cue('video', 0.6, 0, 1);
    this.hero.enter(t, tHero, 'slam', 2 / 24);
    this.hero.emphasis(t, tHero + 0.3, 0.6);
    this.l2b.enter(t, tHero + 0.16, 'rise', 1 / 24);
    this.l3.enter(t, this.cue('come', 1.05, 0, 0), 'rise', 1 / 24);
    // the bar: the buffer runs ahead of the playhead
    const bk = spring(t, tSnap + 0.15, 0.5, 0.06);
    this.bar.scale.set(Math.max(0.001, bk), 1, 1);
    const W = 1.5;
    const play = W * Math.min(0.9, 0.08 + 0.12 * Math.max(0, t - tSnap));
    const buf = Math.min(W, play + W * 0.55 * expo(t, tSnap + 0.3, 1.4));
    this.buf.scale.x = Math.max(0.001, buf); this.buf.position.x = buf / 2;
    this.head.scale.x = Math.max(0.001, play); this.head.position.x = play / 2;
    this.knob.position.x = play;
    return v(-0.6, 0, 0);
  }

}
