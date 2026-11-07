// End card (36 f + tail): the series tag, "100+ billion" slammed over the river of messages from the title, "messages a
// day" under it, and the film's three answers in a row: Tiny processes. Messages that don't linger. Keys on your phone.
import { WaShot, THREE, keyed, em } from './base';
import { Flow, KineticText, Label, expo } from '@kit/motion';
import { F } from '@engine/type';

const D = 7;

export default class End extends WaShot {
  private river!: Flow;
  private river2!: Flow;
  private kicker!: Label;
  private hero!: KineticText;
  private sub!: KineticText;
  private notes: Label[] = [];

  protected build() {
    this.env = { floor: { y: -0.6, centre: [0, -2], reach: 7, poolK: 0.1 }, haze: { k2: 0.08 } };
    this.basePost = { ...this.basePost, bloom: 0.6 };
    const s = this.stage.scene;
    const path = new THREE.CatmullRomCurve3([new THREE.Vector3(-10, -0.3, -6), new THREE.Vector3(-3, 0.1, -3.5), new THREE.Vector3(3, 0.15, -3.5), new THREE.Vector3(10, -0.2, -6)]);
    this.river = this.own(new Flow(path, { rate: 40, speed: 8, radius: 0.02, length: 0.24, spread: 0.45, max: 160, k: 2.4, hotShare: 0.2, seed: 4 }));
    this.river2 = this.own(new Flow(path, { rate: 18, speed: 6, radius: 0.012, length: 0.12, spread: 0.8, max: 80, k: 1.6, seed: 8 }));
    s.add(this.river.mesh, this.river2.mesh);
    this.kicker = this.own(new Label('SYSTEM DESIGN IN 60 SECONDS', { size: em(40, D), family: F.mono(500), role: '#FFB547', k: 1.2, tracking: 0.08 }));
    this.kicker.group.position.set(0, 1.62, 0);
    this.hero = this.own(new KineticText('100+ billion', { size: em(170, D), align: 'center', accentWords: [0], depth: 0.22 }));
    this.hero.group.position.set(0, 0.62, 0);
    this.sub = this.own(new KineticText('messages a day', { size: em(84, D), align: 'center' }));
    this.sub.group.position.set(0, 0.06, 0);
    const lines = ['Tiny processes.', "Messages that don't linger.", 'Keys on your phone.'];
    lines.forEach((l, i) => {
      const n = this.own(new Label(l, { size: em(40, D), role: i === 2 ? 'accent' : 'fgDim', k: i === 2 ? 1.3 : 1, align: 'left' }));
      this.notes.push(n);
      s.add(n.group);
    });
    // one row, centred, a gap between; scaled to stay inside title-safe if it runs wide
    const gap = 0.32, widths = this.notes.map((n) => n.width), tot = widths.reduce((a, b) => a + b, 0) + gap * 2;
    const fit = Math.min(1, 5.6 / tot);
    let x = (-tot / 2) * fit;
    this.notes.forEach((n, i) => {
      n.group.scale.setScalar(fit);
      n.group.position.set(x, -0.55, 0.1);
      x += (widths[i]! + gap) * fit;
    });
    s.add(this.kicker.group, this.hero.group, this.sub.group);
    this.frame({ centre: [0, 0.5, 0], w: 6.5, h: 3 });
    this.hits = [{ t: 0.1, kind: 'punch', amt: 0.8 }, { t: 0.1, kind: 'flash', amt: 0.4 }];
  }

  protected cam(t: number) {
    return keyed(t, [
      { t: 0, pos: [0.4, 0.75, D + 0.4], target: [0, 0.45, 0], fov: 30 },
      { t: this.len, pos: [-0.25, 0.65, D - 0.45], target: [0, 0.45, 0], fov: 30 },
    ]);
  }

  protected pose(t: number) {
    this.river.pose(t, -3);
    this.river2.pose(t, -3);
    this.kicker.pose(t, 0.0, 'rise', expo(t, 0, 0.2));
    this.hero.enter(t, 0.08, 'slam', 0.5 / 24);
    this.hero.emphasis(t, 0.3, 1);
    this.sub.enter(t, 0.22, 'rise');
    this.notes.forEach((n, i) => n.pose(t, 0.45 + i * 0.1, 'rise', expo(t, 0.45 + i * 0.1, 0.2)));
    return new THREE.Vector3(0, 0.6, 0);
  }
}
