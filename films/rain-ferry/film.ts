// 雨渡し — The Rain Ferry. Episode 1, 「一閃」. An original ink-wash anime short (STORY.md): generated key art and
// clips (data/gen.json), laid out and animated with the anime kit, Japanese voices and English subtitles.
import { defineFilm, type ShotSpec } from '@engine/film';
import { Stack } from '@kit/stack';
import { Video } from '@kit/media';
import { InkReveal, Mist, Paper, Parallax, PlateShot, PostKeys, Rain, Rays, Smoke, SpeedLines, Subtitles, Words } from '@kit/anime';
import config from './film.json';

const gen = (n: string) => `assets/gen/${n}.png`;
const lay = (n: string, f: string) => `assets/layers/${n}/${f}.png`;
const clip = (n: string) => `assets/clips/${n}.mp4`;

/** Rain over a shot, with defaults that suit a clip that already has rain painted into it. */
const rain = (p: Record<string, unknown> = {}) => ({ scene: Rain, params: { opacity: 0.32, layers: 3, ...p } });
const mist = (p: Record<string, unknown> = {}) => ({ scene: Mist, params: { intensity: 0.7, ...p } });
const post = (p: Record<string, unknown>) => ({ scene: PostKeys, params: p });
// clips still generating play as their keyframe with a slow push until they land
const PENDING = new Set<string>();
const video = (src: string, p: Record<string, unknown> = {}) => PENDING.has(src)
  ? { scene: Parallax, params: { layers: [{ src: gen(`key-${src}`) }], camera: { from: { zoom: 1 }, to: { zoom: 1.05 } } } }
  : { scene: Video, params: { src: clip(src), fit: 'cover', ...p } };

/** A shot made of layers (the first is the picture); `stack` adds Stack params (its background). */
const shot = (id: string, length: number, layers: Record<string, unknown>[], more: Partial<ShotSpec> = {}, stack: Record<string, unknown> = {}): ShotSpec =>
  ({ id, scene: Stack, length, params: { layers, ...stack }, ...more });

// the cold world and the warm one: the grade the film starts in, and where it ends up when the rain stops
const COLD = { saturation: 0.82, contrast: 1.1, warmth: -0.14, lift: 0.01 };

const scenes: ShotSpec[] = [
  // ---- the road ----
  shot('open', 6, [
    { scene: Parallax, params: { layers: [{ src: gen('key-open'), depthMap: gen('key-open-depth'), relief: 0.9 }],
      camera: { from: { x: -0.012, zoom: 1.0 }, to: { x: 0.016, zoom: 1.09 } } } },
    mist({ band: 0.42, width: 0.22, veil: 0.05, drift: [0.025, 0], intensity: 0.45 }),
    rain({ opacity: 0.5, layers: 4, lightning: [3.3] }),
    post({ fade: [[0, 1], [1.8, 0]] }),
  ]),
  shot('crow', 4, [video('crow', { clipStart: 1.8, loop: false }), rain({ opacity: 0.28 })]),
  shot('step', 2.5, [video('step', { clipStart: 0.1, loop: false }), rain({ opacity: 0.3, ground: 0.66, splash: 1.4 })]),
  shot('walk', 5.5, [video('walk', { loop: false }), mist({ band: 0.15, width: 0.2, veil: 0.05 }), rain({ opacity: 0.36 })]),
  shot('eyes', 3.5, [
    { scene: Parallax, params: { layers: [{ src: gen('key-eyes'), depthMap: gen('key-eyes-depth'), relief: 0.5 }],
      camera: { from: { zoom: 1.0, y: 0.004 }, to: { zoom: 1.07, y: -0.004 } }, shake: 1.5 } },
    rain({ opacity: 0.22, length: 0.8 }),
  ]),
  // ---- the crossing ----
  shot('ferry', 5.5, [
    { scene: Parallax, params: { layers: [{ src: gen('key-ferry-tsuru'), depthMap: gen('key-ferry-tsuru-depth'), relief: 0.8 }],
      camera: { from: { x: -0.014, zoom: 1.03 }, to: { x: 0.012, zoom: 1.07 } } } },
    { scene: Smoke, params: { origin: [0.452, 0.44], height: 0.16, width: 0.45, wind: 0.05, intensity: 0.55 } },
    mist({ band: 0.56, width: 0.12, veil: 0.03, intensity: 0.45 }),
    rain({ opacity: 0.45, layers: 4, ground: 0.72 }),
  ], { transition: { kind: 'ink', pre: 0.45, post: 0.5 } }),
  shot('ask', 5, [video('ask', { loop: false }), rain()]),
  shot('refuse', 4, [
    { scene: Parallax, params: { layers: [
      { src: lay('refuse', 'plate'), depthMap: lay('refuse', 'depth'), relief: 0.6 },
      { src: lay('refuse', 'fg'), depth: 1.25, breathe: 0.0035 },
    ], camera: { from: { x: 0.006, zoom: 1.02 }, to: { x: -0.006, zoom: 1.05 } } } },
    { scene: Smoke, params: { origin: [0.665, 0.475], height: 0.5, wind: 0.03, intensity: 0.7 } },
    rain({ opacity: 0.25 }),
  ]),
  shot('demand', 5.8, [video('demand', { loop: false }), rain({ opacity: 0.38, angle: 11 })]),
  shot('tap', 6, [video('tap', { loop: false }), rain({ opacity: 0.26 })]),
  shot('look', 4, [video('look', { loop: false }), rain({ opacity: 0.2 })]),
  shot('draw', 3.8, [video('draw', { rate: 0.5, loop: false }), rain({ opacity: 0.3 })]),
  shot('rise', 4, [video('rise', { loop: false }), rain()]),
  // ---- the duel ----
  // made entirely in Blender (blender/shots/standoff.py): the set, the cast, the rain and its splashes, the lightning
  shot('standoff', 4.5, [{ scene: PlateShot }]),
  shot('eye-s', 2, [
    { scene: Parallax, params: { layers: [{ src: gen('key-eye-s') }], camera: { from: { zoom: 1.0 }, to: { zoom: 1.05 } } } },
    rain({ opacity: 0.18, length: 0.7 }),
  ]),
  shot('eye-t', 2, [
    { scene: Parallax, params: { layers: [{ src: gen('key-eye-t') }], camera: { from: { zoom: 1.05 }, to: { zoom: 1.0 } } } },
    rain({ opacity: 0.18, length: 0.7 }),
  ]),
  // time stops: the Blender plate (blender/shots/freeze.py), its drops frozen in 3D; the engine's rain slows into it
  shot('freeze', 5, [
    { scene: PlateShot },
    rain({ opacity: 0.55, layers: 5, length: 1.1, slow: [[0.1, 1], [0.9, 0.04]], fade: [[0, 1], [0.7, 0.8], [1.3, 0]] }),
    post({ saturation: [[0, 0.82], [1.2, 0.38]], contrast: [[0, 1.1], [1.2, 1.22]], exposure: [[0, 1], [1.2, 0.93]] }),
  ]),
  shot('charge', 2, [
    video('charge', { rate: 0.7, loop: false }),
    { scene: SpeedLines, params: { center: [0.55, 0.55], inner: 0.32, count: 120, intensity: 0.75 }, opacity: 0.9 },
    rain({ opacity: 0.45, angle: 28, length: 1.8 }),
    post({ shake: [[0, 4], [2, 12]] }),
  ]),
  shot('flash', 1, [
    { scene: Parallax, params: { layers: [{ src: gen('key-flash') }], camera: { from: { zoom: 1.0 }, to: { zoom: 1.12 } } } },
    post({ flash: [[0, 1.6], [0.07, 0]], invert: { keys: [[0, 1], [0.2, 0], [0.29, 1], [0.42, 0]], step: true }, shake: [[0, 34], [0.7, 0]] }),
  ]),
  shot('after', 4.5, [
    video('after', { loop: false }),
    rain({ opacity: 0.4, slow: [[0, 0.02], [1.4, 1]] }),
    post({ saturation: [[0, 0.3], [1.6, 0.82]], contrast: [[0, 1.25], [1.6, 1.1]] }),
  ]),
  shot('fall', 4.5, [video('fall', { loop: false }), rain({ opacity: 0.4 })]),
  shot('lesson', 5.5, [video('lesson', { loop: false }), rain({ opacity: 0.32 })]),
  shot('kneel', 4, [
    { scene: Parallax, params: { layers: [
      { src: lay('kneel', 'plate'), depthMap: lay('kneel', 'depth'), relief: 0.6 },
      { src: lay('kneel', 'fg'), depth: 1.15, breathe: 0.004 },
    ], camera: { from: { zoom: 1.0, y: -0.01 }, to: { zoom: 1.06, y: 0.0 } } } },
    rain({ opacity: 0.5, layers: 4, ground: 0.6 }),
  ]),
  // ---- the rain stops ----
  shot('board', 5.5, [
    video('board', { loop: false }),
    rain({ opacity: 0.3, fade: [[0, 1], [2.6, 0.5], [4.4, 0]] }),
    post({ warmth: [[0, -0.14], [5.5, 0.12]], saturation: [[0, 0.82], [5.5, 0.95]] }),
  ], { transition: { kind: 'xfade', pre: 0.4, post: 0.4 } }),
  shot('light', 5, [
    video('light', { loop: false }),
    { scene: Rays, params: { source: [0.78, 1.08], toward: [0.5, 0.1], spread: 0.55, intensity: 0.35 } },
    post({ warmth: [[0, 0.12], [2, 0.3]], saturation: [[0, 0.95], [2, 1.06]], bloom: [[0, 0.3], [2, 0.55]] }),
  ]),
  shot('cross', 6.5, [
    video('cross', { loop: false }),
    { scene: Rays, params: { source: [0.6, 1.1], toward: [0.5, 0.2], spread: 0.6, intensity: 0.25, motes: 0.6 } },
    post({ warmth: [[0, 0.3], [6.5, 0.3]], saturation: [[0, 1.06], [6.5, 1.06]], bloom: [[0, 0.55], [6.5, 0.5]] }),
  ], { transition: { kind: 'xfade', pre: 0.5, post: 0.5 } }),
  shot('title', 8, [
    { scene: InkReveal, params: { src: gen('title-calligraphy'), x: 0.64, y: 0.5, height: 0.86, at: 0.5, dur: 2.4, seal: 0.35 } },
    { scene: Words, params: { lines: [
      { text: 'THE RAIN FERRY', x: 0.33, y: 0.47, size: 50, tracking: 0.32, color: '#1b1714', at: 2.6, dur: 1.6 },
      { text: '第一話「一閃」', role: 'jp', weight: 600, x: 0.33, y: 0.56, size: 28, tracking: 0.2, color: '#9b2c1f', at: 3.4, dur: 1.4 },
      { text: 'Episode 1 · One Flash', x: 0.33, y: 0.615, size: 24, tracking: 0.18, color: '#3d362e', at: 3.8, dur: 1.4 },
    ] } },
    { scene: Paper, params: { intensity: 1.4, edge: 0.6 } },
    post({ fade: [[6.6, 0], [8, 1]] }),
  ], { transition: { kind: 'ink', pre: 0.5, post: 0.5, color: '#0a0a0c', scale: 1.3 } }, { background: '#efe8da' }),
];

// windows of shots by id (back to back from 0), for the overlays that span several shots
const starts: Record<string, number> = {};
let t = 0;
for (const s of scenes) {
  starts[s.id] = t;
  t += s.length as number;
}

export default defineFilm({
  ...config,
  fonts: { faces: [
    { family: 'Cormorant', url: 'fonts/CormorantGaramond.ttf', role: 'serif', weight: 500 },
    { family: 'Shippori-600', url: 'fonts/ShipporiMincho-SemiBold.ttf', role: 'jp', weight: 600 },
  ] },
  post: { bloom: 0.3, halation: 0.12, grain: 0.06, vignette: 0.42, ca: 0.25, ...COLD },
  scenes,
  overlays: [
    // the duel in 2.39: the bars slide in on the standoff and out as she walks away
    { id: 'bars', scene: PostKeys, start: starts.standoff!, end: starts.kneel!,
      params: { letterboxIn: [0, 1.4, 2.39], letterboxOut: [starts.kneel! - starts.standoff! - 1.6, starts.kneel! - starts.standoff!] } },
    { id: 'paper', scene: Paper, start: 0, end: starts.title!, params: { intensity: 0.8, edge: 0.4, color: '#120e0a' } },
    { id: 'subs', scene: Subtitles, params: { size: 46, y: 0.85 } },
  ],
});
