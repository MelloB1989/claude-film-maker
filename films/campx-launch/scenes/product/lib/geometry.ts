// Pure maths for the product scenes (no DOM): the camera over a screenshot, the yaw-tilted projection of image
// coordinates to the screen, keyframe interpolation, and the per-scene config types (params.ts holds the data).
// (clamp and lerp are inlined so this file has no imports: bun test runs it without the engine's path aliases)
const clamp = (x: number, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** A point or size in image-normalised coordinates: (0,0) top-left, (1,1) bottom-right of the screenshot. */
export type UV = [u: number, v: number];
/** A region of the screenshot: [u0, v0, u1, v1]. */
export type Region = [number, number, number, number];

/** A camera key: at local time t the camera looks at image point (x, y) with zoom z (1 = the fitted screenshot). */
export interface CamKey { t: number; x: number; y: number; z: number; yaw?: number; /** where the focus sits on screen (fractions of the frame); default Cfg.anchor */ ax?: number; ay?: number }
export interface Spot { t0: number; t1: number; rect: Region; /** how dark the rest goes (0..1), default 0.62 */ dim?: number; /** padding in image units */ pad?: number }
export interface Callout { t: number; until?: number; text: string; sub?: string; at: UV; /** label offset from the anchor, ref px (x right, y down) */ off: [number, number] }
export interface Box { t: number; until?: number; rect: Region; label?: string; tone?: 'accent' | 'accent2' }
export interface Tick { t: number; at: UV; /** a drawn check mark (the key point is met) */ tone?: 'accent2' | 'accent' }
export interface Chip { t: number; until?: number; text: string; at: UV; tone?: 'accent' | 'accent2'; pulse?: boolean; off?: [number, number] }
export interface CursorKey { t: number; at: UV; /** a click lands here */ click?: boolean }
export interface ImageKey { src: string; /** local time this image starts to fade in (the first: 0) */ from?: number; fade?: number }

export interface Cfg {
  images: ImageKey[];
  /** The screenshot's size at zoom 1: height as a fraction of the frame's height, or width as a fraction of its width. */
  base: { h?: number; w?: number };
  /** Where the camera's focus sits on screen (fractions of the frame). */
  anchor?: UV;
  /** Resting yaw in degrees (the frame's tilt about its vertical axis) and the perspective distance in ref px. */
  yaw?: number;
  dist?: number;
  cam: CamKey[];
  spots?: Spot[];
  callouts?: Callout[];
  boxes?: Box[];
  ticks?: Tick[];
  chips?: Chip[];
  cursor?: CursorKey[];
  /** Soft light behind the frame: 'brand' (indigo → magenta → coral) */
  light?: 'brand' | 'cool' | 'warm';
}

/** Cosine-eased interpolation of the camera keys at local time t. */
export function camAt(keys: readonly CamKey[], t: number, anchor: UV = [0.5, 0.5]): Required<CamKey> {
  const fill = (k: CamKey): CamKey => ({ yaw: 0, ax: anchor[0], ay: anchor[1], ...k });
  const k0 = fill(keys[0]!);
  if (t <= k0.t) return k0 as Required<CamKey>;
  for (let i = 1; i < keys.length; i++) {
    const a = fill(keys[i - 1]!), b = fill(keys[i]!);
    if (t <= b.t) {
      const s = clamp((t - a.t) / Math.max(1e-6, b.t - a.t));
      const e = 0.5 - 0.5 * Math.cos(Math.PI * s);
      // zoom interpolates in log space so a push feels even
      return { t, x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), z: Math.exp(lerp(Math.log(a.z), Math.log(b.z), e)), yaw: lerp(a.yaw!, b.yaw!, e), ax: lerp(a.ax!, b.ax!, e), ay: lerp(a.ay!, b.ay!, e) };
    }
  }
  return { ...fill(keys[keys.length - 1]!), t } as Required<CamKey>;
}

export interface View {
  /** Screen position of the focus point, px. */
  sx: number; sy: number;
  /** Screenshot size at the current zoom, px. */
  bw: number; bh: number;
  /** Focus point in image coordinates. */
  fx: number; fy: number;
  /** Yaw in radians and perspective distance, px. */
  yaw: number; dist: number;
}

/** Project image point (u, v) to the screen under the yaw tilt (pure; used for the frame, callouts, boxes, cursor). */
export function project(v: View, u: number, w: number): { x: number; y: number; s: number } {
  const dx = (u - v.fx) * v.bw, dy = (w - v.fy) * v.bh;
  const cos = Math.cos(v.yaw), sin = Math.sin(v.yaw);
  const x = dx * cos, z = dx * sin; // z > 0 toward the viewer
  const s = v.dist / (v.dist - z);
  return { x: v.sx + x * s, y: v.sy + dy * s, s };
}

/** The screen quad of a region, clockwise from top-left. */
export function quad(v: View, r: Region, pad = 0): { x: number; y: number }[] {
  const [u0, v0, u1, v1] = r;
  return [project(v, u0 - pad, v0 - pad), project(v, u1 + pad, v0 - pad), project(v, u1 + pad, v1 + pad), project(v, u0 - pad, v1 + pad)];
}

/** 0 → 1 over `dur` s from `t0` (cosine ease), 0 before and 1 after. */
export const rise = (t: number, t0: number, dur = 0.5) => {
  const s = clamp((t - t0) / dur);
  return 0.5 - 0.5 * Math.cos(Math.PI * s);
};

/** 1 between t0 and t1, easing in over `i` s and out over `o` s (t1 undefined: never leaves). */
export const window = (t: number, t0: number, t1: number | undefined, i = 0.45, o = 0.4) => {
  const a = rise(t, t0, i);
  return t1 === undefined ? a : a * (1 - rise(t, t1 - o, o));
};

/** Cursor position at local time t: eased glides between keys (a gentle arc), and the click ripples' ages. */
export function cursorAt(keys: readonly CursorKey[], t: number): { at: UV; clicks: number[] } | null {
  if (!keys.length || t < keys[0]!.t - 0.4) return null;
  const clicks = keys.filter((k) => k.click && t >= k.t).map((k) => t - k.t);
  if (t <= keys[0]!.t) return { at: keys[0]!.at, clicks };
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1]!, b = keys[i]!;
    if (t <= b.t) {
      const s = clamp((t - a.t) / Math.max(1e-6, b.t - a.t));
      const e = s * s * (3 - 2 * s);
      const arc = Math.sin(Math.PI * e) * 0.012 * Math.hypot(b.at[0] - a.at[0], b.at[1] - a.at[1]) * 6;
      return { at: [lerp(a.at[0], b.at[0], e), lerp(a.at[1], b.at[1], e) - arc], clicks };
    }
  }
  return { at: keys[keys.length - 1]!.at, clicks };
}
