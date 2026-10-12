// The kit's type, overlays and data blocks, one shot each, at 110 BPM: every shot a block configured by params alone.
// The voiceover is written here as captions: the kinetic and quote shots land on its words (sync 'vo'), the Captions
// overlay lights it word by word over the data shots. Its times are given from each shot's start (at()), so shots can
// be added or re-cut without re-timing it, and no word starts inside a transition's window.
import { defineFilm } from '@engine/film';
import { BulletList, EndCard, FeatureList, KineticText, Marquee, Quote, TitleCard, LowerThird } from '@kit/text';
import { BarChart, Compare, Counter, LineChart, StatGrid } from '@kit/data';
import { Captions, ProgressBar, Watermark } from '@kit/overlays';
import config from './film.json';

/** A bar at 110 BPM (s). The shots in order and their lengths in bars. */
const BAR = 240 / 110;
const LENGTHS = {
  title: 2, kinetic: 2, reveals: 2, diff: 2, counter: 2, bars: 2, line: 2, stats: 2, compare: 2, quote: 2, list: 2,
  features: 3, marquee: 2, custom: 1, end: 3,
} as const;
type Shot = keyof typeof LENGTHS;
const ORDER = Object.keys(LENGTHS) as Shot[];
/** Where a shot starts (film s), plus `dt`. */
const at = (shot: Shot, dt = 0) => ORDER.slice(0, ORDER.indexOf(shot)).reduce((s, k) => s + LENGTHS[k] * BAR, 0) + dt;
const len = (shot: Shot) => ({ bars: LENGTHS[shot] });

export default defineFilm({
  ...config,
  vo: [
    { text: 'Ship your story in ninety seconds, flat.', start: at('kinetic', 0.64), end: at('kinetic', 2.84) },
    { text: 'Recall jumped to ninety-one point four percent.', start: at('counter', 0.6), end: at('counter', 3.2) },
    { text: 'Every model, measured the same way.', start: at('bars', 0.65), end: at('bars', 2.75) },
    { text: 'From forty-four, to ninety-one point four.', start: at('compare', 0.45), end: at('compare', 3.05) },
    { text: 'It feels like the tool finally remembers me.', start: at('quote', 0.7), end: at('quote', 3.3) },
    { text: 'Built for launch day, in every format you ship.', start: at('features', 0.95), end: at('features', 3.95) },
  ],
  scenes: [
    {
      id: 'title', scene: TitleCard, length: len('title'),
      params: { kicker: 'Lumen · v2', title: 'Launch films,\nwritten in code.', sub: 'Kinetic type, data and captions that land on the beat.' },
    },
    {
      id: 'kinetic', scene: KineticText, length: len('kinetic'), transition: { kind: 'whip', dir: [1, 0] },
      params: { sync: 'vo', text: 'Ship your story\nin ninety seconds, flat.', emphasis: ['ninety', 'seconds,'], size: 136, y: 0.44 },
    },
    {
      // a type specimen: one line per reveal, each landing on its beat
      id: 'reveals', scene: KineticText, length: len('reveals'), transition: { kind: 'whip', dir: [0, -1] },
      params: {
        size: 124, leading: 1.04,
        lines: [
          { text: 'SLAM.', reveal: 'slam', unit: 'glyph', stagger: 0.06, at: { beat: 0 }, emphasis: ['slam.'] },
          { text: 'Blur into focus', reveal: 'blur', at: { beat: 1 }, weight: 500, width: 100 },
          { text: 'DECODE', reveal: 'scramble', unit: 'line', role: 'mono', weight: 700, at: { beat: 2 } },
          { text: 'Wipe it on', reveal: 'wipe', unit: 'line', at: { beat: 3 }, color: 'accent2' },
          { text: 'TRACKING IN', reveal: 'track', at: { beat: 4 }, weight: 300, width: 100 },
        ],
      },
    },
    {
      id: 'diff', scene: KineticText, length: len('diff'), transition: 'cut',
      params: {
        role: 'mono', align: 'left', x: 0.14, size: 76, reveal: 'typewriter', kicker: 'memory/people/user.md',
        lines: [{ text: 'Uses VS Code.', diff: '-' }, { text: 'Uses neovim. Has since 2019.', diff: '+', at: { beat: 3 } }],
      },
    },
    {
      id: 'counter', scene: Counter, length: len('counter'), transition: 'xfade',
      params: { value: 91.4, suffix: '%', label: 'Recall · LongMemEval', kicker: 'v7 · oracle split', land: { beat: 5 }, dur: 1.8, y: 0.45 },
    },
    {
      id: 'bars', scene: BarChart, length: len('bars'), transition: { kind: 'whip', dir: [0, 1] },
      params: {
        kicker: 'LongMemEval · accuracy', title: 'Measured the same way.', suffix: '%', y: 0.47,
        data: [{ label: 'Baseline', value: 44 }, { label: 'RAG', value: 61.2 }, { label: 'Long context', value: 72 }, { label: 'Lumen', value: 91.4, highlight: true }],
      },
    },
    {
      id: 'line', scene: LineChart, length: len('line'), transition: 'cut',
      params: {
        kicker: 'Weekly active teams', title: 'Growing every week.', every: 0.5,
        data: [120, 180, 260, 240, 410, 620, 890, 1284], labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'],
      },
    },
    {
      id: 'stats', scene: StatGrid, length: len('stats'), transition: { kind: 'whip', dir: [-1, 0] },
      params: {
        kicker: 'By the numbers', every: 0.5,
        stats: [{ value: 1284, label: 'Teams' }, { value: 91.4, suffix: '%', label: 'Recall' }, { value: 82, suffix: 'ms', label: 'p50 latency' }, { value: 4.9, suffix: '/5', label: 'Rating' }],
      },
    },
    {
      id: 'compare', scene: Compare, length: len('compare'), transition: 'cut',
      params: { kicker: 'Recall accuracy', from: { value: 44, label: 'v1' }, to: { value: 91.4, label: 'v7' }, suffix: '%', y: 0.46 },
    },
    {
      id: 'quote', scene: Quote, length: len('quote'), transition: 'dip',
      params: { sync: 'vo', quote: 'It feels like the tool finally remembers me.', by: 'Mara Ortiz', byline: 'Staff Engineer', emphasis: ['remembers'] },
    },
    {
      id: 'list', scene: BulletList, length: len('list'), transition: { kind: 'whip', dir: [1, 0] },
      params: { kicker: 'In the box', title: 'Everything a launch needs.', items: ['Kinetic type on the voice', 'Counters, charts and stats', 'Captions for every feed', 'One film, every format'], focus: true },
    },
    {
      id: 'features', scene: FeatureList, length: len('features'), transition: 'xfade',
      params: {
        title: 'Built for launch day.',
        items: [
          { title: 'On the beat', desc: 'Every cut and every word lands on the grid.', icon: 'spark' },
          { title: 'Any format', desc: 'Landscape, vertical and square from one film.', icon: 'plus' },
          { title: 'Deterministic', desc: 'Every frame a pure function of time.', icon: 'check' },
        ],
      },
    },
    {
      id: 'marquee', scene: Marquee, length: len('marquee'), transition: 'cut',
      params: { words: ['Kinetic type', 'Captions', 'Counters', 'Charts', 'End cards', 'Lower thirds'], emphasis: ['Captions', 'End cards'], rows: 3, size: 140 },
    },
    // a scene of the film's own, written on the kit's Scene2D (scenes/pulse.ts)
    { id: 'custom', scene: () => import('./scenes/pulse'), length: len('custom'), transition: 'cut', params: { word: 'Your scene' } },
    {
      id: 'end', scene: EndCard, length: len('end'), transition: { kind: 'zoom', scale: 3 },
      params: { name: 'Lumen', tagline: 'Launch films, written in code.', cta: 'Start building', url: 'lumen.dev/start', logo: 'assets/logo.svg' },
    },
  ],
  overlays: [
    { id: 'lower', scene: LowerThird, start: at('kinetic', 0.24), end: at('reveals', -0.12), params: { name: 'Mara Ortiz', title: 'Head of Product · Lumen' } },
    { id: 'captions', scene: Captions, start: at('counter', -0.1), end: at('quote'), params: { style: 'karaoke' } },
    { id: 'linecaps', scene: Captions, start: at('features', 0.06), end: at('marquee', -0.08), params: { style: 'line', box: true } },
    { id: 'watermark', scene: Watermark, params: { text: 'lumen.dev', corner: 'tr' } },
    { id: 'progress', scene: ProgressBar, params: { marks: ORDER.slice(1).map((s) => at(s)) } },
  ],
});
