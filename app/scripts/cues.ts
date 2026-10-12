// The cue sheet: runs a film's cue modules (film.ts `sfx.cues`) and its transitions' sounds on the film's data and
// writes films/<id>/data/sfx.json, then prints the cues per shot and per sound.
//   bun scripts/cues.ts [--film <id>]            write films/<id>/data/sfx.json
//   bun scripts/cues.ts [--film <id>] --check    fail if sfx.json is not what the data gives now (nothing written)
//   bun scripts/cues.ts [--film <id>] --plot     also draw out/<id>/review/sfx/cues.png: every cue over the words and the
//                                                beats, a row a shot (tools/' matplotlib)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { buildSheet, type Palette } from '../src/sfx/sheet';
import { Track, type TrackData } from '../src/engine/track';
import { sceneSpans } from '../src/engine/film';
import { ROOT, filmArg, loadFilm } from './film';

const argv = process.argv.slice(2);
const ID = filmArg(argv);
const F = await loadFilm(ID);
const OUT = path.join(F.dir, 'data/sfx.json');
const palettePath = path.join(F.dir, F.film.sfx?.palette ?? 'data/sfx_palette.json');
if (!existsSync(palettePath)) throw new Error(`no sound palette at ${path.relative(ROOT, palettePath)} (tools/ film-sfx-lib documents it)`);
const trackDir = path.join(F.dir, 'data/track');
const tracks: Record<string, Track> = {};
if (existsSync(trackDir)) {
  for (const f of new Bun.Glob('*.json').scanSync(trackDir)) tracks[f.replace(/\.json$/, '')] = new Track(JSON.parse(readFileSync(path.join(trackDir, f), 'utf8')) as TrackData);
}
const vo = F.vo;
const shots = sceneSpans(F.timeline);
const sheet = buildSheet({
  vo, audio: F.audio, shots, cues: F.film.sfx?.cues ?? {}, tracks, transitions: F.transitions, duration: F.duration,
  palette: JSON.parse(readFileSync(palettePath, 'utf8')) as Palette, transitionSounds: F.film.sfx?.transitions,
});
const json = JSON.stringify(sheet, null, 1) + '\n';
const rel = path.relative(ROOT, OUT);

if (argv.includes('--check')) {
  let now = '';
  try {
    now = readFileSync(OUT, 'utf8');
  } catch {}
  if (now !== json) {
    console.error(`${rel} is stale: run bun scripts/cues.ts --film ${ID}`);
    process.exit(1);
  }
  console.log(`${rel} is up to date`);
} else {
  writeFileSync(OUT, json);
  console.log(`wrote ${rel}: ${sheet.cues.length} cues, ${sheet.ducks.length} ducks`);
}

// ---- the counts
const pad = (s: string | number, n: number) => String(s).padEnd(n);
console.log('\nper scene (cues, of which keys; cues a second; without the keys)');
const scenes = [...shots.map((s) => s.id), ...new Set(sheet.cues.map((c) => c.scene).filter((s) => !shots.some((x) => x.id === s)))];
for (const id of scenes) {
  const cs = sheet.cues.filter((c) => c.scene === id), keys = cs.filter((c) => c.anchor.includes(':key:')).length;
  const span = shots.find((s) => s.id === id);
  const len = span ? span.end - span.start : 0;
  const rate = len ? `${(cs.length / len).toFixed(1)}/s; ${((cs.length - keys) / len).toFixed(1)}/s` : '(a transition)';
  console.log(`  ${pad(id, 18)}${pad(cs.length, 5)}${pad(keys, 5)}${rate}`);
}
for (const d of sheet.ducks) console.log(`  duck ${pad(d.id, 14)} ${d.bus} ${d.depth} dB at ${d.t.toFixed(3)} for ${d.dur.toFixed(3)} s (${d.anchor})`);
console.log('\nper sound');
const bySound = new Map<string, number>();
for (const c of sheet.cues) {
  const base = c.sound.replace(/_\d+$/, '');
  bySound.set(base, (bySound.get(base) ?? 0) + 1);
}
for (const [s, n] of [...bySound].sort((a, b) => b[1] - a[1])) console.log(`  ${pad(s, 18)}${n}`);

// ---- the plot
if (argv.includes('--plot')) {
  const dir = path.join(ROOT, 'out', ID, 'review/sfx');
  mkdirSync(dir, { recursive: true });
  const png = path.join(dir, 'cues.png');
  const py = `
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sheet = json.load(open(sys.argv[1])); vo = json.load(open(sys.argv[2])); au = json.load(open(sys.argv[3]))
scenes = vo["shots"]
fig, axes = plt.subplots(len(scenes), 1, figsize=(22, 2.0 * len(scenes)))
fam = {}
cmap = plt.get_cmap("tab20")
def colour(s):
    import re
    b = re.sub(r"_\\d+$", "", s)
    if b not in fam: fam[b] = cmap(len(fam) % 20)
    return fam[b]
for ax, sc in zip(axes, scenes):
    a, b = sc["start"] - 0.3, sc["end"] + 0.3
    ax.set_xlim(a, b); ax.set_ylim(-1.2, 1.6); ax.set_yticks([])
    ax.set_title(sc["id"], loc="left", fontsize=10)
    for t in au["beats"]:
        if a <= t <= b: ax.axvline(t, color="#ccc", lw=0.5)
    for t in au["downbeats"]:
        if a <= t <= b: ax.axvline(t, color="#888", lw=0.9)
    ax.axvline(sc["start"], color="k", lw=1.5); ax.axvline(sc["end"], color="k", lw=1.5)
    for l in vo["lines"]:
        for w in l["words"]:
            if w["end"] >= a and w["start"] <= b:
                ax.axvspan(w["start"], w["end"], ymin=0.0, ymax=0.18, color="#f3c6c6")
                ax.text(w["start"], -1.15, w["w"], fontsize=6)
    rows = {}
    for c in sheet["cues"]:
        if not (a <= c["t"] <= b): continue
        key = c["anchor"].find(":key:") >= 0
        y = -0.4 if key else rows.setdefault(c["sound"], len(rows) % 6 * 0.3)
        if c.get("dur"):
            ax.plot([c["t"], c["t"] + c["dur"]], [1.45, 1.45], color=colour(c["sound"]), lw=4)
            ax.text(c["t"], 1.5, c["sound"], fontsize=6)
        else:
            ax.plot([c["t"]], [y], "|" if key else "o", color=colour(c["sound"]), ms=6 if key else 5)
            if not key: ax.text(c["t"], y + 0.08, c["sound"], fontsize=6, rotation=20)
    for d in sheet["ducks"]:
        if a <= d["t"] <= b: ax.axvspan(d["t"], d["t"] + d["dur"], color="#6aa", alpha=0.4)
fig.tight_layout(); fig.savefig(sys.argv[4], dpi=70)
`;
  // the shots and words, and the grid, as the plot reads them
  const tmp = path.join(dir, 'plot-input');
  mkdirSync(tmp, { recursive: true });
  writeFileSync(path.join(tmp, 'vo.json'), JSON.stringify({ shots, lines: vo.lines }));
  writeFileSync(path.join(tmp, 'audio.json'), JSON.stringify({ beats: F.audio.beats, downbeats: F.audio.downbeats }));
  const r = Bun.spawnSync(['uv', 'run', '--project', path.join(ROOT, 'tools'), 'python', '-c', py, OUT, path.join(tmp, 'vo.json'), path.join(tmp, 'audio.json'), png], { stdout: 'inherit', stderr: 'inherit' });
  if (r.exitCode !== 0) throw new Error('the plot failed');
  console.log(`\nplotted ${path.relative(ROOT, png)}`);
}
