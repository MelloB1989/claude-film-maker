// Media (W15, 124 f, panel): "Photos go to a blob store, encrypted. Only the key rides in the message."
// A photo lifts off your phone on "photos" and arcs up to the blob store on "go to a blob store"; on "encrypted" it
// scrambles and a lock snaps on before it drops into the store. On "only the key rides in the message" a small bubble
// carrying a glowing key (KEY + LINK) runs along the chat link to your friend's phone; their phone then pulls the blob
// from the store (served via CDN) and the photo opens on their screen.
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, BlobStore, Key, Lock, Screen, Bag, bubbleShape, extrude, drawPhoto, hdr, GREEN } from './props';
import { Beam, Flow, Label, antic, expo, spring, win } from '@kit/motion';
import { RoundedBoxGeometry } from '@engine/three';
import { F } from '@engine/type';
import { ease } from '@engine/util';

const D = 7.5;
const SND: V3 = [-1.05, -0.42, 0.25];
const FRD: V3 = [0.2, -0.5, 0.25];
const BLOB: V3 = [1.0, -0.22, -0.3];

export default class Media extends WaShot {
  private bag = new Bag();
  private snd!: Phone;
  private frd!: Phone;
  private store!: BlobStore;
  private photo!: THREE.Group;
  private photoScr!: Screen;
  private photoMat!: THREE.MeshBasicMaterial;
  private lock!: Lock;
  private arc!: THREE.CatmullRomCurve3;
  private chat!: THREE.CatmullRomCurve3;
  private chatBeam!: Beam;
  private pull!: Flow;
  private pullBeam!: Beam;
  private msg!: THREE.Group;
  private key!: Key;
  private kicker!: Label;
  private blobL!: Label;
  private cdn!: Label;
  private pill!: Label;

  protected build() {
    this.env = this.panel ? this.env : { floor: { y: -1.1, centre: [0, 0], reach: 5, poolK: 0.06 }, haze: { k2: 0.06 } };
    const s = this.stage.scene;
    this.snd = this.own(new Phone());
    this.frd = this.own(new Phone());
    for (const [p, at, ry] of [[this.snd, SND, 0.35], [this.frd, FRD, -0.35]] as const) {
      p.group.position.set(...at);
      p.group.rotation.y = ry;
      p.group.scale.setScalar(0.8);
      s.add(p.group);
    }
    this.store = this.own(new BlobStore(GREEN));
    this.store.group.position.set(...BLOB);
    this.store.group.scale.setScalar(0.62);
    s.add(this.store.group);
    // the photo card
    this.photoScr = this.bag.own(new Screen(512, 384));
    this.photo = new THREE.Group();
    const back = new THREE.Mesh(this.bag.own(new RoundedBoxGeometry(0.62, 0.47, 0.03, 3, 0.03)), this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr('#F2ECE4', 0.9), roughness: 0.5, clearcoat: 0.6 })));
    this.photoMat = this.bag.own(new THREE.MeshBasicMaterial({ map: this.photoScr.tex, toneMapped: false }));
    const face = new THREE.Mesh(this.bag.own(new THREE.PlaneGeometry(0.56, 0.41)), this.photoMat);
    face.position.z = 0.017;
    this.photo.add(back, face);
    this.lock = this.own(new Lock('#FFB547'));
    this.lock.group.scale.setScalar(0.42);
    this.lock.group.position.set(0, 0, 0.12);
    this.photo.add(this.lock.group);
    s.add(this.photo);
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.arc = new THREE.CatmullRomCurve3([v(SND[0] + 0.05, SND[1] + 0.25, SND[2] + 0.25), v(-0.55, 0.45, 0.35), v(0.35, 0.55, 0.15), v(BLOB[0], 0.62, BLOB[2] + 0.1)]);
    // the chat link along the bottom, and the pull from the store to the friend
    this.chat = new THREE.CatmullRomCurve3([v(SND[0] + 0.3, SND[1] - 0.1, SND[2] + 0.1), v(-0.42, -0.95, 0.6), v(FRD[0] - 0.3, FRD[1] - 0.1, FRD[2] + 0.1)]);
    this.chatBeam = this.own(new Beam(this.chat, { radius: 0.008, k: 1.8 }));
    const pc = new THREE.CatmullRomCurve3([v(BLOB[0] - 0.3, 0.1, BLOB[2] + 0.4), v(0.65, 0.2, 0.3), v(FRD[0] + 0.15, FRD[1] + 0.45, FRD[2] + 0.12)]);
    this.pull = this.own(new Flow(pc, { rate: 22, speed: 2.6, radius: 0.018, length: 0.1, k: 3.5, hotShare: 0.4, max: 40, spread: 0.03 }));
    this.pullBeam = this.own(new Beam(pc, { radius: 0.006, k: 1.4 }));
    s.add(this.chatBeam.mesh, this.pull.mesh, this.pullBeam.mesh);
    // the message carrying the key
    this.msg = new THREE.Group();
    const bub = new THREE.Mesh(extrude(this.bag, bubbleShape(0.44, 0.3, 0.09), 0.06, 0.015), this.bag.own(new THREE.MeshPhysicalMaterial({ color: hdr('#0E6B47', 1), emissive: hdr(GREEN), emissiveIntensity: 0.5, roughness: 0.3, clearcoat: 1 })));
    this.msg.add(bub);
    this.key = this.own(new Key(GREEN, 2.2));
    this.key.group.scale.setScalar(0.3);
    this.key.group.position.set(0.0, 0.0, 0.07);
    this.key.group.rotation.z = 0.35;
    this.msg.add(this.key.group);
    s.add(this.msg);
    // labels
    this.kicker = this.own(new Label('PHOTOS & VIDEO', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.2, align: 'left', tracking: 0.08 }));
    this.kicker.group.position.set(-1.42, 0.76, 0);
    this.blobL = this.own(new Label('blob store', { size: em(48, D), role: 'fg', align: 'center' }));
    this.blobL.group.position.set(BLOB[0] + 0.05, 0.53, BLOB[2] + 0.1);
    this.cdn = this.own(new Label('SERVED VIA CDN', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.2, align: 'left', tracking: 0.08 }));
    this.cdn.group.position.set(-1.42, 0.76, 0);
    this.pill = this.own(new Label('KEY + LINK', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.3, align: 'center', tracking: 0.06 }));
    for (const k of [this.kicker, this.blobL, this.cdn, this.pill]) s.add(k.group);
    this.frame({ centre: [0, 0, 0], w: 3.2, h: 2.4 });
    const enc = this.cue('encrypted', 2.04), key = this.cue('key', 3.54);
    this.hits = [{ t: enc + 0.05, kind: 'punch', amt: 0.6 }, { t: key + 0.05, kind: 'punch', amt: 0.5 }];
  }

  private times() {
    const photos = this.cue('photos', 0.38), go = this.cue('go', 0.88), store = this.cue('store', 1.63), enc = this.cue('encrypted', 2.04);
    const only = this.cue('only', 3.13), msg = this.cue('message', 4.38);
    return { photos, go, store, enc, only, msg, drop: enc + 0.55, keyDep: only - 0.05, keyArr: msg - 0.05, pull: msg, open: msg + 0.55 };
  }

  protected cam(t: number) {
    const T = this.times();
    const k = this.panel ? 1 : 0.85;
    const z = (p: V3): V3 => [p[0] * k, p[1], p[2] * k];
    return keyed(t, [
      { t: 0, pos: z([-0.9, 0.45, D]), target: [0, -0.1, 0], fov: 30 },
      { t: T.enc - 0.1, pos: z([-0.35, 0.55, D]), target: [0.05, -0.08, 0], fov: 30 },
      { t: T.enc + 0.35, pos: z([0.05, 0.5, D - 0.2]), target: [0.08, -0.08, 0], fov: 30, ease: ease.outExpo },
      { t: this.len, pos: z([0.8, 0.25, D - 0.15]), target: [0.05, -0.1, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const T = this.times();
    for (const [p, i] of [[this.snd, 0], [this.frd, 1]] as const) {
      const k = spring(t, 0.12 + i * 0.08, 0.5, 0.08);
      p.group.visible = k > 0.01;
      p.group.position.y = (i ? FRD : SND)[1] - (1 - k) * 0.5;
    }
    const sk = spring(t, 0.2, 0.55, 0.1);
    this.store.group.visible = sk > 0.01;
    this.store.group.scale.setScalar(0.62 * Math.max(0.001, sk));
    this.store.pose(t, 0.3 + 0.7 * expo(t, T.drop, 0.15) * Math.exp(-Math.max(0, t - T.drop) * 2) + 0.5 * expo(t, T.pull, 0.2));
    // screens
    const opened = expo(t, T.open, 0.25);
    this.snd.set({ on: 1, name: 'Friend', status: 'online', msgs: [{ text: 'beach!', mine: true, k: 1, photo: 0, ticks: t > T.keyArr ? 2 : t > T.drop ? 1 : 0 }] }, 1.15);
    this.frd.set({ on: 1, name: 'You', status: 'online', msgs: t > T.keyArr ? [{ text: 'beach!', k: expo(t, T.keyArr, 0.2), photo: 1 - opened }] : [] }, 1.15 + 0.8 * opened * Math.exp(-Math.max(0, t - T.open) * 4));
    // the photo: lifts, flies, seals, drops in
    const lift = antic(t, T.photos, { amt: 0.06, settle: 0.45, over: 0.12 });
    const fly = ease.inOutCubic(win(t, T.go, T.store + 0.15 - T.go));
    const sealed = expo(t, T.enc, 0.3);
    const drop = ease.inCubic(win(t, T.drop, 0.3));
    this.photo.visible = t > T.photos - 0.12 && drop < 1;
    const p = this.arc.getPointAt(fly);
    p.y += (1 - fly) * lift * 0.15;
    this.photo.position.copy(p);
    if (drop > 0) this.photo.position.lerp(new THREE.Vector3(BLOB[0], 0.35, BLOB[2]), drop);
    this.photo.scale.setScalar(Math.max(0.001, (0.45 + 0.55 * lift) * (1 - 0.65 * drop)));
    this.photo.rotation.set(-0.15 + 0.15 * fly, 0.3 - 0.5 * fly + 0.05 * Math.sin(t * 2), 0.1 * Math.sin(fly * Math.PI));
    this.photoScr.draw((c, w, h) => drawPhoto(c, 0, 0, w, h, sealed));
    this.photoMat.color.setScalar(1.1 + 0.6 * Math.exp(-Math.max(0, t - T.enc) * 6) * (t > T.enc ? 1 : 0));
    const lk = antic(t, T.enc + 0.1, { amt: 0.1, settle: 0.4, over: 0.15 });
    this.lock.group.visible = lk > 0.01;
    this.lock.group.scale.setScalar(0.42 * Math.max(0.001, lk));
    this.lock.pose(1 - expo(t, T.enc + 0.25, 0.12));
    // the key rides in the message
    this.chatBeam.pose(t, 0.25, 0.4, 1 + 0.3 * Math.sin(t * 8) ** 2);
    const run = ease.inOutCubic(win(t, T.keyDep, T.keyArr - T.keyDep));
    const ma = antic(t, T.keyDep - 0.15, { amt: 0.08, settle: 0.4, over: 0.12 });
    this.msg.visible = t > T.keyDep - 0.2 && t < T.keyArr + 0.2;
    const mp = this.chat.getPointAt(run).add(new THREE.Vector3(0, 0.22, 0.05));
    this.msg.position.copy(mp);
    this.msg.scale.setScalar(Math.max(0.001, ma) * (1 - ease.inCubic(win(t, T.keyArr, 0.2))));
    this.msg.lookAt(this.stage.camera.position);
    this.key.mat.emissiveIntensity = 2.2 + 1.2 * Math.sin(t * 9) ** 2;
    this.pill.group.position.copy(mp).add(new THREE.Vector3(0, 0.26, 0));
    this.pill.pose(t, this.cue('key', 3.54), 'rise', expo(t, this.cue('key', 3.54) - 0.05, 0.2) * (1 - expo(t, T.keyArr, 0.15)));
    // the friend pulls the blob
    this.pullBeam.pose(t, T.pull, 0.3, 1);
    this.pull.pose(t, T.pull + 0.05, T.open + 0.1);
    // labels
    this.kicker.pose(t, 0.12, 'rise', 1 - expo(t, T.pull - 0.1, 0.15));
    this.blobL.pose(t, this.cue('blob', 1.3), 'rise', expo(t, this.cue('blob', 1.3) - 0.05, 0.2));
    this.cdn.pose(t, T.pull, 'rise', expo(t, T.pull - 0.05, 0.2));
    if (t < T.drop + 0.2) return this.photo.position.clone();
    if (t < T.keyArr) return this.msg.position.clone();
    return new THREE.Vector3(FRD[0] - 0.2, FRD[1] + 0.3, FRD[2]);
  }

  override dispose() {
    this.bag.dispose();
    super.dispose();
  }
}

void Key;
