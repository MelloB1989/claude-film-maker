// The showcase: the engine's own launch film, made from kit blocks configured by params alone (no scene code). Every
// shot is a length in bars of the film's grid (120 BPM, a bar is 2 s). The captions are timed from each shot's start
// (at()), so shots can be re-cut without re-timing them, and no word starts inside a transition's window.
import { defineFilm } from '@engine/film';
import { EndCard, KineticText } from '@kit/text';
import { Counter, StatGrid } from '@kit/data';
import { Captions, ProgressBar, Watermark } from '@kit/overlays';
import { Cards3D, GlyphCloud, Hero3D, Logo3D, Panel3D } from '@kit/3d';
import { Aurora, Grid, MeshGradient, Particles } from '@kit/bg';
import { Stack } from '@kit/stack';
import { Device } from '@kit/media';
import { BeatFx } from '@kit/fx';
import config from './film.json';

/** A bar at the film's tempo (s). The shots in order and their lengths in bars. */
const BAR = 240 / config.audio.bpm;
const LENGTHS = { cloud: 2, hero: 2, frame: 2, code: 3, formats: 2, stats: 2, blur: 2, player: 2, cards: 3, logo: 2, end: 2 } as const;
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
    { text: 'Scrub it, tweak it, render it.', start: at('player', 0.5), end: at('player', 2.9) },
  ],
  scenes: [
    {
      // a field of glyphs drifting past the lens; on the fourth beat they fly into the film's first words
      id: 'cloud', scene: GlyphCloud, length: len('cloud'),
      params: { resolve: 'frame by frame', resolveAt: { beat: 3 }, resolveSize: 150, sparkle: 0.05 },
    },
    {
      // the camera dives through the resolved words into the title: extruded, slammed in a word a beat
      id: 'hero', scene: Hero3D, length: len('hero'), transition: { kind: 'zoom', scale: 3 }, look: 'cinematic',
      params: { text: 'Films,\nwritten in code.', emphasis: ['code.'], sync: 'beats', reveal: 'slam', exit: 'blow', exitDur: 0.45, whip: 'left' },
    },
    {
      // type over light: an aurora under a line that lands on its words
      id: 'frame', scene: Stack, length: len('frame'), transition: { kind: 'whip', dir: [-1, 0] },
      params: {
        layers: [
          { scene: Aurora, params: { intensity: 0.85, pulse: 'downbeat' } },
          { scene: KineticText, params: { sync: 'vo', text: 'Every frame is\na function of time.', emphasis: ['time.'], size: 132 } },
        ],
      },
    },
    {
      // the tools themselves: a terminal starts a film and renders it while the editor writes its first shot
      id: 'code', scene: Panel3D, length: len('code'), transition: 'slide',
      params: {
        layout: 'pair',
        panels: [
          { kind: 'terminal', title: 'zsh', rows: 7, type: 0.4, lines: [
            { text: '$ bun scripts/new.ts launch --theme ember', kind: 'cmd' },
            { text: 'films/launch (from starter): Launch, landscape', kind: 'out' },
            { text: '$ bun scripts/render.ts video --film launch', kind: 'cmd' },
            { text: '✔ out/launch/launch.mp4', kind: 'out' },
          ] },
          { kind: 'editor', title: 'films/launch/film.ts', lang: 'ts', rows: 7, type: { beat: 4 }, enter: 0.3, lines: [
            { text: 'scenes: [' },
            { text: "  { id: 'open', scene: Hero3D," },
            { text: "    params: { text: 'Launch.' } }," },
            { text: '],' },
          ] },
        ],
        highlight: { panel: 1, line: 1, at: { beat: 9 }, color: 'accent' },
      },
    },
    {
      // one film, every format: the specimen lands a line a beat over a floor grid running to the horizon
      id: 'formats', scene: Stack, length: len('formats'), transition: { kind: 'wipe', dir: 0, edge: 'accent' }, look: 'neon',
      params: {
        layers: [
          { scene: Grid, params: { horizon: 0.62, pulse: 'beat', intensity: 0.8 } },
          { scene: KineticText, params: {
            size: 118, leading: 1.02, y: 0.4, exit: 'rise',
            lines: [
              { text: 'Landscape.', reveal: 'slam', unit: 'glyph', stagger: 0.04, at: { beat: 0 } },
              { text: 'Vertical.', reveal: 'blur', at: { beat: 1 }, weight: 500 },
              { text: 'Square.', reveal: 'wipe', unit: 'line', at: { beat: 2 }, color: 'accent2' },
              { text: 'One film.', reveal: 'rise', at: { beat: 3 }, emphasis: ['film.'] },
            ],
          } },
        ],
      },
    },
    {
      id: 'stats', scene: Stack, length: len('stats'), transition: 'cut',
      params: {
        layers: [
          { scene: Particles, params: { intensity: 0.7 } },
          { scene: StatGrid, params: {
            kicker: 'One engine', every: 0.5, y: 0.45,
            stats: [{ value: 5, label: 'Formats' }, { value: 6, label: 'Themes' }, { value: 9, label: 'Type reveals' }, { value: 4, suffix: 'K', label: 'Masters' }],
          } },
        ],
      },
    },
    {
      id: 'blur', scene: Stack, length: len('blur'), transition: { kind: 'iris', edge: 'accent2' },
      params: {
        layers: [
          { scene: MeshGradient, params: { intensity: 0.45 } },
          { scene: Counter, params: { value: 324, label: 'Motion-blur sub-frames, at most', kicker: 'adaptive sampling', land: { beat: 5 }, dur: 1.6, y: 0.45 } },
        ],
      },
    },
    {
      // the player, in a browser window floating over soft light
      id: 'player', scene: Stack, length: len('player'), transition: 'glitch', look: 'clean',
      params: {
        layers: [
          { scene: MeshGradient, params: { intensity: 0.6 } },
          { scene: Device, params: { device: 'browser', src: 'assets/player.jpg', url: 'localhost:5173/?film=showcase', w: 0.6, y: 0.43 } },
        ],
      },
    },
    {
      id: 'cards', scene: Cards3D, length: len('cards'), transition: { kind: 'spin', angle: 90 },
      params: {
        layout: 'carousel', every: 2,
        cards: [
          { title: 'On the beat', lines: ['Cuts, words and hits', 'land on the grid.'] },
          { title: 'In 3D', lines: ['Extruded type, panels,', 'glyph clouds, logos.'] },
          { title: 'Any format', lines: ['Landscape, vertical', 'and square.'] },
          { title: 'With sound', lines: ['Voice, score, effects', 'and the final mix.'] },
          { title: 'Deterministic', lines: ['Every frame a pure', 'function of time.'] },
        ],
      },
    },
    {
      id: 'logo', scene: Logo3D, length: len('logo'), transition: 'flash',
      params: { tagline: 'Films, written in code.', reveal: 'spin' },
    },
    {
      id: 'end', scene: EndCard, length: len('end'), transition: 'xfade',
      params: { name: 'Film Maker', tagline: 'Films, written in code.', cta: 'bun scripts/new.ts', url: 'github.com/MelloB1989/claude-film-maker', logo: 'assets/logo.svg', delay: 0.15 },
    },
  ],
  overlays: [
    // hits on the grid: the title punches in on every beat; the formats and stats kick, shaking on the downbeat
    { id: 'hits', scene: BeatFx, start: at('hero'), end: at('frame', -0.3), params: { punch: true } },
    { id: 'kicks', scene: BeatFx, start: at('formats', 0.3), end: at('blur', -0.3), params: { punch: { amount: 0.02 }, shake: { on: 'downbeat', amount: 5 } } },
    { id: 'captions', scene: Captions, start: at('stats', -0.1), end: at('cards'), params: { style: 'karaoke' } },
    { id: 'watermark', scene: Watermark, start: at('frame'), end: at('logo'), params: { text: 'claude-film-maker', corner: 'tr' } },
    { id: 'progress', scene: ProgressBar, params: { marks: ORDER.slice(1).map((s) => at(s)) } },
  ],
});
