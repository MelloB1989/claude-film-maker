// Scene `weave`: the end card's signature credit, its copy against the facts sheet, its time and its place.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { VO } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { CREDIT, creditAt, timesOf } from './weave';
import S from './weave.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'weave')!;
const T = timesOf(vo, audio, span.start, span.end);
const facts = json('facts.json') as { copy: { text: string; source: string }[] };
const strings = S as string[];

describe('weave: the signature credit', () => {
  test('it reads "Created by MelloB", approved copy on the sheet', () => {
    expect(strings[5]).toBe('Created by MelloB');
    const e = facts.copy.find((c) => c.text === 'Created by MelloB');
    expect(e?.source).toBe('user request: end-card credit');
  });

  test('it comes up on a beat after the call to action has settled, and is fully in before the last 0.3 s', () => {
    const at = creditAt(T);
    expect(at).toBeGreaterThan(T.after + 0.41);
    expect(audio.beats.some((b) => Math.abs(b - at) < 1e-9)).toBe(true);
    expect(at + CREDIT.fade).toBeLessThan(T.end - 0.3);
  });

  test('it sits bottom-right inside title-safe (the frame less 5 % a side)', () => {
    expect(CREDIT.right).toBeLessThanOrEqual(1920 * 0.95);
    expect(CREDIT.base + 0.3 * CREDIT.px).toBeLessThanOrEqual(1080 * 0.95);
    expect(CREDIT.base).toBeGreaterThan(1080 * 0.85);
    expect(CREDIT.px).toBeLessThan(30);
  });
});
