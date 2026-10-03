// Group C's cuts (Plan 3 Task 6): merkle → graph, graph → honest, honest → proof, against the film's own data: the specs
// validate on vo.json and her words; the dip is a dip with nothing after the cut; the dissolve is the film's only one;
// and the zoom-through's centre is merkle's file as merkle's own camera shows it at frame F − 1.
import { describe, expect, test } from 'bun:test';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { specOf, transitionEntries, type TransitionModule, type TransitionSpec } from '../engine/transition';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { CameraRig } from '../engine/stage';
import { W, H } from '../engine/gl';
import { timesOf as merkleTimes } from '../scenes/merkle-time';
import { timesOf as graphTimes } from '../scenes/graph-time';
import { aimAt, diveAt, divePath, landingAim, onScreen, rigKeys } from '../scenes/merkle-camera';
import { drainAt } from '../scenes/graph';
import { HANDLES as HONEST_HANDLES, quietAt } from '../scenes/honest';
import merkleGraph from './merkle-graph';
import graphHonest from './graph-honest';
import honestProof from './honest-proof';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const FRAME = 1 / 30;
const specs: TransitionSpec[] = [merkleGraph, graphHonest, honestProof];
const entries = transitionEntries(specs, vo.scenes, vo.words);
const entry = (id: string) => entries.find((e) => e.id === id)!;
const span = (id: string) => vo.scenes.find((s) => s.id === id)!;
/** B's first frame of a cut. */
const firstFrame = (cut: number) => Math.ceil(cut * 30 - 1e-9);

describe('group C: the windows', () => {
  test('the three validate on the real vo.json, her words included, each at its scene boundary', () => {
    expect(entries.map((e) => e.id)).toEqual(['merkle-graph', 'graph-honest', 'honest-proof']);
    for (const e of entries) expect(e.cut).toBe(span(e.spec.from).end);
  });

  test('graph → honest is a dip with nothing after the cut: honest comes in hard on its own ink', () => {
    expect(graphHonest.kind).toBe('dip');
    expect(graphHonest.post).toBe(0);
  });

  test("honest → proof is the only 'xfade' among the film's transition files", async () => {
    const dir = import.meta.dir;
    const files = readdirSync(dir).filter((f) => f.endsWith('.ts') && !f.startsWith('_') && !f.endsWith('.test.ts'));
    expect(files).toContain('honest-proof.ts');
    const xfades: string[] = [];
    for (const f of files) {
      const s = specOf((await import(path.join(dir, f))) as TransitionModule, vo);
      if (s.kind === 'xfade') xfades.push(f);
    }
    expect(xfades).toEqual(['honest-proof.ts']);
  });

  test('merkle → graph starts after "fifty." and ends more than a frame before "I"', () => {
    const e = entry('merkle-graph');
    const fifty = vo.words.filter((w) => w.start < e.cut && norm(w.w) === 'fifty').at(-1)!;
    expect(e.start).toBeGreaterThan(fifty.start);
    const next = vo.words.find((w) => w.start >= e.cut)!;
    expect(e.end + FRAME).toBeLessThan(next.start);
  });

  test('the dissolve ends before "Forty-four…", so the band of light across 44 is proof\'s own', () => {
    const e = entry('honest-proof');
    const forty = vo.words.find((w) => w.start >= e.cut)!;
    expect(norm(forty.w)).toBe('fortyfour');
    expect(e.end + FRAME).toBeLessThan(forty.start);
  });

  test('honest runs into its tail under the dissolve, within the handles it declares', () => {
    expect(honestProof.fromMode).toBe('run');
    expect(HONEST_HANDLES.tail).toBeGreaterThanOrEqual(honestProof.post);
  });

  test('the dip and the dissolve are slower than every whip and zoom around them', () => {
    const quick = [merkleGraph];
    const len = (s: TransitionSpec) => s.pre + s.post;
    for (const q of quick) {
      expect(len(honestProof)).toBeGreaterThan(len(q));
    }
    // the dip's drain (graph.ts) starts before the dip: the light leaves first
    const g = span('graph'), T = graphTimes(vo, audio, g.start, g.end);
    expect(T.drain).toBeGreaterThan(T.found);
    expect(T.drain).toBeLessThan(entry('graph-honest').start);
    expect(drainAt(T.drain, T).moss).toBe(0);
    expect(drainAt(T.end - 1e-6, T).light).toBeGreaterThan(0.99);
  });

  test("honest's hush starts inside the dissolve's lead-in and is whole just after the cut", () => {
    const h = span('honest'), e = entry('honest-proof');
    expect(quietAt(e.start, { end: h.end })).toBe(0);
    expect(quietAt(e.end, { end: h.end })).toBe(1);
  });
});

describe('group C: the geometry comes from the scenes', () => {
  // merkle's own camera, built headless: the dive path, the crane's keys from her clock, the dive into the file
  const s = span('merkle'), T = merkleTimes(vo, audio, s.start, s.end);
  const { P } = divePath();
  const rig = new CameraRig(rigKeys(T, P));
  const fileShown = (t: number) => {
    const cam = new THREE.PerspectiveCamera(34, W / H, 0.004, 20);
    aimAt(cam, rig, t, T, P[4]!);
    const [x, y] = onScreen(cam, P[4]!);
    return { dive: diveAt(t, T), miss: Math.hypot(x - merkleGraph.center![0], y - merkleGraph.center![1]), x, y };
  };

  test("merkle → graph's centre is merkle's landed file where merkle renders it at frame F − 1, within 1 px", () => {
    const f = fileShown((firstFrame(s.end) - 1) / 30);
    expect(f.dive).toBeGreaterThan(0.2); // well into the dive
    expect(f.miss).toBeLessThan(1);
    expect(merkleGraph.center).toEqual(landingAim(P).screen);
  });

  test('the file is on screen and settles onto the centre through the push (each frame no further than the last)', () => {
    const e = entry('merkle-graph');
    let last = Infinity;
    for (let f = Math.ceil(e.start * 30); f < firstFrame(e.cut); f++) {
      const p = fileShown(f / 30);
      expect(p.x).toBeGreaterThan(0); expect(p.x).toBeLessThan(W);
      expect(p.y).toBeGreaterThan(0); expect(p.y).toBeLessThan(H);
      expect(p.miss).toBeLessThanOrEqual(last + 1e-9);
      last = p.miss;
    }
  });

  test('the dive keeps the file where it is in the frame: driving along the line of sight moves it < 0.01 px', () => {
    const t = s.end - 0.05;
    const cam = new THREE.PerspectiveCamera(34, W / H, 0.004, 20);
    rig.apply(cam, t);
    const [x0, y0] = onScreen(cam, P[4]!);
    const f = fileShown(t);
    expect(f.dive).toBeGreaterThan(0);
    expect(Math.hypot(f.x - x0, f.y - y0)).toBeLessThan(0.01);
  });
});
