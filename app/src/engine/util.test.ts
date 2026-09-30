import { expect, test } from 'bun:test';
import { FPS, frameIdx } from './util';

test('the film runs at 30 fps', () => {
  expect(FPS).toBe(30);
  expect(frameIdx(1)).toBe(30);
  expect(frameIdx(1 + 0.4 / 30)).toBe(30);
});
