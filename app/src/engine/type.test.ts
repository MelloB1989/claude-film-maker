import { expect, test } from 'bun:test';
import { F } from './type';

test('font keys map to the static instances', () => {
  expect(F.display(75, 300)).toBe('Bricolage-750-300');
  expect(F.display(90, 650)).toBe('Bricolage-875-600');
  expect(F.mono(700)).toBe('JBMono-700');
  expect(F.mono(400, true)).toBe('JBMonoItalic-400');
  expect(F.ui(550)).toBe('Geist-500');
});
