// Title (W02, 59 f): "And almost none of them stay on its servers."
// A river of messages pours through a server tower and out the other side: none of it stays. "100+ billion" rises
// on the cut over the stream with its tag; on "none" it flies off through the lens, and on "stay" a big accent 0
// slams onto the server: STORED ON SERVER 0, then "delivered, then deleted".
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Server, GREEN } from './props';
import { Flow, KineticText, Label, expo } from '@kit/motion';
import { F } from '@engine/type';
import { ease } from '@engine/util';

const SRV: V3 = [1.55, 0, -0.2];

export default class Title extends WaShot {
  private server!: Server;
  private stream!: Flow;
  private stream2!: Flow;
  private hero!: KineticText;
  private tag!: Label;
  private zero!: KineticText;
  private zTag!: Label;
  private zSub!: Label;

  protected build() {
    this.env = { floor: { y: 0, centre: [SRV[0], SRV[2]], reach: 7, poolK: 0.08 }, haze: { y: 1, z: -14, k2: 0.07 } };
    this.basePost = { ...this.basePost, bloom: 0.55, bloomRadius: 0.7 };
    const s = this.stage.scene;
    this.server = this.own(new Server(5));
    this.server.group.position.set(...SRV);
    this.server.group.rotation.y = -0.38;
    s.add(this.server.group);
    // the river: in from deep left, through the tower, out toward the right front
    const path = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-10, 0.5, -7), new THREE.Vector3(-3.5, 0.75, -2.6), new THREE.Vector3(SRV[0], 0.95, SRV[2]),
      new THREE.Vector3(4.2, 0.85, 1.6), new THREE.Vector3(9, 0.8, 4),
    ]);
    this.stream = this.own(new Flow(path, { rate: 46, speed: 7.5, radius: 0.02, length: 0.22, spread: 0.3, max: 200, k: 2.6, hotShare: 0.2, seed: 3 }));
    this.stream2 = this.own(new Flow(path, { rate: 22, speed: 5.5, radius: 0.012, length: 0.12, spread: 0.55, max: 100, k: 1.8, hotShare: 0.05, seed: 9 }));
    s.add(this.stream.mesh, this.stream2.mesh);
    // type: the headline over the stream, left third
    const D = 7.2;
    this.hero = this.own(new KineticText('100+ billion', { size: em(118, D), accentWords: [0], align: 'left' }));
    this.hero.group.position.set(-2.75, 2.25, 0.2);
    this.tag = this.own(new Label('MESSAGES A DAY', { size: em(42, D), family: F.mono(500), role: 'fgDim', align: 'left', tracking: 0.06 }));
    this.tag.group.position.set(-2.7, 1.78, 0.2);
    // the 0 on the server
    this.zero = this.own(new KineticText('0', { size: em(340, 6), accentWords: [0], align: 'left', depth: 0.22 }));
    this.zero.group.position.set(-1.8, 1.0, 0.3);
    this.zTag = this.own(new Label('STORED ON SERVER', { size: em(40, 6), family: F.mono(500), role: 'fgDim', tracking: 0.06, align: 'left' }));
    this.zTag.group.position.set(-1.72, 2.2, 0.3);
    this.zSub = this.own(new Label('delivered, then deleted', { size: em(56, 6), role: 'fg', align: 'left' }));
    this.zSub.group.position.set(-1.72, 0.5, 0.3);
    for (const x of [this.hero, this.tag, this.zero, this.zTag, this.zSub]) s.add(x.group);
    this.frame({ centre: [0.3, 1.2, 0], w: 6.6, h: 3.4 });
    this.hits = [{ t: this.cue('stay', 1.42), kind: 'punch' }, { t: this.cue('stay', 1.42), kind: 'flash', amt: 0.7 }];
  }

  protected cam(t: number) {
    const stay = this.cue('stay', 1.42);
    return keyed(t, [
      { t: 0, pos: [-1.2, 2.1, 7.8], target: [-0.4, 1.35, 0], fov: 30 },
      { t: stay - 0.25, pos: [-0.7, 1.9, 7.2], target: [-0.1, 1.3, 0], fov: 30 },
      { t: stay + 0.35, pos: [0.3, 1.6, 6.3], target: [0.55, 1.25, 0], fov: 30, ease: ease.outExpo },
      { t: this.len, pos: [0.45, 1.55, 6.0], target: [0.6, 1.25, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const none = this.cue('none', 1.0), stay = this.cue('stay', 1.42), servers = this.cue('servers', 1.9);
    this.server.pose(t, 0.9);
    this.stream.pose(t, -3);
    this.stream2.pose(t, -3);
    // the server barely notices: messages pass straight through
    this.hero.enter(t, 0.04, 'rise');
    this.hero.emphasis(t, 0.32, 1);
    this.tag.pose(t, 0.2, 'rise');
    this.hero.exit(t, none - 0.02, 0.32);
    this.tag.pose(t, 0.2, 'rise', 1 - expo(t, none, 0.25));
    this.zTag.pose(t, stay - 0.1, 'rise', expo(t, stay - 0.1, 0.2));
    this.zero.enter(t, stay, 'slam');
    this.zero.emphasis(t, stay + 0.1, 1.2);
    this.zSub.pose(t, servers + 0.05, 'rise', expo(t, servers, 0.2));
    return t < stay - 0.1 ? new THREE.Vector3(-1.6, 2.0, 0.2) : new THREE.Vector3(-1.2, 1.2, 0.3);
  }
}

void GREEN;
