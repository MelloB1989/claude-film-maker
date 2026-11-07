// v3 buffer ("Network dips? The next chunk is a little softer."): playback as a conveyor. Chunks ride left into the
// playhead and are played; new ones drop onto the tail from the network stream. On "dips?" the stream thins and
// stutters (a glitch hit); the chunk that arrives on "chunk" is a rung lower (720p, smaller and dimmer: "a little
// softer"), and the buffer ahead of the playhead never runs dry ("no stall").
// Panel mode (params.panel): the same in the presenter shot's card.
// Facts (facts_netflix.json): the player picks a rung per chunk from measured throughput and buffer.
import { Flow, accentSolid, spring, expo, smooth, win, pulse, breathe } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, RoundedBoxGeometry, type CamPose } from './lib';

const FOV = 30;
const P = 0.6, CW = 0.52, HEAD = -2.1, TAIL = 1.75, Y = -0.25, NCH = 16;

export default class Buffer extends MotionScene {
  private D = 7.8;
  private chunks: THREE.Mesh[] = [];
  private mats: THREE.MeshPhysicalMaterial[] = [];
  private head!: THREE.Group;
  private flow!: Flow;
  private hero!: KineticText;
  private soft!: Label;
  private r720!: Label;
  private nostall!: Label;
  private track!: THREE.Mesh;
  private bufBar!: THREE.Mesh;
  private v = 0;

  protected build() {
    const s = this.stage.scene;
    const PN = this.panel;
    this.D = PN ? 19 : 7.8;
    const em = (px: number) => emFor(px, this.D, FOV);
    this.defaults = { fstop: PN ? 4 : 2.2 };
    this.env = { floor: { y: -0.75, pool: 'accent', poolK: 0.05, reach: 6 }, haze: {} };
    const tDip = this.cue('dips', 0.72);
    this.hits = [{ t: tDip, kind: 'glitch', amt: 1 }, { t: tDip + 0.18, kind: 'glitch', amt: 0.5 }];
    this.v = P / 0.5; // the conveyor: one chunk per 0.5 s
    const geo = new RoundedBoxGeometry(CW, 0.42, 0.42, 3, 0.05);
    for (let i = 0; i < NCH; i++) {
      const m = accentSolid('accent', 0.7);
      const c = new THREE.Mesh(geo, m);
      this.chunks.push(c); this.mats.push(m); s.add(c);
    }
    // the playhead: a red line and knob, and the track under the conveyor
    this.head = new THREE.Group();
    const line = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.95, 0.03), glowMat('accentBright', 5));
    const knob = new THREE.Mesh(new THREE.SphereGeometry(0.075, 20, 12), glowMat('accentBright', 6));
    knob.position.y = 0.52;
    this.head.add(line, knob);
    this.head.position.set(HEAD, Y, 0.25);
    this.track = new THREE.Mesh(new THREE.BoxGeometry(TAIL - HEAD + 1.4, 0.03, 0.5), surfaceMat('#1a1410', { rough: 0.9, coat: 0 }));
    this.track.position.set((HEAD + TAIL) / 2 + 0.2, Y - 0.24, 0);
    this.bufBar = new THREE.Mesh(new THREE.BoxGeometry(1, 0.035, 0.52), glowMat('#8a7d70', 1.1));
    s.add(this.head, this.track, this.bufBar);
    // the network stream, from the upper right onto the tail
    const curve = new THREE.QuadraticBezierCurve3(v(3.6, 1.7, -0.6), v(2.6, 1.3, 0), v(TAIL, Y + 0.35, 0));
    this.flow = this.own(new Flow(curve, { rate: 30, speed: 3.6, radius: 0.024, length: 0.16, k: 5, spread: 0.1, max: 80 }));
    s.add(this.flow.mesh);
    // type
    this.hero = this.own(new KineticText('Network dips?', { size: em(PN ? 72 : 104), align: 'left', accentWords: [1], accentMat: accentSolid('accent2', 1.2) }));
    this.hero.group.position.set(HEAD - 0.35, PN ? 2.35 : 1.25, 0);
    this.soft = this.own(new Label('a little softer', { size: em(PN ? 44 : 52), role: 'accent2', k: 1.3, align: 'center' }));
    this.r720 = this.own(new Label('720p', { size: em(PN ? 40 : 44), family: F.mono(500), role: 'accent2', k: 1.3 }));
    this.nostall = this.own(new Label('no stall', { size: em(PN ? 44 : 48), family: F.mono(500), role: 'accent', k: 1.4, align: 'left', tracking: 0.04 }));
    this.nostall.group.position.set(HEAD - 0.3, Y - (PN ? 1.0 : 0.72), 0.3);
    for (const l of [this.hero.group, this.soft.group, this.r720.group, this.nostall.group]) s.add(l);
    this.frame({ centre: [0, 0.3, 0], w: 6.4, h: 3.2, dist: this.D });
  }

  /** Chunk n's slot x at time t (it rides left at speed v). */
  private slot(n: number, t: number) { return HEAD - 0.6 + n * P - this.v * t; }

  protected cam(t: number): CamPose {
    const D = this.D, m = this.panel ? 0.35 : 1;
    const az = THREE.MathUtils.degToRad(m * (-9 + 6 * smooth(t, 0, this.len)));
    const d = D * (1 - m * 0.05 * smooth(t, 0, this.len));
    const ty = this.panel ? 0.75 : 0.3;
    return { pos: [Math.sin(az) * d - 0.1, ty + 0.75, Math.cos(az) * d], target: [-0.1, ty, 0], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const tNet = this.cue('network', 0.2), tDip = this.cue('dips', 0.72), tNext = this.cue('next', 1.55), tChunk = this.cue('chunk', 1.85);
    const tSoft = this.cue('softer', 2.65);
    // which chunk is the softer one: the first to land on the tail at or after "chunk"
    const landT = (n: number) => (HEAD - 0.6 + n * P - TAIL) / this.v;
    let softN = 0;
    while (landT(softN) < tChunk - 0.15) softN++;
    const intro = spring(t, 0, 0.45, 0.06);
    this.chunks.forEach((c, n) => {
      const x = this.slot(n, t), tl = landT(n);
      const isSoft = n === softN;
      // arriving: drop onto the tail over 0.3 s before its landing; played: shrink into the playhead
      const arr = tl > 0 ? expo(t, tl - 0.3, 0.3) : 1;
      const played = win(HEAD + 0.1 - x, 0, 0.45);
      const k = arr * (1 - played) * intro;
      const h = isSoft ? 0.72 : 1;
      c.position.set(Math.max(x, HEAD + 0.05), Y + (1 - arr) * 1.1 + (h - 1) * 0.21, 0);
      c.scale.set(Math.max(0.001, k) * (isSoft ? 0.86 : 1), Math.max(0.001, k) * h, Math.max(0.001, k) * (isSoft ? 0.86 : 1));
      c.rotation.set((1 - arr) * 0.7, 0, 0);
      c.visible = k > 0.003 && x < TAIL + 0.01;
      const m = this.mats[n]!;
      m.color.copy(isSoft ? hdr('#7a2a22', 1) : hdr('accent', 1));
      m.emissive.copy(isSoft ? hdr('accent2', 1) : hdr('accent', 1));
      m.emissiveIntensity = (isSoft ? 0.35 : 0.75) + 1.4 * pulse(t, tl, 0.03, 0.12);
      if (isSoft) {
        const lp = c.position.clone();
        const f = this.panel ? 1.5 : 1;
        this.r720.group.position.set(lp.x, lp.y + 0.42 * f, 0.25);
        this.soft.group.position.set(lp.x, lp.y + 0.95 * f, 0.25);
        this.r720.pose(t, tl - 0.05, 'flip', c.visible ? 1 : 0);
        this.soft.pose(t, Math.max(tl, tSoft - 0.05), 'rise', c.visible ? 1 : 0);
      }
    });
    // the buffer ahead (a warm bar under the chunks from the playhead to the tail): it never runs dry
    const ahead = TAIL - HEAD;
    this.bufBar.scale.x = Math.max(0.001, ahead * intro);
    this.bufBar.position.set(HEAD + (ahead * intro) / 2, Y - 0.215, 0.01);
    this.head.position.y = Y + 0.02 * breathe(t, 2);
    // the stream: dense, then thin and stuttering through the dip, then back
    const dip = (dep: number) => (dep > tDip - 0.15 && dep < tDip + 1.3 ? 0.18 + 0.12 * Math.sin(dep * 30) : 1);
    this.flow.pose(t, -1.5, Infinity, dip);
    this.hero.enter(t, [tNet - 0.05, tDip], 'rise');
    this.hero.emphasis(t, tDip + 0.05, 1);
    this.nostall.pose(t, tSoft + 0.25, 'type');
    return v(-0.1, Y + 0.2, 0);
  }
}
