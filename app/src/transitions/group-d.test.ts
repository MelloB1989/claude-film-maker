// Group D's cuts (Plan 3 Task 7): proof → connect, connect → anywhere, anywhere → weave, against the film's own data:
// the specs validate on vo.json and her words, their windows keep clear of her onsets and of the cards' read time, and
// each one's geometry comes from its scenes (the carousel's turn, the face it lands, the dive's crossing, B15's mark).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { transitionEntries, type TransitionSpec } from '../engine/transition';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { Panel } from '../engine/panels';
import { Track } from '../engine/track';
import { W, H } from '../engine/gl';
import { EXIT as PROOF_EXIT } from '../scenes/proof';
import { timesOf as proofTimes } from '../scenes/proof-time';
import { ARRIVE as CONNECT_ARRIVE, HANDLES as CONNECT_HANDLES, frontFaceAt } from '../scenes/connect';
import { EXIT, STEP, timesOf as connectTimes, turnAt } from '../scenes/connect-time';
import { copyOf, faceOf } from '../scenes/connect-cards';
import CONNECT_S from '../scenes/connect.strings.json';
import {
  ARRIVE as ANYWHERE_ARRIVE, DIVE, connectLanding, diveAim, diveCamera, diveTarget, onScreen, terminalAt, terminalBox, terminalCorners, terminalSpec,
} from '../scenes/anywhere';
import { timesOf as anywhereTimes } from '../scenes/anywhere-time';
import proofConnect from './proof-connect';
import connectAnywhere from './connect-anywhere';
import anywhereWeaveOf from './anywhere-weave';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const FRAME = 1 / 30;
const anywhereWeave = anywhereWeaveOf(vo);
const specs: TransitionSpec[] = [proofConnect, connectAnywhere, anywhereWeave];
const words = vo.lines.flatMap((l) => l.words);
const entries = transitionEntries(specs, vo.scenes, words);
const span = (id: string) => vo.scenes.find((s) => s.id === id)!;
/** B's first frame of a cut. */
const firstFrame = (cut: number) => Math.ceil(cut * 30 - 1e-9);

describe('group D: the windows', () => {
  test('the three validate on the real vo.json, her words included, each at its scene boundary', () => {
    expect(entries.map((e) => e.id)).toEqual(['proof-connect', 'connect-anywhere', 'anywhere-weave']);
    for (const e of entries) expect(e.cut).toBe(span(e.spec.from).end);
  });

  test('anywhere → weave ends more than a frame before "GitLoom."', () => {
    const cut = span('weave').start;
    const gitloom = words.find((w) => w.start >= cut && norm(w.w) === 'gitloom')!;
    expect(anywhereWeave.post).toBeLessThan(gitloom.start - cut - FRAME);
  });

  test("connect's cards keep their read: connect → anywhere's pre ≤ 0.1 s", () => {
    expect(connectAnywhere.pre).toBeLessThanOrEqual(0.1);
  });

  test('the whips run along unit vectors, both camera right', () => {
    for (const s of [proofConnect, connectAnywhere]) {
      expect(s.kind).toBe('whip');
      expect(Math.hypot(...s.dir!)).toBeCloseTo(1, 12);
      expect(s.dir).toEqual([1, 0]);
    }
    expect(anywhereWeave.kind).toBe('zoom');
  });

  test("connect runs on through the window only inside its handle; weave's plate holds", () => {
    expect(connectAnywhere.fromMode).toBe('run');
    expect(CONNECT_HANDLES.tail).toBeGreaterThanOrEqual(connectAnywhere.post);
    expect(anywhereWeave.toMode ?? 'hold').toBe('hold');
  });
});

describe('proof → connect: the light leads the whip', () => {
  const s = span('proof'), T = proofTimes(vo, audio, s.start, s.end);
  test("proof's swing is the window's pre, and its last band runs from the last downbeat to the cut", () => {
    expect(proofConnect.pre).toBe(PROOF_EXIT.lead);
    expect(T.shine).not.toBeNull();
    expect(audio.downbeats.some((d) => Math.abs(d - T.shine!) < 1e-9)).toBe(true);
    expect(T.shine!).toBeLessThan(s.end - proofConnect.pre);
  });
  test("connect's arrival brakes before her first word", () => {
    const one = words.find((w) => w.start >= s.end)!;
    expect(s.end + CONNECT_ARRIVE.brake).toBeLessThan(one.start);
  });
});

describe('connect → anywhere: the carousel turns into the whip', () => {
  const cs = span('connect'), CT = connectTimes(vo, audio, cs.start, cs.end);
  const turn = (t: number) => turnAt(t, CT.cards, CT.end);
  const vel = (t: number) => (turn(t + 1e-4) - turn(t - 1e-4)) / 2e-4;

  test("the whip's dir has the sign of the carousel's last turn (its faces travel left, the camera right)", () => {
    const e = entries.find((x) => x.id === 'connect-anywhere')!;
    expect(Math.sign(connectAnywhere.dir![0])).toBe(Math.sign(vel(e.cut)));
    expect(vel(e.cut)).toBeGreaterThan(0);
    // it starts as the window opens, after the last card has landed and held, and comes round a whole face
    expect(turn(e.start - 1e-6)).toBeCloseTo(CT.cards.length * STEP, 12);
    expect(turn(e.end)).toBeCloseTo((CT.cards.length + 1) * STEP, 12);
    expect(e.start - CT.cards.at(-1)!).toBeGreaterThan(0.5 - 1e-9);
  });

  test("anywhere's terminal lands where connect's face stood: centred on it and as wide (±8 px), from frame F + 1 on", () => {
    const as = span('anywhere'), AT = anywhereTimes(vo, audio, as.start, as.end);
    const corners = terminalCorners(terminalBox(new Panel(terminalSpec(AT))));
    const land = connectLanding(vo, audio);
    const face = frontFaceAt(cs.end - EXIT.lead, CT, faceOf(copyOf(CONNECT_S as string[])));
    expect(land.centre).toEqual(face.centre);
    const F = firstFrame(as.start);
    // turning in (foreshortened, so narrower), but centred where the face stood
    for (let f = F + 1; f / 30 < as.start + ANYWHERE_ARRIVE.brake; f++) {
      const q = terminalAt(f / 30, AT, corners, land);
      expect(Math.hypot(q.centre[0] - face.centre[0], q.centre[1] - face.centre[1])).toBeLessThan(8);
      expect(q.width).toBeLessThan(face.width + 8);
    }
    // and landed: centred on it and as wide
    const q = terminalAt(as.start + ANYWHERE_ARRIVE.brake, AT, corners, land);
    expect(Math.hypot(q.centre[0] - face.centre[0], q.centre[1] - face.centre[1])).toBeLessThan(8);
    expect(Math.abs(q.width - face.width)).toBeLessThan(8);
  });
});

describe('anywhere → weave: the dive and the zoom are one move', () => {
  const as = span('anywhere'), AT = anywhereTimes(vo, audio, as.start, as.end);
  const e = entries.find((x) => x.id === 'anywhere-weave')!;
  const aim = diveAim(AT.end), target = diveTarget(AT, aim);

  test("the zoom's centre is B15's mark centre on weave's first frame (its track), where its threads weave the mark", () => {
    const track = new Track(json('track/b15_weave.json'));
    const c = track.at('mark_c', span('weave').start);
    expect(anywhereWeave.center![0]).toBeCloseTo(c.x, 9);
    expect(anywhereWeave.center![1]).toBeCloseTo(c.y, 9);
    expect(anywhereWeave.pre).toBe(DIVE.lead);
  });

  test("the dive's crossing shows on that centre within 1 px on every frame of the push, F − 1 included", () => {
    const cam = new THREE.PerspectiveCamera(24, W / H, 0.005, 200);
    for (let f = Math.ceil(e.start * 30) + 3; f < firstFrame(e.cut); f++) {
      diveCamera(cam, f / 30, AT, aim, target);
      const [x, y] = onScreen(cam, target);
      expect(Math.hypot(x - anywhereWeave.center![0], y - anywhereWeave.center![1])).toBeLessThan(1);
    }
  });

  test('the dive plunges: at F − 1 the camera is many times closer to the crossing than as it began', () => {
    const cam = new THREE.PerspectiveCamera(24, W / H, 0.005, 200);
    const d0 = diveCamera(cam, e.start, AT, aim, target).d, d1 = diveCamera(cam, (firstFrame(e.cut) - 1) / 30, AT, aim, target).d;
    expect(d0 / d1).toBeGreaterThan(100);
    expect(cam.near).toBeLessThan(d1);
  });
});
