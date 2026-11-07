// v3 adaptive bitrate: the video is one long glowing bar with light running along it; on "cut" a laser sweeps it and
// it falls apart into chunks ("CHUNKS" rises over them, a bracket marks "a few seconds"). The camera swings back to show
// the quality ladder underneath (240p..1080p shelves) and the amber bandwidth line; from "picks" the player drops each
// chunk onto the rung the bandwidth allows, so they land as a staircase under the line, brighter the higher the rung.
// Facts (facts_netflix.json): chunks of a few seconds; the player picks a bitrate per chunk from throughput and buffer.
import { Flow, Beam, accentSolid, spring, expo, smooth, win, antic, pulse, breathe } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, RoundedBoxGeometry, type CamPose } from './lib';

const FOV = 30;
const RES = ['240p', '360p', '480p', '720p', '1080p'];
const N = 12, CW = 0.44, GAP = 0.08, STRIP_Y = 1.18;
const xOf = (i: number, gap: number) => (i - (N - 1) / 2) * (CW + gap);
const yOf = (r: number) => -0.98 + r * 0.36;

export default class Abr extends MotionScene {
  private chunks: THREE.Mesh[] = [];
  private chunkMats: THREE.MeshPhysicalMaterial[] = [];
  private laser!: THREE.Mesh;
  private shelves: THREE.Mesh[] = [];
  private resLabels: Label[] = [];
  private hero!: KineticText;
  private few!: Label;
  private bracket!: Beam;
  private net!: Beam;
  private netLabel!: Label;
  private title!: KineticText;
  private feed!: Flow;
  private rungs: number[] = [];
  private netv: number[] = [];

  protected build() {
    const s = this.stage.scene;
    this.defaults = { fstop: 2.2 };
    this.env = { floor: { y: -1.25, pool: 'accent', poolK: 0.05, reach: 6 }, haze: {} };
    this.rungs = this.p('rungs', [4, 4, 4, 3, 2, 2, 3, 4, 4, 4, 4, 4]);
    this.netv = this.p('net', [4.6, 4.5, 4.4, 3.4, 2.5, 2.3, 3.3, 4.3, 4.6, 4.7, 4.6, 4.6]);
    const tCut = this.cue('cut', 1.05), tChunks = this.cue('chunks', 1.5);
    this.hits = [{ t: tCut, kind: 'punch', amt: 0.6 }, { t: tChunks, kind: 'punch', amt: 0.8 }];
    const geo = new RoundedBoxGeometry(CW, 0.28, 0.34, 3, 0.03);
    for (let i = 0; i < N; i++) {
      const m = accentSolid('accent', 0.3);
      m.color.copy(hdr('#3a1214', 1));
      const c = new THREE.Mesh(geo, m);
      this.chunks.push(c); this.chunkMats.push(m); s.add(c);
    }
    this.laser = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.75, 0.6), glowMat('accentBright', 8));
    s.add(this.laser);
    // the ladder: glass shelves with their resolution tags
    const shelfGeo = new THREE.BoxGeometry(N * (CW + GAP) + 0.2, 0.018, 0.5);
    RES.forEach((r, k) => {
      const m = new THREE.Mesh(shelfGeo, glowMat('#5a4a3e', 0.7 + k * 0.12));
      m.position.set(0, yOf(k) - 0.15, 0);
      this.shelves.push(m); s.add(m);
      const l = this.own(new Label(r, { size: emFor(42, 7.4, FOV), family: F.mono(500), role: k === 4 ? 'fg' : 'fgDim', align: 'right' }));
      l.group.position.set(xOf(0, GAP) - CW / 2 - 0.22, yOf(k) - 0.06, 0);
      this.resLabels.push(l); s.add(l.group);
    });
    // the bandwidth line: amber, through the per-chunk bandwidth (in rungs), a little above the chunks
    const pts = this.netv.map((n, i) => v(xOf(i, GAP), yOf(n) + 0.06, 0.2));
    pts.unshift(v(xOf(0, GAP) - 0.3, pts[0]!.y, 0.2)); pts.push(v(xOf(N - 1, GAP) + 0.3, pts[pts.length - 1]!.y, 0.2));
    this.net = this.own(new Beam(new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.3), { radius: 0.014, role: 'accent2', k: 3 }));
    s.add(this.net.mesh);
    this.netLabel = this.own(new Label('your bandwidth', { size: emFor(38, 8.3, FOV), family: F.mono(500), role: 'accent2', k: 1.3, align: 'right' }));
    this.netLabel.group.position.set(xOf(N - 1, GAP) + CW / 2, yOf(4.6) + 0.26, 0.2);
    s.add(this.netLabel.group);
    // light running along the bar before the cut (the video playing)
    this.feed = this.own(new Flow(new THREE.LineCurve3(v(xOf(0, 0) - CW / 2, STRIP_Y, 0.18), v(xOf(N - 1, 0) + CW / 2, STRIP_Y, 0.18)), { rate: 9, speed: 3.2, radius: 0.016, length: 0.3, k: 5, spread: 0.06, max: 30 }));
    s.add(this.feed.mesh);
    // type
    this.hero = this.own(new KineticText('CHUNKS', { size: emFor(150, 5, FOV), align: 'center', accentWords: [0], accentMat: accentSolid('accent', 1.3), depth: 0.24 }));
    this.hero.group.position.set(0.2, STRIP_Y + 0.42, 0);
    this.few = this.own(new Label('a few seconds each', { size: emFor(44, 5, FOV), family: F.mono(500), role: 'accent2', k: 1.3 }));
    this.few.group.position.set(xOf(8, GAP), STRIP_Y - 0.42, 0.1);
    const bx0 = xOf(8, GAP) - CW / 2, bx1 = xOf(8, GAP) + CW / 2, by = STRIP_Y - 0.2;
    this.bracket = this.own(new Beam(new THREE.CatmullRomCurve3([v(bx0, by + 0.04, 0.2), v(bx0, by, 0.2), v(bx1, by, 0.2), v(bx1, by + 0.04, 0.2)], false, 'catmullrom', 0.05), { radius: 0.007, role: 'accent2', k: 2.5, segments: 60 }));
    s.add(this.bracket.mesh, this.hero.group, this.few.group);
    this.title = this.own(new KineticText('The right rung, every chunk', { size: emFor(76, 7.4, FOV), align: 'center', accentWords: [1, 2], accentMat: accentSolid('accent', 1.2) }));
    this.title.group.position.set(-0.15, STRIP_Y + 0.52, 0);
    s.add(this.title.group);
    this.frame({ centre: [0, 0, 0], w: 6.4, h: 3.6, dist: 7.4 });
  }

  protected cam(t: number): CamPose {
    // part A: low and close, tracking along the bar; part B: back and up to the whole ladder
    const tSwing = this.cue('your', 3.4, 0, -4);
    const k = smooth(t, tSwing - 0.25, 1.1);
    const a = { pos: v(-1.6 + t * 0.55, STRIP_Y + 0.05, 3.9), tgt: v(-0.5 + t * 0.45, STRIP_Y + 0.1, 0) };
    const b = { pos: v(0.15 - 0.1 * (t - tSwing), 0.6, 8.9), tgt: v(-0.15, 0.22, 0) };
    const p = a.pos.clone().lerp(b.pos, k), g = a.tgt.clone().lerp(b.tgt, k);
    return { pos: [p.x, p.y, p.z], target: [g.x, g.y, g.z], fov: FOV };
  }

  protected pose(t: number, _f: Frame) {
    const tVideo = this.cue('video', 0.55), tCut = this.cue('cut', 1.05), tChunks = this.cue('chunks', 1.5), tFew = this.cue('few', 2.2);
    const tSwing = this.cue('your', 3.4, 0, -4), tPlayer = this.cue('player', 3.65), tPick = this.cue('picks', 4.25), tRight = this.cue('right', 4.75), tEvery = this.cue('every', 5.85);
    // the laser sweeps left to right; each chunk separates as it passes
    const sweep = win(t, tCut - 0.05, 0.42);
    const lx = xOf(0, 0) - CW + sweep * (N * CW + 2 * CW);
    this.laser.position.set(lx, STRIP_Y, 0.02);
    this.laser.visible = sweep > 0 && sweep < 1;
    const step = 0.16;
    this.chunks.forEach((c, i) => {
      const passed = tCut - 0.05 + (i / N) * 0.42;
      const g = GAP * spring(t, passed, 0.4, 0.2);
      const home = v(xOf(i, g), STRIP_Y, 0);
      // the bar is born on "video": chunks grow in from the centre out
      const born = spring(t, tVideo - 0.35 + Math.abs(i - (N - 1) / 2) * 0.025, 0.45, 0.08);
      // the drop onto its rung, from "picks"
      const r = this.rungs[i]!, t0 = tPick + i * step;
      const k = expo(t, t0, 0.32), bounce = spring(t, t0 + 0.2, 0.35, 0.18);
      const dest = v(xOf(i, GAP), yOf(r), 0);
      const p = t < t0 ? home : home.clone().lerp(dest, k);
      if (t >= t0 + 0.2) p.y = dest.y + (1 - bounce) * 0.06;
      p.y += t < t0 ? 0.02 * breathe(t, 0.8, i) * win(t, tCut + 0.4, 0.3) : 0;
      c.position.copy(p);
      c.rotation.set(t >= t0 ? (1 - k) * 0.6 : 0, 0, 0);
      c.scale.setScalar(Math.max(0.001, born));
      // the colour: a dark red bar, lit by the feed; once placed, brighter for a higher rung
      const m = this.chunkMats[i]!;
      const placed = win(t, t0 + 0.15, 0.2);
      const lit = 0.35 + 0.5 * pulse(t, passed, 0.02, 0.15);
      m.emissiveIntensity = lit * (1 - placed) + placed * (0.25 + r * 0.32) + 1.2 * pulse(t, t0 + 0.28, 0.02, 0.12);
      m.color.copy(hdr('#3a1214', 1)).lerp(hdr('accent', 1), placed * (0.3 + r * 0.16));
    });
    this.feed.pose(t, tVideo - 0.2, tCut - 0.1);
    this.hero.enter(t, tChunks, 'slam', 1.5 / 24);
    this.hero.exit(t, tSwing - 0.3, 0.4);
    this.few.pose(t, tFew, 'type', 1 - win(t, tSwing - 0.4, 0.3));
    this.bracket.pose(t, tFew - 0.05, 0.3, t < tSwing - 0.4 ? 1 : 0);
    // the ladder comes up on "Your player"
    this.shelves.forEach((m, k) => {
      const sk = spring(t, tPlayer - 0.2 + k * 0.05, 0.5, 0.08);
      m.scale.set(Math.max(0.001, sk), 1, 1);
    });
    this.resLabels.forEach((l, k) => l.pose(t, tPlayer - 0.1 + k * 0.05, 'rise'));
    this.net.pose(t, tPlayer + 0.1, 0.8, 1 + 0.5 * pulse(t, tPick, 0.05, 0.4));
    this.netLabel.pose(t, tPlayer + 0.6, 'rise');
    this.title.enter(t, tRight - 0.12, 'rise', 1 / 24);
    this.title.emphasis(t, tEvery, 0.8);
    return t < tSwing ? v(-0.5 + t * 0.45, STRIP_Y, 0) : v(0, 0, 0);
  }
}
