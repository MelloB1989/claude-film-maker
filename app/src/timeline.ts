// The edit: scene windows come from data/vo.json, where tools/ snapped them to the beat grid (film-snap). A scene
// whose module exists (scenes/<id>.ts) plays it; the others play the animatic card. The cuts between them are hard
// unless transitions/<from>-<to>.ts designs one (engine/transition.ts).
import type { TimelineEntry } from './engine/engine';
import type { SceneClass } from './engine/scene';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';
import { specOf, type TransitionModule, type TransitionSpec } from './engine/transition';
import { entriesFrom } from './edit';

// (not the tests beside them: a build would bundle bun:test)
const modules = import.meta.glob<{ default: SceneClass }>(['./scenes/*.ts', '!./scenes/*.test.ts']);

// the film's transitions: not the dev probes (_probe-*.ts, played only through ?transition=), nor tests
const transitionModules = import.meta.glob<TransitionModule>(['./transitions/*.ts', '!./transitions/_*.ts', '!./transitions/*.test.ts'], { eager: true });

export function makeTimeline(vo: VO, _audio: AudioData): TimelineEntry[] {
  return entriesFrom(vo, Object.keys(modules)).map((e) => ({
    id: e.id, file: e.file, start: e.start, end: e.end, params: e.params,
    load: () => {
      const m = modules[`./scenes/${e.file}.ts`];
      return m ? m() : Promise.reject(new Error(`scene module not found: scenes/${e.file}.ts`));
    },
  }));
}

/** The film's transitions, one per transitions/<from>-<to>.ts (Engine.init validates them against vo.json). */
export function makeTransitions(vo: VO): TransitionSpec[] {
  return Object.keys(transitionModules).sort().map((k) => specOf(transitionModules[k]!, vo));
}
