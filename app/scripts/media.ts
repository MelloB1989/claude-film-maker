#!/usr/bin/env bun
// Extract a film's clips into frames for the Video and Device blocks (kit/media), at the film's frame rate:
//   bun scripts/media.ts --film <id> [--src assets/clip.mp4] [--force] [--q 3]
// Every clip in films/<id>/assets/ (mp4, m4v, mov, webm, mkv), or the one --src names, becomes
// out/<id>/media/<name>/0000.jpg … (frame 0 first) and meta.json { fps, count, width, height, src }. A clip whose frames
// are newer than it is skipped (--force redoes it). out/ is never committed; rerun after replacing a clip.
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { isVideo, mediaName } from '../src/kit/media/paths';

const argv = process.argv.slice(2);
const opt = (k: string, d?: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const flag = (k: string) => argv.includes(`--${k}`);
const FILM = opt('film') ?? process.env.FILM ?? 'showcase';
if (!/^[\w-]+$/.test(FILM)) throw new Error(`--film takes a film id (films/<id>/), got '${FILM}'`);
const ROOT = path.resolve(import.meta.dir, '..', '..');
const DIR = path.join(ROOT, 'films', FILM);
if (!existsSync(path.join(DIR, 'film.json'))) throw new Error(`no film '${FILM}': films/${FILM}/film.json does not exist`);
const fps: number = JSON.parse(readFileSync(path.join(DIR, 'film.json'), 'utf8')).fps ?? 30;

/** Every clip under assets/, as paths relative to the film's folder. */
function clips(dir = path.join(DIR, 'assets'), rel = 'assets'): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((n) => {
    const p = path.join(dir, n), r = `${rel}/${n}`;
    return statSync(p).isDirectory() ? clips(p, r) : isVideo(n) ? [r] : [];
  });
}

const srcs = opt('src') ? [opt('src')!] : clips();
if (!srcs.length) console.log(`films/${FILM}/assets has no clips`);
for (const src of srcs) {
  const file = path.join(DIR, src);
  if (!existsSync(file)) throw new Error(`no clip ${path.relative(ROOT, file)}`);
  const name = mediaName(src), out = path.join(ROOT, 'out', FILM, 'media', name), meta = path.join(out, 'meta.json');
  if (!flag('force') && existsSync(meta) && statSync(meta).mtimeMs >= statSync(file).mtimeMs) {
    const m = JSON.parse(readFileSync(meta, 'utf8'));
    if (m.fps === fps) {
      console.log(`${src}: up to date (${m.count} frames at ${fps} fps)`);
      continue;
    }
  }
  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });
  // at the film's frame rate (frames dropped or doubled to land on its grid), full range, high quality JPEG
  const ff = Bun.spawnSync(['ffmpeg', '-y', '-loglevel', 'error', '-i', file, '-vf', `fps=${fps}`, '-start_number', '0', '-q:v', opt('q', '3')!, path.join(out, '%04d.jpg')], { stdout: 'inherit', stderr: 'inherit' });
  if (ff.exitCode !== 0) throw new Error(`ffmpeg failed on ${src} (exit ${ff.exitCode})`);
  const frames = readdirSync(out).filter((n) => /^\d{4}\.jpg$/.test(n)).sort();
  const probe = Bun.spawnSync(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', file]);
  const [width, height] = probe.stdout.toString().trim().split('x').map(Number);
  writeFileSync(meta, JSON.stringify({ fps, count: frames.length, width, height, src }, null, 2) + '\n');
  console.log(`${src}: ${frames.length} frames at ${fps} fps → ${path.relative(ROOT, out)}/`);
}
