// The transitions' sounds: by default a whip's whoosh and a zoom-through's rush, each peaking on the cut (their palette
// sounds are peak-aligned); a film maps any kind to a sound of its palette (film.ts `sfx.transitions`). Kinds it maps
// to nothing carry no sound of their own: the scenes either side do.
import type { TransitionEntry } from '../engine/transition';
import type { Cue, Duck } from './cue';

/** How far a whip's whoosh leans toward where the camera travels (pan, at a horizontal whip). */
const WHIP_PAN = 0.25;

/** The palette sounds transitions make at their cuts, by kind (null or missing: silent). */
export type TransitionSounds = Partial<Record<TransitionEntry['spec']['kind'], string | null>>;
export const DEFAULT_TRANSITION_SOUNDS: TransitionSounds = { whip: 'whoosh_whip', zoom: 'whoosh_zoom' };

/** Each transition's cues, grouped under its id (`<from>-<to>`). */
export function transitionCues(transitions: TransitionEntry[], sounds: TransitionSounds = DEFAULT_TRANSITION_SOUNDS): { scene: string; items: (Cue | Duck)[] }[] {
  const out: { scene: string; items: (Cue | Duck)[] }[] = [];
  for (const e of transitions) {
    const anchor = `cut:${e.id}`;
    const items: Cue[] = [];
    const sound = sounds[e.spec.kind];
    if (sound && e.spec.kind === 'whip') {
      const dx = e.spec.dir?.[0] ?? 0;
      items.push({ sound, t: e.cut, anchor, pan: Math.round(WHIP_PAN * dx * 1000) / 1000 });
    } else if (sound) {
      items.push({ sound, t: e.cut, anchor });
    }
    if (items.length) out.push({ scene: e.id, items });
  }
  return out;
}
