// v3 Open Connect: the viewer's internet provider is a glowing platform with homes on it. At first, every stream crawls
// in from a far-away library across the open internet (sparse grey packets through a cloud). On "get them free" an
// Open Connect Appliance drops onto the platform ("FREE" slams beside it); on "inside their own networks" short, dense
// red streams run from the box to every home, the long haul fades, and the camera pushes in on the box.
// Facts (facts_netflix.json): OCAs are given free to qualifying ISPs and sit inside their networks.
import { Flow, accentSolid, spring, expo, smooth, win, antic, breathe, pulse } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, Cloud, House, ServerBox, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, type CamPose } from './lib';

const FOV = 30;
const PLAT = v(0.9, -0.62, -0.4);

export default class Oca extends MotionScene {
  private plat!: THREE.Group;
  private ringMat!: THREE.MeshBasicMaterial;
  private homes: House[] = [];
  private box!: ServerBox;
  private lib!: ServerBox;
  private cloud!: Cloud;
  private far: Flow[] = [];
  private near: Flow[] = [];
  private ispLabel!: Label;
  private boxLabel!: Label;
  private libLabel!: Label;
  private free!: KineticText;
  private slow!: Label;
  private homesAt: THREE.Vector3[] = [];

  protected build() {
    const s = this.stage.scene;
    this.defaults = { fstop: 1.8 };
    this.env = { floor: { y: -0.67, pool: 'accent2', poolK: 0.05, centre: [PLAT.x, PLAT.z], reach: 7 }, haze: { y: 0.5 } };
    const tGet = this.cue('get', 1.2), tFree = this.cue('free', 1.65), tIn = this.cue('inside', 2.3);
    this.hits = [{ t: tGet + 0.32, kind: 'shake', amt: 0.35 }, { t: tFree, kind: 'punch', amt: 1 }, { t: tFree, kind: 'flash', amt: 0.25 }];
    // the provider's platform: a low disc with an amber rim of light
    this.plat = new THREE.Group();
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.95, 2.0, 0.1, 96), surfaceMat('#120d0a', { rough: 0.9, coat: 0 }));
    this.ringMat = glowMat('accent2', 2.2);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.97, 0.012, 8, 160), this.ringMat);
    ring.rotation.x = Math.PI / 2; ring.position.y = 0.05;
    this.plat.add(disc, ring);
    this.plat.position.copy(PLAT);
    s.add(this.plat);
    // homes round the front and right of the platform
    const spots: [number, number][] = [[-1.2, 0.75], [0.1, 1.25], [1.35, 0.6], [1.15, -0.8]];
    spots.forEach(([x, z], i) => {
      const h = this.own(new House(0.62));
      h.group.position.set(PLAT.x + x, PLAT.y + 0.05 + 0.19, PLAT.z + z);
      h.group.rotation.y = -0.25 + i * 0.12;
      s.add(h.group);
      this.homes.push(h);
      this.homesAt.push(h.group.position.clone().add(v(0, 0.38, 0)));
    });
    // the appliance (it drops in on "get")
    this.box = this.own(new ServerBox(1.3, 0.26, 0.85, 3));
    s.add(this.box.group);
    // the far library: a tall red-lit rack, far back left
    this.lib = this.own(new ServerBox(1.6, 0.34, 1.0, 7));
    this.lib.group.position.set(-6.0, 0.3, -16);
    this.lib.group.rotation.y = 0.5;
    s.add(this.lib.group);
    this.cloud = this.own(new Cloud(1.25));
    this.cloud.group.position.set(-3.0, 1.0, -8.5);
    s.add(this.cloud.group);
    // the long haul: sparse, slow grey packets from the library through the cloud to each home
    const libTop = v(-5.4, 1.4, -15.4);
    this.homesAt.forEach((h, i) => {
      const c = new THREE.CatmullRomCurve3([libTop, v(-4.4, 1.9, -12.5), v(-3.0, 1.05 + i * 0.12, -8.5), v((h.x - 3.0) / 2, 1.1, (h.z - 8.5) / 2), h]);
      const f = this.own(new Flow(c, { rate: 3.5, speed: 2.4, radius: 0.026, length: 0.2, role: '#a89e92', hot: '#c8bdb0', k: 1.3, vary: 0.5, max: 40, seed: 3 + i }));
      this.far.push(f); s.add(f.mesh);
    });
    // the short hop: dense red streams from the box to each home
    const boxOut = v(PLAT.x, PLAT.y + 0.95, PLAT.z);
    this.homesAt.forEach((h, i) => {
      const m = boxOut.clone().add(h).multiplyScalar(0.5).add(v(0, 0.55, 0));
      const c = new THREE.QuadraticBezierCurve3(boxOut.clone(), m, h.clone());
      const f = this.own(new Flow(c, { rate: 16, speed: 3.2, radius: 0.026, length: 0.14, k: 5, hotShare: 0.35, spread: 0.03, max: 60, seed: 20 + i }));
      this.near.push(f); s.add(f.mesh);
    });
    // labels
    this.ispLabel = this.own(new Label('YOUR INTERNET PROVIDER', { size: emFor(40, 7, FOV), family: F.mono(500), role: 'accent2', k: 1.3, tracking: 0.06, align: 'right' }));
    this.ispLabel.group.position.set(PLAT.x - 1.95, PLAT.y + 0.45, PLAT.z + 1.0);
    this.ispLabel.group.rotation.y = 0.15;
    this.libLabel = this.own(new Label('Netflix library', { size: emFor(56, 18, FOV), role: 'fgDim' }));
    this.libLabel.group.position.set(-5.7, 2.5, -15.6);
    this.slow = this.own(new Label('far away · slow to start', { size: emFor(44, 8, FOV), family: F.mono(500), role: 'fgDim', tracking: 0.04 }));
    this.slow.group.position.set(-1.6, 0.35, -4.0);
    this.boxLabel = this.own(new Label('Open Connect Appliance', { size: emFor(56, 5.5, FOV) }));
    this.boxLabel.group.position.set(PLAT.x - 0.55, PLAT.y + 1.5, PLAT.z + 0.3);
    this.free = this.own(new KineticText('FREE', { size: emFor(150, 5.5, FOV), align: 'left', accentWords: [0], accentMat: accentSolid('accent', 1.5), depth: 0.24 }));
    this.free.group.position.set(PLAT.x + 0.8, PLAT.y + 1.45, PLAT.z + 0.5);
    this.free.group.rotation.y = -0.3;
    for (const l of [this.ispLabel.group, this.libLabel.group, this.slow.group, this.boxLabel.group, this.free.group]) s.add(l);
    this.frame({ centre: [0, -0.2, -1], w: 7, h: 4, dist: 8 });
  }

  protected cam(t: number): CamPose {
    // wide on the whole route, then a push and a swing onto the box after "inside"
    const tIn = this.cue('inside', 2.3);
    const k = smooth(t, tIn - 0.5, 1.9);
    const w = { pos: v(-0.4, 2.0, 8.4), tgt: v(-0.9, -0.55, -2.4) };
    const c = { pos: v(1.7, 1.1, 5.1), tgt: v(PLAT.x + 0.05, PLAT.y + 0.6, PLAT.z) };
    const drift = t * 0.06;
    const p = w.pos.clone().lerp(c.pos, k).add(v(drift, 0, -drift * 0.5)), g = w.tgt.clone().lerp(c.tgt, k);
    return { pos: [p.x, p.y, p.z], target: [g.x, g.y, g.z], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const tProv = this.cue('providers', 0.55), tGet = this.cue('get', 1.2), tFree = this.cue('free', 1.65), tIn = this.cue('inside', 2.3), tNet = this.cue('networks', 3.3);
    // platform and homes rise in on "Internet providers"
    const pk = spring(t, this.cue('internet', 0.1) - 0.05, 0.6, 0.06);
    this.plat.scale.set(Math.max(0.001, pk), 1, Math.max(0.001, pk));
    this.ringMat.color.copy(hdr('accent2', 2.2 * (1 + 1.2 * pulse(t, tProv, 0.05, 0.3) + 0.8 * pulse(t, tNet, 0.05, 0.4))));
    this.homes.forEach((h, i) => {
      const k = antic(t, tProv - 0.1 + i * 0.07, { amt: 0, settle: 0.45, over: 0.12 });
      h.group.scale.setScalar(Math.max(0.001, k));
      h.group.visible = k > 0.001;
      h.win.color.copy(hdr('accent2', 1.6 + 1.6 * win(t, tIn + 0.4 + i * 0.08, 0.2)));
    });
    this.ispLabel.pose(t, tProv + 0.1, 'rise');
    // the long haul, fading once the box serves
    const farA = 1 - win(t, tIn + 0.2, 0.7);
    this.far.forEach((f) => f.pose(t, -2.5, tIn + 0.2, farA > 0 ? 1 : 0));
    this.libLabel.pose(t, 0.25, 'rise', 1 - win(t, tIn + 0.3, 0.5));
    this.slow.pose(t, tProv + 0.35, 'type', 1 - win(t, tGet - 0.1, 0.3));
    this.lib.blink(t);
    // the box drops onto the platform with a little bounce
    const drop = expo(t, tGet, 0.3), land = spring(t, tGet + 0.28, 0.45, 0.15);
    const y0 = PLAT.y + 0.05 + 0.45 * 0.85;
    this.box.group.position.set(PLAT.x, t < tGet + 0.28 ? y0 + (1 - drop) * 3.2 : y0 + (1 - land) * -0.05, PLAT.z);
    this.box.group.scale.setScalar(0.85 * (t < tGet + 0.28 ? 1 : 1 + 0.06 * Math.sin(Math.min(1, (t - tGet - 0.28) / 0.25) * Math.PI) * (1 - land * 0.5)));
    this.box.group.rotation.y = -0.35 + 0.04 * breathe(t, 0.3);
    this.box.group.visible = t >= tGet - 0.02;
    this.box.blink(t, t > tIn);
    this.boxLabel.pose(t, tGet + 0.3, 'rise');
    this.free.enter(t, tFree, 'slam', 2 / 24);
    this.free.emphasis(t, tNet, 0.7);
    // the short hop, on "inside"
    this.near.forEach((f, i) => f.pose(t, tIn + i * 0.06, Infinity, 1, 1));
    return t < tIn ? v(-0.6, 0, -1.2) : v(PLAT.x, PLAT.y + 0.7, PLAT.z);
  }
}
