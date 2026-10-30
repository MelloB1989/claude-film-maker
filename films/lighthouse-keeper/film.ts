// Your Life As a Lighthouse Keeper: a 74 s storybook explainer in the flat-cartoon style of the "Your Life As..."
// videos. Every shot is a Blender drawing (blender/draw/<id>.py, rendered by blender/draw.py into
// out/lighthouse-keeper/media/<id>/) played through the kit's Image with a slow camera move on top, as those videos
// move over still illustrations. The windows are the voiceover's (timing 'vo'): each scene runs while its line is said.
import { defineFilm } from '../../app/src/engine/film';
import config from './film.json';

const image = () => import('./scenes/kit-image');
const stack = () => import('./scenes/kit-stack');
const text = () => import('./scenes/kit-text');

type KB = { zoom?: number; x?: number; y?: number };
/** A drawing with a camera move from `from` to `to` over the shot (Ken Burns keys: zoom >= 1, pan -1..1). */
const draw = (id: string, from: KB, to: KB, extra: Record<string, unknown> = {}) =>
  ({ src: `frames/${id}`, from, to, loop: false, entry: 'none', fit: 'cover', ...extra });
/** Handwritten words written on over a drawing. */
const hand = (words: string, at: number, extra: Record<string, unknown> = {}) => ({
  scene: text, start: at, params: { text: words, role: 'hand', size: 150, color: '#1b1a1d', reveal: 'wipe', unit: 'line', push: 0, delay: 0, ...extra },
});
const xfade = (s = 0.3) => ({ kind: 'xfade' as const, pre: s, post: s });
const dip = (s = 0.3) => ({ kind: 'dip' as const, pre: s, post: s });

export default defineFilm({
  ...config,
  vo: 'data/vo.json',
  timing: 'vo',
  fonts: { faces: [{ family: 'PatrickHand', url: 'fonts/PatrickHand-Regular.ttf', role: 'hand', weight: 400 }] },
  // flat colour must stay flat: no bloom, halation or grain; the faintest vignette
  look: 'clean',
  post: { bloom: 0, halation: 0, grain: 0, vignette: 0.05, contrast: 1, saturation: 1, warmth: 0, lift: 0 },
  scenes: [
    // act 1: the keeper
    { id: 'open', scene: stack, params: { layers: [
      { scene: image, params: draw('open', { zoom: 1.0 }, { zoom: 1.12, x: 0.35, y: -0.05 }) },
      hand('1891', 0.7, { x: 0.17, y: 0.37, size: 170 }),
    ] } },
    { id: 'rock', scene: image, params: draw('rock', { zoom: 1.16 }, { zoom: 1.0 }), transition: xfade(0.3) },
    { id: 'wake', scene: image, params: draw('wake', { zoom: 1.0 }, { zoom: 1.06 }), transition: dip(0.3) },
    { id: 'stairs', scene: image, params: draw('stairs', { zoom: 1.0, y: 1 }, { zoom: 1.0, y: -0.58 }) },
    { id: 'lens', scene: image, params: draw('lens', { zoom: 1.0 }, { zoom: 1.05, x: -0.2 }) },
    { id: 'log', scene: image, params: draw('log', { zoom: 1.08, x: -0.5 }, { zoom: 1.08, x: 0.5 }) },
    // act 2: the month
    { id: 'boat', scene: image, params: draw('boat', { zoom: 1.1, x: 0.5 }, { zoom: 1.02, x: 0.2 }, { float: 6 }), transition: xfade(0.3) },
    { id: 'noboat', scene: image, params: draw('noboat', { zoom: 1.0 }, { zoom: 1.08 }) },
    { id: 'meal', scene: image, params: draw('meal', { zoom: 1.0 }, { zoom: 1.06 }) },
    // act 3: the storm
    { id: 'storm', scene: image, params: draw('storm', { zoom: 1.0 }, { zoom: 1.06 }), transition: dip(0.3) },
    { id: 'ship', scene: image, params: draw('ship', { zoom: 1.0 }, { zoom: 1.1, x: -0.3 }), transition: { kind: 'flash', pre: 0.1, post: 0.25, color: '#fff8e0' } },
    { id: 'worry', scene: image, params: draw('worry', { zoom: 1.0 }, { zoom: 1.08 }) },
    { id: 'dawn', scene: image, params: draw('dawn', { zoom: 1.1, x: 0.3 }, { zoom: 1.0 }), transition: { kind: 'xfade', pre: 0.5, post: 0.28 } },
    // act 4: the light
    { id: 'alone', scene: image, params: draw('alone', { zoom: 1.0 }, { zoom: 1.05 }), transition: dip(0.3) },
    { id: 'light', scene: image, params: draw('light', { zoom: 1.0 }, { zoom: 1.08 }) },
    { id: 'end', scene: stack, transition: xfade(0.3), params: { layers: [
      { scene: image, params: draw('end', { zoom: 1.06 }, { zoom: 1.0 }) },
      hand('Your Life As a\nLighthouse Keeper', 1.4, { x: 0.06, y: 0.7, align: 'left', size: 104, color: '#fff6d8', reveal: 'fade', unit: 'line', stagger: 0.35 }),
    ] } },
  ],
});
