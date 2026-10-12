// The kit's backgrounds, stacks and media, one shot each, at 110 BPM, every shot configured by params alone: the five
// backgrounds alone, then Stacks of a background under type, then screenshots and a clip framed (Image, Device, Video)
// over backgrounds. Media are this folder's assets/ (make-assets.py draws them); the clip plays from frames extracted by
// `cd app && bun scripts/media.ts --film gallery-bg`.
import { defineFilm } from '@engine/film';
import { Aurora, Grid, MeshGradient, Particles, Warp } from '@kit/bg';
import { Stack } from '@kit/stack';
import { Device, Image, Video } from '@kit/media';
import { KineticText, TitleCard } from '@kit/text';
import config from './film.json';

/** Two bars at 110 BPM. */
const len = { bars: 2 };

export default defineFilm({
  ...config,
  scenes: [
    // ---- the backgrounds alone
    { id: 'aurora', scene: Aurora, length: len, params: { pulse: 'downbeat' } },
    { id: 'mesh', scene: MeshGradient, length: len, transition: 'xfade', params: { pulse: 'downbeat' } },
    { id: 'grid', scene: Grid, length: len, transition: 'cut', params: { pulse: 'beat' } },
    { id: 'dots', scene: Grid, length: len, transition: 'cut', params: { mode: 'dots', pulse: 'beat' } },
    { id: 'particles', scene: Particles, length: len, transition: 'xfade' },
    { id: 'warp', scene: Warp, length: len, transition: 'cut', params: { pulse: 'beat' } },
    // ---- stacks: a background under type (layers above the first are transparent)
    {
      id: 'stack-aurora', scene: Stack, length: len, transition: { kind: 'whip', dir: [0, -1] },
      params: { layers: [{ scene: Aurora, params: { pulse: 'downbeat', intensity: 0.8 } }, { scene: TitleCard, params: { kicker: 'Stack', title: 'Type over light.' } }] },
    },
    {
      id: 'stack-grid', scene: Stack, length: len, transition: 'cut',
      params: { layers: [{ scene: Grid, params: { horizon: 0.36, pulse: 'beat' } }, { scene: KineticText, params: { text: 'Every frame,\na function of time.', emphasis: ['time.'], y: 0.36, size: 120 } }] },
    },
    {
      id: 'stack-mesh', scene: Stack, length: len, transition: 'xfade',
      params: {
        layers: [
          { scene: MeshGradient, params: { intensity: 0.8 } },
          { scene: Particles, params: { intensity: 0.7, focus: 0.2 }, blend: 'screen' },
          { scene: KineticText, params: { kicker: 'Three layers', text: 'Depth, for free.', size: 150 }, start: 0.3 },
        ],
      },
    },
    // ---- media
    {
      id: 'image', scene: Image, length: len, transition: 'cut',
      params: { src: 'assets/dashboard.jpg', from: { zoom: 1.35, x: -0.6, y: -0.4 }, to: { zoom: 1.12, x: 0.2, y: 0.1 }, entry: 'fade', entryDur: 0.5 },
    },
    {
      id: 'image-card', scene: Stack, length: len, transition: 'xfade',
      params: {
        layers: [
          { scene: MeshGradient, params: { intensity: 0.7, seed: 3 } },
          { scene: Image, params: { src: 'assets/dashboard.jpg', fit: 'contain', w: 0.66, h: 0.66, y: 0.52, radius: 16, shadow: 1, border: 'ruleStrong', entry: 'rise', delay: 0.15, drift: [0, -24], from: { zoom: 1 }, to: { zoom: 1 } } },
        ],
      },
    },
    {
      id: 'browser', scene: Stack, length: len, transition: { kind: 'whip', dir: [1, 0] },
      params: {
        layers: [
          { scene: Grid, params: { mode: 'dots', light: 1 } },
          { scene: Device, params: { device: 'browser', src: 'assets/dashboard.jpg', url: 'app.orbit.dev/overview', y: 0.53, delay: 0.1 } },
        ],
      },
    },
    {
      id: 'phone', scene: Stack, length: { bars: 3 }, transition: 'cut',
      params: {
        layers: [
          { scene: Aurora, params: { intensity: 0.7, height: 0.62 } },
          { scene: Device, params: { device: 'phone', src: 'assets/feed.jpg', x: 0.7, h: 0.84, scroll: [0, 1], scrollAt: [0.9, 5.6] } },
          { scene: KineticText, params: { kicker: 'Device', text: 'Your app,\nin its frame.', emphasis: ['frame.'], align: 'left', x: 0.1, y: 0.47, size: 120, maxWidth: 0.45 }, start: 0.3 },
        ],
      },
    },
    {
      id: 'video', scene: Stack, length: len, transition: 'xfade',
      params: {
        layers: [
          { scene: Particles, params: { intensity: 0.8 } },
          { scene: Video, params: { src: 'assets/clip.mp4', fit: 'contain', w: 0.7, h: 0.7, radius: 14, shadow: 1, border: 'ruleStrong', entry: 'scale' } },
        ],
      },
    },
    { id: 'warp-out', scene: Warp, length: len, transition: 'cut', params: { pulse: 'beat', boost: 5, center: [0.5, 0.45], seed: 2 } },
  ],
});
