// 雨渡し — The Rain Ferry. Episode 1, 「一閃」. An original ink-wash anime short (STORY.md), made entirely in Blender:
// every shot a plate (blender/shots/<id>.py), graded along the film's colour arc by the look schedule (data/look.json),
// with the engine's paper, letterbox, subtitles, transitions and impact marks over it, Japanese voices and the mix.
import { defineFilm, type ShotSpec } from '@engine/film';
import { Stack } from '@kit/stack';
import { gradeKeys, Paper, PlateShot, PostKeys, SpeedLines, Subtitles, Words, type LookSchedule } from '@kit/anime';
import config from './film.json';

import schedule from './data/look.json';
import plates from './data/plates.json';

const look = schedule as unknown as LookSchedule;  // (JSON key lists type as number[][])

/** A Blender plate (blender/shots/<id>.py, or the one data/plates.json names) as a shot, the look schedule's grade over it
 * (data/look.json: the engine grades, the plate never bakes it in), then `layers` (the engine's marks the plate does not
 * make). A plate not rendered yet plays as a slate (PlateShot `missing`). */
const plate = (id: string, length: number, layers: Record<string, unknown>[] = [], more: Partial<ShotSpec> = {}): ShotSpec => {
  const name = (plates.plates as Record<string, string>)[id];  // data/plates.json: a scene made by another shot file
  return { id, scene: Stack, length, params: { layers: [{ scene: PlateShot, params: name ? { plate: name } : {} }, ...layers] }, ...more };
};
const post = (p: Record<string, unknown>) => ({ scene: PostKeys, params: p });

const scenes: ShotSpec[] = [
  // ---- the road ----
  plate('open', 6, [post({ fade: [[0, 1], [1.8, 0]] })]),
  plate('crow', 4),
  plate('step', 2.5),
  plate('walk', 5.5),
  plate('eyes', 3.5),
  // ---- the crossing ----
  plate('ferry', 5.5, [], { transition: { kind: 'ink', pre: 0.45, post: 0.5 } }),
  plate('ask', 5),
  plate('refuse', 4),
  plate('demand', 5.8),
  plate('tap', 6),
  plate('look', 4),
  plate('draw', 3.8),
  plate('rise', 4),
  // ---- the duel ----
  // the 3D cast's standoff (data/plates.json: shots/standoff_vroid.py); the drawn one stays: --plates standoff:standoff
  plate('standoff', 4.5),
  plate('eye-s', 2),
  plate('eye-t', 2),
  plate('freeze', 5),
  plate('charge', 2, [
    { scene: SpeedLines, params: { center: [0.55, 0.55], inner: 0.32, count: 120, intensity: 0.75 }, opacity: 0.9 },
    post({ shake: [[0, 4], [2, 12]] }),
  ]),
  // the impact frame: a white flash, an inverted strobe and a hard shake over the plate
  plate('flash', 1, [post({ flash: [[0, 1.6], [0.07, 0]], invert: { keys: [[0, 1], [0.2, 0], [0.29, 1], [0.42, 0]], step: true }, shake: [[0, 34], [0.7, 0]] })]),
  plate('after', 4.5),
  plate('fall', 4.5),
  plate('lesson', 5.5),
  plate('kneel', 4),
  // ---- the rain stops ----
  plate('board', 5.5, [], { transition: { kind: 'xfade', pre: 0.4, post: 0.4 } }),
  plate('light', 5),
  plate('cross', 6.5, [], { transition: { kind: 'xfade', pre: 0.5, post: 0.5 } }),
  // the calligraphy and its paper are the plate's; the type is set here, crisp at any size
  plate('title', 8, [
    { scene: Words, params: { lines: [
      { text: 'THE RAIN FERRY', x: 0.33, y: 0.47, size: 50, tracking: 0.32, color: '#1b1714', at: 2.6, dur: 1.6 },
      { text: '第一話「一閃」', role: 'jp', weight: 600, x: 0.33, y: 0.56, size: 28, tracking: 0.2, color: '#9b2c1f', at: 3.4, dur: 1.4 },
      { text: 'Episode 1 · One Flash', x: 0.33, y: 0.615, size: 24, tracking: 0.18, color: '#3d362e', at: 3.8, dur: 1.4 },
    ] } },
    post({ fade: [[6.6, 0], [8, 1]] }),
  ], { transition: { kind: 'ink', pre: 0.5, post: 0.5, color: '#0a0a0c', scale: 1.3 } }),
];

// windows of shots by id (back to back from 0), for the overlays that span several shots
const starts: Record<string, number> = {};
let t = 0;
for (const s of scenes) {
  starts[s.id] = t;
  t += s.length as number;
}
// the look schedule's grade under each shot's own marks (a mark's keys, the impact's strobe, win over it)
for (const s of scenes) {
  const layers = (s.params as { layers: Record<string, unknown>[] }).layers;
  layers.splice(1, 0, post(gradeKeys(look, s.id, starts[s.id]!, starts[s.id]! + (s.length as number), config.fps)));
}

export default defineFilm({
  ...config,
  fonts: { faces: [
    { family: 'Cormorant', url: 'fonts/CormorantGaramond.ttf', role: 'serif', weight: 500 },
    { family: 'Shippori-600', url: 'fonts/ShipporiMincho-SemiBold.ttf', role: 'jp', weight: 600 },
  ] },
  // the film-wide post; each shot's grade (saturation, contrast, warmth, lift, bloom, ...) is the look schedule's
  post: { ca: 0.25 },
  scenes,
  overlays: [
    // the duel in 2.39: the bars slide in on the standoff and out as she walks away
    { id: 'bars', scene: PostKeys, start: starts.standoff!, end: starts.kneel!,
      params: { letterboxIn: [0, 1.4, 2.39], letterboxOut: [starts.kneel! - starts.standoff! - 1.6, starts.kneel! - starts.standoff!] } },
    { id: 'paper', scene: Paper, start: 0, end: starts.title!, params: { intensity: 0.8, edge: 0.4, color: '#120e0a' } },
    { id: 'subs', scene: Subtitles, params: { size: 46, y: 0.85 } },
  ],
});
