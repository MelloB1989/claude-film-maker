// The transitions' sounds: a whip's whoosh and a zoom-through's rush, each peaking on the cut (their palette sounds are
// peak-aligned). A match, a hard cut, a dip and a dissolve carry no sound of their own: the scenes either side do.
import type { TransitionEntry } from '../engine/transition';
import type { Cue, Duck } from './cue';

/** How far a whip's whoosh leans toward where the camera travels (pan, at a horizontal whip). */
const WHIP_PAN = 0.25;

/** Each transition's cues, grouped under its id (`her-repo`). */
export function transitionCues(transitions: TransitionEntry[]): { scene: string; items: (Cue | Duck)[] }[] {
  const out: { scene: string; items: (Cue | Duck)[] }[] = [];
  for (const e of transitions) {
    const anchor = `cut:${e.id}`;
    const items: Cue[] = [];
    if (e.spec.kind === 'whip') {
      const dx = e.spec.dir?.[0] ?? 0;
      items.push({ sound: 'whoosh_whip', t: e.cut, anchor, pan: Math.round(WHIP_PAN * dx * 1000) / 1000 });
    } else if (e.spec.kind === 'zoom') {
      items.push({ sound: 'whoosh_zoom', t: e.cut, anchor });
    }
    if (items.length) out.push({ scene: e.id, items });
  }
  return out;
}
