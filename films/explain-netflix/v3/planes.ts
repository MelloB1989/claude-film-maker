// v3 control plane vs data plane ("Press play, and AWS points you to that box. It streams the video."): your screen on
// the left, AWS above right as an amber-lit cloud ringed by what it runs (login, profiles, recommendations), the
// Open Connect box below right. Press play: an amber request flies up to AWS; AWS points an amber beam at the box
// ("use this box"); then the box streams the video to the screen in a thick red stream and the screen comes alive.
// Facts (facts_netflix.json): the control plane (sign-in, browsing, recommendations, playback authorisation, steering to
// OCAs) runs on AWS; the video bytes come from OCAs.
import { Flow, Beam, accentSolid, spring, expo, smooth, win, antic, pulse, breathe, keyed } from '@kit/motion';
import type { Frame } from '@engine/scene';
import { THREE, F, Cloud, ServerBox, KineticText, Label, MotionScene, glowMat, surfaceMat, hdr, emFor, v, arc, playGeometry, RoundedBoxGeometry, type CamPose } from './lib';

const FOV = 30, D = 9.2;
const em = (px: number) => emFor(px, D, FOV);
const TV = v(-2.45, -0.1, 0), AWS = v(1.0, 1.05, -0.4), BOX = v(1.75, -0.2, 0.2);

export default class Planes extends MotionScene {
  private tv!: THREE.Group;
  private screen!: THREE.ShaderMaterial;
  private play!: THREE.Mesh;
  private cloud!: Cloud;
  private aws!: KineticText;
  private chips: Label[] = [];
  private box!: ServerBox;
  private boxRing!: THREE.Mesh;
  private boxRingMat!: THREE.MeshBasicMaterial;
  private req!: Flow;
  private point!: Beam;
  private use!: Label;
  private stream!: Flow;
  private ctl!: Label;
  private data!: Label;
  private boxLabel!: Label;

  protected build() {
    const s = this.stage.scene;
    this.defaults = { fstop: 2.4 };
    this.env = { floor: { y: -1.25, pool: 'accent', poolK: 0.05, reach: 7 }, haze: {} };
    const tPress = this.cue('press', 0.2), tPoints = this.cue('points', 1.85), tStreams = this.cue('streams', 3.5);
    this.hits = [{ t: tPress + 0.12, kind: 'punch', amt: 0.6 }, { t: tPoints, kind: 'punch', amt: 0.5 }, { t: tStreams, kind: 'punch', amt: 0.9 }, { t: tStreams, kind: 'flash', amt: 0.2 }];
    // the screen
    this.tv = new THREE.Group();
    this.tv.add(new THREE.Mesh(new RoundedBoxGeometry(2.0, 1.2, 0.08, 3, 0.05), surfaceMat('#16110d', { rough: 0.3, coat: 1 })));
    this.screen = new THREE.ShaderMaterial({
      toneMapped: false,
      uniforms: { uT: { value: 0 }, uOn: { value: 0 }, uProg: { value: 0 } },
      vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform float uT, uOn, uProg; varying vec2 vUv;
        void main() {
          vec2 p = vUv;
          vec3 off = vec3(0.03, 0.025, 0.022);
          // playing: a warm moving picture (soft bands of colour drifting) and a red progress bar
          float b = 0.5 + 0.5 * sin(p.x * 5.0 + uT * 1.6) * cos(p.y * 4.0 - uT * 1.1);
          vec3 pic = mix(vec3(0.35, 0.12, 0.08), vec3(0.95, 0.55, 0.3), b) * (0.55 + 0.45 * p.y);
          vec3 c = mix(off, pic, uOn);
          float bar = step(abs(p.y - 0.07), 0.012) * step(p.x, 0.92) * step(0.08, p.x);
          c = mix(c, vec3(0.25), bar * 0.6 * uOn);
          c = mix(c, vec3(2.4, 0.1, 0.12), bar * step(p.x, 0.08 + 0.84 * uProg) * uOn);
          gl_FragColor = vec4(c, 1.0);
        }`,
    });
    const face = new THREE.Mesh(new THREE.PlaneGeometry(1.88, 1.06), this.screen);
    face.position.z = 0.045;
    this.play = new THREE.Mesh(playGeometry(0.2, 0.06), surfaceMat('#fff6ec', { rough: 0.25, coat: 1, k: 1.1 }));
    this.play.position.z = 0.12;
    const stand = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.05, 0.3), surfaceMat('#1a1410'));
    stand.position.set(0, -0.75, 0);
    const neck = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.18, 0.06), surfaceMat('#1a1410'));
    neck.position.set(0, -0.66, 0);
    this.tv.add(face, this.play, stand, neck);
    this.tv.position.copy(TV);
    this.tv.rotation.y = 0.28;
    s.add(this.tv);
    // AWS: an amber-lit cloud, the word, and what it runs
    this.cloud = this.own(new Cloud(1.0, '#33251b'));
    this.cloud.mat.emissive.copy(hdr('accent2', 1)); this.cloud.mat.emissiveIntensity = 0.04;
    this.cloud.group.position.copy(AWS);
    s.add(this.cloud.group);
    this.aws = this.own(new KineticText('AWS', { size: em(96), align: 'center', accentWords: [0], accentMat: accentSolid('accent2', 1.2), depth: 0.2 }));
    this.aws.group.position.copy(AWS).add(v(0, -0.15, 0.75));
    s.add(this.aws.group);
    const chipNames = ['Login', 'Profiles', 'Recommendations'];
    const chipAt = [v(-1.05, 0.55, 0.3), v(1.3, 0.55, 0.3), v(-0.6, -0.72, 0.9)];
    chipNames.forEach((n, i) => {
      const l = this.own(new Label(n, { size: em(42), family: F.mono(500), role: 'accent2', k: 1.2 }));
      l.group.position.copy(AWS).add(chipAt[i]!);
      s.add(l.group); this.chips.push(l);
    });
    this.ctl = this.own(new Label('CONTROL PLANE', { size: em(40), family: F.mono(500), role: 'fgDim', tracking: 0.08 }));
    this.ctl.group.position.copy(AWS).add(v(0, 1.0, 0.3));
    s.add(this.ctl.group);
    // the box
    this.box = this.own(new ServerBox(1.2, 0.26, 0.8, 2));
    this.box.group.position.copy(BOX); this.box.group.rotation.y = -0.4;
    s.add(this.box.group);
    this.boxRingMat = glowMat('accent2', 3);
    this.boxRing = new THREE.Mesh(new THREE.TorusGeometry(0.95, 0.014, 8, 120), this.boxRingMat);
    this.boxRing.rotation.x = Math.PI / 2;
    this.boxRing.position.copy(BOX).add(v(0, -0.32, 0));
    s.add(this.boxRing);
    this.boxLabel = this.own(new Label('Open Connect', { size: em(52) }));
    this.boxLabel.group.position.copy(BOX).add(v(0.15, -0.6, 0.4));
    s.add(this.boxLabel.group);
    this.use = this.own(new Label('use this box', { size: em(44), family: F.mono(500), role: 'accent2', k: 1.3, align: 'right' }));
    this.use.group.position.copy(BOX).add(v(-0.95, 0.15, 0.5));
    s.add(this.use.group);
    // the request (screen to AWS), the pointer (AWS to box), the stream (box to screen)
    const tvTop = TV.clone().add(v(0.55, 0.62, 0.1));
    this.req = this.own(new Flow(arc(tvTop, AWS.clone().add(v(-0.7, -0.15, 0.2)), 0.7), { rate: 7, speed: 4.5, radius: 0.03, length: 0.16, role: 'accent2', hot: 'accent2Bright', k: 4, max: 20 }));
    this.point = this.own(new Beam(new THREE.QuadraticBezierCurve3(AWS.clone().add(v(0.3, -0.45, 0.2)), v(2.3, 0.4, 0.3), BOX.clone().add(v(0.2, 0.35, 0))), { radius: 0.014, role: 'accent2', k: 3 }));
    this.stream = this.own(new Flow(new THREE.CatmullRomCurve3([BOX.clone().add(v(-0.65, 0.05, 0.1)), v(-0.2, -0.85, 0.3), TV.clone().add(v(1.0, -0.25, 0.1))]), { rate: 46, speed: 4.2, radius: 0.03, length: 0.2, k: 5.5, hotShare: 0.4, spread: 0.11, max: 120 }));
    s.add(this.req.mesh, this.point.mesh, this.stream.mesh);
    this.data = this.own(new Label('DATA PLANE', { size: em(40), family: F.mono(500), role: 'fgDim', tracking: 0.08 }));
    this.data.group.position.set(-0.45, -1.18, 0.4);
    s.add(this.data.group);
    this.frame({ centre: [0, 0.15, 0], w: 7, h: 3.8, dist: D });
  }

  protected cam(t: number): CamPose {
    const tPoints = this.cue('points', 1.85), tStreams = this.cue('streams', 3.5);
    return keyed(t, [
      { t: 0, pos: [-0.9, 0.55, 7.4], target: [-0.7, 0.35, 0], fov: FOV },
      { t: tPoints - 0.3, pos: [-0.4, 0.5, 8.2], target: [-0.3, 0.32, 0], fov: FOV },
      { t: tStreams - 0.2, pos: [0.1, 0.4, 8.9], target: [-0.2, 0.25, 0], fov: FOV },
      { t: this.len, pos: [-0.3, 0.35, D], target: [-0.25, 0.25, 0], fov: FOV },
    ]);
  }

  protected pose(t: number, _f: Frame) {
    const tPress = this.cue('press', 0.2), tPlay = this.cue('play', 0.5), tAws = this.cue('aws', 1.25), tPoints = this.cue('points', 1.85);
    const tBox = this.cue('box', 2.7), tIt = this.cue('it', 3.3), tStreams = this.cue('streams', 3.5), tVideo = this.cue('video', 4.05);
    // the screen and its play button (pressed on "play")
    const tk = antic(t, 0, { amt: 0, settle: 0.45, over: 0.08 });
    this.tv.scale.setScalar(Math.max(0.001, tk));
    const press = pulse(t, tPlay, 0.06, 0.12);
    this.play.scale.setScalar(Math.max(0.001, (1 - 0.35 * press) * (1 - win(t, tStreams, 0.25))));
    this.play.position.z = 0.12 - 0.05 * press;
    this.screen.uniforms.uT!.value = t;
    this.screen.uniforms.uOn!.value = smooth(t, tStreams + 0.15, 0.5);
    this.screen.uniforms.uProg!.value = 0.04 + 0.08 * Math.max(0, t - tStreams);
    // AWS
    const ck = antic(t, tPress, { amt: 0, settle: 0.6, over: 0.06 });
    this.cloud.group.scale.setScalar(Math.max(0.001, ck));
    this.cloud.mat.emissiveIntensity = 0.04 + 0.25 * pulse(t, tAws, 0.05, 0.3) + 0.2 * pulse(t, tPoints, 0.05, 0.3);
    this.cloud.group.position.copy(AWS).add(v(0, 0.04 * breathe(t, 0.4), 0));
    this.aws.enter(t, tAws - 0.08, 'slam', 1.5 / 24);
    this.aws.emphasis(t, tPoints, 0.6);
    this.chips.forEach((l, i) => l.pose(t, tPress + 0.25 + i * 0.12, 'rise', 1 - 0.5 * win(t, tStreams, 0.4)));
    this.ctl.pose(t, tAws + 0.2, 'type');
    // the request, then the pointer to the box
    this.req.pose(t, tPlay, tPlay + 0.6);
    this.point.pose(t, tPoints, 0.45, 1 + 1.2 * pulse(t, tBox, 0.05, 0.25));
    const bk = antic(t, tPress + 0.4, { amt: 0, settle: 0.5, over: 0.1 });
    this.box.group.scale.setScalar(Math.max(0.001, bk));
    this.box.blink(t, t > tStreams);
    const rk = spring(t, tBox - 0.05, 0.45, 0.12);
    this.boxRing.scale.setScalar(Math.max(0.001, rk));
    this.boxRingMat.color.copy(hdr('accent2', 3 * (1 + pulse(t, tBox, 0.05, 0.3))));
    this.use.pose(t, tBox, 'type', 1 - win(t, tStreams + 0.4, 0.3));
    this.boxLabel.pose(t, tPress + 0.55, 'rise');
    // the stream
    this.stream.pose(t, tIt, Infinity);
    this.data.pose(t, tVideo - 0.1, 'type');
    return t < tPoints ? v(-0.8, 0.4, 0) : t < tStreams ? v(1.2, 0.2, 0) : v(-0.3, -0.2, 0.2);
  }
}
