// Store and forward (W08-W09, 134 f): "Then it goes straight down their connection. If not, it waits. And once it's
// delivered, it's deleted."
// Sender phone, server, friend phone on a lit track. A message (a glowing 3D bubble with a light trail) shoots
// straight through to the online friend. "If not": the friend drops OFFLINE (amber), the next message parks in a slot
// over the server with an amber clock ring sweeping round it: WAITS. "Once it's delivered": the friend is back, the
// message shoots across (two ticks), and on "deleted" the server's copy shatters into sparks. The headline lands in two
// beats: "Delivered," then "then deleted".
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, Server, bubbleShape, extrude, Bag, hdr, GREEN, BONE } from './props';
import { Beam, KineticText, Label, expo, spring, win, glowMat } from '@kit/motion';
import { F } from '@engine/type';
import { ease, hash, clamp } from '@engine/util';

const SND: V3 = [-2.7, 0.82, 0.1];
const FRD: V3 = [2.7, 0.82, 0.1];
const SRV: V3 = [0, 0, -0.25];
const PARK: V3 = [0, 2.05, 0.35];
const AMBER = '#FFB547';
const TRAIL = 6;
const SHARDS = 70;

export default class Store extends WaShot {
  private bag = new Bag();
  private snd!: Phone;
  private frd!: Phone;
  private server!: Server;
  private toSrv!: THREE.CatmullRomCurve3;
  private toFrd!: THREE.CatmullRomCurve3;
  private beamA!: Beam;
  private beamB!: Beam;
  private msgs: { body: THREE.Mesh; trail: THREE.Mesh[] }[] = [];
  private ghost!: THREE.Mesh;
  private ghostMat!: THREE.MeshPhysicalMaterial;
  private shards!: THREE.InstancedMesh;
  private clock!: THREE.Mesh;
  private clockMat!: THREE.MeshBasicMaterial;
  private on!: Label;
  private off!: Label;
  private waits!: Label;
  private l1!: KineticText;
  private l2!: KineticText;

  protected build() {
    this.env = { floor: { y: 0, centre: [0, 0], reach: 8, poolK: 0.06 }, haze: { k2: 0.06 } };
    this.basePost = { ...this.basePost, bloom: 0.65 };
    const s = this.stage.scene;
    this.snd = this.own(new Phone());
    this.frd = this.own(new Phone());
    for (const [p, at, ry] of [[this.snd, SND, 0.4], [this.frd, FRD, -0.4]] as const) {
      p.group.position.set(...at);
      p.group.rotation.y = ry;
      p.group.scale.setScalar(1.05);
      s.add(p.group);
    }
    this.server = this.own(new Server(4));
    this.server.group.position.set(...SRV);
    s.add(this.server.group);
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.toSrv = new THREE.CatmullRomCurve3([v(SND[0] + 0.35, 1.15, 0.25), v(-1.35, 1.55, 0.55), v(0, 1.35, 0.7)]);
    this.toFrd = new THREE.CatmullRomCurve3([v(0, 1.35, 0.7), v(1.35, 1.55, 0.55), v(FRD[0] - 0.35, 1.15, 0.25)]);
    this.beamA = this.own(new Beam(this.toSrv, { radius: 0.01, k: 1.8 }));
    this.beamB = this.own(new Beam(this.toFrd, { radius: 0.01, k: 1.8 }));
    s.add(this.beamA.mesh, this.beamB.mesh);
    // two messages, each a glowing bubble with a trail of fading copies
    const geo = extrude(this.bag, bubbleShape(0.34, 0.24, 0.07), 0.06, 0.018);
    const body = new THREE.MeshPhysicalMaterial({ color: hdr(GREEN, 0.6), emissive: hdr(GREEN), emissiveIntensity: 2.4, roughness: 0.3, clearcoat: 1 });
    this.bag.own(body);
    for (let m = 0; m < 2; m++) {
      const b = new THREE.Mesh(geo, body);
      const trail: THREE.Mesh[] = [];
      for (let i = 0; i < TRAIL; i++) {
        const tm = this.bag.own(new THREE.MeshBasicMaterial({ color: hdr(GREEN, 2.2 * (1 - (i + 1) / (TRAIL + 1))), toneMapped: false }));
        const g = new THREE.Mesh(geo, tm);
        trail.push(g);
        s.add(g);
      }
      s.add(b);
      this.msgs.push({ body: b, trail });
    }
    // the server's copy (left behind in the slot) and its shards
    this.ghostMat = this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr(GREEN, 0.4), emissive: hdr(GREEN), emissiveIntensity: 1.2, roughness: 0.4, transparent: true }));
    this.ghost = new THREE.Mesh(geo, this.ghostMat);
    this.ghost.position.set(...PARK);
    s.add(this.ghost);
    this.shards = new THREE.InstancedMesh(this.bag.own(new THREE.BoxGeometry(0.03, 0.03, 0.03)), glowMat('accent', 4), SHARDS);
    this.shards.frustumCulled = false;
    s.add(this.shards);
    // the clock ring round the slot (draws on as the message waits)
    this.clockMat = glowMat(AMBER as `#${string}`, 3);
    this.clock = new THREE.Mesh(this.bag.own(new THREE.TorusGeometry(0.34, 0.012, 8, 96)), this.clockMat);
    this.clock.position.set(...PARK);
    s.add(this.clock);
    // labels
    const D = 6;
    this.on = this.own(new Label('ONLINE', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.3, tracking: 0.08 }));
    this.off = this.own(new Label('OFFLINE', { size: em(40, D), family: F.mono(500), role: AMBER as `#${string}`, k: 1.3, tracking: 0.08 }));
    for (const l of [this.on, this.off]) l.group.position.set(FRD[0] - 0.25, 1.95, FRD[2]);
    this.waits = this.own(new Label('WAITS', { size: em(60, 4.6), family: F.mono(500), role: AMBER as `#${string}`, k: 1.4, align: 'left', tracking: 0.08 }));
    this.waits.group.position.set(PARK[0] + 0.5, PARK[1] - 0.1, PARK[2]);
    const DH = 9.5;
    this.l1 = this.own(new KineticText('Delivered,', { size: em(84, DH), align: 'left', accentWords: [0] }));
    this.l2 = this.own(new KineticText('then deleted', { size: em(84, DH), align: 'left', accentWords: [1] }));
    {
      const gap = this.l1.size * 0.3, tot = this.l1.width + gap + this.l2.width;
      this.l1.group.position.set(-tot / 2, 3.0, 0.4);
      this.l2.group.position.set(-tot / 2 + this.l1.width + gap, 3.0, 0.4);
    }
    for (const k of [this.on, this.off, this.waits, this.l1, this.l2]) s.add(k.group);
    this.frame({ centre: [0, 1.2, 0], w: 7.5, h: 3.5 });
    const del = this.cue('deleted', 4.8), delv = this.cue('delivered', 4.12);
    this.hits = [{ t: del, kind: 'punch', amt: 1 }, { t: del, kind: 'flash', amt: 0.6 }, { t: delv + 0.25, kind: 'punch', amt: 0.4 }];
  }

  /** When each message runs: departs, reaches the server, leaves it, arrives. */
  private times() {
    const straight = this.cue('straight', 0.72), ifT = this.cue('if', 2.25), delv = this.cue('delivered', 4.12);
    return [
      { dep: straight - 0.2, srv: straight + 0.18, out: straight + 0.2, arr: straight + 0.62 },
      { dep: ifT + 0.05, srv: ifT + 0.5, out: delv - 0.1, arr: delv + 0.28 },
    ];
  }

  protected cam(t: number) {
    const straight = this.cue('straight', 0.72), ifT = this.cue('if', 2.25), waits = this.cue('waits', 3.0), delv = this.cue('delivered', 4.12), del = this.cue('deleted', 4.8);
    return keyed(t, [
      { t: 0, pos: [-3.4, 1.75, 5.6], target: [-2.1, 1.1, 0], fov: 30 },
      { t: straight + 0.7, pos: [1.6, 1.8, 6.4], target: [1.3, 1.15, 0], fov: 30 },
      { t: ifT + 0.35, pos: [0.4, 2.0, 7.6], target: [0.3, 1.35, 0], fov: 30 },
      { t: waits + 0.35, pos: [0.55, 2.35, 4.9], target: [0.35, 1.9, 0.3], fov: 30, ease: ease.outExpo },
      { t: delv - 0.15, pos: [0.65, 2.4, 4.6], target: [0.4, 1.9, 0.3], fov: 30 },
      { t: delv + 0.45, pos: [0.6, 2.3, 9.2], target: [0.25, 1.65, 0], fov: 30, ease: ease.outExpo },
      { t: del + 0.4, pos: [0.25, 2.4, 8.4], target: [0.1, 1.75, 0], fov: 30, ease: ease.outExpo },
      { t: this.len, pos: [0.1, 2.45, 8.1], target: [0.05, 1.8, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const ifT = this.cue('if', 2.25), waits = this.cue('waits', 3.0), once = this.cue('once', 3.75), delv = this.cue('delivered', 4.12), del = this.cue('deleted', 4.8);
    const T = this.times();
    // phones and server
    for (const [p, i] of [[this.snd, 0], [this.frd, 1]] as const) {
      const k = spring(t, 0.02 + i * 0.06, 0.5, 0.08);
      p.group.position.y = (i ? FRD : SND)[1] - (1 - k) * 0.6;
      p.group.visible = k > 0.01;
    }
    const offline = expo(t, ifT + 0.1, 0.15) * (1 - expo(t, once, 0.2));
    const tick = (m: number) => (t >= T[m]!.arr ? 2 : t >= T[m]!.srv ? 1 : 0);
    this.snd.set({ on: 1, name: 'Friend', status: offline > 0.5 ? 'last seen today' : 'online', msgs: [
      { text: 'on my way', mine: true, k: expo(t, T[0]!.dep - 0.25, 0.25), ticks: tick(0) },
      { text: 'see you at 8?', mine: true, k: expo(t, T[1]!.dep - 0.25, 0.25), ticks: tick(1) },
    ] }, 1.2);
    this.frd.set({ on: 1 - 0.85 * offline, name: 'You', status: offline > 0.5 ? 'offline' : 'online', msgs: [
      { text: 'on my way', k: expo(t, T[0]!.arr, 0.25) },
      { text: 'see you at 8?', k: expo(t, T[1]!.arr, 0.25) },
    ] }, 1.2 + 0.8 * Math.exp(-Math.max(0, t - T[0]!.arr) * 6) + 0.8 * Math.exp(-Math.max(0, t - T[1]!.arr) * 6));
    this.server.pose(t, 0.5 + 0.5 * Math.exp(-Math.abs(t - T[0]!.srv) * 4) + 0.5 * Math.exp(-Math.abs(t - T[1]!.srv) * 4));
    // off while the camera is in close on the slot (the friend's phone is at the frame's edge there)
    const close = expo(t, waits - 0.4, 0.2) * (1 - expo(t, delv - 0.2, 0.2));
    this.off.pose(t, ifT + 0.1, 'drop', offline * (1 - close));
    this.on.pose(t, 0.15, 'rise', expo(t, 0.15, 0.2) * (1 - offline) * (1 - close));
    // the links: sender's draws first, friend's goes dark while they're away
    this.beamA.pose(t, 0.05, 0.4, 1 + 0.3 * Math.sin(t * 7) ** 2);
    this.beamB.pose(t, 0.12, 0.4, (1 - 0.85 * offline) * (1 + 0.3 * Math.sin(t * 7 + 1) ** 2));
    // the messages
    const parkAt = new THREE.Vector3(...PARK);
    this.msgs.forEach((m, i) => {
      const tm = T[i]!;
      const posAt = (x: number): THREE.Vector3 | null => {
        if (x < tm.dep || x > tm.arr + 0.02) return null;
        if (x < tm.srv) return this.toSrv.getPointAt(ease.inOutQuad(win(x, tm.dep, tm.srv - tm.dep)));
        if (i === 1 && x < tm.out) {
          // up into the slot, and wait there, bobbing
          const k = ease.outBack(win(x, tm.srv, 0.35));
          return this.toSrv.getPointAt(1).lerp(parkAt, k).add(new THREE.Vector3(0, 0.03 * Math.sin(x * 5), 0));
        }
        if (i === 1 && x < tm.out + 0.12) return parkAt.clone().lerp(this.toFrd.getPointAt(0.12), ease.inCubic(win(x, tm.out, 0.12)));
        const from = i === 1 ? tm.out + 0.12 : tm.out;
        return this.toFrd.getPointAt(Math.min(1, (i === 1 ? 0.12 : 0) + ease.inOutQuad(win(x, from, tm.arr - from)) * (i === 1 ? 0.88 : 1)));
      };
      const p = posAt(t);
      m.body.visible = !!p;
      if (p) {
        m.body.position.copy(p);
        m.body.scale.setScalar(1 + 0.25 * Math.exp(-Math.max(0, t - tm.dep) * 8));
        m.body.lookAt(this.stage.camera.position);
      }
      m.trail.forEach((g, j) => {
        const q = posAt(t - (j + 1) * 0.022);
        g.visible = !!q && !!p && q.distanceTo(p) > 0.02;
        if (q) {
          g.position.copy(q);
          g.scale.setScalar(1 - (j + 1) * 0.11);
          g.quaternion.copy(m.body.quaternion);
        }
      });
    });
    // the slot: the clock ring sweeps while it waits, the copy stays behind and shatters on "deleted"
    const wait = T[1]!;
    const ca = expo(t, wait.srv + 0.2, 0.2) * (1 - expo(t, wait.out, 0.15));
    this.clock.visible = ca > 0.01;
    this.clock.scale.setScalar(0.85 + 0.15 * spring(t, wait.srv + 0.2, 0.5, 0.1));
    this.clock.rotation.z = -t * 2.2;
    this.clockMat.color.copy(hdr(AMBER, 3 * ca * (0.8 + 0.2 * Math.sin(t * 10))));
    this.clock.lookAt(this.stage.camera.position);
    this.waits.pose(t, waits, 'rise', expo(t, waits - 0.05, 0.2) * (1 - expo(t, wait.out, 0.15)));
    this.waits.group.lookAt(this.stage.camera.position);
    const gk = t >= wait.out && t < del ? 1 : 0;
    this.ghost.visible = gk > 0;
    this.ghost.lookAt(this.stage.camera.position);
    this.ghostMat.opacity = 0.75 + 0.25 * Math.sin(t * 8);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
    const sh = t - del;
    if (sh >= 0 && sh < 1) {
      for (let i = 0; i < SHARDS; i++) {
        const dir = new THREE.Vector3(hash(i, 1) - 0.5, hash(i, 2) - 0.3, hash(i, 3) - 0.5).normalize();
        const sp = 1.2 + 2.2 * hash(i, 4);
        const d = sp * (1 - Math.exp(-sh * 4)) / 4 * 4;
        const p = parkAt.clone().addScaledVector(dir, d * 0.6).add(new THREE.Vector3(0, -1.2 * sh * sh, 0));
        const sc = clamp(1 - sh / (0.4 + 0.5 * hash(i, 5))) * (0.6 + 0.8 * hash(i, 6));
        e.set(sh * 9 * hash(i, 7), sh * 7, 0);
        m4.compose(p, q.setFromEuler(e), new THREE.Vector3(sc, sc, sc));
        this.shards.setMatrixAt(i, m4);
      }
      this.shards.count = SHARDS;
      this.shards.visible = true;
      this.shards.instanceMatrix.needsUpdate = true;
    } else this.shards.visible = false;
    // the headline
    this.l1.enter(t, delv, 'rise');
    this.l1.emphasis(t, delv + 0.1, 0.8);
    this.l2.enter(t, [this.cue("it's", 4.6, 1) - 0.08, del], 'rise');
    this.l2.emphasis(t, del + 0.05, 1.3);
    if (t < T[0]!.arr) return this.msgs[0]!.body.visible ? this.msgs[0]!.body.position.clone() : new THREE.Vector3(...SND);
    if (t < delv + 0.2) return parkAt;
    return new THREE.Vector3(0, 2.3, 0.3);
  }

  override dispose() {
    this.bag.dispose();
    this.shards.dispose();
    super.dispose();
  }
}

void BONE;
