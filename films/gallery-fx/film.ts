// The engine's effects, one shot each at 116 BPM: every transition kind (each shot comes in by the next one: whip, wipe,
// iris, slide, spin, flash, glitch, zoom, match, xfade, dip, cut), a look per shot cycling through the presets (film,
// clean, cinematic, neon, dreamy, gritty, retro), and a BeatFx overlay punching the middle of the film on the beat.
// Every shot is a kit block configured by params alone, on a background of its own.
import { defineFilm } from '@engine/film';
import { EndCard, KineticText, Quote, TitleCard } from '@kit/text';
import { BarChart, Counter, StatGrid } from '@kit/data';
import { BeatFx } from '@kit/fx';
import config from './film.json';

const bar = { bars: 1 } as const, two = { bars: 2 } as const;
/** A bar at 116 BPM (s): BeatFx plays over bars 5-10 (slide, spin, flash and glitch). */
const BAR = 240 / config.audio.bpm;

export default defineFilm({
  ...config,
  scenes: [
    {
      id: 'open', look: 'film', scene: TitleCard, length: two,
      params: { kicker: 'Effects · gallery', title: 'Cut on the beat.', sub: 'Transitions, looks and hits, written as params.' },
    },
    {
      id: 'whip', look: 'clean', scene: KineticText, length: bar, transition: { kind: 'whip', dir: [1, 0] },
      params: { text: 'Whip it.', size: 190, emphasis: ['it.'], kicker: 'whip', background: 'bg2' },
    },
    {
      id: 'wipe', look: 'cinematic', scene: Counter, length: bar, transition: { kind: 'wipe', dir: 0, edge: 'accent' },
      params: { value: 116, suffix: 'bpm', label: 'Wipe · a glowing edge', land: { beat: 2 }, dur: 1, background: { from: 'bg', to: 'surface2', angle: 120 } },
    },
    {
      id: 'iris', look: 'neon', scene: KineticText, length: bar, transition: { kind: 'iris', center: [1340, 470], edge: 'accent2' },
      params: { text: 'Open the iris.', size: 160, emphasis: ['iris.'], emphasisColor: 'accent2', kicker: 'iris', kickerColor: 'accent2' },
    },
    {
      id: 'slide', look: 'dreamy', scene: BarChart, length: two, transition: 'slide',
      params: {
        kicker: 'slide · a card push', title: 'Every kind, one param.', suffix: '%', background: 'surface',
        data: [{ label: 'Cut', value: 38 }, { label: 'Whip', value: 64 }, { label: 'Slide', value: 81 }, { label: 'Glitch', value: 92, highlight: true }],
      },
    },
    {
      id: 'spin', look: 'gritty', scene: KineticText, length: bar, transition: { kind: 'spin', angle: 120 },
      params: { text: 'SPIN', size: 300, width: 100, weight: 900, reveal: 'slam', unit: 'glyph', stagger: 0.05, emphasis: ['spin'], background: { from: 'accentDim', to: 'bg', angle: 90 } },
    },
    {
      id: 'flash', look: 'retro', scene: StatGrid, length: bar, transition: { kind: 'flash' },
      params: {
        kicker: 'flash · out of white', every: 0.5,
        stats: [{ value: 6, label: 'New kinds' }, { value: 7, label: 'Looks' }, { value: 0, label: 'Random' }],
      },
    },
    {
      id: 'glitch', look: 'film', scene: KineticText, length: bar, transition: { kind: 'glitch', amount: 1 },
      params: { text: 'GLITCH_OK', role: 'mono', weight: 700, size: 150, reveal: 'scramble', unit: 'line', kicker: 'glitch · seeded by the pair', background: 'bg2' },
    },
    {
      id: 'zoom', look: 'clean', scene: Counter, length: bar, transition: { kind: 'zoom', scale: 3 },
      params: { value: 91.4, suffix: '%', label: 'Zoom · through the frame', land: { beat: 2 }, dur: 1, style: 'roll' },
    },
    {
      id: 'match', look: 'cinematic', scene: Quote, length: two, transition: { kind: 'match', pre: 0.4, post: 0.4 },
      params: { quote: 'Every frame a pure function of time.', by: 'The engine', byline: 'match · a luma key', emphasis: ['pure'], background: { from: 'bg2', to: 'accent2Dim', angle: 60 } },
    },
    {
      id: 'xfade', look: 'dreamy', scene: KineticText, length: bar, transition: { kind: 'xfade', pre: 0.4, post: 0.4 },
      params: { text: 'Dissolve.', size: 180, weight: 300, width: 100, reveal: 'blur', kicker: 'xfade', background: 'surface' },
    },
    {
      id: 'dip', look: 'neon', scene: KineticText, length: bar, transition: 'dip',
      params: { text: 'Dip to ink.', size: 170, reveal: 'fade', kicker: 'dip', emphasis: ['ink.'] },
    },
    {
      id: 'end', look: 'cinematic', scene: EndCard, length: two, transition: 'cut',
      params: { name: 'Effects', tagline: 'Every transition, look and hit, from film.ts.', cta: 'Make a film', url: 'docs/kit/fx.md' },
    },
  ],
  overlays: [
    {
      // punches on the beat, a shake and an accent flash on the downbeats, a pump, and bars that spring in and out
      id: 'beat', scene: BeatFx, start: 5 * BAR, end: 10 * BAR,
      params: {
        punch: { amount: 0.03 }, shake: { amount: 9 }, flash: { on: 'bar', amount: 0.22, color: 'accent' }, pump: { amount: 0.08 },
        bars: { aspect: 2.39, in: { beat: 1 }, out: { bar: 4.5 } },
      },
    },
  ],
});
