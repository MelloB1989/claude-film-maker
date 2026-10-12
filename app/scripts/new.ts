#!/usr/bin/env bun
// Start a new film from a template film:
//   bun scripts/new.ts <id> [--from starter] [--title "My Film"] [--format landscape|vertical|square|portrait|cinema]
//                           [--fps 30] [--theme noir|midnight|ember|aurora|mono|paper] [--bpm 120]
// copies films/<from>/ to films/<id>/ (its scenes, film.ts and film.json; not its rendered data, audio or out/), sets the
// id and the options in film.json, and prints how to play and render it.
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { FORMATS } from '../src/engine/config';
import { THEME_PRESETS } from '../src/engine/palette';

const argv = process.argv.slice(2);
const opt = (k: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const id = argv.find((a, i) => !a.startsWith('--') && !argv[i - 1]?.startsWith('--'));
const ROOT = path.resolve(import.meta.dir, '../..');

if (!id || !/^[a-z0-9][\w-]*$/.test(id)) {
  console.error('usage: bun scripts/new.ts <id> [--from starter] [--title T] [--format F] [--fps N] [--theme T] [--bpm N]\n(the id is a folder name: lowercase letters, digits, - and _)');
  process.exit(2);
}
const from = opt('from') ?? 'starter';
const src = path.join(ROOT, 'films', from), dst = path.join(ROOT, 'films', id);
if (!existsSync(path.join(src, 'film.ts'))) throw new Error(`no template film '${from}' (films/${from}/film.ts)`);
if (existsSync(dst)) throw new Error(`films/${id} exists already`);

const format = opt('format'), theme = opt('theme');
if (format && !(format in FORMATS)) throw new Error(`--format: one of ${Object.keys(FORMATS).join(', ')}`);
if (theme && !(theme in THEME_PRESETS)) throw new Error(`--theme: one of ${Object.keys(THEME_PRESETS).join(', ')}`);

// the film's own source, not what was rendered or recorded for it
const skip = new Set(['out', 'node_modules']);
const generated = /^(data\/(vo|audio|sfx|timeline|music_plan)\.json|audio\/(vo|music|mix|sfx\/lib)\b)/;
cpSync(src, dst, {
  recursive: true,
  filter: (p) => {
    const rel = path.relative(src, p).split(path.sep).join('/');
    return !rel || (!skip.has(rel.split('/')[0]!) && !generated.test(rel));
  },
});

const cfgPath = path.join(dst, 'film.json');
const cfg = JSON.parse(readFileSync(cfgPath, 'utf8'));
cfg.id = id;
cfg.title = opt('title') ?? id.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
if (format) cfg.format = format;
if (opt('fps')) cfg.fps = +opt('fps')!;
if (theme) cfg.theme = theme;
if (opt('bpm')) cfg.audio = { ...(cfg.audio ?? {}), bpm: +opt('bpm')! };
writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n');

console.log(`films/${id} (from ${from}): ${cfg.title}, ${cfg.format ?? 'landscape'} at ${cfg.fps ?? 30} fps, theme ${typeof cfg.theme === 'string' ? cfg.theme : 'custom'}

  play:    cd app && bunx vite   → http://localhost:5173/?film=${id}
  stills:  cd app && bun scripts/render.ts stills --film ${id} --t 1,2,3
  video:   cd app && bun scripts/render.ts video --film ${id} --samples auto
  edit:    films/${id}/film.ts (shots, transitions, overlays) and films/${id}/scenes/`);
