import { expect, test } from 'bun:test';
import { entriesFrom, moduleFor } from './edit';

const vo = { scenes: [{ id: 'thread', act: 'I', start: 0, end: 6.2 }, { id: 'ex', act: 'I', start: 6.2, end: 15 }] };

test('a scene plays its own module when one exists, else the card', () => {
  expect(moduleFor('thread', ['./scenes/card.ts', './scenes/thread.ts'])).toBe('thread');
  expect(moduleFor('ex', ['./scenes/card.ts'])).toBe('card');
});

test('entries mirror the snapped scene windows', () => {
  const e = entriesFrom(vo, ['./scenes/card.ts']);
  expect(e.map((x) => [x.id, x.file, x.start, x.end])).toEqual([['thread', 'card', 0, 6.2], ['ex', 'card', 6.2, 15]]);
  expect(e[1]!.params).toEqual({ scene: 'ex', act: 'I', n: 2 });
});
