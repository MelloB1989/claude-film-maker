// Cards3D: a hand of cards in the studio, a carousel, a fan, a deck or a grid, that advances one card every few beats
// on the house spring; the card in front is in focus and the others fall soft behind it. A card is a panel of kind
// 'card' (engine/panels.ts: a label and lines of copy or code) or an image from the film's assets.
//
// Params:
//   cards              a list of { title?, lines?: (string | PanelLine)[], lang?, image? ('assets/x.png'), w?, h? }
//                      (text cards: w 680, h 0.8 w, code size 32; an image card is sized w by its
//                      picture's aspect)
//   layout 'carousel'  'carousel' | 'fan' | 'stack' | 'grid'
//   every 2            beats per advance (0: never advances); startAt ({ beat: 1 }): the first advance
//   front 0            the card in front at the start
//   camera 'push', az 0, el 3, fov 30, fstop 2.0, and every Scene3D param
import * as THREE from 'three';
import { Panel, type Lang, type PanelLine } from '../../engine/panels';
import { filmUrl } from '../../engine/config';
import { W, H } from '../../engine/gl';
import { LIN } from '../../engine/palette';
import { spring } from '../../engine/motion';
import type { TimeRef } from '../text/fx';
import { Scene3D, type Frame } from './scene3d';
import { boundsOf, cardPlacement, type CardLayout, type Placement } from './layout3d';

export interface CardParam { title?: string; lines?: (string | PanelLine)[]; lang?: Lang; image?: string; w?: number; h?: number }

const IMAGE_FRAG = /* glsl */ `
uniform sampler2D map; uniform vec2 uSize; uniform float uRadius; uniform vec3 uEdge; varying vec2 vUv;
void main() {
  vec2 p = (vUv - 0.5) * uSize, q = abs(p) - 0.5 * uSize + uRadius;
  float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - uRadius;
  float aa = fwidth(d);
  float a = 1.0 - smoothstep(-aa, aa, d);
  if (a <= 0.0) discard;
  vec3 c = texture2D(map, vUv).rgb;
  c = mix(c, uEdge, (1.0 - smoothstep(-1.5 * aa - 1.0, -aa, d)) * 0.6);
  gl_FragColor = vec4(c * a, a);
}`;

export class Cards3D extends Scene3D {
  protected override defaults: Record<string, unknown> = { camera: 'push', az: 0, el: 3, fov: 30, fstop: 2.0 };
  private cards: { obj: THREE.Object3D; size: { w: number; h: number }; panel?: Panel }[] = [];
  private b0 = 0;

  protected async build() {
    const list = this.need<CardParam[]>('cards');
    if (!list.length) throw new Error(`shot ${this.ctx.id}: Cards3D needs at least one card`);
    for (const c of list) {
      if (c.image) {
        const tex = this.own(await new THREE.TextureLoader().loadAsync(filmUrl(c.image)));
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = 8;
        const img = tex.image as { width: number; height: number };
        const w = c.w ?? 760, h = c.h ?? Math.round((w * img.height) / img.width);
        const mat = this.own(new THREE.ShaderMaterial({
          uniforms: { map: { value: tex }, uSize: { value: new THREE.Vector2(w, h) }, uRadius: { value: 18 }, uEdge: { value: new THREE.Vector3(...LIN.ruleStrong) } },
          vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
          fragmentShader: IMAGE_FRAG, transparent: true, side: THREE.DoubleSide,
          blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
        }));
        const geo = this.own(new THREE.PlaneGeometry(w / 1000, h / 1000));
        this.cards.push({ obj: new THREE.Mesh(geo, mat), size: { w: w / 1000, h: h / 1000 } });
      } else {
        const lines = (c.lines ?? []).map((l) => (typeof l === 'string' ? { text: l } : l));
        const w = c.w ?? 680;
        const panel = this.own(new Panel({ kind: 'card', title: c.title, w, h: c.h ?? Math.round(0.8 * w), size: 32, lang: c.lang, lines }));
        panel.draw(this.ctx.start);
        this.cards.push({ obj: panel.mesh, size: { w: panel.spec.w / 1000, h: panel.spec.h / 1000 }, panel });
      }
    }
    const g = new THREE.Group();
    for (const c of this.cards) g.add(c.obj);
    this.stage.scene.add(g);
    const { audio } = this.ctx;
    this.b0 = audio.beatAt(this.at(this.p<TimeRef>('startAt', { beat: 1 })));
    // framing: the layout at rest, every card shown
    const layout = this.p<CardLayout>('layout', 'carousel');
    const size = this.maxSize();
    const k0 = this.p('front', 0);
    const ps: Placement[] = this.cards.map((_, i) => cardPlacement(layout, i, this.cards.length, k0, size, W / H));
    const shown = layout === 'carousel' ? ps.filter((p) => p.pos[2] > -size.w) : layout === 'stack' ? ps.slice(0, 1) : ps;
    const b = boundsOf(shown, [size]);
    const pad = layout === 'stack' ? 1.25 : layout === 'carousel' ? 1.1 : 1.04;
    this.frame({ centre: [b.centre[0], b.centre[1], 0], w: b.w * pad, h: b.h * pad, margin: [0.07, 0.1] });
  }

  private maxSize() {
    return { w: Math.max(...this.cards.map((c) => c.size.w)), h: Math.max(...this.cards.map((c) => c.size.h)) };
  }

  /** The front slot at t: `front`, then one more every `every` beats from startAt, each step on a soft spring. */
  private slot(t: number): number {
    const n = this.cards.length, every = this.p('every', 2), k0 = this.p('front', 0);
    if (!(every > 0)) return k0;
    const { audio } = this.ctx;
    const steps = Math.floor((audio.beatAt(t) - this.b0) / every + 1e-9) + 1;
    let k = k0;
    for (let s = 0; s < steps && k0 + s < n - 1; s++) k += spring(t - audio.timeOfBeat(this.b0 + s * every), 3.2, 0.72);
    return Math.min(k, n - 1 + 0.05);
  }

  protected update(f: Frame): THREE.Vector3 {
    const layout = this.p<CardLayout>('layout', 'carousel'), n = this.cards.length;
    const k = this.slot(f.t), size = this.maxSize();
    const front = Math.min(n - 1, Math.max(0, Math.round(k)));
    this.cards.forEach((c, i) => {
      const pl = cardPlacement(layout, i, n, k, size, W / H);
      c.obj.position.set(...pl.pos);
      c.obj.rotation.set(...pl.rot);
      // a carousel's cards past the side of the ring and a deck's flown cards go
      c.obj.visible = !(layout === 'stack' && i < k - 0.999) && !(layout === 'carousel' && Math.abs(i - k) > 2.6);
      c.panel?.draw(f.t);
    });
    return this.cards[front]!.obj.getWorldPosition(new THREE.Vector3());
  }
}

export default Cards3D;
