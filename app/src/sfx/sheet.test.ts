// The cue sheet (Plan 3 Task 8): cues follow the film's own data (Review Focus 2), and the sheet is musical rather
// than noisy: each sound on its event, honest left to its room tone, the snap's two frames of near-silence.
import { describe, expect, test } from 'bun:test';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { buildSheet, paletteSound, type SfxSheet } from './sheet';
import { load, shifted, TRANSITIONS, type SheetInputs } from './testdata';
import { typing } from './cue';
import { VO } from '../engine/vo';
import { typedCount } from '../engine/panels';
import { threadTimes } from '../scenes/thread-time';
import { ARCS } from '../scenes/weave-time';
import { timesOf as connectTimes } from '../scenes/connect-time';
import { copyOf, terminalLines } from '../scenes/connect-cards';
import CONNECT_S from '../scenes/connect.strings.json';

const FRAME = 1 / 30;

/** A copy of the voiceover with one word of a line renamed (its text too). */
function renameWord(vo: VO, line: string, from: string, to: string): VO {
  const j = {
    duration: vo.duration, scenes: vo.scenes, acts: vo.acts,
    lines: vo.lines.map((l) => ({
      ...l, text: l.id === line ? l.text.replace(from, to) : l.text,
      words: l.words.map((w) => ({ w: l.id === line && w.w === from ? to : w.w, start: w.start, end: w.end })),
    })),
  };
  return new VO(j);
}

const real = load();
const sheet: SfxSheet = buildSheet(...real);
const [vo, audio] = real;
const span = (id: string) => vo.scenes.find((s) => s.id === id)!;
const inScene = (id: string) => sheet.cues.filter((c) => c.scene === id);

describe('cues follow the data (Review Focus 2)', () => {
  test('shifting every time by +0.5 s shifts every cue and duck by exactly +0.5 s', () => {
    const a = sheet, b = buildSheet(...shifted(0.5));
    expect(b.cues.length).toBe(a.cues.length);
    expect(b.ducks.length).toBe(a.ducks.length);
    a.cues.forEach((c, i) => {
      expect(b.cues[i]!.anchor).toBe(c.anchor);
      expect(b.cues[i]!.sound).toBe(c.sound);
      expect(b.cues[i]!.t).toBeCloseTo(c.t + 0.5, 9);
      if (c.dur !== undefined) expect(b.cues[i]!.dur!).toBeCloseTo(c.dur, 9);
    });
    a.ducks.forEach((d, i) => {
      expect(b.ducks[i]!.t).toBeCloseTo(d.t + 0.5, 9);
      expect(b.ducks[i]!.dur).toBeCloseTo(d.dur, 9);
    });
  });

  test('a cue whose word is gone fails loudly, naming it', () => {
    const [v, ...rest] = load();
    const broken = renameWord(v, 'L01', 'forgets.', 'leaves.');
    expect(() => buildSheet(broken, ...(rest as [SheetInputs[1], SheetInputs[2], SheetInputs[3], SheetInputs[4]]))).toThrow(/no word "forgets" in L01/);
  });

  test('the test data holds every transition the film has', () => {
    const dir = path.resolve(import.meta.dir, '../transitions');
    const files = readdirSync(dir).filter((f) => f.endsWith('.ts') && !f.startsWith('_') && !f.endsWith('.test.ts')).map((f) => f.slice(0, -3));
    expect(Object.keys(TRANSITIONS).sort()).toEqual(files.sort());
  });
});

describe('the sheet', () => {
  test('every cue names a palette sound and lies in the film', () => {
    const palette = real[3];
    expect(sheet.cues.length).toBeGreaterThan(0);
    for (const c of sheet.cues) {
      expect(paletteSound(palette, c.sound)).not.toBeNull();
      expect(c.t).toBeGreaterThanOrEqual(0);
      expect(c.t).toBeLessThan(vo.duration);
      expect(Number.isFinite(c.gain)).toBe(true);
      expect(Math.abs(c.pan ?? 0)).toBeLessThanOrEqual(1);
    }
    // ids are unique and in time order within their scene
    expect(new Set(sheet.cues.map((c) => c.id)).size).toBe(sheet.cues.length);
    for (let i = 1; i < sheet.cues.length; i++) expect(sheet.cues[i]!.t).toBeGreaterThanOrEqual(sheet.cues[i - 1]!.t);
  });

  test('an unknown sound or a cue outside the film throws', () => {
    const [v, a, t, p, e] = load();
    expect(() => buildSheet(v, a, t, { sounds: { ...p.sounds, stamp: undefined as never } }, e)).toThrow(/no sound "stamp"/);
    const short = new VO({ duration: 50, lines: v.lines.map((l) => ({ ...l, words: l.words.map((w) => ({ w: w.w, start: w.start, end: w.end })) })), scenes: v.scenes, acts: v.acts });
    expect(() => buildSheet(short, a, t, p, e)).toThrow(/outside the film/);
  });

  test('word cues sit on their onsets; beat cues on the grid', () => {
    let words = 0, beats = 0;
    for (const c of sheet.cues) {
      const w = /^word:(L\d+):(\d+)$/.exec(c.anchor);
      if (w) {
        words++;
        expect(c.t).toBe(vo.lines.find((l) => l.id === w[1])!.words[Number(w[2])]!.start);
      }
      const b = /^beat:(\d+)$/.exec(c.anchor);
      if (b) {
        beats++;
        expect(c.t).toBe(audio.beats[Number(b[1])]!);
      }
      const d = /^downbeat:(\d+)$/.exec(c.anchor);
      if (d) expect(c.t).toBe(audio.downbeats[Number(d[1])]!);
    }
    expect(words).toBeGreaterThan(5);
    expect(beats).toBeGreaterThan(10);
  });

  test('typing keys land on frame times, one per character shown', () => {
    const c = span('connect');
    const T = connectTimes(vo, audio, c.start, c.end);
    const lines = terminalLines(copyOf(CONNECT_S as string[]), T);
    const typed = lines.filter((l) => l.kind === 'cmd' && l.cps !== undefined);
    const keys = inScene('connect').filter((x) => x.anchor.includes(':key:'));
    const chars = typed.reduce((n, l) => n + Array.from(l.text).length - (l.text.startsWith('$ ') ? 2 : 0), 0);
    expect(keys.length).toBe(chars);
    // each key on a frame, or spread k/30 inside one: its frame shows exactly that many more characters
    const byFrame = new Map<number, number>();
    for (const k of keys) {
      const f = Math.floor(k.t * 30 + 1e-9);
      byFrame.set(f, (byFrame.get(f) ?? 0) + 1);
      expect(k.sound).toMatch(/^key_soft_[1-8]$/);
    }
    for (const [f, n] of byFrame) {
      const more = typed.reduce((s, l) => s + typedCount(l, f / 30) - typedCount(l, (f - 1) / 30), 0);
      expect(n).toBe(more);
      const ks = keys.filter((k) => Math.floor(k.t * 30 + 1e-9) === f);
      ks.forEach((k, j) => expect(k.t * 30).toBeCloseTo(f + j / n, 9));
    }
  });

  test('typing() places a frame\'s k new characters k to a frame, the first on it', () => {
    const count = (t: number) => Math.max(0, Math.min(10, Math.floor((t - 1) * 75 + 1e-6) + 1)); // 2.5 a frame
    const ks = typing('x', count, 0.9, 1.5, 'x');
    expect(ks.length).toBe(10);
    expect(ks[0]!.t).toBeCloseTo(1, 12);
    expect(new Set(ks.map((k) => k.anchor)).size).toBe(10);
    expect(typing('x', count, 0.9, 1.5, 'x')).toEqual(ks);
  });

  test('the snap duck is two frames at the snap; the silent beat is one beat after ex → her', () => {
    const th = span('thread');
    const T = threadTimes(vo, audio, th.start, th.end);
    const snap = sheet.ducks.filter((d) => d.scene === 'thread');
    expect(snap.length).toBe(1);
    expect(snap[0]!.t).toBe(T.snap);
    expect(snap[0]!.dur).toBeCloseTo(2 * FRAME, 12);
    expect(snap[0]!.depth).toBe(-30);
    expect(inScene('thread').find((c) => c.sound === 'thread_snap')!.t).toBe(T.snap);
    expect(inScene('thread').find((c) => c.sound === 'fibre_whoosh')!.t).toBeCloseTo(T.snap + 2 * FRAME, 12);
    // the hum is a bed from the light coming up to the snap
    const hum = inScene('thread').find((c) => c.sound === 'thread_hum')!;
    expect(hum.t).toBe(T.lightOn);
    expect(hum.t + hum.dur!).toBeCloseTo(T.snap, 12);

    const cut = span('her').start;
    const silent = sheet.ducks.filter((d) => Math.abs(d.t - cut) < 1e-9);
    expect(silent.length).toBe(1);
    const i = audio.beats.findIndex((b) => Math.abs(b - cut) < 1e-6);
    expect(i).toBeGreaterThanOrEqual(0);
    expect(silent[0]!.dur).toBeCloseTo(audio.beats[i + 1]! - audio.beats[i]!, 9);
    expect(silent[0]!.bus).toBe('music');
    expect(silent[0]!.depth).toBe(-24);
    expect(silent[0]!.fade).toBeCloseTo(0.03, 12);
  });

  test('the shuttle clacks within one frame of a beat', () => {
    const clacks = inScene('loom').filter((c) => c.sound === 'shuttle_clack');
    expect(clacks.length).toBeGreaterThan(8);
    for (const c of clacks) {
      expect(c.anchor).toMatch(/^beat:\d+$/);
      expect(audio.beats.some((b) => b === c.t)).toBe(true);
    }
  });

  test('honest carries only room tone and typing', () => {
    const h = inScene('honest');
    expect(h.length).toBeGreaterThan(0);
    for (const c of h) expect(c.sound === 'room_tone' || /^key_soft_\d$/.test(c.sound)).toBe(true);
    const room = h.filter((c) => c.sound === 'room_tone');
    expect(room.length).toBe(1);
    const sec = audio.sections.find((s) => s.name === 'honest')!;
    expect(room[0]!.t).toBe(sec.start);
    for (const c of h.filter((x) => x.sound !== 'room_tone')) expect(c.gain).toBeLessThanOrEqual(-24 - 8 + 1.5 + 1e-9);
    // no other scene's cue (no transition's either) falls in honest's music-out window, save its room tone and typing
    const quiet = sheet.cues.filter((c) => c.t >= sec.start && c.t < span('honest').end && c.scene !== 'honest');
    expect(quiet).toEqual([]);
  });

  test('restraint: outside its typing (a key a character) no scene carries more than 6 cues a second', () => {
    for (const s of vo.scenes) {
      const n = inScene(s.id).filter((c) => !c.anchor.includes(':key:')).length;
      expect(n / (s.end - s.start)).toBeLessThan(6);
    }
  });

  test('a frame\'s keys sum to one key\'s energy', () => {
    const count = (t: number) => Math.max(0, Math.min(40, 4 * (Math.floor((t - 1) * 30 + 1e-6) + 1))); // 4 a frame
    for (const k of typing('x', count, 0.9, 1.5, 'x')) expect(k.gain!).toBeLessThanOrEqual(-10 * Math.log10(4) + 1.5 + 1e-9);
  });

  test('the sheet is deterministic', () => {
    expect(JSON.stringify(buildSheet(...load()))).toBe(JSON.stringify(sheet));
  });

  test('weave\'s arcs arrive when B15 flies them (blender/mark/choreo.py FLIGHTS)', () => {
    const py = readFileSync(path.resolve(import.meta.dir, '../../../blender/mark/choreo.py'), 'utf8');
    for (const [k, enter] of Object.entries(ARCS)) {
      const m = new RegExp(`"${k}": Flight\\(([0-9.]+),`).exec(py);
      expect(m).not.toBeNull();
      expect(Number(m![1])).toBe(enter);
    }
  });
});
