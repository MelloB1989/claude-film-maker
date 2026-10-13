// CampX Digital Evaluation × Medha AI: the 90 s launch film. The scene windows are a contract (BRIEF.md): the plates,
// the product scenes and the audio all key off them, so every length is in seconds and the sum is 90.
import { defineFilm, type ShotSpec } from '../../app/src/engine/film';
// (a relative import: bun 1.2 here does not resolve @engine/* for scripts/timeline.ts; vite resolves both to one module)
import config from './film.json';

// Product scenes are the product agent's files, scenes/product/<id>.ts. Until one exists the placeholder stands in; the
// glob (the dev server and the renderer) finds it as soon as it is written. (Under bun, timeline.ts, scenes are never
// loaded, so there is no glob.)
const product: Record<string, () => Promise<any>> =
  typeof window === 'undefined' ? {} : import.meta.glob('./scenes/product/*.ts');
const productScene = (id: string): ShotSpec['scene'] => product[`./scenes/product/${id}.ts`] ?? (() => import('./scenes/placeholder'));
const plate = () => import('./scenes/plate');
const stack = () => import('./scenes/kit-stack');
const aurora = () => import('./scenes/kit-aurora');
const logo3d = () => import('./scenes/kit-logo3d');

// Logo3D frames its logo (unit height, centred on the origin) by camera keys here: the logo `h` of the frame's height,
// its centre `y` of the frame's height above the middle, the camera easing in from `from`× the distance over the shot.
const FOV = 28, TAN = Math.tan((FOV * Math.PI) / 360);
const logoCam = (h: number, y: number, len: number, from = 1.08) => {
  const d = 1 / (2 * TAN * h), dy = -y * 2 * TAN * d;
  return [
    { t: 0, pos: [0, dy, d * from], target: [0, dy, 0] },
    { t: len, pos: [0, dy, d], target: [0, dy, 0], ease: 'outCubic' },
  ];
};

export default defineFilm({
  ...config,
  // the voice: data/vo.json (the manager's). Transition windows are kept clear of every spoken word (wordGuard).
  vo: 'data/vo.json',
  fonts: { faces: [{ family: 'InstrumentSerif-Italic', url: 'fonts/InstrumentSerif-Italic.ttf', role: 'serif', weight: 400, italic: true }] },
  // the film look: grain, halation, a grade toward the brand (a cool indigo in the shadows, warm paper in the lights);
  // no letterbox: the product's UI is shown whole. No Captions overlay.
  look: 'film',
  post: { grain: 0.05, halation: 0.4, vignette: 0.34, contrast: 1.08, saturation: 0.96, warmth: 0.06, tint: 0.07, tintColor: 'accentDim', lift: 0.01 },
  scenes: [
    // act 1: the stakes
    { id: 'open', scene: plate, length: 9, params: { variant: 'rise' } },
    { id: 'stakes', scene: () => import('./scenes/stakes'), length: 6, transition: { kind: 'match', pre: 0.5, post: 0.5 } },
    // the title card: a low aurora in the brand inks, the X-mark in 3D spinning in on "Introducing", the name swept in
    {
      id: 'title', scene: stack, length: 6, transition: { kind: 'wipe', dir: 0, edge: 'accent', pre: 0.5, post: 0.45 },
      params: { layers: [
        { scene: aurora, params: { color: 'accentDim', color2: 'accent', intensity: 0.55, height: 0.12, spread: 0.2, stars: 0, speed: 0.6 } },
        { scene: logo3d, params: { logo: 'assets/brand/campx-xmark.svg', colors: 'svg', reveal: 'spin', landAt: 0.9, depth: 0.22, pulse: 0.12, sway: 6, fov: FOV, camera: logoCam(0.2, 0.21, 6) } },
        { scene: () => import('./scenes/title'), params: { nameY: 0.58 } },
      ] },
    },
    // act 2: the pipeline
    { id: 'ingest3d', scene: plate, length: 8, params: { variant: 'push', sheet: 'assets/sheets/hires_38189_p03.jpg' }, transition: { kind: 'zoom', scale: 2.4, pre: 0.3, post: 0.45 } },
    { id: 'ingestui', scene: productScene('ingestui'), length: 6, transition: { kind: 'xfade', pre: 0.4, post: 0.4 } },
    { id: 'read3d', scene: plate, length: 7, params: { variant: 'scan', sheet: 'assets/sheets/hires_38189_p01.jpg' }, transition: { kind: 'xfade', pre: 0.4, post: 0.4 } },
    { id: 'readui', scene: productScene('readui'), length: 7, transition: { kind: 'xfade', pre: 0.25, post: 0.25 } },
    { id: 'mark3d', scene: plate, length: 6, params: { variant: 'push', overlay: 'mark', sheet: 'assets/sheets/hires_38189_p04.jpg' }, transition: { kind: 'xfade', pre: 0.4, post: 0.4 } },
    { id: 'markui', scene: productScene('markui'), length: 7, transition: { kind: 'xfade', pre: 0.2, post: 0.05 } },
    // act 3: the faculty's word
    { id: 'control', scene: productScene('control'), length: 16, transition: { kind: 'whip', dir: [1, 0], pre: 0.25, post: 0.35 } },
    // act 4: the outcome
    {
      id: 'outcome', scene: stack, length: 7, transition: { kind: 'dip', pre: 0.4, post: 0.45 },
      params: { layers: [
        { scene: aurora, params: { color: 'accentDim', color2: 'accent2', intensity: 0.4, height: 0.1, spread: 0.25, stars: 0, speed: 0.5, seed: 3 } },
        { scene: () => import('./scenes/outcome') },
      ] },
    },
    // the logo in 3D rising on "CampX.", the lines under it on the voice
    {
      id: 'end', scene: stack, length: 5, transition: { kind: 'xfade', pre: 0.5, post: 0.45 },
      params: { layers: [
        { scene: aurora, params: { color: 'accentDim', color2: 'accent', intensity: 0.3, height: 0.08, spread: 0.2, stars: 0, speed: 0.4, seed: 7 } },
        { scene: logo3d, params: { logo: 'assets/brand/campx-logo-3d.svg', colors: 'svg', reveal: 'rise', landAt: 0.55, depth: 0.16, pulse: 0.1, sway: 5, fov: FOV, camera: logoCam(0.17, 0.1, 5) } },
        { scene: () => import('./scenes/end'), params: { logo: false } },
      ] },
    },
  ],
});
