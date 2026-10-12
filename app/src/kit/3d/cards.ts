// Cards3D: a hand of cards in the studio, a carousel, a fan, a deck or a grid, that advances one card every few beats
// on the house spring. The card in front is in focus, lit along its edge by a line of accent light that flares as it
// arrives; the others fall back, dimmed and out of focus. A card is editorial: a mono kicker in the accent, a big line
// in the display face, a quieter body, an index; an `image` from the film's assets fills it, the type over a scrim.
//
// Params:
//   cards              a list of { kicker?, title?, body?, image? ('assets/x.png': cover-fitted), w?, h? }; `lines`
//                      (strings) are taken as the body; a card 520 x 680 panel px by default
//   layout 'carousel'  'carousel' | 'fan' | 'stack' | 'grid'
//   every 2            beats per advance (0: never advances); startAt ({ beat: 1 }): the first advance; front 0
//   size 0.56          the front card's height as a share of the frame's (its width at most 0.36 of a landscape
//                      frame's, 0.64 of a tall one's)
//   edge 1             the front card's accent edge (0: none); edgeColor 'accent' | 'accent2'; dim 0.6 (how far the
//                      cards behind fall toward the background); index true (01, 02… in the corner)
//   camera 'push', az 0, el 3, fov 30, fstop 1.8, and every Scene3D param
import * as THREE from 'three';
import { filmUrl } from '../../engine/config';
import { W, H } from '../../engine/gl';
import { glow } from '../../engine/look';
import { LIN, rgba } from '../../engine/palette';
import { F, font } from '../../engine/type';
import { onBeat, spring } from '../../engine/motion';
import { clamp, pulse } from '../../engine/util';
import type { TimeRef } from '../text/fx';
import { family, setToMeasure } from '../text/layout';
import { isTall } from '../scene2d';
import { Scene3D, type Frame } from './scene3d';
import { boundsOf, cardPlacement, type CardLayout, type Placement } from './layout3d';

export interface CardParam { kicker?: string; title?: string; body?: string; lines?: string[]; image?: string; w?: number; h?: number }

/** Canvas px per card px (the card's texture is painted this much finer than its panel px). */
const PAINT = 2;
/** The shadow's reach round a card (card px). */
const PAD = 70;

/**
 * Paint a card (w x h card px) on a canvas: its picture cover-fitted under a scrim, or a quiet surface gradient; the
 * kicker with an accent dot at the top; the big line and the body set from the bottom; the index in the top corner.
 */
export function paintCard(c: CardParam, w: number, h: number, img: HTMLImageElement | null, index: string): HTMLCanvasElement {
  const cv = document.createElement('canvas');
  cv.width = Math.round(w * PAINT);
  cv.height = Math.round(h * PAINT);
  const g = cv.getContext('2d')!;
  g.scale(PAINT, PAINT);
  const pad = Math.round(0.085 * w);
  if (img) {
    const s = Math.max(w / img.width, h / img.height);
    g.drawImage(img, (w - img.width * s) / 2, (h - img.height * s) / 2, img.width * s, img.height * s);
    const scrim = g.createLinearGradient(0, h * 0.3, 0, h);
    scrim.addColorStop(0, rgba('bg', 0));
    scrim.addColorStop(0.55, rgba('bg', 0.62));
    scrim.addColorStop(1, rgba('bg', 0.92));
    g.fillStyle = scrim;
    g.fillRect(0, 0, w, h);
    const top = g.createLinearGradient(0, 0, 0, h * 0.22);
    top.addColorStop(0, rgba('bg', 0.55));
    top.addColorStop(1, rgba('bg', 0));
    g.fillStyle = top;
    g.fillRect(0, 0, w, h * 0.22);
  } else {
    const bgG = g.createLinearGradient(0, 0, w * 0.4, h);
    bgG.addColorStop(0, rgba('surface2'));
    bgG.addColorStop(1, rgba('surface'));
    g.fillStyle = bgG;
    g.fillRect(0, 0, w, h);
    // a breath of the accent from the top corner
    const glowG = g.createRadialGradient(w, 0, 0, w, 0, w * 1.1);
    glowG.addColorStop(0, rgba('accent', 0.16));
    glowG.addColorStop(1, rgba('accent', 0));
    g.fillStyle = glowG;
    g.fillRect(0, 0, w, h);
  }
  g.textBaseline = 'alphabetic';
  // the kicker: mono, tracked, in the accent, after a dot
  const kSize = Math.round(0.042 * w);
  if (c.kicker) {
    g.fillStyle = rgba('accent');
    g.beginPath();
    g.arc(pad + 0.3 * kSize, pad + 0.62 * kSize, 0.28 * kSize, 0, Math.PI * 2);
    g.fill();
    g.font = font(F.mono(500), kSize);
    g.letterSpacing = `${0.16 * kSize}px`;
    g.fillStyle = rgba(img ? 'fg' : 'accentBright');
    g.fillText(c.kicker.toUpperCase(), pad + 1.1 * kSize, pad + 0.98 * kSize);
    g.letterSpacing = '0px';
  }
  if (index) {
    g.font = font(F.mono(400), kSize);
    g.textAlign = 'right';
    g.fillStyle = rgba(img ? 'fgDim' : 'fgFaint');
    g.fillText(index, w - pad, pad + 0.98 * kSize);
    g.textAlign = 'left';
  }
  // from the bottom: the body, then the big line over it
  let y = h - pad;
  const body = c.body ?? c.lines?.join(' ');
  if (body) {
    const bFam = F.ui(400), bSize = Math.round(0.05 * w);
    const set = setToMeasure(body, bFam, bSize, w - 2 * pad, { wrap: true, fit: 'shrink' });
    g.font = font(bFam, set.size);
    g.fillStyle = rgba(img ? 'fg' : 'fgDim', img ? 0.82 : 1);
    for (let i = set.lines.length - 1; i >= 0; i--) {
      g.fillText(set.lines[i]!, pad, y);
      y -= 1.38 * set.size;
    }
    y -= 0.5 * set.size;
  }
  if (c.title) {
    const tFam = family({ role: 'display', width: 87.5, weight: 800 }), tSize = Math.round(0.13 * w);
    const set = setToMeasure(c.title, tFam, tSize, w - 2 * pad, { wrap: true, fit: 'shrink', tracking: -0.025 });
    g.font = font(tFam, set.size);
    g.letterSpacing = `${-0.025 * set.size}px`;
    g.fillStyle = rgba('fg');
    for (let i = set.lines.length - 1; i >= 0; i--) {
      g.fillText(set.lines[i]!, pad - 0.03 * set.size, y);
      y -= 0.98 * set.size;
    }
  }
  return cv;
}

const CARD_VERT = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';
// The card on a plane PAD px larger each side: its face (rounded corners cut by a signed distance, a hairline edge),
// the soft shadow under it, the front card's accent edge light, the dimming of the cards behind; premultiplied.
const CARD_FRAG = /* glsl */ `
uniform sampler2D map; uniform vec2 uSize; uniform float uPad, uRadius, uDim, uRimK;
uniform vec3 uEdge, uRim, uBg;
varying vec2 vUv;
float box(vec2 p, vec2 b, float r) { vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
void main() {
  vec2 p = (vUv - 0.5) * (uSize + 2.0 * uPad);
  float d = box(p, 0.5 * uSize, uRadius);
  float aa = max(fwidth(d), 1e-3);
  float inside = 1.0 - smoothstep(-aa, aa, d);
  float sh = 0.6 * (1.0 - smoothstep(-20.0, uPad * 0.85, box(p + vec2(0.0, 0.03 * uSize.y), 0.5 * uSize, uRadius)));
  vec3 c = texture2D(map, clamp(p / uSize + 0.5, 0.0, 1.0)).rgb;
  c = mix(c, uEdge, (1.0 - smoothstep(0.0, 1.2 * aa + 0.8, -d)) * 0.7);
  c = mix(c, uBg, uDim);
  // the accent edge: a line of light just inside the edge, and its spill just outside it
  vec3 rim = uRim * uRimK * (exp(-max(-d, 0.0) / 2.2) * inside + 0.16 * exp(-max(d, 0.0) / 12.0) * (1.0 - inside));
  float a = inside + (1.0 - inside) * sh;
  if (a < 0.002 && uRimK <= 0.0) discard;
  gl_FragColor = vec4(c * inside + rim, a);
}`;

interface Card { mesh: THREE.Mesh; mat: THREE.ShaderMaterial; size: { w: number; h: number } }

export class Cards3D extends Scene3D {
  protected override defaults: Record<string, unknown> = { camera: 'push', az: 0, el: 3, fov: 30, fstop: 1.8, cameraAmount: 0.7 };
  private cards: Card[] = [];
  private b0 = 0;
  private steps: number[] = [];

  protected async build() {
    const list = this.need<CardParam[]>('cards');
    if (!list.length) throw new Error(`shot ${this.ctx.id}: Cards3D needs at least one card`);
    const showIndex = this.p('index', true);
    const rimKey = this.p<'accent' | 'accent2'>('edgeColor', 'accent');
    for (const [i, c] of list.entries()) {
      const img = c.image ? await loadImage(filmUrl(c.image)) : null;
      const w = c.w ?? 520, h = c.h ?? 680;
      const cv = paintCard(c, w, h, img, showIndex ? String(i + 1).padStart(2, '0') : '');
      const tex = this.own(new THREE.CanvasTexture(cv));
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      const mat = this.own(new THREE.ShaderMaterial({
        uniforms: {
          map: { value: tex }, uSize: { value: new THREE.Vector2(w, h) }, uPad: { value: PAD }, uRadius: { value: 22 },
          uDim: { value: 0 }, uRimK: { value: 0 }, uEdge: { value: new THREE.Vector3(...LIN.ruleStrong) },
          uRim: { value: new THREE.Vector3(...glow(rimKey, 1)) }, uBg: { value: new THREE.Vector3(...LIN.bg) },
        },
        vertexShader: CARD_VERT, fragmentShader: CARD_FRAG, transparent: true, side: THREE.DoubleSide,
        blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
        blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
      }));
      const geo = this.own(new THREE.PlaneGeometry((w + 2 * PAD) / 1000, (h + 2 * PAD) / 1000));
      this.cards.push({ mesh: new THREE.Mesh(geo, mat), mat, size: { w: w / 1000, h: h / 1000 } });
    }
    const g = new THREE.Group();
    for (const c of this.cards) g.add(c.mesh);
    this.stage.scene.add(g);
    const { audio } = this.ctx;
    this.b0 = audio.beatAt(this.at(this.p<TimeRef>('startAt', { beat: 1 })));
    const every = this.p('every', 2), n = this.cards.length, k0 = this.p('front', 0);
    if (every > 0) for (let s = 0; k0 + s < n - 1; s++) this.steps.push(audio.timeOfBeat(this.b0 + s * every));
    // framing: a carousel or a deck on its front card (the size of the frame given by `size`), a fan or a grid whole
    const layout = this.p<CardLayout>('layout', 'carousel');
    const size = this.maxSize();
    if (layout === 'carousel' || layout === 'stack') {
      const frac = this.p('size', 0.56), wMax = isTall() ? 0.64 : 0.36;
      this.frame({ centre: [0, 0, 0], w: size.w, h: size.h, margin: [(1 - wMax) / 2, (1 - frac) / 2] });
    } else {
      const ps: Placement[] = this.cards.map((_, i) => cardPlacement(layout, i, n, k0, size, W / H));
      const b = boundsOf(ps, [size]);
      this.frame({ centre: [b.centre[0], b.centre[1], 0], w: b.w, h: b.h, margin: [0.12, 0.14] });
    }
  }

  private maxSize() {
    return { w: Math.max(...this.cards.map((c) => c.size.w)), h: Math.max(...this.cards.map((c) => c.size.h)) };
  }

  /** The front slot at t: `front`, then one more at each step, on a soft spring. */
  private slot(t: number): number {
    let k = this.p('front', 0);
    for (const s of this.steps) k += spring(t - s, 3.2, 0.72);
    return k;
  }

  protected update(f: Frame): THREE.Vector3 {
    const layout = this.p<CardLayout>('layout', 'carousel'), n = this.cards.length;
    const t = f.t, k = this.slot(t), size = this.maxSize();
    const front = Math.min(n - 1, Math.max(0, Math.round(k)));
    // the rim flares as each card arrives in front and breathes on the beat
    let arrive = 0;
    for (const s of this.steps) arrive = Math.max(arrive, pulse(t, s + 0.18, 0.3));
    const rim = this.p('edge', 1) * (this.glowLevel / 3), dim = this.p('dim', 0.6);
    this.cards.forEach((c, i) => {
      const pl = cardPlacement(layout, i, n, k, size, W / H);
      c.mesh.position.set(...pl.pos);
      c.mesh.rotation.set(...pl.rot);
      c.mesh.visible = !(layout === 'stack' && i < k - 0.999) && !(layout === 'carousel' && Math.abs(i - k) > 2.6);
      const near = clamp(1 - Math.abs(i - k));
      c.mat.uniforms.uDim!.value = dim * clamp(Math.abs(i - k));
      c.mat.uniforms.uRimK!.value = rim * near * near * (0.42 + 0.7 * arrive + 0.15 * onBeat(f, 0.3));
    });
    return this.cards[front]!.mesh.getWorldPosition(new THREE.Vector3());
  }
}

async function loadImage(url: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.src = url;
  try {
    await img.decode();
  } catch {
    throw new Error(`Cards3D: can't load the image ${url}`);
  }
  return img;
}

export default Cards3D;
