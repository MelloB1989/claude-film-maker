// v3 per-title encoding ("A cartoon needs fewer bits than an action film, so each gets its own ladder."): two titles as
// floating screens, a flat cartoon and a grainy action film, each with its own ladder of five glowing rungs (240p..1080p)
// whose lengths are the bits each rung needs. The camera starts close on the cartoon (a thin trickle of bits, short
// rungs), whips across to the action film (a torrent, long rungs), then pulls back to both as "Its own ladder" lands.
// Facts (facts_netflix.json): per-title encode optimisation, each title its own bitrate ladder. Bitrates illustrative
// (no numbers on screen; the rung lengths follow v2's illustrative kbps).
import { Flow, accentSolid, spring, expo, smooth, win, antic, pulse, breathe, keyed } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, RoundedBoxGeometry, type CamPose } from './lib';

const FOV = 30, D = 8.2;
const RES = ['240p', '360p', '480p', '720p', '1080p'];
const em = (px: number) => emFor(px, D, FOV);

interface Col { x: number; name: string; sub: string; kbps: number[]; rate: number }

export default class Ladder extends MotionScene {
  private cols: Col[] = [];
  private screens: THREE.Group[] = [];
  private screenMats: THREE.ShaderMaterial[] = [];
  private bars: THREE.Mesh[][] = [];
  private barMats: THREE.MeshBasicMaterial[][] = [];
  private names: Label[] = [];
  private res: Label[][] = [];
  private flows: Flow[] = [];
  private tags: Label[] = [];
  private hero!: KineticText;
  private note!: Label;

  protected build() {
    const s = this.stage.scene;
    this.defaults = { fstop: 2.4 };
    this.env = { floor: { y: -1.45, pool: 'accent', poolK: 0.05, reach: 7 }, haze: {} };
    const A = this.p('a', { name: 'Cartoon', sub: 'flat colour, clean lines', rungs: [150, 300, 550, 900, 1600] });
    const B = this.p('b', { name: 'Action film', sub: 'grain, fast motion', rungs: [300, 750, 1500, 3000, 5800] });
    this.cols = [{ x: -1.95, name: A.name, sub: A.sub, kbps: A.rungs, rate: 5 }, { x: 1.75, name: B.name, sub: B.sub, kbps: B.rungs, rate: 26 }];
    const tFewer = this.cue('fewer', 1.3), tFilm = this.cue('film', 2.65), tLadder = this.cue('ladder', 4.9);
    this.hits = [{ t: tFewer, kind: 'punch', amt: 0.4 }, { t: tFilm, kind: 'punch', amt: 0.8 }, { t: tLadder, kind: 'punch', amt: 0.9 }, { t: tLadder, kind: 'flash', amt: 0.25 }];
    const scrGeo = new RoundedBoxGeometry(1.7, 0.96, 0.06, 3, 0.05);
    const faceGeo = new THREE.PlaneGeometry(1.58, 0.86);
    const barGeo = new RoundedBoxGeometry(1, 0.15, 0.15, 2, 0.04);
    const maxK = 5800, maxLen = 1.7;
    this.cols.forEach((c, ci) => {
      // the screen: a dark bezel with the title's picture (a shader: flat shapes or grainy fire)
      const g = new THREE.Group();
      g.add(new THREE.Mesh(scrGeo, surfaceMat('#1a1410', { rough: 0.35, coat: 0.9 })));
      const mat = new THREE.ShaderMaterial({
        toneMapped: false,
        uniforms: { uT: { value: 0 }, uKind: { value: ci }, uLit: { value: 0 } },
        vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
        fragmentShader: /* glsl */ `
          uniform float uT, uKind, uLit; varying vec2 vUv;
          float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
          float n(vec2 p) { vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
            return mix(mix(h(i), h(i + vec2(1, 0)), f.x), mix(h(i + vec2(0, 1)), h(i + vec2(1, 1)), f.x), f.y); }
          void main() {
            vec2 p = vUv; vec3 c;
            if (uKind < 0.5) {
              // the cartoon: sky, a sun, two hills, flat colour
              c = mix(vec3(0.35, 0.62, 0.95), vec3(0.6, 0.82, 1.0), p.y);
              float sun = step(length((p - vec2(0.75 + 0.03 * sin(uT), 0.72)) * vec2(1.78, 1.0)), 0.13);
              c = mix(c, vec3(1.0, 0.82, 0.2), sun);
              float hill1 = step(p.y, 0.32 + 0.12 * sin(p.x * 5.0 + 0.6));
              float hill2 = step(p.y, 0.22 + 0.08 * sin(p.x * 7.0 + 2.0 + uT * 0.4));
              c = mix(c, vec3(0.28, 0.7, 0.32), hill1); c = mix(c, vec3(0.18, 0.55, 0.25), hill2);
            } else {
              // the action film: fire and smoke in motion, heavy grain
              float f = n(p * vec2(6.0, 4.0) + vec2(0.0, -uT * 2.2)) * 0.6 + n(p * vec2(14.0, 9.0) + vec2(uT * 1.3, -uT * 3.0)) * 0.4;
              float fire = smoothstep(0.75, 0.15, p.y + f * 0.5 - 0.1);
              c = mix(vec3(0.08, 0.06, 0.06), mix(vec3(0.9, 0.18, 0.04), vec3(1.0, 0.75, 0.3), fire * f), fire);
              c += (h(p * 900.0 + floor(uT * 24.0)) - 0.5) * 0.28;
            }
            gl_FragColor = vec4(c * (0.25 + 0.9 * uLit), 1.0);
          }`,
      });
      const face = new THREE.Mesh(faceGeo, mat);
      face.position.z = 0.035;
      g.add(face);
      g.position.set(c.x + 0.25, 0.95, 0);
      s.add(g);
      this.screens.push(g); this.screenMats.push(mat);
      const name = this.own(new Label(c.name, { size: em(56), family: F.display(100, 800), align: 'left' }));
      name.group.position.set(c.x - 0.6, 0.1, 0.05);
      s.add(name.group);
      this.names.push(name);
      // the rungs
      const row: THREE.Mesh[] = [], rm: THREE.MeshBasicMaterial[] = [], rl: Label[] = [];
      c.kbps.forEach((k, i) => {
        const m = glowMat('accent', 1.5 + i * 0.35);
        const b = new THREE.Mesh(barGeo, m);
        b.userData.len = maxLen * Math.max(0.12, k / maxK);
        s.add(b); row.push(b); rm.push(m);
        const l = this.own(new Label(RES[i]!, { size: em(40), family: F.mono(500), role: i === 4 ? 'fg' : 'fgDim', align: 'right' }));
        l.group.position.set(c.x - 0.72, this.rowY(i) - 0.07, 0.05);
        s.add(l.group); rl.push(l);
      });
      this.bars.push(row); this.barMats.push(rm); this.res.push(rl);
      // the bits pouring from the screen into the ladder: a trickle for the cartoon, a torrent for the film
      const curve = new THREE.QuadraticBezierCurve3(v(c.x + 0.25, 0.45, 0.1), v(c.x - 1.15, 0.0, 0.25), v(c.x - 0.55, this.rowY(2), 0.2));
      const f = this.own(new Flow(curve, { rate: c.rate, speed: 2.6, radius: 0.02, length: 0.1, k: 4.5, spread: 0.05, max: 80, seed: 9 + ci }));
      s.add(f.mesh); this.flows.push(f);
      const tag = this.own(new Label(ci === 0 ? 'fewer bits' : 'more bits', { size: em(44), family: F.mono(500), role: ci === 0 ? 'accentBright' : 'fgDim', k: ci === 0 ? 1.4 : 1, align: ci === 0 ? 'left' : 'right' }));
      s.add(tag.group); this.tags.push(tag);
    });
    this.hero = this.own(new KineticText('Its own ladder', { size: em(92), align: 'center', accentWords: [2], accentMat: accentSolid('accent', 1.3) }));
    this.hero.group.position.set(0.1, 1.6, 0.1);
    this.note = this.own(new Label('illustrative', { size: em(40), family: F.mono(500), role: 'fgFaint' }));
    this.note.group.position.set(0.15, 0.1, 0);
    s.add(this.hero.group, this.note.group);
    this.frame({ centre: [0, 0.1, 0], w: 7, h: 3.8, dist: D });
  }

  private rowY(i: number) { return -1.28 + i * 0.25; }

  protected cam(t: number): CamPose {
    const tAction = this.cue('action', 2.2), tSo = this.cue('so', 3.4), A = this.cols[0]!.x, B = this.cols[1]!.x;
    return keyed(t, [
      { t: 0, pos: [A + 0.2, 0.0, 6.7], target: [A + 0.35, -0.15, 0], fov: FOV },
      { t: tAction - 0.25, pos: [A + 0.45, 0.0, 6.5], target: [A + 0.5, -0.15, 0], fov: FOV },
      { t: tAction + 0.3, pos: [B + 0.1, 0.0, 6.7], target: [B + 0.35, -0.15, 0], fov: FOV, ease: (x) => 1 - Math.pow(1 - x, 4) },
      { t: tSo - 0.1, pos: [B - 0.1, 0.0, 6.6], target: [B + 0.2, -0.15, 0], fov: FOV },
      { t: tSo + 0.9, pos: [0.15, 0.12, D * 1.03], target: [0.1, 0.04, 0], fov: FOV },
      { t: this.len, pos: [-0.1, 0.1, D * 1.01], target: [0.1, 0.04, 0], fov: FOV },
    ]);
  }

  protected pose(t: number, _f: Frame) {
    const tCartoon = this.cue('cartoon', 0.3), tFewer = this.cue('fewer', 1.3), tAction = this.cue('action', 2.2), tFilm = this.cue('film', 2.65);
    const tEach = this.cue('each', 3.95), tOwn = this.cue('own', 4.6), tLadder = this.cue('ladder', 4.9);
    const at = [tCartoon - 0.1, tAction - 0.1];
    this.cols.forEach((c, ci) => {
      const t0 = at[ci]!;
      const sk = antic(t, t0, { amt: 0, settle: 0.5, over: 0.1 });
      const g = this.screens[ci]!;
      g.scale.setScalar(Math.max(0.001, sk));
      g.rotation.set(0.04 * breathe(t, 0.3, ci), (ci === 0 ? 0.12 : -0.12) + 0.05 * breathe(t, 0.25, ci + 2), 0);
      this.screenMats[ci]!.uniforms.uT!.value = t;
      this.screenMats[ci]!.uniforms.uLit!.value = win(t, t0, 0.3);
      this.names[ci]!.pose(t, t0 + 0.12, 'rise');
      // rungs shoot out one after another, then hold; the 1080p rung flashes on its "fewer"/"film"
      const hiT = ci === 0 ? tFewer : tFilm;
      this.bars[ci]!.forEach((b, i) => {
        const k = spring(t, t0 + 0.3 + i * 0.07, 0.5, 0.1);
        const len = (b.userData.len as number) * Math.max(0.001, k);
        b.scale.set(len, 1, 1);
        b.position.set(c.x - 0.6 + len / 2, this.rowY(i), 0);
        b.visible = k > 0.002;
        const m = this.barMats[ci]![i]!;
        m.color.copy(hdr('accent', (1.5 + i * 0.35) * (1 + (i === 4 ? 1.5 * pulse(t, hiT, 0.04, 0.3) : 0) + 0.6 * pulse(t, tLadder + i * 0.04, 0.03, 0.2))));
        this.res[ci]![i]!.pose(t, t0 + 0.3 + i * 0.07, 'rise');
      });
      this.flows[ci]!.pose(t, t0 + 0.2, Infinity);
      const top = this.bars[ci]![4]!;
      const tag = this.tags[ci]!;
      if (ci === 0) tag.group.position.set(c.x - 0.6 + (top.userData.len as number) + 0.15, this.rowY(4) - 0.07, 0.05);
      else tag.group.position.set(c.x - 0.6 + (top.userData.len as number), this.rowY(3) - 0.07, 0.05);
      tag.pose(t, hiT + 0.1, 'type');
    });
    this.hero.enter(t, [tEach, tOwn, tLadder], 'rise');
    this.hero.emphasis(t, tLadder + 0.1, 0.9);
    this.note.pose(t, tEach, 'rise', 0.9);
    return t < tAction ? v(this.cols[0]!.x, 0.2, 0) : t < this.cue('so', 3.4) ? v(this.cols[1]!.x, 0.2, 0) : v(0, 0.1, 0);
  }
}
