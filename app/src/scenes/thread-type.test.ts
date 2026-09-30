import { describe, expect, test } from 'bun:test';
import { loosen, reveal } from './thread-type';
import { CRACK_EM } from './thread-crack';

// "forgets." as spoken: 1.71 to 2.322, gone by 2.94
const AT = 1.71, END = 2.322, GONE = 2.94, N = 8;

describe('thread: forgets comes apart as she says it', () => {
  test('nothing moves before the word is spoken', () => {
    for (let i = 0; i < N; i++) {
      const l = loosen(AT - 0.01, i, N, AT, END, GONE);
      for (const v of [l.dx, l.dy, l.rot, l.blur]) expect(v).toBeCloseTo(0, 12);
      expect(l.a).toBe(1);
    }
  });

  test('the gaps open letter by letter, from the first', () => {
    const t = AT + 0.3; // the key moment: halfway through the word
    const dx = Array.from({ length: N }, (_, i) => loosen(t, i, N, AT, END, GONE).dx);
    for (let i = 1; i < N; i++) expect(dx[i]!).toBeGreaterThanOrEqual(dx[i - 1]! - 0.3); // drift aside, spacing only grows
    const gap = (i: number) => dx[i]! - dx[i - 1]!;
    expect(gap(1)).toBeGreaterThan(0.1); // the first gap is well open
    expect(loosen(t, N - 1, N, AT, END, GONE).dy).toBeCloseTo(0, 12); // the voice has not reached the last letter yet
  });

  test('every letter has let go by the end, and the same time gives the same letters', () => {
    for (let i = 0; i < N; i++) expect(loosen(GONE, i, N, AT, END, GONE).a).toBe(0);
    expect(loosen(2.2, 3, N, AT, END, GONE)).toEqual(loosen(2.2, 3, N, AT, END, GONE));
  });

  test('a word appears on its onset', () => {
    expect(reveal(AT - 0.03, AT).a).toBe(0);
    expect(reveal(AT + 0.2, AT).a).toBe(1);
  });
});

describe('thread: the crack in "zero."', () => {
  test('runs bottom to top (the shader finds its segment by height) and past the glyphs at both ends', () => {
    for (let i = 1; i < CRACK_EM.length; i++) expect(CRACK_EM[i]![1]).toBeGreaterThan(CRACK_EM[i - 1]![1]);
    expect(CRACK_EM[0]![1]).toBeLessThan(-0.2); // below the descent of e and o
    expect(CRACK_EM[CRACK_EM.length - 1]![1]).toBeGreaterThan(0.6); // above the x-height
  });
});
