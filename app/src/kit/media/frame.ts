// Framing for the media blocks (Image, Video, Device): where the picture sits, what part of it shows (fit, Ken Burns,
// scroll), how it comes in, and the Scene2D base that draws it with rounded corners, a shadow and a hairline border.
// The math is pure (no DOM): media.test.ts tests it.
import { Scene2D, type Frame } from '../scene2d';
import { W, H } from '../../engine/gl';
import { rgba } from '../../engine/palette';
import { spring } from '../../engine/motion';
import { clamp, ease, lerp, prog } from '../../engine/util';
import { openSource, type MediaSource } from './source';

export type Fit = 'cover' | 'contain';
export type Entry = 'none' | 'fade' | 'rise' | 'scale' | 'wipe';
/** A rectangle, top-left and size, in logical px. */
export interface Box { x: number; y: number; w: number; h: number }
/** A Ken Burns key: zoom (1 = the fitted picture), pan x and y (-1..1 of the slack the zoom and fit leave; y down). */
export interface KB { zoom?: number; x?: number; y?: number }

const ENTRIES: readonly Entry[] = ['none', 'fade', 'rise', 'scale', 'wipe'];

/**
 * The box a picture of aspect `aspect` (w / h) shows in: centred at (cx, cy) (fractions of the frame), at most w x h
 * (fractions of W and H). 'cover' fills that box (the picture is cropped to it); 'contain' shrinks it to the picture's
 * own aspect, so its corners and shadow wrap the picture.
 */
export function layoutBox(o: { cx: number; cy: number; w: number; h: number; fit: Fit; aspect: number; W: number; H: number }): Box {
  let bw = o.w * o.W, bh = o.h * o.H;
  if (o.fit === 'contain') {
    if (bw / bh > o.aspect) bw = bh * o.aspect;
    else bh = bw / o.aspect;
  }
  return { x: o.cx * o.W - bw / 2, y: o.cy * o.H - bh / 2, w: bw, h: bh };
}

/**
 * The part of a mw x mh picture that fills a box of aspect `aspect` (w / h), zoomed by `zoom` (>= 1 crops in) and panned
 * by (px, py) in -1..1 of the slack on each side (0 centred, -1 left / top, 1 right / bottom). Always inside the picture.
 */
export function cropRect(mw: number, mh: number, aspect: number, zoom = 1, px = 0, py = 0): { sx: number; sy: number; sw: number; sh: number } {
  let sw = mw, sh = mw / aspect;
  if (sh > mh) {
    sh = mh;
    sw = mh * aspect;
  }
  const z = Math.max(1, zoom);
  sw /= z;
  sh /= z;
  const sx = ((mw - sw) / 2) * (1 + clamp(px, -1, 1));
  const sy = ((mh - sh) / 2) * (1 + clamp(py, -1, 1));
  return { sx, sy, sw, sh };
}

/** The Ken Burns state at progress k (0..1, eased in and out like a slow camera move): zoom and pan between two keys. */
export function kenBurns(from: KB, to: KB, k: number): Required<KB> {
  const e = 0.5 - 0.5 * Math.cos(Math.PI * clamp(k));
  return { zoom: lerp(from.zoom ?? 1, to.zoom ?? 1, e), x: lerp(from.x ?? 0, to.x ?? 0, e), y: lerp(from.y ?? 0, to.y ?? 0, e) };
}

/** How the picture comes in, `lt` s after its entry starts (dur s long): alpha, a rise (ref px), a scale and a wipe (0..1 of its width shown). */
export function entryState(kind: Entry, lt: number, dur = 0.8): { alpha: number; dy: number; scale: number; wipe: number } {
  if (!ENTRIES.includes(kind)) throw new Error(`entry is ${ENTRIES.join(' | ')}, got '${kind}'`);
  const shown = { alpha: 1, dy: 0, scale: 1, wipe: 1 };
  if (kind === 'none') return shown;
  if (lt <= 0) return { alpha: 0, dy: kind === 'rise' ? 80 : 0, scale: kind === 'scale' ? 0.9 : 1, wipe: 0 };
  const k = prog(lt, 0, dur);
  const s = spring(lt / (dur / 0.8), 2.2, 0.75);
  switch (kind) {
    case 'fade': return { ...shown, alpha: ease.outCubic(k) };
    case 'rise': return { ...shown, alpha: ease.outCubic(Math.min(1, k * 1.6)), dy: 80 * (1 - s) };
    case 'scale': return { ...shown, alpha: ease.outCubic(Math.min(1, k * 1.8)), scale: lerp(0.9, 1, s) };
    case 'wipe': return { ...shown, wipe: ease.outExpo(k) };
  }
}

/** A rounded rectangle path (radius clamped to the box). */
export function roundRect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2)));
}

/**
 * The media blocks' base: a Scene2D that opens its `src` (an image, or a clip's frames: source.ts) and draws it framed.
 * Params every media block reads (sizes in reference px of a 1080 px short side, positions as fractions of the frame):
 *   src               the picture: a path in the film's folder ('assets/shot.png'), or a clip ('assets/clip.mp4')
 *   x 0.5, y 0.5      the picture's centre
 *   w, h              its box (fractions of W, H; Image: 1, 1 full frame)
 *   fit 'cover'       'cover' (fills the box, cropped) | 'contain' (the box takes the picture's aspect)
 *   from, to          Ken Burns keys { zoom, x, y } over the shot (default a slow push, zoom 1 → 1.06)
 *   radius 0          corner radius; shadow 0 (0..1, a soft drop shadow in shadowColor '#000000'); border (a role:
 *                     a hairline round it)
 *   entry 'fade'      'none' | 'fade' | 'rise' | 'scale' | 'wipe', `delay` 0 s after the shot starts, over entryDur 0.8
 *   drift [0, 0]      a slow parallax drift over the shot (ref px, x and y), and float 0 (ref px of a slow bob)
 *   exit, background, glow (Scene2D)
 */
export abstract class Framed extends Scene2D {
  protected media: MediaSource | null = null;
  /** The block's defaults (the film's params override them). */
  protected defaults: Record<string, unknown> = {};

  protected k<T>(key: string, fallback: T): T {
    const v = this.ctx.params[key] ?? this.defaults[key];
    return (v ?? fallback) as T;
  }

  override async init() {
    entryState(this.k<Entry>('entry', 'fade'), 1); // (throws on an unknown entry, at load)
    const fit = this.k<Fit>('fit', 'cover');
    if (fit !== 'cover' && fit !== 'contain') throw new Error(`shot ${this.ctx.id}: fit is 'cover' or 'contain', got '${fit}'`);
    const src = this.need<string>('src');
    this.media = await openSource(src, { id: this.ctx.id, start: this.ctx.start, rate: this.k('rate', 1), offset: this.k('clipStart', 0), loop: this.k('loop', true) });
  }

  override async prepare(t: number) {
    await this.media?.prepare(t);
  }

  /** The block's motion at frame f: entry, drift and float, as an offset (px), scale and alpha, and the wipe. */
  protected motion(f: Frame) {
    const u = this.u;
    const e = entryState(this.k<Entry>('entry', 'fade'), f.t - (this.ctx.start + this.k('delay', 0)), this.k('entryDur', 0.8));
    const drift = this.k<[number, number]>('drift', [0, 0]);
    const fl = this.k('float', 0);
    const dx = drift[0] * (f.p - 0.5) * u;
    const dy = drift[1] * (f.p - 0.5) * u + fl * u * Math.sin(f.t * 1.3) + e.dy * u;
    return { dx, dy, scale: e.scale, alpha: e.alpha, wipe: e.wipe };
  }

  /**
   * Draw the picture at film time t into `box` (logical px): the shadow under it, the picture cropped by `crop`
   * (cropRect), clipped to its rounded corners, a hairline border over it.
   */
  protected drawPicture(c: CanvasRenderingContext2D, box: Box, crop: (mw: number, mh: number) => { sx: number; sy: number; sw: number; sh: number }, t: number, o: { radius: number; shadow: number; border?: string; fill?: string }) {
    const u = this.u;
    const img = this.media?.frame(t);
    if (o.shadow > 0) {
      c.save();
      c.shadowColor = rgba(this.k('shadowColor', '#000000'), Math.min(0.85, 0.6 * o.shadow));
      c.shadowBlur = 70 * u * o.shadow;
      c.shadowOffsetY = 28 * u * o.shadow;
      c.fillStyle = rgba(o.fill ?? 'bg');
      roundRect(c, box.x, box.y, box.w, box.h, o.radius);
      c.fill();
      c.restore();
    }
    c.save();
    roundRect(c, box.x, box.y, box.w, box.h, o.radius);
    c.clip();
    if (o.fill) {
      c.fillStyle = rgba(o.fill);
      c.fillRect(box.x, box.y, box.w, box.h);
    }
    if (img) {
      const r = crop(img.width, img.height);
      c.imageSmoothingQuality = 'high';
      c.drawImage(img.el, r.sx, r.sy, r.sw, r.sh, box.x, box.y, box.w, box.h);
    }
    c.restore();
    if (o.border) {
      c.save();
      c.strokeStyle = rgba(o.border, 0.9);
      c.lineWidth = Math.max(1, 1.2 * u);
      roundRect(c, box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, o.radius);
      c.stroke();
      c.restore();
    }
  }

  override dispose() {
    this.media?.dispose();
    this.media = null;
    super.dispose();
  }
}

/** The film's frame size (live), for the blocks' layout. */
export const frameSize = () => ({ W, H });
