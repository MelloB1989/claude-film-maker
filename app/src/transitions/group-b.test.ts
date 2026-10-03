// Group B's cuts (Plan 3 Task 5): loom → diff, diff → cite, cite → braid, braid → merkle, against the film's own data:
// the specs validate on vo.json and her words, their windows keep clear of her onsets and of the read time, and each
// one's geometry comes from its scenes (loom's last snap, diff's ember as the camera renders it, cite's seam).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { transitionEntries, type TransitionSpec } from '../engine/transition';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { CameraRig } from '../engine/stage';
import { Panel } from '../engine/panels';
import { Track } from '../engine/track';
import { W, H } from '../engine/gl';
import { ROW, aimDive, cameraKeys, editorSpec, emberAt, emberAim, onScreen, punch } from '../scenes/diff';
import { docTime, timesOf } from '../scenes/diff-time';
import { lastSnapDir } from '../scenes/loom-time';
import { seamAxis } from '../scenes/cite';
import loomDiff from './loom-diff';
import diffCite from './diff-cite';
import citeBraid from './cite-braid';
import braidMerkle from './braid-merkle';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const FRAME = 1 / 30;
const specs: TransitionSpec[] = [loomDiff, diffCite, citeBraid, braidMerkle];
const entries = transitionEntries(specs, vo.scenes, vo.words);
const entry = (id: string) => entries.find((e) => e.id === id)!;
const span = (id: string) => vo.scenes.find((s) => s.id === id)!;
/** B's first frame of a cut. */
const firstFrame = (cut: number) => Math.ceil(cut * 30 - 1e-9);
const deg = (a: [number, number], b: [number, number]) => (Math.acos(Math.min(1, a[0] * b[0] + a[1] * b[1])) * 180) / Math.PI;

describe('group B: the windows', () => {
  test('the four validate on the real vo.json, her words included, each at its scene boundary', () => {
    expect(entries.map((e) => e.id)).toEqual(['loom-diff', 'diff-cite', 'cite-braid', 'braid-merkle']);
    for (const e of entries) expect(e.cut).toBe(span(e.spec.from).end);
  });

  test('loom → diff ends more than a frame before "Change"', () => {
    const cut = span('diff').start;
    const change = vo.words.find((w) => w.start >= cut && norm(w.w) === 'change')!;
    expect(loomDiff.post).toBeLessThan(change.start - cut - FRAME);
  });

  test('diff → cite pushes only after "diff." has started, and ends before the next word', () => {
    const e = entry('diff-cite');
    const diff = vo.words.filter((w) => w.start < e.cut && norm(w.w) === 'diff').at(-1)!;
    expect(e.start).toBeGreaterThan(diff.start);
    const next = vo.words.find((w) => w.start >= e.cut)!;
    expect(e.end + FRAME).toBeLessThan(next.start);
  });

  test("cite's settled chain and braid's result card keep their read time: pre ≤ 0.1 s", () => {
    expect(citeBraid.pre).toBeLessThanOrEqual(0.1);
    expect(braidMerkle.pre).toBeLessThanOrEqual(0.1);
  });

  test('every whip runs along a unit vector', () => {
    for (const s of specs.filter((x) => x.kind === 'whip')) expect(Math.hypot(...s.dir!)).toBeCloseTo(1, 12);
  });
});

describe('group B: the geometry comes from the scenes', () => {
  test("loom → diff whips on the way loom's last snap travelled (within 6°)", () => {
    const track = new Track(json('track/b05_loom.json'));
    expect(deg(loomDiff.dir!, lastSnapDir(track))).toBeLessThan(6);
  });

  // diff's own camera, built headless: its editor Panel, its keys, the rig, then the dive; the ember as the blade draws
  // it (its row as the Panel lays it out at the file's time), through that camera and the frame's punch-in (post zoom
  // about the centre)
  const s = span('diff'), T = timesOf(vo, audio, s.start, s.end);
  const edit = new Panel(editorSpec(T));
  const rig = new CameraRig(cameraKeys(T, (i, d) => edit.rowTop(i, d)));
  const emberShown = (t: number) => {
    const cam = new THREE.PerspectiveCamera(24, W / H, 0.01, 30);
    rig.apply(cam, t);
    const dive = aimDive(cam, t, T, emberAim());
    const [x, y] = onScreen(cam, emberAt(edit.rowTop(ROW.old, docTime(t, T))));
    const z = punch(t, T);
    return { dive, miss: Math.hypot(W / 2 + (x - W / 2) * z - diffCite.center![0], H / 2 + (y - H / 2) * z - diffCite.center![1]) };
  };

  test("diff → cite's centre is the ember where diff renders it at frame F − 1, within 1 px", () => {
    const e = emberShown((firstFrame(s.end) - 1) / 30);
    expect(e.dive).toBeGreaterThan(0.3); // well into the dive
    expect(e.miss).toBeLessThan(1);
  });

  test('the dive holds the ember on that centre through every frame of the push before the cut', () => {
    const e = entry('diff-cite');
    for (let f = Math.ceil(e.start * 30); f < firstFrame(e.cut); f++) expect(emberShown(f / 30).miss).toBeLessThan(1);
  });

  test("cite → braid whips along cite's seam as the camera's last stop frames it", () => {
    expect(citeBraid.dir).toEqual(seamAxis());
    expect(seamAxis()[1]).toBeGreaterThan(0.99); // the seam runs down the margin: the camera follows it down
  });

  test('braid → merkle tilts straight up: its streak is vertical', () => {
    expect(braidMerkle.dir).toEqual([0, -1]);
  });
});
