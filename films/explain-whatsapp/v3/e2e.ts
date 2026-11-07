// End to end (W14, 68 f): "The Signal protocol keeps the keys on your phones."
// Two phones talk through a server set back between them; the stream that passes through it reads only as scrambled
// ciphertext (the server sees only ciphertext). "Signal protocol" rises on the words with ON BY DEFAULT SINCE 2016;
// on "keys" a key drops onto each phone and docks there with a hit, and on "phones" both pulse.
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, Server, Key, GREEN } from './props';
import { Beam, Flow, KineticText, Label, antic, expo, pulse } from '@kit/motion';
import { F } from '@engine/type';
import { ease, hash } from '@engine/util';

const L: V3 = [-2.35, 0.85, 0.3];
const R: V3 = [2.35, 0.85, 0.3];
const SRV: V3 = [0, 0, -1.6];
const GARBLE = ['x9#Qf2@kL7!vZ', 'Pz!8u$Wq1#cN4', 'm3&Rk9^tB0%yE', 'G#7wq2!Lz8@sV'];

export default class E2E extends WaShot {
  private a!: Phone;
  private b!: Phone;
  private server!: Server;
  private beams: Beam[] = [];
  private flows: Flow[] = [];
  private keys: Key[] = [];
  private garble: Label[] = [];
  private seen!: Label;
  private l1!: KineticText;
  private tag!: Label;

  protected build() {
    this.env = { floor: { y: 0, centre: [0, 0], reach: 7, poolK: 0.06 }, haze: { k2: 0.06 } };
    const s = this.stage.scene;
    this.a = this.own(new Phone());
    this.b = this.own(new Phone());
    for (const [p, at, ry] of [[this.a, L, 0.5], [this.b, R, -0.5]] as const) {
      p.group.position.set(...at);
      p.group.rotation.y = ry;
      p.group.scale.setScalar(1.08);
      s.add(p.group);
    }
    this.server = this.own(new Server(3));
    this.server.group.position.set(...SRV);
    this.server.group.scale.setScalar(0.85);
    s.add(this.server.group);
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const mid = v(0, 1.05, SRV[2] + 0.5);
    const c1 = new THREE.CatmullRomCurve3([v(L[0] + 0.35, 1.05, L[2] + 0.1), v(-1.2, 1.35, -0.6), mid, v(1.2, 1.35, -0.6), v(R[0] - 0.35, 1.05, R[2] + 0.1)]);
    const c2 = new THREE.CatmullRomCurve3([...c1.points].reverse());
    for (const [c, seed] of [[c1, 2], [c2, 7]] as const) {
      const f = this.own(new Flow(c, { rate: 7, speed: 3.6, radius: 0.02, length: 0.14, k: 3.2, hotShare: 0.3, max: 30, seed }));
      this.flows.push(f);
      s.add(f.mesh);
    }
    const bm = this.own(new Beam(c1, { radius: 0.007, k: 1.5 }));
    this.beams.push(bm);
    s.add(bm.mesh);
    const DS = 7.4;
    for (const g of GARBLE) {
      const l = this.own(new Label(g, { size: em(40, DS), family: F.mono(500), role: 'accent', k: 1.1, tracking: 0.04 }));
      l.group.position.set(0, 1.62, SRV[2] + 0.55);
      this.garble.push(l);
      s.add(l.group);
    }
    this.seen = this.own(new Label('server sees only ciphertext', { size: em(42, DS), role: 'fgDim' }));
    this.seen.group.position.set(0, 2.02, SRV[2] + 0.55);
    s.add(this.seen.group);
    for (let i = 0; i < 2; i++) {
      const k = this.own(new Key(GREEN, 1.6));
      k.group.scale.setScalar(0.7);
      this.keys.push(k);
      s.add(k.group);
    }
    const D = 7.4;
    this.l1 = this.own(new KineticText('Signal protocol', { size: em(96, D), align: 'center', accentWords: [0] }));
    this.l1.group.position.set(0, 2.78, 0.4);
    this.tag = this.own(new Label('END-TO-END · ON BY DEFAULT SINCE 2016', { size: em(40, D), family: F.mono(500), role: 'fg', tracking: 0.05 }));
    this.tag.group.position.set(0, 2.38, 0.4);
    s.add(this.l1.group, this.tag.group);
    this.frame({ centre: [0, 1.4, 0], w: 6.4, h: 3.4 });
    const keys = this.cue('keys', 1.6);
    this.hits = [{ t: keys + 0.25, kind: 'punch', amt: 0.9 }, { t: this.cue('signal', 0.38), kind: 'punch', amt: 0.4 }];
  }

  protected cam(t: number) {
    const keys = this.cue('keys', 1.6);
    return keyed(t, [
      { t: 0, pos: [-0.6, 2.0, 8.0], target: [0, 1.5, 0], fov: 30 },
      { t: keys, pos: [-0.2, 1.95, 7.4], target: [0, 1.45, 0], fov: 30 },
      { t: keys + 0.45, pos: [0.25, 1.95, 7.1], target: [0, 1.58, 0], fov: 30, ease: ease.outExpo },
      { t: this.len, pos: [0.45, 1.95, 6.95], target: [0, 1.58, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const sig = this.cue('signal', 0.38), proto = this.cue('protocol', 0.71), keeps = this.cue('keeps', 1.2), keys = this.cue('keys', 1.6), phones = this.cue('phones', 2.1);
    for (const [p, i] of [[this.a, 0], [this.b, 1]] as const) {
      const k = antic(t, 0.03 + i * 0.05, { amt: 0.05, settle: 0.45, over: 0.08 });
      p.group.position.y = (i ? R : L)[1] - (1 - k) * 0.6;
      p.group.visible = k > -0.5 && t > 0.0;
      const docked = expo(t, keys + 0.22, 0.15);
      p.set({ on: 1, name: i ? 'You' : 'Friend', status: 'online', msgs: [{ text: i ? 'got it' : 'the code is 4471', mine: !i, lock: true, k: expo(t, 0.1 + i * 0.25, 0.25), ticks: 2 }] }, 1.15 + 0.9 * docked * pulse(t, keys + 0.22, 0.03, 0.2) + 0.6 * pulse(t, phones, 0.04, 0.2));
    }
    this.server.pose(t, 0.4);
    this.beams[0]!.pose(t, 0.05, 0.45, 0.8);
    this.flows[0]!.pose(t, -2);
    this.flows[1]!.pose(t, -2);
    // the ciphertext over the server: a scramble that changes every 3 frames
    const fr = Math.floor(t * 24 / 3);
    const ga = expo(t, 0.15, 0.25);
    this.garble.forEach((l, i) => l.pose(t, 0.15, 'type', i === fr % GARBLE.length ? ga : 0));
    this.seen.pose(t, keeps - 0.25, 'rise', expo(t, keeps - 0.25, 0.2));
    // the keys drop onto the phones
    this.keys.forEach((k, i) => {
      const at = keys + i * 0.06;
      const ph = i ? R : L;
      const land = new THREE.Vector3(ph[0] + (i ? -0.08 : 0.08), ph[1] + 0.95, ph[2] + 0.25);
      const x = (t - (at - 0.25)) / 0.3;
      const k1 = ease.inCubic(Math.min(1, Math.max(0, x)));
      k.group.visible = t > at - 0.25;
      k.group.position.copy(land).add(new THREE.Vector3(0, (1 - k1) * 2.2, (1 - k1) * 0.6));
      const settle = antic(t, at + 0.05, { antic: 0.02, amt: 0.0, settle: 0.4, over: 0.2 });
      k.group.rotation.set(0, (1 - k1) * 3 + (i ? Math.PI : 0), (i ? 1 : -1) * (0.25 + 0.1 * (1 - settle)));
      k.group.scale.setScalar(0.7 * (1 + 0.25 * pulse(t, phones + 0.05, 0.04, 0.15)));
      k.mat.emissiveIntensity = 1.6 + 3 * pulse(t, at + 0.05, 0.03, 0.15) + 2 * pulse(t, phones + 0.05, 0.04, 0.2);
    });
    // type
    this.l1.enter(t, [sig, proto], 'rise');
    this.l1.emphasis(t, sig + 0.1, 1);
    this.tag.pose(t, proto + 0.15, 'rise', expo(t, proto + 0.1, 0.2));
    void hash;
    return t < keys ? new THREE.Vector3(0, 2.3, 0.4) : new THREE.Vector3(0, 1.5, 0.3);
  }
}
