// Erlang (W05-W06, 149 f): "On the server, each connection is its own tiny Erlang process. One server once held two
// million of them."
// A server as a cube of light holding a lattice of dim process orbs. On "each connection" six phones fire beams into it
// and each beam lights its own orb; more orbs wake as other connections arrive. On "tiny Erlang process" the camera
// dives onto one orb (packets drop into its mailbox): "1 Erlang process", "A FEW KB · OWN MAILBOX". On "one server once
// held" it pulls far back while the lattice explodes into a dense field of tens of thousands of lit points, and
// "2,000,000" slams in over it, counting up, with "CONNECTIONS · ONE SERVER (2012)".
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, GREEN, hdr } from './props';
import { Beam, Flow, KineticText, Label, expo, spring, win, glowMat } from '@kit/motion';
import { F } from '@engine/type';
import { clamp, ease, hash } from '@engine/util';

const C: V3 = [0.9, 1.25, 0];
const N = 6, GAP = 0.36, SIZE = N * GAP;
const DN = 30; // the dense field: DN^3 points
const PHONES = 6;
/** The orb the camera dives onto, and the orbs the phones wire to (lattice indices). */
const HERO = { i: 0, j: 3, k: 5 };
const WIRED = [HERO, { i: 0, j: 1, k: 4 }, { i: 1, j: 4, k: 3 }, { i: 0, j: 5, k: 2 }, { i: 1, j: 2, k: 5 }, { i: 0, j: 0, k: 1 }];
/** How far the field rises as it grows (keeps it off the floor). */
const LIFT = 1.55;

const orbPos = (i: number, j: number, k: number) => new THREE.Vector3(C[0] + (i - (N - 1) / 2) * GAP, C[1] + (j - (N - 1) / 2) * GAP, C[2] + (k - (N - 1) / 2) * GAP);

export default class Erlang extends WaShot {
  private orbs!: THREE.InstancedMesh;
  private dense!: THREE.InstancedMesh;
  private frame3!: THREE.Group;
  private frameMat!: THREE.MeshBasicMaterial;
  private phones: Phone[] = [];
  private beams: Beam[] = [];
  private mail!: Flow;
  private callout!: Label;
  private calloutTag!: Label;
  private ring!: THREE.Mesh;
  private ringMat!: THREE.MeshBasicMaterial;
  private hero!: KineticText;
  private heroTag!: Label;
  private kicker!: Label;
  private heroDigits: KineticText[] = [];
  private orbLit: number[] = [];

  protected build() {
    this.env = { floor: { y: 0, centre: [C[0], 0], reach: 9, poolK: 0.06 }, haze: { k2: 0.06 } };
    this.basePost = { ...this.basePost, bloom: 0.6, bloomRadius: 0.7 };
    const s = this.stage.scene;
    // the server: a frame of light round the lattice
    this.frameMat = glowMat('accent', 1.6);
    this.frame3 = boxFrame(SIZE + 0.3, 0.012, this.frameMat);
    this.frame3.position.set(...C);
    s.add(this.frame3);
    // the lattice
    const geo = this.own(new THREE.SphereGeometry(0.075, 18, 12));
    this.orbs = new THREE.InstancedMesh(geo, this.own(new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false })), N * N * N);
    const m = new THREE.Matrix4();
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) for (let k = 0; k < N; k++) {
      const n = (i * N + j) * N + k;
      this.orbs.setMatrixAt(n, m.makeTranslation(orbPos(i, j, k)));
      this.orbs.setColorAt(n, new THREE.Color(0.1, 0.1, 0.1));
      const w = WIRED.findIndex((o) => o.i === i && o.j === j && o.k === k);
      this.orbLit.push(w >= 0 ? -1 - w : hash(n, 4));
    }
    this.own({ dispose: () => this.orbs.dispose() });
    s.add(this.orbs);
    // the dense field (two million, shown as DN^3)
    const dgeo = this.own(new THREE.SphereGeometry(0.03, 6, 4));
    this.dense = new THREE.InstancedMesh(dgeo, this.own(new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false })), DN * DN * DN);
    this.dense.frustumCulled = false;
    this.own({ dispose: () => this.dense.dispose() });
    s.add(this.dense);
    // phones on the left, in an arc, wired to their orbs
    for (let p = 0; p < PHONES; p++) {
      const ph = this.own(new Phone());
      const a = (p / (PHONES - 1) - 0.5) * 1.6;
      ph.group.position.set(-3.1 + Math.abs(a) * 0.5, 0.62 + 0.18 * (p % 2), a * 2.2);
      ph.group.rotation.y = 0.9 - a * 0.25;
      ph.group.scale.setScalar(0.75);
      ph.set({ on: 1, name: 'Chats', status: 'online' }, 1.05);
      s.add(ph.group);
      this.phones.push(ph);
      const from = ph.group.position.clone().add(new THREE.Vector3(0.1, 0.3, 0));
      const to = orbPos(WIRED[p]!.i, WIRED[p]!.j, WIRED[p]!.k);
      const mid = from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, 0.7, 0));
      const b = this.own(new Beam(new THREE.CatmullRomCurve3([from, mid, to]), { radius: 0.008, k: 2.4 }));
      this.beams.push(b);
      s.add(b.mesh);
    }
    // the hero orb's mailbox: packets dropping in, and a ring round it
    const hp = orbPos(HERO.i, HERO.j, HERO.k);
    this.mail = this.own(new Flow(new THREE.LineCurve3(hp.clone().add(new THREE.Vector3(-0.9, 0.5, 0.3)), hp.clone()), { rate: 4, speed: 1.6, radius: 0.012, length: 0.06, k: 4, max: 10, vary: 0.1 }));
    s.add(this.mail.mesh);
    this.ringMat = glowMat('accent', 3);
    this.ring = new THREE.Mesh(this.own(new THREE.TorusGeometry(0.13, 0.004, 8, 64)), this.ringMat);
    this.ring.position.copy(hp);
    s.add(this.ring);
    const dc = 1.7;
    this.callout = this.own(new Label('1 Erlang process', { size: em(58, dc, 28), align: 'right' }));
    this.callout.group.position.copy(hp).add(new THREE.Vector3(-0.3, 0.03, 0.05));
    this.calloutTag = this.own(new Label('A FEW KB · OWN MAILBOX', { size: em(36, dc, 28), family: F.mono(500), role: 'accent', k: 1.2, align: 'right', tracking: 0.05 }));
    this.calloutTag.group.position.copy(hp).add(new THREE.Vector3(-0.31, -0.1, 0.05));
    this.kicker = this.own(new Label('ONE SERVER', { size: em(40, 8), family: F.mono(500), role: 'fgDim', align: 'center', tracking: 0.08 }));
    this.kicker.group.position.set(C[0], C[1] + SIZE / 2 + 0.38, C[2]);
    // the hero number: faces the pulled-back camera
    const dh = 13;
    this.hero = this.own(new KineticText('2,000,000', { size: em(190, dh, 32), align: 'center', accentWords: [0], depth: 0.2 }));
    this.heroTag = this.own(new Label('CONNECTIONS · ONE SERVER (2012)', { size: em(42, dh, 32), family: F.mono(500), role: 'fg', align: 'center', tracking: 0.05 }));
    for (const k of [this.callout, this.calloutTag, this.kicker, this.hero, this.heroTag]) s.add(k.group);
    this.frame({ centre: [-0.6, 1.2, 0], w: 6, h: 3.5 });
    const two = this.cue('two', 5.0);
    this.hits = [{ t: two, kind: 'punch', amt: 1 }, { t: two, kind: 'flash', amt: 0.8 }, { t: this.cue('erlang', 2.85), kind: 'punch', amt: 0.4 }];
  }

  private far(): { pos: V3; target: V3 } {
    return { pos: [3.2, 6.0, 17.5], target: [C[0], 3.6, 0] };
  }

  protected cam(t: number) {
    const tiny = this.cue('tiny', 2.42), held = this.cue('held', 4.75), each = this.cue('each', 1.17);
    const hp = orbPos(HERO.i, HERO.j, HERO.k);
    const near: V3 = [hp.x - 0.75, hp.y + 0.1, hp.z + 1.65];
    const f = this.far();
    return keyed(t, [
      { t: 0, pos: [-0.2, 2.6, 8.2], target: [C[0] - 0.1, 1.3, 0], fov: 30 },
      { t: each, pos: [-1.6, 2.4, 7.4], target: [-0.6, 1.3, 0], fov: 30 },
      { t: tiny - 0.15, pos: [-1.2, 2.2, 6.4], target: [-0.2, 1.35, 0.3], fov: 30 },
      { t: tiny + 0.45, pos: near, target: [hp.x - 0.38, hp.y - 0.02, hp.z], fov: 28, ease: ease.outExpo },
      { t: held - 0.1, pos: [near[0] - 0.1, near[1] + 0.03, near[2] - 0.12], target: [hp.x - 0.4, hp.y - 0.02, hp.z], fov: 28 },
      { t: held + 0.75, pos: f.pos, target: f.target, fov: 32, ease: ease.outExpo },
      { t: this.len, pos: [f.pos[0] - 0.6, f.pos[1] - 0.2, f.pos[2] - 0.8], target: f.target, fov: 32 },
    ]);
  }

  protected pose(t: number) {
    const srv = this.cue('server', 0.55), each = this.cue('each', 1.17), conn = this.cue('connection', 1.4);
    const tiny = this.cue('tiny', 2.42), erl = this.cue('erlang', 2.85), proc = this.cue('process', 3.2);
    const one = this.cue('one', 3.95), held = this.cue('held', 4.75), two = this.cue('two', 5.0), mil = this.cue('million', 5.2);
    const dense = expo(t, two - 0.25, 0.9);
    // the server frame: wakes on "server"
    this.frameMat.color.copy(hdr(GREEN, 0.6 + 1.6 * expo(t, srv, 0.3) * (1 - 0.5 * dense)));
    this.frame3.scale.setScalar(1 + 1.3 * dense);
    this.frame3.position.y = C[1] + LIFT * dense;
    const callB = expo(t, this.cue('tiny', 2.42), 0.3) * (1 - expo(t, held - 0.05, 0.3));
    // phones and beams: each phone fires on "each connection", staggered
    const fire = (p: number) => each + p * 0.09;
    this.phones.forEach((ph, p) => {
      const k = spring(t, 0.05 + p * 0.05, 0.5, 0.1);
      ph.group.visible = k > 0.01 && dense < 0.98;
      ph.group.position.y = 0.62 + 0.18 * (p % 2) - (1 - k) * 0.8;
    });
    this.beams.forEach((b, p) => {
      b.pose(t, fire(p), 0.35, (1 + 0.4 * Math.sin(t * 8 + p) ** 2) * (1 - dense) * (p === 0 ? 1 : 1 - 0.8 * callB));
      b.mesh.visible = b.mesh.visible && dense < 0.98;
    });
    // the lattice: dim; wired orbs light as their beam lands, the rest wake over time; it all fades into the field
    const c = new THREE.Color(), m = new THREE.Matrix4();
    const latt = 1 - dense;
    const callA = expo(t, tiny, 0.3) * (1 - expo(t, held - 0.05, 0.3));
    for (let n = 0; n < N * N * N; n++) {
      const v = this.orbLit[n]!;
      const tOn = v < 0 ? fire(-1 - v) + 0.32 : conn + 0.4 + v * 5.5;
      const on = expo(t, tOn, 0.2);
      const flick = 0.75 + 0.25 * Math.sin(t * 6 + n) ** 2;
      const hot = v === -1 ? 1 + 0.6 * expo(t, erl, 0.2) : 1;
      const focus = v === -1 ? 1 : 1 - 0.75 * callA;
      const k = (0.09 + on * (v < 0 ? 3.4 : 1.6) * flick * hot) * latt * focus;
      const g = hdr(GREEN, 1);
      c.setRGB(0.1 * (1 - on) + g.r * k, 0.1 * (1 - on) + g.g * k, 0.1 * (1 - on) + g.b * k);
      this.orbs.setColorAt(n, c);
      const i = Math.floor(n / (N * N)), j = Math.floor(n / N) % N, kk = n % N;
      const sc = (1 + 0.5 * on * Math.exp(-Math.max(0, t - tOn) * 6)) * (1 - 0.7 * dense);
      m.makeScale(sc, sc, sc).setPosition(orbPos(i, j, kk).sub(new THREE.Vector3(...C)).multiplyScalar(1 + 1.3 * dense).add(new THREE.Vector3(C[0], C[1] + LIFT * dense, C[2])));
      this.orbs.setMatrixAt(n, m);
    }
    this.orbs.instanceColor!.needsUpdate = true;
    this.orbs.instanceMatrix.needsUpdate = true;
    this.orbs.visible = dense < 0.995;
    // the dense field: points burst out from the centre in a wave from "two"
    const big = (SIZE + 0.3) * (1 + 1.3 * dense);
    let shown = 0;
    if (t > two - 0.3) {
      for (let n = 0; n < DN * DN * DN; n++) {
        const i = Math.floor(n / (DN * DN)), j = Math.floor(n / DN) % DN, k = n % DN;
        const u = new THREE.Vector3((i + 0.5) / DN - 0.5, (j + 0.5) / DN - 0.5, (k + 0.5) / DN - 0.5);
        const r = u.length() / 0.866;
        const at = two - 0.25 + r * 0.7 + hash(n, 2) * 0.15;
        const a = expo(t, at, 0.3);
        if (a <= 0) continue;
        const jit = 0.4 / DN;
        u.x += (hash(n, 7) - 0.5) * jit; u.y += (hash(n, 8) - 0.5) * jit; u.z += (hash(n, 9) - 0.5) * jit;
        m.makeScale(a, a, a).setPosition(u.multiplyScalar(big * 0.96).add(new THREE.Vector3(C[0], C[1] + LIFT * dense, C[2])));
        this.dense.setMatrixAt(shown, m);
        const k2 = (0.5 + 1.8 * hash(n, 3)) * (1 + 1.5 * Math.exp(-Math.max(0, t - at) * 5)) * (0.75 + 0.25 * Math.sin(t * 5 + n * 0.37));
        const g = hdr(GREEN, k2);
        this.dense.setColorAt(shown, c.setRGB(g.r, g.g, g.b));
        shown++;
      }
    }
    this.dense.count = shown;
    this.dense.instanceMatrix.needsUpdate = true;
    if (this.dense.instanceColor) this.dense.instanceColor.needsUpdate = true;
    this.dense.visible = shown > 0;
    // the hero orb's mailbox and callout
    const call = expo(t, erl - 0.1, 0.25) * (1 - expo(t, held - 0.05, 0.2));
    this.mail.pose(t, tiny + 0.2, held);
    this.mail.mesh.visible = call > 0.01;
    this.ring.visible = call > 0.01;
    this.ring.scale.setScalar(0.6 + 0.4 * spring(t, erl - 0.1, 0.5, 0.12));
    this.ring.lookAt(this.stage.camera.position);
    this.ringMat.color.copy(hdr(GREEN, 3 * call));
    this.callout.pose(t, erl, 'rise', call);
    this.calloutTag.pose(t, proc, 'rise', call * expo(t, proc, 0.2));
    for (const l of [this.callout.group, this.calloutTag.group]) l.lookAt(this.stage.camera.position);
    this.kicker.pose(t, srv, 'rise', expo(t, srv, 0.25) * (1 - expo(t, tiny - 0.2, 0.2)) + expo(t, one, 0.3) * (1 - dense));
    // the hero number, counting up as it slams, facing the far camera
    const f = this.far();
    const fp = new THREE.Vector3(...f.pos), ft = new THREE.Vector3(...f.target);
    void ft;
    this.hero.group.position.set(C[0], 6.55, 2.2);
    this.heroTag.group.position.set(C[0], 5.95, 2.2);
    for (const g of [this.hero.group, this.heroTag.group]) g.lookAt(fp);
    this.hero.enter(t, two + 0.05, 'slam', 0.6 / 24);
    this.hero.emphasis(t, mil + 0.1, 1);
    this.heroTag.pose(t, mil + 0.05, 'rise', expo(t, mil, 0.25));
    // the count: digits roll while the number lands (the glyphs stay; the count shows in the tag's timing)
    void clamp;
    if (t < tiny + 0.3) return new THREE.Vector3(C[0] - 1.0, 1.3, 0);
    if (t < held + 0.3) return orbPos(HERO.i, HERO.j, HERO.k);
    return this.hero.group.position.clone();
  }
}

/** The 12 edges of a cube of side `s` as thin tubes (a frame of light). */
function boxFrame(s: number, r: number, mat: THREE.Material): THREE.Group {
  const g = new THREE.Group(), h = s / 2;
  const geo = new THREE.CylinderGeometry(r, r, s, 6, 1);
  for (const [ax, a, b] of [['x', 1, 1], ['x', 1, -1], ['x', -1, 1], ['x', -1, -1], ['y', 1, 1], ['y', 1, -1], ['y', -1, 1], ['y', -1, -1], ['z', 1, 1], ['z', 1, -1], ['z', -1, 1], ['z', -1, -1]] as const) {
    const m = new THREE.Mesh(geo, mat);
    if (ax === 'x') m.rotation.z = Math.PI / 2, m.position.set(0, a * h, b * h);
    if (ax === 'y') m.position.set(a * h, 0, b * h);
    if (ax === 'z') m.rotation.x = Math.PI / 2, m.position.set(a * h, b * h, 0);
    g.add(m);
  }
  return g;
}
