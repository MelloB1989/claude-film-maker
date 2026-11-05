// The look schedule's grade (films/<id>/data/look.json; blender/lib/look_schedule.py is its reader and documents the
// file): each shot's place on the film's colour arc (`warm`, 0 cold .. 1 warm, keyable) blends the arc's two ends,
// over the file's `base`, under the shot's own `grade`. The engine applies the grade over the shot's plate (the Blender
// builders light their worlds from the same file but never bake the grade in), so the film grades as one.
//
// `gradeKeys(schedule, id, start, end, fps)` is the shot's grade as PostKeys params ([[s, value], ...] per post
// parameter): one key for a constant, the shot's own keys for a keyed field alone, and a key on every film frame of the
// window when its warmth moves (PostKeys reads its keys on whole frames, so that is exact). The keys ease as PostKeys
// eases them (in-out sine), as the Python reader does.
import { trackAt, type Keys } from './postkeys';

/** The engine's post parameters a schedule grades (post.ts PostParams), and what each is when nobody sets it. */
export const GRADE = { exposure: 1, saturation: 1, contrast: 1, warmth: 0, tint: 0, lift: 0, bloom: 0.3, halation: 0.12, vignette: 0.42, grain: 0.06 } as const;
export type GradeField = keyof typeof GRADE;

type Value = number | Keys;
interface Sections { grade?: Partial<Record<GradeField, Value>>; [section: string]: unknown }
export interface LookSchedule {
  arc?: { cold?: Sections; warm?: Sections };
  base?: Sections;
  shots?: Record<string, Sections & { warm?: Value }>;
}

const isKeys = (v: unknown): v is Keys => Array.isArray(v) && v.length > 0 && v.every((k) => Array.isArray(k) && k.length === 2 && typeof k[0] === 'number');
const at = (v: Value, t: number) => (isKeys(v) ? trackAt(v, t) : v);

/** The shot's warmth at t (s from its start), clamped to 0..1. */
export function warmAt(s: LookSchedule, id: string, t: number): number {
  const w = s.shots?.[id]?.warm ?? 0;
  return Math.min(1, Math.max(0, at(w, t)));
}

/** One grade field of shot `id` at t s into it. */
export function gradeAt(s: LookSchedule, id: string, field: GradeField, t: number): number {
  const own = s.shots?.[id]?.grade?.[field];
  if (own !== undefined) return at(own, t);
  const c = s.arc?.cold?.grade?.[field], w = s.arc?.warm?.grade?.[field];
  if (c !== undefined || w !== undefined) {
    const a = at((c ?? w)!, t), b = at((w ?? c)!, t);
    return a + (b - a) * warmAt(s, id, t);
  }
  const base = s.base?.grade?.[field];
  return base !== undefined ? at(base, t) : GRADE[field];
}

/** Shot `id`'s grade over its window [start, end) (film s) as PostKeys params. */
export function gradeKeys(s: LookSchedule, id: string, start: number, end: number, fps: number): Record<GradeField, Keys> {
  const shot = s.shots?.[id];
  const warmMoves = isKeys(shot?.warm);
  const out = {} as Record<GradeField, Keys>;
  for (const field of Object.keys(GRADE) as GradeField[]) {
    const own = shot?.grade?.[field];
    const arcMoves = [s.arc?.cold?.grade?.[field], s.arc?.warm?.grade?.[field]].some(isKeys) ||
      (warmMoves && s.arc?.cold?.grade?.[field] !== s.arc?.warm?.grade?.[field]);
    const base = s.base?.grade?.[field];
    if (own !== undefined && isKeys(own)) out[field] = own.map(([t, v]) => [t, v] as [number, number]);
    else if (own === undefined && !arcMoves && s.arc?.cold?.grade?.[field] === undefined && s.arc?.warm?.grade?.[field] === undefined && isKeys(base)) out[field] = base;
    else if (own === undefined && arcMoves) {
      const keys: Keys = [];
      for (let n = Math.ceil(start * fps - 1e-6); n / fps < end; n++) keys.push([n / fps - start, gradeAt(s, id, field, n / fps - start)]);
      out[field] = keys;
    } else out[field] = [[0, gradeAt(s, id, field, 0)]];
  }
  return out;
}
