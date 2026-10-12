// The showcase: the engine's own launch film, made from kit blocks configured by params alone. Every shot is a length
// in bars of the film's grid (120 BPM, a bar is 2 s); the captions are timed from each shot's start (at()), so shots
// can be re-cut without re-timing them, and no word starts inside a transition's window.
import { defineFilm } from '@engine/film';
import { EndCard, FeatureList, KineticText, TitleCard } from '@kit/text';
import { Counter, StatGrid } from '@kit/data';
import { Captions, ProgressBar, Watermark } from '@kit/overlays';
import config from './film.json';

/** A bar at the film's tempo (s). The shots in order and their lengths in bars. */
const BAR = 240 / config.audio.bpm;
const LENGTHS = { open: 2, frame: 2, formats: 2, stats: 2, blur: 2, features: 3, end: 3 } as const;
type Shot = keyof typeof LENGTHS;
const ORDER = Object.keys(LENGTHS) as Shot[];
/** Where a shot starts (film s), plus `dt`. */
const at = (shot: Shot, dt = 0) => ORDER.slice(0, ORDER.indexOf(shot)).reduce((s, k) => s + LENGTHS[k] * BAR, 0) + dt;
const len = (shot: Shot) => ({ bars: LENGTHS[shot] });

export default defineFilm({
  ...config,
  vo: [
    { text: 'Every frame is a function of time.', start: at('frame', 0.55), end: at('frame', 2.9) },
    { text: 'Rendered the same way, every time.', start: at('stats', 0.5), end: at('stats', 3.2) },
    { text: 'Real motion blur, up to three hundred twenty-four samples a frame.', start: at('blur', 0.4), end: at('blur', 3.5) },
  ],
  scenes: [
    {
      id: 'open', scene: TitleCard, length: len('open'),
      params: { kicker: 'claude-film-maker', title: 'Films,\nwritten in code.', sub: 'Type, 3D, data and sound that land on the beat.' },
    },
    {
      id: 'frame', scene: KineticText, length: len('frame'), transition: { kind: 'whip', dir: [1, 0] },
      params: { sync: 'vo', text: 'Every frame is\na function of time.', emphasis: ['time.'], size: 140 },
    },
    {
      id: 'formats', scene: KineticText, length: len('formats'), transition: { kind: 'whip', dir: [0, -1] },
      params: {
        size: 128, leading: 1.02, exit: 'rise',
        lines: [
          { text: 'Landscape.', reveal: 'slam', unit: 'glyph', stagger: 0.04, at: { beat: 0 } },
          { text: 'Vertical.', reveal: 'blur', at: { beat: 1 }, weight: 500 },
          { text: 'Square.', reveal: 'wipe', unit: 'line', at: { beat: 2 }, color: 'accent2' },
          { text: 'One film.', reveal: 'rise', at: { beat: 3 }, emphasis: ['film.'] },
        ],
      },
    },
    {
      id: 'stats', scene: StatGrid, length: len('stats'), transition: 'cut',
      params: {
        kicker: 'One engine', every: 0.5, y: 0.45,
        stats: [{ value: 5, label: 'Formats' }, { value: 6, label: 'Themes' }, { value: 9, label: 'Type reveals' }, { value: 4, suffix: 'K', label: 'Masters' }],
      },
    },
    {
      id: 'blur', scene: Counter, length: len('blur'), transition: 'xfade',
      params: { value: 324, label: 'Motion-blur sub-frames, at most', kicker: 'adaptive sampling', land: { beat: 5 }, dur: 1.6, y: 0.45 },
    },
    {
      id: 'features', scene: FeatureList, length: len('features'), transition: { kind: 'whip', dir: [-1, 0] },
      params: {
        kicker: 'What you get', title: 'Built for launch day.',
        items: [
          { title: 'On the beat', desc: 'Cuts, words and hits land on the grid of the score.', icon: 'spark' },
          { title: 'Any format', desc: 'Landscape, vertical and square from one film.', icon: 'plus' },
          { title: 'Deterministic', desc: 'Every frame a pure function of time.', icon: 'check' },
        ],
      },
    },
    {
      id: 'end', scene: EndCard, length: len('end'), transition: { kind: 'zoom', scale: 3 },
      params: { name: 'Film Maker', tagline: 'Films, written in code.', cta: 'bun scripts/new.ts', url: 'github.com/MelloB1989/claude-film-maker', logo: 'assets/logo.svg' },
    },
  ],
  overlays: [
    { id: 'captions', scene: Captions, start: at('stats', -0.1), end: at('features'), params: { style: 'karaoke' } },
    { id: 'watermark', scene: Watermark, end: at('end'), params: { text: 'claude-film-maker', corner: 'tr' } },
    { id: 'progress', scene: ProgressBar, params: { marks: ORDER.slice(1).map((s) => at(s)) } },
  ],
});
