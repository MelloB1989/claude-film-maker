// Ticks (W10-W11, 155 f, panel): "Your ticks? One: the server has it. Two: it reached their phone. Blue: they've read
// it."
// A big sent bubble swings in on "ticks". Its ticks are solid 3D checks: the first slams in on "One", the second on
// "Two", and on "Blue" both turn blue in a glow wave. Under it each beat's heading flips in over the last ("One tick",
// "Two ticks", "Blue ticks") with its meaning, and a small route (you, server, friend) lights the leg it means.
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Bag, bubbleShape, tickShape, extrude, hdr, GREEN, BLUE } from './props';
import { Beam, KineticText, Label, antic, expo, spring, pulse, glowMat } from '@kit/motion';
import { RoundedBoxGeometry } from '@engine/three';
import { F } from '@engine/type';
import { Mat } from '@engine/type3d';

const D = 7.5;
const B: V3 = [0.05, 0.2, 0];
const BW = 2.3, BH = 0.86;

export default class Ticks extends WaShot {
  private bag = new Bag();
  private bubble!: THREE.Group;
  private ticks: THREE.Mesh[] = [];
  private tickMats: THREE.MeshPhysicalMaterial[] = [];
  private text!: Label;
  private heads: KineticText[] = [];
  private bodies: Label[] = [];
  private nodes: THREE.Mesh[] = [];
  private nodeMats: THREE.MeshPhysicalMaterial[] = [];
  private legs: Beam[] = [];
  private kicker!: Label;
  private blueMat!: THREE.MeshPhysicalMaterial;

  protected build() {
    this.env = this.panel ? this.env : { floor: { y: -1.25, centre: [0, 0], reach: 5, poolK: 0.06 }, haze: { k2: 0.06 } };
    const s = this.stage.scene;
    // the bubble: a dark green slab with a lit edge
    this.bubble = new THREE.Group();
    const body = new THREE.Mesh(extrude(this.bag, bubbleShape(BW, BH, 0.2), 0.12, 0.03), this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr('#0E6B47', 1), emissive: hdr('#0E6B47'), emissiveIntensity: 0.35, roughness: 0.35, clearcoat: 1, clearcoatRoughness: 0.15 })));
    this.bubble.add(body);
    this.text = this.own(new Label('see you at 8?', { size: em(58, D), align: 'left' }));
    this.text.group.position.set(-BW / 2 + 0.2, 0.0, 0.1);
    this.bubble.add(this.text.group);
    const tg = extrude(this.bag, tickShape(0.2), 0.08, 0.02);
    for (let i = 0; i < 2; i++) {
      const m = this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr('#D8D0C6', 1), emissive: hdr(BLUE), emissiveIntensity: 0, roughness: 0.3, clearcoat: 1 }));
      this.tickMats.push(m);
      const t = new THREE.Mesh(tg, m);
      t.scale.setScalar(0.26);
      t.position.set(BW / 2 - 0.5 + i * 0.13, -BH / 2 + 0.2, 0.1);
      this.ticks.push(t);
      this.bubble.add(t);
    }
    this.bubble.position.set(...B);
    s.add(this.bubble);
    // the beats' headings and meanings
    const heads = ['One tick', 'Two ticks', 'Blue ticks'];
    const bodies = ['the server has it', 'it reached their phone', "they've read it"];
    this.blueMat = Mat.accent('accent', 3);
    this.blueMat.emissive.copy(hdr(BLUE, 1));
    this.bag.own(this.blueMat);
    heads.forEach((h, i) => {
      const k = this.own(new KineticText(h, { size: em(64, D), align: 'center', accentWords: i === 2 ? [0] : [], accentMat: i === 2 ? this.blueMat : undefined }));
      k.group.position.set(0, -0.53, 0.1);
      this.heads.push(k);
      const b = this.own(new Label(bodies[i]!, { size: em(46, D), role: 'fgDim', align: 'center' }));
      b.group.position.set(0, -0.8, 0.1);
      this.bodies.push(b);
      s.add(k.group, b.group);
    });
    // the route: you, server, friend
    const ng = this.bag.own(new RoundedBoxGeometry(0.22, 0.32, 0.06, 3, 0.04));
    const sg = this.bag.own(new RoundedBoxGeometry(0.34, 0.26, 0.2, 3, 0.03));
    [-1.0, 0, 1.0].forEach((x, i) => {
      const m = this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr('#2A211B', 1), emissive: hdr(GREEN), emissiveIntensity: 0, roughness: 0.4, clearcoat: 0.8 }));
      const n = new THREE.Mesh(i === 1 ? sg : ng, m);
      n.position.set(x, -1.08, 0);
      this.nodes.push(n);
      this.nodeMats.push(m);
      s.add(n);
    });
    for (let i = 0; i < 2; i++) {
      const a = new THREE.Vector3(-1.0 + i + 0.17, -1.08, 0), b = new THREE.Vector3(i - 0.17 + 0.0 + (i === 0 ? -0.03 : 0.03) + (i === 0 ? 0 : 0) , -1.08, 0);
      b.x = i === 0 ? -0.2 : 0.83;
      const l = this.own(new Beam(new THREE.LineCurve3(a, b), { radius: 0.012, k: 3 }));
      this.legs.push(l);
      s.add(l.mesh);
    }
    this.kicker = this.own(new Label('READ RECEIPTS', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.2, align: 'left', tracking: 0.08 }));
    this.kicker.group.position.set(-1.42, 0.76, 0);
    s.add(this.kicker.group);
    this.frame({ centre: [0, 0, 0], w: 3.2, h: 2.4 });
    const one = this.cue('one', 1.33), two = this.cue('two', 3.0), blue = this.cue('blue', 4.92);
    this.hits = [{ t: one + 0.05, kind: 'punch', amt: 0.6 }, { t: two + 0.05, kind: 'punch', amt: 0.6 }, { t: blue + 0.05, kind: 'punch', amt: 0.9 }, { t: blue + 0.05, kind: 'flash', amt: 0.4 }];
  }

  protected cam(t: number) {
    const k = this.panel ? 1 : 0.85;
    const one = this.cue('one', 1.33), two = this.cue('two', 3.0), blue = this.cue('blue', 4.92);
    const z = (v: V3): V3 => [v[0] * k, v[1], v[2] * k];
    return keyed(t, [
      { t: 0, pos: z([-0.9, 0.45, D]), target: [0, -0.1, 0], fov: 30 },
      { t: one + 0.3, pos: z([-0.55, 0.35, D]), target: [0, -0.1, 0], fov: 30 },
      { t: two + 0.3, pos: z([0.2, 0.25, D]), target: [0, -0.1, 0], fov: 30 },
      { t: blue + 0.3, pos: z([0.65, 0.3, D - 0.15]), target: [0.02, -0.1, 0], fov: 30 },
      { t: this.len, pos: z([0.85, 0.25, D - 0.2]), target: [0.02, -0.1, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const ticks = this.cue('ticks', 0.65), one = this.cue('one', 1.33), srv = this.cue('server', 2.0), two = this.cue('two', 3.0);
    const reached = this.cue('reached', 3.83), blue = this.cue('blue', 4.92), read = this.cue('read', 5.79);
    // the bubble swings in on "ticks" and breathes
    const bk = antic(t, ticks - 0.1, { amt: 0.06, settle: 0.55, over: 0.1 });
    this.bubble.visible = t > ticks - 0.2;
    this.bubble.scale.setScalar(Math.max(0.001, 0.4 + 0.6 * bk));
    this.bubble.rotation.set(0.08 * (1 - bk) + 0.02 * Math.sin(t * 1.3), -0.22 + 0.5 * (1 - bk) + 0.03 * Math.sin(t * 0.9), -0.05 * (1 - bk));
    this.text.pose(t, ticks + 0.05, 'rise');
    // the ticks slam in, then go blue
    [one, two].forEach((at, i) => {
      const tk = this.ticks[i]!;
      const k = t < at ? 0 : t < at + 0.1 ? 2.4 - 1.4 * ((t - at) / 0.1) : 1 + 0.15 * (1 - spring(t, at + 0.1, 0.35, 0.15));
      tk.scale.setScalar(0.26 * k);
      tk.visible = k > 0;
      tk.position.z = 0.1 + (t < at + 0.1 && t >= at ? (1 - (t - at) / 0.1) * 0.6 : 0);
      const bl = expo(t, blue + i * 0.06, 0.2);
      const m = this.tickMats[i]!;
      m.color.copy(hdr('#D8D0C6', 1)).lerp(hdr(BLUE, 1), bl);
      m.emissiveIntensity = bl * (2.2 + 4 * pulse(t, blue + i * 0.06, 0.04, 0.2));
    });
    // headings and meanings: each flips in on its beat; the previous one leaves toward the lens
    const beats = [[one, srv], [two, reached], [blue, read]] as const;
    beats.forEach(([h, b], i) => {
      const next = beats[i + 1]?.[0];
      this.heads[i]!.enter(t, h + 0.02, 'flip');
      if (i === 2) this.heads[i]!.emphasis(t, h + 0.1, 1.2);
      if (next !== undefined) this.heads[i]!.exit(t, next - 0.12, 0.25);
      const ba = expo(t, b - 0.05, 0.2) * (next === undefined ? 1 : 1 - expo(t, next - 0.15, 0.12));
      this.bodies[i]!.pose(t, b - 0.05, 'rise', ba);
    });
    // the route
    const lit = [expo(t, one, 0.25), expo(t, Math.min(one + 0.25, srv), 0.25), expo(t, two + 0.2, 0.25)];
    this.nodes.forEach((n, i) => {
      const a = spring(t, 0.15 + i * 0.08, 0.5, 0.1);
      n.scale.setScalar(Math.max(0.001, a));
      n.visible = a > 0.01;
      const m = this.nodeMats[i]!;
      const on = i === 0 ? lit[0]! : i === 1 ? lit[1]! : lit[2]!;
      const isBlue = i === 2 ? expo(t, blue + 0.1, 0.2) : 0;
      m.emissive.copy(hdr(GREEN, 1)).lerp(hdr(BLUE, 1), isBlue);
      m.emissiveIntensity = 0.15 + on * 1.4 + isBlue * 1.2;
    });
    this.legs[0]!.pose(t, one, 0.3, 1 + 0.3 * Math.sin(t * 8) ** 2);
    this.legs[1]!.pose(t, two + 0.05, 0.3, 1 + 0.3 * Math.sin(t * 8 + 1) ** 2);
    this.kicker.pose(t, 0.12, 'rise');
    return new THREE.Vector3(B[0], B[1] - 0.1, 0.1);
  }

  override dispose() {
    this.bag.dispose();
    super.dispose();
  }
}

void glowMat;
