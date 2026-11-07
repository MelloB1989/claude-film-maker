// Connect (W04, 94 f, panel): "Open the app, and your phone keeps one connection open to WhatsApp."
// The phone swings up and its screen wakes on "open"; on "connection" a beam of light arcs from the phone to the chat
// server and stays live: heartbeat packets run both ways for the rest of the shot. The headline lands in two beats:
// "One connection," on "one", "always open" on "open".
import { WaShot, THREE, keyed, em, type V3 } from './base';
import { Phone, Server } from './props';
import { Beam, Flow, KineticText, Label, antic, expo, spring, breathe } from '@kit/motion';
import { F } from '@engine/type';

const D = 7.5;
const PH: V3 = [-0.92, -0.5, 0.25];
const SV: V3 = [0.9, -1.12, -0.3];

export default class Connect extends WaShot {
  private phone!: Phone;
  private server!: Server;
  private beam!: Beam;
  private up!: Flow;
  private down!: Flow;
  private kicker!: Label;
  private l1!: KineticText;
  private l2!: KineticText;
  private srvLabel!: Label;

  protected build() {
    this.env = this.panel ? this.env : { floor: { y: SV[1], centre: [0, 0], reach: 5, poolK: 0.08 }, haze: { k2: 0.07 } };
    const s = this.stage.scene;
    this.phone = this.own(new Phone());
    this.phone.group.position.set(...PH);
    this.phone.group.scale.setScalar(0.8);
    this.server = this.own(new Server(3));
    this.server.group.position.set(...SV);
    this.server.group.rotation.y = -0.5;
    this.server.group.scale.setScalar(0.72);
    s.add(this.phone.group, this.server.group);
    const a = new THREE.Vector3(PH[0] + 0.27, PH[1] + 0.2, PH[2] + 0.05), b = new THREE.Vector3(SV[0] - 0.2, SV[1] + 0.55, SV[2] + 0.35);
    const mid = a.clone().lerp(b, 0.5).add(new THREE.Vector3(0, 0.38, 0.25));
    const path = new THREE.QuadraticBezierCurve3(a, mid, b);
    this.beam = this.own(new Beam(path, { radius: 0.014, k: 3 }));
    const back = new THREE.QuadraticBezierCurve3(b.clone(), mid.clone(), a.clone());
    this.up = this.own(new Flow(path, { rate: 3.2, speed: 2.6, radius: 0.035, length: 0.22, k: 4, hotShare: 0.6, vary: 0.05, max: 12, seed: 2 }));
    this.down = this.own(new Flow(back, { rate: 2.2, speed: 2.4, radius: 0.03, length: 0.18, k: 3.5, hotShare: 0.3, vary: 0.05, max: 10, seed: 5 }));
    s.add(this.beam.mesh, this.up.mesh, this.down.mesh);
    const x0 = -1.42;
    this.kicker = this.own(new Label('ALWAYS-ON LINK', { size: em(40, D), family: F.mono(500), role: 'accent', k: 1.2, align: 'left', tracking: 0.06 }));
    this.kicker.group.position.set(x0, 0.7, 0);
    this.l1 = this.own(new KineticText('One connection,', { size: em(64, D), align: 'left', accentWords: [0] }));
    this.l1.group.position.set(x0, 0.33, 0);
    this.l2 = this.own(new KineticText('always open', { size: em(64, D), align: 'left', accentWords: [1] }));
    this.l2.group.position.set(x0, 0.01, 0);
    this.srvLabel = this.own(new Label('server', { size: em(44, D), role: 'fgDim', align: 'center' }));
    this.srvLabel.group.position.set(SV[0] + 0.12, SV[1] + 0.86, SV[2] + 0.3);
    for (const k of [this.kicker, this.l1, this.l2, this.srvLabel]) s.add(k.group);
    this.frame({ centre: [0, -0.2, 0], w: 3.2, h: 2.4 });
    const conn = this.cue('connection', 2.5);
    this.hits = [{ t: conn + 0.35, kind: 'punch', amt: 0.6 }];
  }

  protected cam(t: number) {
    const k = this.panel ? 1 : 0.82, conn = this.cue('connection', 2.5);
    const z = (v: V3): V3 => [v[0] * k, v[1], v[2] * k];
    return keyed(t, [
      { t: 0, pos: z([-0.9, 0.45, D]), target: [-0.05, -0.12, 0], fov: 30 },
      { t: conn - 0.1, pos: z([-0.4, 0.35, D - 0.1]), target: [-0.05, -0.12, 0], fov: 30 },
      { t: conn + 0.45, pos: z([0.35, 0.22, D - 0.55]), target: [0.0, -0.14, 0], fov: 30, ease: (x: number) => 1 - Math.pow(2, -10 * x) },
      { t: this.len, pos: z([0.75, 0.15, D - 0.7]), target: [0.05, -0.15, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    const open = this.cue('open', 0.4), conn = this.cue('connection', 2.5), one = this.cue('one', 2.3), open2 = this.cue('open', 2.95, 1);
    const wa = this.cue('whatsapp', 3.3);
    // the phone: swings up into place, wakes on "open"
    const pk = antic(t, 0.14, { amt: 0.05, settle: 0.6, over: 0.08 });
    const g = this.phone.group;
    g.visible = t >= 0.04;
    this.server.group.visible = t >= 0.12;
    g.position.set(PH[0], PH[1] - (1 - pk) * 0.6, PH[2]);
    g.rotation.set(-0.15 * (1 - pk) + 0.02 * breathe(t, 0.4), 0.45 - 0.2 * pk + 0.03 * breathe(t, 0.3, 1), 0.06 * (1 - pk));
    const on = expo(t, open, 0.25);
    this.phone.set({ on, name: 'Chats', status: t > conn + 0.3 ? 'connected' : 'connecting…', msgs: [
      { text: 'you up?', k: expo(t, conn + 0.75, 0.3) },
      { text: 'call later?', k: expo(t, conn + 1.35, 0.3) },
    ] }, 1.25 + 0.6 * Math.exp(-Math.max(0, t - open) * 5));
    // the server: lands early, wakes harder when the connection arrives
    const sk = spring(t, 0.22, 0.6, 0.08);
    this.server.group.position.y = SV[1] - (1 - sk) * 0.5;
    this.server.pose(t, 0.25 + 0.75 * expo(t, conn + 0.3, 0.3));
    this.srvLabel.pose(t, wa - 0.1, 'rise', expo(t, wa - 0.1, 0.25));
    // the beam draws on with "connection"; then it breathes with the heartbeats
    this.beam.pose(t, conn - 0.08, 0.42, 1 + 0.35 * Math.sin(t * 9) ** 2);
    this.up.pose(t, conn + 0.3);
    this.down.pose(t, conn + 0.55);
    // type
    this.kicker.pose(t, 0.12, 'rise');
    this.l1.enter(t, [one, conn], 'rise');
    this.l1.emphasis(t, one + 0.05, 1);
    this.l2.enter(t, [open2 - 0.12, open2], 'rise');
    this.l2.emphasis(t, open2 + 0.12, 1);
    return t < conn - 0.2 ? new THREE.Vector3(...PH) : new THREE.Vector3(0, -0.3, 0);
  }
}
