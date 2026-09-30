// The edit: scene windows come from data/vo.json, where tools/ snapped them to the beat grid (film-snap). A scene
// whose module exists (scenes/<id>.ts) plays it; the others play the animatic card.
import type { TimelineEntry } from './engine/engine';
import type { SceneClass } from './engine/scene';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';
import { entriesFrom } from './edit';

const modules = import.meta.glob<{ default: SceneClass }>('./scenes/*.ts');

export function makeTimeline(vo: VO, _audio: AudioData): TimelineEntry[] {
  return entriesFrom(vo, Object.keys(modules)).map((e) => ({
    id: e.id, file: e.file, start: e.start, end: e.end, params: e.params,
    load: () => {
      const m = modules[`./scenes/${e.file}.ts`];
      return m ? m() : Promise.reject(new Error(`scene module not found: scenes/${e.file}.ts`));
    },
  }));
}
