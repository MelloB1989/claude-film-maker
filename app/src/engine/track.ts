// Tracked 2D anchors of a Blender shot: where named objects (empties) land on screen, frame by frame, so engine
// overlays sit on the plate. blender/lib/export.py `track()` writes data/track/<shot>.json:
//   { "fps": 30, "f0": <the shot's first film frame>, "anchors": { name: [[x, y, visible], ...] } }
// with one sample per film frame from f0, x and y in the film's logical 1920x1080 px (top-left origin, the frame's
// edges at 0 and 1920/1080, as Canvas2D draws), and visible 1 when the anchor is in front of the camera and inside
// the frame. Sample i is film frame f0 + i, at t = (f0 + i) / 30: the middle of Blender's shutter.
import { clamp, lerp } from './util';

export interface TrackData {
  fps: number;
  f0: number;
  anchors: Record<string, [number, number, number][]>;
}

/** An anchor at a time: logical px, and visible 0..1 (fractional between a visible and a hidden frame). */
export interface Anchor {
  x: number;
  y: number;
  visible: number;
}

export class Track {
  constructor(private data: TrackData) {}

  /** data/track/<shot>.json */
  static async load(shot: string): Promise<Track> {
    const url = `data/track/${shot}.json`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`track ${url}: HTTP ${r.status} (render it: blender/render.py --shot ${shot})`);
    return new Track((await r.json()) as TrackData);
  }

  /** The shot's first film frame. */
  get f0() {
    return this.data.f0;
  }

  /** Samples per anchor (the shot's frame count). */
  get frames() {
    return Math.max(0, ...Object.values(this.data.anchors).map((s) => s.length));
  }

  names() {
    return Object.keys(this.data.anchors);
  }

  /** Where anchor `name` is at film time t: linear between the frames around t, holding the ends outside the shot. */
  at(name: string, t: number): Anchor {
    const s = this.data.anchors[name];
    if (!s?.length) throw new Error(`track has no anchor '${name}' (it has: ${this.names().join(', ') || 'none'})`);
    let u = clamp(t * this.data.fps - this.data.f0, 0, s.length - 1);
    const r = Math.round(u);
    if (Math.abs(u - r) < 1e-9) u = r; // n / 30 * 30 can miss n by an ulp: frame times land exactly on their samples
    const i = Math.min(Math.floor(u), s.length - 1), j = Math.min(i + 1, s.length - 1), k = u - i;
    const a = s[i]!, b = s[j]!;
    return { x: lerp(a[0], b[0], k), y: lerp(a[1], b[1], k), visible: lerp(a[2], b[2], k) };
  }
}
