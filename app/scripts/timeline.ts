#!/usr/bin/env bun
// Resolve a film's timeline and write it where Blender and the audio tools read scene windows:
//   bun scripts/timeline.ts [--film <id>] [--print]
// writes films/<id>/data/timeline.json: { fps, duration, format: [w, h], scenes: [{ id, start, end }], overlays: [...],
// transitions: [{ id, kind, cut, start, end }] }. --print only prints it.
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { FPS, H, W } from '../src/engine/config';
import { ROOT, filmArg, loadFilm } from './film';

const id = filmArg();
const f = await loadFilm(id);
const win = (e: { id: string; start: number; end: number }) => ({ id: e.id, start: e.start, end: e.end });
const out = {
  fps: FPS,
  duration: f.duration,
  format: [W, H],
  scenes: f.timeline.filter((e) => e.kind !== 'overlay').map(win),
  overlays: f.timeline.filter((e) => e.kind === 'overlay').map(win),
  transitions: f.transitions.map((t) => ({ id: t.id, kind: t.spec.kind, cut: t.cut, start: t.start, end: t.end })),
};
const json = JSON.stringify(out, null, 1) + '\n';
if (process.argv.includes('--print')) console.log(json);
else {
  const p = path.join(f.dir, 'data', 'timeline.json');
  mkdirSync(path.dirname(p), { recursive: true });
  writeFileSync(p, json);
  console.log(`wrote ${path.relative(ROOT, p)}: ${out.scenes.length} shots, ${out.transitions.length} transitions, ${f.duration.toFixed(3)} s`);
}
