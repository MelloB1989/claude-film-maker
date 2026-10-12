// The kit's type, overlays and data blocks, one shot each, at 110 BPM: every shot a block configured by params alone.
// The voiceover is written here as captions: the kinetic and quote shots land on its words (sync 'vo'), the Captions
// overlay lights it word by word over the data shots. No word starts inside a transition's window.
import { defineFilm } from '@engine/film';
import { BulletList, EndCard, FeatureList, KineticText, Marquee, Quote, TitleCard, LowerThird } from '@kit/text';
import { BarChart, Compare, Counter, LineChart, StatGrid } from '@kit/data';
import { Captions, ProgressBar, Watermark } from '@kit/overlays';
import config from './film.json';

/** A bar at 110 BPM (s); the shots' lengths below are in bars of the grid. */
const BAR = 240 / 110;
const LENGTHS = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2, 3];
/** Where each shot starts (film s), for the progress bar's chapter marks. */
const STARTS = LENGTHS.map((_, i) => LENGTHS.slice(0, i).reduce((a, b) => a + b, 0) * BAR);

export default defineFilm({
  ...config,
  vo: [
    { text: 'Ship your story in ninety seconds, flat.', start: 5.0, end: 7.2 },
    { text: 'Recall jumped to ninety-one point four percent.', start: 13.7, end: 16.3 },
    { text: 'Every model, measured the same way.', start: 18.1, end: 20.2 },
    { text: 'From forty-four, to ninety-one point four.', start: 31.0, end: 33.6 },
    { text: 'It feels like the tool finally remembers me.', start: 35.6, end: 38.2 },
    { text: 'Built for launch day, in every format you ship.', start: 44.6, end: 47.6 },
  ],
  scenes: [
    {
      id: 'title', scene: TitleCard, length: { bars: LENGTHS[0]! },
      params: { kicker: 'Lumen · v2', title: 'Launch films,\nwritten in code.', sub: 'Kinetic type, data and captions that land on the beat.' },
    },
    {
      id: 'kinetic', scene: KineticText, length: { bars: LENGTHS[1]! }, transition: { kind: 'whip', dir: [1, 0] },
      params: { sync: 'vo', text: 'Ship your story\nin ninety seconds, flat.', emphasis: ['ninety', 'seconds,'], size: 136, y: 0.44 },
    },
    {
      id: 'diff', scene: KineticText, length: { bars: LENGTHS[2]! }, transition: 'cut',
      params: {
        role: 'mono', align: 'left', x: 0.14, size: 76, reveal: 'typewriter', kicker: 'memory/people/user.md',
        lines: [{ text: 'Uses VS Code.', diff: '-' }, { text: 'Uses neovim. Has since 2019.', diff: '+', at: { beat: 3 } }],
      },
    },
    {
      id: 'counter', scene: Counter, length: { bars: LENGTHS[3]! }, transition: 'xfade',
      params: { value: 91.4, suffix: '%', label: 'Recall · LongMemEval', kicker: 'v7 · oracle split', land: { beat: 5 }, dur: 1.8, y: 0.45 },
    },
    {
      id: 'bars', scene: BarChart, length: { bars: LENGTHS[4]! }, transition: { kind: 'whip', dir: [0, 1] },
      params: {
        kicker: 'LongMemEval · accuracy', title: 'Measured the same way.', suffix: '%', y: 0.47,
        data: [{ label: 'Baseline', value: 44 }, { label: 'RAG', value: 61.2 }, { label: 'Long context', value: 72 }, { label: 'Lumen', value: 91.4, highlight: true }],
      },
    },
    {
      id: 'line', scene: LineChart, length: { bars: LENGTHS[5]! }, transition: 'cut',
      params: {
        kicker: 'Weekly active teams', title: 'Growing every week.', every: 0.5,
        data: [120, 180, 260, 240, 410, 620, 890, 1284], labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'],
      },
    },
    {
      id: 'stats', scene: StatGrid, length: { bars: LENGTHS[6]! }, transition: { kind: 'whip', dir: [-1, 0] },
      params: {
        kicker: 'By the numbers', every: 0.5,
        stats: [{ value: 1284, label: 'Teams' }, { value: 91.4, suffix: '%', label: 'Recall' }, { value: 82, suffix: 'ms', label: 'p50 latency' }, { value: 4.9, suffix: '/5', label: 'Rating' }],
      },
    },
    {
      id: 'compare', scene: Compare, length: { bars: LENGTHS[7]! }, transition: 'cut',
      params: { kicker: 'Recall accuracy', from: { value: 44, label: 'v1' }, to: { value: 91.4, label: 'v7' }, suffix: '%', y: 0.46 },
    },
    {
      id: 'quote', scene: Quote, length: { bars: LENGTHS[8]! }, transition: 'dip',
      params: { sync: 'vo', quote: 'It feels like the tool finally remembers me.', by: 'Mara Ortiz', byline: 'Staff Engineer', emphasis: ['remembers'] },
    },
    {
      id: 'list', scene: BulletList, length: { bars: LENGTHS[9]! }, transition: { kind: 'whip', dir: [1, 0] },
      params: { kicker: 'In the box', title: 'Everything a launch needs.', items: ['Kinetic type on the voice', 'Counters, charts and stats', 'Captions for every feed', 'One film, every format'], focus: true },
    },
    {
      id: 'features', scene: FeatureList, length: { bars: LENGTHS[10]! }, transition: 'xfade',
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
      id: 'marquee', scene: Marquee, length: { bars: LENGTHS[11]! }, transition: 'cut',
      params: { words: ['Kinetic type', 'Captions', 'Counters', 'Charts', 'End cards', 'Lower thirds'], emphasis: ['Captions', 'End cards'], rows: 3, size: 140 },
    },
    {
      id: 'end', scene: EndCard, length: { bars: LENGTHS[12]! }, transition: { kind: 'zoom', scale: 3 },
      params: { name: 'Lumen', tagline: 'Launch films, written in code.', cta: 'Start building', url: 'lumen.dev/start', logo: 'assets/logo.svg' },
    },
  ],
  overlays: [
    { id: 'lower', scene: LowerThird, start: 4.6, end: 8.6, params: { name: 'Mara Ortiz', title: 'Head of Product · Lumen' } },
    { id: 'captions', scene: Captions, start: 13.0, end: 34.9, params: { style: 'karaoke' } },
    { id: 'linecaps', scene: Captions, start: 43.7, end: 50.1, params: { style: 'line', box: true } },
    { id: 'watermark', scene: Watermark, params: { text: 'lumen.dev', corner: 'tr' } },
    { id: 'progress', scene: ProgressBar, params: { marks: STARTS.slice(1) } },
  ],
});
