// The kit's blocks in a vertical (1080x1920) frame: the same params as the landscape gallery lay out for a phone. Bars
// turn into rows, stats into a 2x2 grid, the comparison stacks, feature cards make a column, captions sit clear of a
// feed's UI. The SafeArea guides show over the stats shot (a dev overlay: leave it out of a delivered film).
import { defineFilm } from '@engine/film';
import { EndCard, FeatureList, KineticText, TitleCard } from '@kit/text';
import { BarChart, Compare, Counter, StatGrid } from '@kit/data';
import { Captions, ProgressBar, SafeArea, Watermark } from '@kit/overlays';
import config from './film.json';

const BAR = 240 / 110;

export default defineFilm({
  ...config,
  vo: [
    { text: 'Your story, cut on the beat.', start: 4.9, end: 6.4 },
    { text: 'Teams shipping every single week.', start: 9.3, end: 11.2 },
    { text: 'Every model, measured the same way.', start: 13.6, end: 15.6 },
    { text: 'From forty-four to ninety-one point four.', start: 22.4, end: 24.8 },
  ],
  scenes: [
    { id: 'title', scene: TitleCard, length: { bars: 2 }, params: { kicker: 'New', title: 'Launch films, written in code.', sub: 'Every cut on the beat.' } },
    { id: 'vo', scene: KineticText, length: { bars: 2 }, transition: { kind: 'whip', dir: [1, 0] }, params: { sync: 'vo', text: 'Your story,\ncut on the beat.', emphasis: ['beat.'], size: 150, y: 0.42 } },
    { id: 'counter', scene: Counter, length: { bars: 2 }, transition: 'xfade', params: { value: 1284, style: 'flip', label: 'Teams shipping weekly', kicker: 'August', y: 0.42 } },
    { id: 'bars', scene: BarChart, length: { bars: 2 }, transition: 'cut', params: { kicker: 'Accuracy', title: 'Measured the same way.', suffix: '%', data: [{ label: 'Baseline', value: 44 }, { label: 'RAG', value: 61.2 }, { label: 'Long context', value: 72 }, { label: 'Lumen', value: 91.4, highlight: true }], y: 0.44 } },
    { id: 'stats', scene: StatGrid, length: { bars: 2 }, transition: { kind: 'whip', dir: [0, 1] }, params: { kicker: 'By the numbers', every: 0.5, stats: [{ value: 1284, label: 'Teams' }, { value: 91.4, suffix: '%', label: 'Recall' }, { value: 82, suffix: 'ms', label: 'p50 latency' }, { value: 4.9, suffix: '/5', label: 'Rating' }] } },
    { id: 'compare', scene: Compare, length: { bars: 2 }, transition: 'cut', params: { kicker: 'Recall accuracy', from: { value: 44, label: 'v1' }, to: { value: 91.4, label: 'v7' }, suffix: '%', y: 0.44 } },
    {
      id: 'features', scene: FeatureList, length: { bars: 3 }, transition: 'xfade',
      params: {
        title: 'Built for launch day.',
        items: [
          { title: 'On the beat', desc: 'Every cut and every word lands on the grid.', icon: 'spark' },
          { title: 'Any format', desc: 'Landscape, vertical and square from one film.', icon: 'plus' },
          { title: 'Deterministic', desc: 'Every frame a pure function of time.', icon: 'check' },
        ],
      },
    },
    { id: 'end', scene: EndCard, length: { bars: 3 }, transition: { kind: 'whip', dir: [0, 1] }, params: { name: 'Lumen', tagline: 'Launch films, written in code.', cta: 'Start building', url: 'lumen.dev/start', logo: 'assets/logo.svg' } },
  ],
  overlays: [
    { id: 'captions', scene: Captions, start: 8.7, end: 26.2, params: { style: 'karaoke' } },
    { id: 'pop', scene: Captions, start: 4.4, end: 8.7, params: { style: 'pop' } },
    { id: 'safe', scene: SafeArea, start: 8 * BAR, end: 10 * BAR },
    { id: 'watermark', scene: Watermark, params: { text: 'lumen.dev', corner: 'tl' } },
    { id: 'progress', scene: ProgressBar, params: { position: 'top' } },
  ],
});
