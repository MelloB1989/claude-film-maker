// Group (W12, 101 f): "In a group, your phone encrypts once. The server fans it out to everyone."
// The group's phones pop up in an arc on "group". On "encrypts" a lock slams shut over the message on your phone; on
// "once" the one sealed copy flies up to the server (1 UPLOAD). On "fans" the server bursts: a stream splits to every
// member, each phone lighting as its copy lands, while the camera cranes up to take in the whole fan. The headline:
// "Encrypt once," then "fan out"; GROUPS UP TO 1,024 MEMBERS on "everyone".
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, Server, Lock, Bag, bubbleShape, extrude, hdr, GREEN } from './props';
import { Beam, Flow, KineticText, Label, antic, expo, spring, win } from '@kit/motion';
import { F } from '@engine/type';
import { ease } from '@engine/util';

const SND: V3 = [-3.0, 0.82, 0.7];
const SRV: V3 = [-0.4, 0, -0.5];
const M = 8;
const ARC = { r: 3.0, a0: -1.45, a1: 0.45 };

export default class Group extends WaShot {
  private bag = new Bag();
  private snd!: Phone;
  private server!: Server;
  private members: Phone[] = [];
  private fans: Flow[] = [];
  private fanBeams: Beam[] = [];
  private up!: THREE.CatmullRomCurve3;
  private upBeam!: Beam;
  private packet!: THREE.Group;
  private lock!: Lock;
  private l1!: KineticText;
  private l2!: KineticText;
  private upload!: Label;
  private tag!: Label;
  private hitAt: number[] = [];

  protected build() {
    this.env = { floor: { y: 0, centre: [0, 0], reach: 8, poolK: 0.07 }, haze: { k2: 0.06 } };
    this.basePost = { ...this.basePost, bloom: 0.65 };
    const s = this.stage.scene;
    this.snd = this.own(new Phone());
    this.snd.group.position.set(...SND);
    this.snd.group.rotation.y = 0.45;
    this.snd.group.scale.setScalar(1.05);
    this.server = this.own(new Server(4));
    this.server.group.position.set(...SRV);
    s.add(this.snd.group, this.server.group);
    const top = new THREE.Vector3(SRV[0], 1.5, SRV[2] + 0.6);
    for (let i = 0; i < M; i++) {
      const a = ARC.a0 + ((ARC.a1 - ARC.a0) * i) / (M - 1);
      const p = this.own(new Phone());
      p.group.position.set(SRV[0] + 0.6 + ARC.r * Math.cos(a), 0.5, SRV[2] + ARC.r * Math.sin(a));
      p.group.rotation.y = -0.35 - a * 0.35;
      p.group.scale.setScalar(0.62);
      s.add(p.group);
      this.members.push(p);
      const end = p.group.position.clone().add(new THREE.Vector3(0, 0.15, 0.05));
      const mid = top.clone().lerp(end, 0.5).add(new THREE.Vector3(0, 0.9, 0));
      const c = new THREE.CatmullRomCurve3([top.clone(), mid, end]);
      const f = this.own(new Flow(c, { rate: 9, speed: 5.5, radius: 0.022, length: 0.15, k: 3.5, hotShare: 0.4, max: 24, seed: 10 + i, vary: 0.15 }));
      const b = this.own(new Beam(c, { radius: 0.006, k: 1.4 }));
      this.fans.push(f);
      this.fanBeams.push(b);
      s.add(f.mesh, b.mesh);
    }
    this.up = new THREE.CatmullRomCurve3([new THREE.Vector3(SND[0] + 0.3, 1.3, SND[2] + 0.3), new THREE.Vector3(-1.9, 2.4, 0.4), top.clone()]);
    this.upBeam = this.own(new Beam(this.up, { radius: 0.01, k: 2 }));
    s.add(this.upBeam.mesh);
    // the sealed message: a bubble with the lock on it
    this.packet = new THREE.Group();
    const bub = new THREE.Mesh(extrude(this.bag, bubbleShape(0.5, 0.36, 0.1), 0.08, 0.02), this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr(GREEN, 0.5), emissive: hdr(GREEN), emissiveIntensity: 1.6, roughness: 0.3, clearcoat: 1 })));
    this.packet.add(bub);
    this.lock = this.own(new Lock('#FFB547'));
    this.lock.group.scale.setScalar(0.5);
    this.lock.group.position.set(0.02, -0.02, 0.12);
    this.packet.add(this.lock.group);
    s.add(this.packet);
    const D = 8.5;
    this.l1 = this.own(new KineticText('Encrypt once,', { size: em(96, D), align: 'right', accentWords: [1] }));
    this.l1.group.position.set(-0.2, 3.05, 0.3);
    this.l2 = this.own(new KineticText('fan out', { size: em(96, D), align: 'left', accentWords: [1] }));
    this.l2.group.position.set(0.1, 3.05, 0.3);
    this.upload = this.own(new Label('1 UPLOAD', { size: em(42, 7), family: F.mono(500), role: 'accent', k: 1.3, align: 'left', tracking: 0.08 }));
    this.upload.group.position.set(-1.75, 2.55, 0.4);
    this.tag = this.own(new Label('GROUPS UP TO 1,024 MEMBERS', { size: em(44, 9.5), family: F.mono(500), role: 'fg', tracking: 0.06 }));
    this.tag.group.position.set(1.4, 2.45, 0.6);
    for (const k of [this.l1, this.l2, this.upload, this.tag]) s.add(k.group);
    this.frame({ centre: [0, 1.3, 0], w: 7, h: 3.6 });
    const enc = this.cue('encrypts', 1.3), fans = this.cue('fans', 2.67);
    this.hits = [{ t: enc + 0.12, kind: 'punch', amt: 0.6 }, { t: fans + 0.1, kind: 'punch', amt: 1 }, { t: fans + 0.1, kind: 'flash', amt: 0.5 }];
    for (let i = 0; i < M; i++) this.hitAt.push(fans + 0.1 + 0.45 + i * 0.04);
  }

  protected cam(t: number) {
    const enc = this.cue('encrypts', 1.3), once = this.cue('once', 1.71), fans = this.cue('fans', 2.67);
    return keyed(t, [
      { t: 0, pos: [-1.2, 1.9, 7.6], target: [-1.2, 1.3, 0], fov: 30 },
      { t: enc - 0.1, pos: [-2.1, 1.8, 5.4], target: [-2.4, 1.25, 0.4], fov: 30 },
      { t: enc + 0.35, pos: [-2.5, 1.65, 4.4], target: [-2.7, 1.2, 0.5], fov: 30, ease: ease.outExpo },
      { t: once + 0.45, pos: [-1.3, 2.4, 6.6], target: [-1.0, 1.75, 0], fov: 30 },
      { t: fans + 0.6, pos: [0.4, 4.0, 9.4], target: [0.3, 1.45, 0], fov: 30, ease: ease.outExpo },
      { t: this.len, pos: [0.7, 4.2, 9.0], target: [0.35, 1.45, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const grp = this.cue('group', 0.63), enc = this.cue('encrypts', 1.3), once = this.cue('once', 1.71), srv = this.cue('server', 2.33);
    const fans = this.cue('fans', 2.67), every = this.cue('everyone', 3.33);
    // phones
    const sk = spring(t, 0.02, 0.5, 0.08);
    this.snd.group.position.y = SND[1] - (1 - sk) * 0.6;
    this.snd.group.visible = sk > 0.01;
    this.snd.set({ on: 1, name: 'Family', status: '8 members', msgs: [{ text: 'dinner at 8!', mine: true, k: expo(t, 0.15, 0.25), lock: t > enc + 0.1, ticks: t > once + 0.5 ? 1 : 0 }] }, 1.2);
    this.members.forEach((p, i) => {
      const at = grp - 0.15 + i * 0.05;
      const k = spring(t, at, 0.45, 0.12);
      p.group.visible = k > 0.01;
      p.group.position.y = 0.5 - (1 - k) * 0.7;
      const land = this.hitAt[i]!;
      p.set({ on: 0.35 + 0.65 * expo(t, land, 0.15), name: 'Family', msgs: [{ text: 'dinner at 8!', k: expo(t, land, 0.2) }] }, 1.15 + 1.2 * Math.exp(-Math.max(0, t - land) * 5) * (t > land ? 1 : 0));
    });
    this.server.pose(t, 0.4 + 0.6 * expo(t, fans, 0.2));
    // the lock closes on "encrypts"; the sealed copy rides up on "once"
    const lk = antic(t, enc, { amt: 0.08, settle: 0.45, over: 0.12 });
    this.lock.group.scale.setScalar(Math.max(0.001, 0.5 * lk));
    this.lock.group.visible = lk > 0.01;
    this.lock.pose(1 - expo(t, enc + 0.12, 0.15));
    const scr = new THREE.Vector3(SND[0] + 0.12, 1.15, SND[2] + 0.35);
    const fly = ease.inOutCubic(win(t, once - 0.05, 0.5));
    const pkVisible = t > enc - 0.15 && t < once + 0.5;
    this.packet.visible = pkVisible;
    const ap = antic(t, enc - 0.15, { amt: 0.05, settle: 0.4, over: 0.1 });
    this.packet.scale.setScalar(Math.max(0.001, ap) * (1 - 0.35 * fly));
    this.packet.position.copy(fly > 0 ? this.up.getPointAt(fly) : scr);
    this.packet.lookAt(this.stage.camera.position);
    this.upBeam.pose(t, once - 0.1, 0.45, 1.1);
    this.upload.pose(t, once + 0.05, 'rise', expo(t, once, 0.2) * (1 - expo(t, fans, 0.2)));
    this.upload.group.lookAt(this.stage.camera.position);
    // the fan-out: beams split out from the server, streams run to every member
    this.fans.forEach((f, i) => {
      this.fanBeams[i]!.pose(t, fans + 0.1 + i * 0.03, 0.4, 1 + 0.3 * Math.sin(t * 9 + i) ** 2);
      f.pose(t, fans + 0.1 + i * 0.03);
    });
    // type
    this.l1.enter(t, [enc - 0.02, once], 'rise');
    this.l1.emphasis(t, once + 0.05, 1);
    this.l2.enter(t, [fans, this.cue('out', 3.0)], 'rise');
    this.l2.emphasis(t, this.cue('out', 3.0) + 0.05, 1.2);
    this.tag.pose(t, every, 'rise', expo(t, every - 0.05, 0.2));
    this.tag.group.lookAt(this.stage.camera.position);
    void srv;
    if (t < once + 0.3) return this.packet.visible ? this.packet.position.clone() : new THREE.Vector3(...SND);
    if (t < fans + 0.2) return new THREE.Vector3(SRV[0], 1.6, SRV[2]);
    return new THREE.Vector3(0.6, 1.4, 0);
  }

  override dispose() {
    this.bag.dispose();
    super.dispose();
  }
}
