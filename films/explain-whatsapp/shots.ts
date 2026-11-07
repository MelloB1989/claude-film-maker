// The film's shots, timed by agent-11's EDL (data/edl.json: each graphics shot's frame count and its words on the
// shot's own clock). Every shot runs its EDL length plus TAIL frames that hold the end state (the edit's handle).
import edl from './data/edl.json';
import type { ShotSpec } from '@engine/film';

export const TAIL = 12;
const FPS = edl.fps;

const scenes: Record<string, ShotSpec['scene']> = {
  title: () => import('./v3/title'),
  connect: () => import('./v3/connect'),
  erlang: () => import('./v3/erlang'),
  store: () => import('./v3/store'),
  ticks: () => import('./v3/ticks'),
  group: () => import('./v3/group'),
  e2e: () => import('./v3/e2e'),
  media: () => import('./v3/media'),
  end: () => import('./v3/end'),
};

export interface GfxShot { id: string; kind: string; frames: number; seconds: number }

/** The graphics shots in film order. */
export const GFX: GfxShot[] = edl.shots.map((s) => ({ id: s.gfx, kind: s.kind, frames: s.frames + TAIL, seconds: (s.frames + TAIL) / FPS }));

/**
 * Half a frame of lead before the first shot: every shot boundary then falls between two frame times, so `--only <id>`
 * owns exactly its frames (a boundary landing on a frame time in floating point could give a shot one frame too many
 * at one end and one too few at the other). Shots are sampled half a frame into each frame's interval.
 */
export const LEAD: ShotSpec = { id: 'lead', scene: () => import('./v3/end'), length: 0.5 / FPS, params: { layout: 'full', words: [], cut: 0.5 / FPS } };

/** One shot per graphics beat, laid out `layout`, with the extra params given (a matte background, say). */
export function shots(o: { layout: (kind: string) => 'full' | 'panel'; suffix?: string; params?: Record<string, unknown>; only?: (kind: string) => boolean } ): ShotSpec[] {
  return edl.shots.filter((s) => (o.only ? o.only(s.kind) : true)).map((s) => ({
    id: s.gfx + (o.suffix ?? ''),
    scene: scenes[s.gfx]!,
    length: (s.frames + TAIL) / FPS,
    params: { layout: o.layout(s.kind), words: s.words.map((w) => ({ w: w.w, f: w.f, t: w.f / FPS })), cut: s.frames / FPS, ...(o.params ?? {}) },
  }));
}
