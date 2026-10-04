import { expect, test } from 'bun:test';
import { F, fontFaceDescriptors, fontFamilies } from './type';

test('font keys map to the static instances', () => {
  expect(F.display(75, 300)).toBe('Bricolage-750-300');
  expect(F.display(90, 650)).toBe('Bricolage-875-600');
  expect(F.mono(700)).toBe('JBMono-700');
  expect(F.mono(400, true)).toBe('JBMonoItalic-400');
  expect(F.ui(550)).toBe('Geist-500');
});

test('JetBrains Mono faces load with ligatures and contextual alternates off (verbatim `--scope`, `// reads`)', () => {
  const mono = fontFamilies().filter((f) => f.startsWith('JBMono'));
  expect(mono.sort()).toEqual(['JBMono-400', 'JBMono-500', 'JBMono-700', 'JBMonoItalic-400']);
  for (const f of mono) expect(fontFaceDescriptors(f)).toEqual({ featureSettings: '"calt" 0, "liga" 0' });
});

test('display and UI faces keep their own features', () => {
  expect(fontFaceDescriptors(F.display(100, 800))).toBeUndefined();
  expect(fontFaceDescriptors(F.ui(500))).toBeUndefined();
  expect(() => fontFaceDescriptors('Comic-400')).toThrow('Comic-400');
});
