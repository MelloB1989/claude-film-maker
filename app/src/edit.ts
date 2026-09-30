// Pure mapping from the snapped edit (data/vo.json scenes) to timeline entries. Kept free of Vite-only APIs so bun
// can test it.
import type { SceneSpan } from './engine/vo';

export function moduleFor(id: string, available: string[]): string {
  return available.includes(`./scenes/${id}.ts`) ? id : 'card';
}

export function entriesFrom(vo: { scenes: SceneSpan[] }, available: string[]) {
  return vo.scenes.map((s, i) => ({
    id: s.id, file: moduleFor(s.id, available), start: s.start, end: s.end,
    params: { scene: s.id, act: s.act, n: i + 1 },
  }));
}
