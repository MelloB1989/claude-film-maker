import { expect, test } from 'bun:test';
import { VO } from './vo';

const data = {
  duration: 10,
  lines: [{
    id: 'L03', scene: 'ex', act: 'I', text: "It's not you... it's your vector store.", start: 1, end: 3,
    words: [
      { w: "It's", start: 1.0, end: 1.2 }, { w: 'not', start: 1.25, end: 1.4 }, { w: 'you...', start: 1.45, end: 1.8 },
      { w: "it's", start: 2.0, end: 2.2 }, { w: 'your', start: 2.25, end: 2.4 }, { w: 'vector', start: 2.45, end: 2.7 },
      { w: 'store.', start: 2.75, end: 3.0 },
    ],
  }],
  scenes: [{ id: 'ex', act: 'I', start: 0, end: 10 }],
  acts: [{ id: 'I', name: 'The Ex', start: 0, end: 10 }],
};

test('display text is typographic', () => {
  const vo = new VO(data);
  expect(vo.lines[0]!.text).toBe('It’s not you… it’s your vector store.');
  expect(vo.words[2]!.w).toBe('you…');
  expect(vo.lines[0]!.scene).toBe('ex');
});

test('lookup by content and by time', () => {
  const vo = new VO(data);
  expect(vo.get('vector store').id).toBe('L03');
  expect(() => vo.get('nope')).toThrow('line not found');
  expect(vo.wordAt(1.3)?.w).toBe('not');
  expect(vo.sceneAt(5)?.id).toBe('ex');
  expect(vo.duration).toBe(10);
});

test('word progress', () => {
  const w = new VO(data).words[0]!;
  expect(VO.wordProgress(w, 0.9)).toBe(0);
  expect(VO.wordProgress(w, 1.1)).toBeCloseTo(0.5);
  expect(VO.wordProgress(w, 2)).toBe(1);
});
