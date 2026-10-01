// Scene `braid`: its times from the data, its camera the plate's (B08 renders through the Python port of this rig, from
// the same keys, data/look/b08_braid.json), its card hung where the plate's rope lands, and its names landing on the
// card's own cells.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { CameraRig } from '../engine/stage';
import { panelLayout } from '../engine/panels';
import { VO } from '../engine/vo';
import type { AudioData } from '../engine/audio';
import { ARMS, PHRASE, WORLD, ZIP_LEAD, braidKeys, braidTimes, cardTimes, landOf } from './braid-time';
import { CHIP, LBL, QUERY, chipText, flight, flightPoint, rowWord, splitLabel, steadyAt } from './braid-type';
import { Track, type TrackData } from '../engine/track';
import { cardSpec } from './braid';
import S from './braid.strings.json';
import TRACK from '../../../data/track/b08_braid.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const vo = new VO(JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8')));
const audio = JSON.parse(readFileSync(path.join(DATA, 'audio.json'), 'utf8')) as AudioData;
const scene = vo.scenes.find((s) => s.id === 'braid')!;
const T = braidTimes(vo, audio, scene.start, scene.end);
const C = cardTimes(T);
const track = new Track(TRACK as unknown as TrackData);
const raw = JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8'));
const L19 = raw.lines.find((l: { id: string }) => l.id === 'L19').words as { w: string; start: number }[];

describe('braid times', () => {
  test('are her line, word by word: each arm lands on her first word for it, in the order she names them', () => {
    expect(ARMS).toEqual(['lexical', 'body', 'cues']);
    expect(T.phrase.lexical.map((w) => w.start)).toEqual([L19[0]!.start, L19[1]!.start]);
    expect(T.phrase.body.map((w) => w.start)).toEqual([L19[2]!.start, L19[3]!.start, L19[4]!.start]);
    expect(T.phrase.cues.map((w) => w.start)).toEqual([L19[5]!.start, L19[6]!.start, L19[7]!.start]);
    expect([T.braided, T.into, T.one, T.answer]).toEqual([8, 9, 10, 11].map((i) => L19[i]!.start));
    expect(landOf(T, 'lexical')).toBeLessThan(landOf(T, 'body'));
    expect(landOf(T, 'body')).toBeLessThan(landOf(T, 'cues'));
    expect(T.zip).toBeCloseTo(T.braided - ZIP_LEAD, 12);
    for (const a of ARMS) expect(splitLabel(S[1 + ARMS.indexOf(a)]!).words.length).toBe(PHRASE[a].length);
  });

  test('land the card on the rope, its rows after it, the matched row on the downbeat of "answer", all in the scene', () => {
    expect(C.swing).toBeLessThan(T.one);
    expect(C.path.at).toBeGreaterThan(C.swing);
    expect(audio.downbeats).toContain(C.matched);
    expect(C.matched).toBeGreaterThanOrEqual(T.answer - 0.1);
    expect(C.mode).toBeGreaterThan(C.matched);
    expect(C.millis).toBeGreaterThan(C.mode);
    const note = Array.from(S[8]!).length;
    expect(C.note + (note - 1) / 100).toBeLessThan(T.end - 0.1); // the footnote is whole before the cut
    expect(C.millis).toBeLessThan(T.end - 0.3);
  });
});

describe('the plate and the scene share one camera', () => {
  test('the track covers the scene from its first frame to its last', () => {
    expect(TRACK.f0).toBe(Math.ceil(scene.start * 30));
    expect(TRACK.anchors.hinge.length).toBe(Math.ceil(scene.end * 30) - TRACK.f0);
  });

  test("the plate's tracked hinge and P0 are where the scene's rig projects them, within half a pixel, every frame", () => {
    const rig = new CameraRig(braidKeys(T));
    const cam = new THREE.PerspectiveCamera(30, 16 / 9, 0.005, 60);
    const hinge = new THREE.Vector3(...(WORLD.card.hinge as [number, number, number]));
    const p0 = new THREE.Vector3(...(WORLD.p0 as [number, number, number]));
    let worst = 0, seen = 0;
    for (const [name, at] of [['hinge', hinge], ['p0', p0]] as const) {
      (TRACK.anchors as Record<string, number[][]>)[name]!.forEach(([x, y, vis], i) => {
        rig.apply(cam, (TRACK.f0 + i) / 30);
        const p = at.clone().project(cam);
        const px = ((p.x + 1) / 2) * 1920, py = ((1 - p.y) / 2) * 1080;
        if (!vis || Math.abs(p.x) > 1.5 || Math.abs(p.y) > 1.5) return;
        seen++;
        worst = Math.max(worst, Math.hypot(px - x!, py - y!));
      });
    }
    expect(seen).toBeGreaterThan(200);
    expect(worst).toBeLessThan(0.5);
  });

  test("the plait's head lands on the hinge on 'one' (the tracked head and hinge meet)", () => {
    const i = Math.round(T.one * 30) - TRACK.f0;
    const [hx, hy] = TRACK.anchors.head[i]!, [gx, gy] = TRACK.anchors.hinge[i]!;
    expect(Math.hypot(hx! - gx!, hy! - gy!)).toBeLessThan(3);
  });
});

describe('the card and the names', () => {
  test("holds §11.6's fields, verbatim, at the card's size, each row landing at its moment", () => {
    const spec = cardSpec(C);
    expect(spec.lines.map((l) => l.text)).toEqual([S[4], S[5], S[6], S[7]]);
    expect(spec.lines.map((l) => l.at)).toEqual([C.path.at, C.matched, C.mode, C.millis]);
    // the matched row shows its three arms' words bright, exactly where the names land
    const row = S[5]!;
    expect([...spec.lines[1]!.spans!].sort((a, b) => a.from - b.from)).toEqual(['lexical', 'cue', 'body'].map((w) => ({ from: row.indexOf(w), to: row.indexOf(w) + w.length, tone: 'kw' })));
    const g = panelLayout({ kind: 'card', size: spec.size, lines: spec.lines });
    expect(spec.w).toBeGreaterThanOrEqual(g.textX + Array.from(S[4]!).length * g.adv + g.padX); // the path fits
    expect(spec.h).toBeGreaterThanOrEqual(g.bar + g.padTop + 4 * g.lineH + g.padBottom);
  });

  test("each arm's name lands on its own word in the matched row (cues on cue)", () => {
    const row = S[5]!;
    expect(rowWord('lexical', row)).toEqual({ word: 'lexical', col: row.indexOf('lexical') });
    expect(rowWord('body', row)).toEqual({ word: 'body', col: row.indexOf('body') });
    expect(rowWord('cues', row)).toEqual({ word: 'cue', col: row.indexOf('cue') });
    expect(() => rowWord('vector', row)).toThrow();
  });

  test('the names are taken into the braid on "braided", come out of its head, and land on the matched row as it lands', () => {
    for (const a of ARMS) {
      expect(flight(T.zip - 0.01, a, T.zip, C.matched)).toEqual({ absorb: 0, emerge: 0, land: 0 });
      const mid = flight(T.zip + 0.46 + ARMS.indexOf(a) * 0.05 - 1e-3, a, T.zip, C.matched);
      expect(mid.absorb).toBe(1); // wholly in the braid before it comes out of the head
      expect(mid.emerge).toBe(0);
      const f = flight(C.matched, a, T.zip, C.matched);
      expect(f).toEqual({ absorb: 1, emerge: 1, land: 1 });
      const P = (x: number, y: number) => ({ x, y });
      const p = flightPoint(f, P(0, 0), P(5, 5), P(10, 10), P(20, 20), P(60, 30), P(500, 300));
      expect(p.x).toBeCloseTo(500, 9);
      expect(p.y).toBeCloseTo(300, 9);
      expect(p.alpha).toBe(1);
      const gone = flightPoint(mid, P(0, 0), P(5, 5), P(10, 10), P(20, 20), P(60, 30), P(500, 300));
      expect(gone).toEqual({ x: 10, y: 10, alpha: 0 }); // at P0, taken in
      expect(flight(C.matched - 0.25, a, T.zip, C.matched).land).toBe(0); // riding the head until just before
    }
    // they come out of the head only once it has pulled clear of P0 on screen
    const track = new Track(TRACK as unknown as TrackData);
    const out = Math.min(...ARMS.map((a) => T.zip + 0.46 + ARMS.indexOf(a) * 0.05));
    const h = track.at('head', out), p0 = track.at('p0', out);
    expect(Math.hypot(h.x - p0.x, h.y - p0.y)).toBeGreaterThan(150);
  });

  test('labels stay inside title safe while they show, and the query too', () => {
    const w = (s: string) => Array.from(s).length * 0.6 * LBL.px;
    for (const a of ARMS) {
      const text = S[1 + ARMS.indexOf(a)]!;
      for (let f = Math.round(landOf(T, a) * 30); f < Math.round(T.zip * 30); f++) {
        const pos = chipText(a, steadyAt(track, `lbl_${a}`, f / 30), w(text)); // the chip hangs from the smoothed anchor
        expect(pos.x - LBL.padX).toBeGreaterThan(96);
        expect(pos.x + w(text) + LBL.padX).toBeLessThan(1920 - 96);
        expect(pos.base - LBL.px).toBeGreaterThan(96);
        expect(pos.base + LBL.padY).toBeLessThan(1080 - 96);
      }
      expect(CHIP[a]).toBeDefined();
    }
    expect(QUERY.right).toBeLessThanOrEqual(1920 - 96);
    expect(QUERY.right - Array.from(S[0]!).length * 0.6 * QUERY.px).toBeGreaterThan(96);
    expect(QUERY.base - QUERY.px).toBeGreaterThanOrEqual(96);
  });
});
