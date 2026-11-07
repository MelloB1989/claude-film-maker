// v3 end card (2 s, after "That's why it just plays."): the title's play ring returns, whole and pulsing, with
// packets racing round it; "The cloud decides." rises in warm white, "The box next door delivers." slams in red, the
// series tag types on, and the camera keeps pushing in. Everything lands in the first second.
import { Flow, accentSolid, spring, expo, pulse, breathe, antic } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, Circle, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, playGeometry, type CamPose } from './lib';

const FOV = 30, D = 7.4;
const em = (px: number) => emFor(px, D, FOV);

export default class EndCard extends MotionScene {
  private ring!: THREE.Mesh;
  private ringMat!: THREE.MeshBasicMaterial;
  private spin!: Flow;
  private play!: THREE.Mesh;
  private l1!: KineticText;
  private l2!: KineticText;
  private tag!: Label;
  private P = v(0, 1.15, 0);

  protected build() {
    const s = this.stage.scene;
    this.arrival = { dur: 0.35, dist: 0.12, yaw: 0, pitch: 4, roll: 0 };
    this.env = { floor: { y: -1.5, pool: 'accent', poolK: 0.08, reach: 6 }, haze: { role2: 'accentDim', k2: 0.12 } };
    this.hits = [{ t: 0.42, kind: 'punch', amt: 0.8 }];
    this.ringMat = glowMat('accent', 3.5);
    this.ring = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.018, 12, 120), this.ringMat);
    this.ring.position.copy(this.P);
    this.spin = this.own(new Flow(new Circle(this.P.clone().add(v(0, 0, 0.02)), 0.42, 1), { rate: 10, speed: 2.4, radius: 0.022, length: 0.15, k: 5, max: 20 }));
    this.play = new THREE.Mesh(playGeometry(0.22, 0.1), surfaceMat('#fff6ec', { rough: 0.25, coat: 1, k: 1.1 }));
    this.play.position.copy(this.P).add(v(0.03, 0, 0));
    s.add(this.ring, this.spin.mesh, this.play);
    this.l1 = this.own(new KineticText('The cloud decides.', { size: em(96), align: 'center' }));
    this.l1.group.position.set(0, 0.12, 0);
    this.l2 = this.own(new KineticText('The box next door delivers.', { size: em(96), align: 'center', accentWords: [0, 1, 2, 3, 4], accentMat: accentSolid('accent', 1.3) }));
    this.l2.group.position.set(0, -0.55, 0);
    this.tag = this.own(new Label('SYSTEM DESIGN IN 60 SECONDS', { size: em(34), family: F.mono(500), role: 'fgDim', tracking: 0.08 }));
    this.tag.group.position.set(0, -1.08, 0);
    s.add(this.l1.group, this.l2.group, this.tag.group);
    this.frame({ centre: [0, 0.1, 0], w: 6, h: 3.4, dist: D });
  }

  protected cam(t: number): CamPose {
    const k = Math.min(1, t / this.len);
    return { pos: [0.15 - 0.3 * k, 0.25, D * (1.02 - 0.05 * k)], target: [0, 0.18, 0], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const rk = antic(t, 0.0, { amt: 0, settle: 0.45, over: 0.12 });
    this.ring.scale.setScalar(Math.max(0.001, rk));
    this.ringMat.color.copy(hdr('accent', 3.5 * (1 + 0.5 * pulse(t, 0.42, 0.04, 0.25) + 0.15 * breathe(t, 1.2))));
    this.spin.pose(t, -0.5, Infinity);
    const pk = spring(t, 0.08, 0.4, 0.14);
    this.play.scale.setScalar(Math.max(0.001, pk));
    this.play.rotation.y = 0.3 * breathe(t, 0.5);
    this.l1.enter(t, 0.06, 'rise', 0.8 / 24);
    this.l2.enter(t, 0.42, 'slam', 0.8 / 24);
    this.l2.emphasis(t, 0.9, 0.5);
    this.tag.pose(t, 0.7, 'type');
    return v(0, 0, 0);
  }
}
