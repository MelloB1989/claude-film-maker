// Scene2D: the base of every 2D kit block, and of a film's own 2D scenes. It owns a full-frame Canvas2D layer (logical
// px, the film's format), clears the frame to the block's `background` (common.ts: 'theme', 'none' for transparent, a
// role, a #hex or a gradient), calls draw(c, f) and composites the layer over it. An optional second layer, `this.glow`,
// is added as light ('add') at the film's glow level (look.ts GLOW_LEVEL): draw on it in glowInk('accent') (or any
// accent) and that light blooms in the post, while the fg on the main layer stays crisp (fg never blooms).
//
// A custom scene is a few lines:
//
//   import { Scene2D, type Frame } from '@kit/scene2d';
//   import { F, font } from '@engine/type';
//   import { rgba } from '@engine/palette';
//   import { W, H } from '@engine/gl';
//
//   export default class Hello extends Scene2D {
//     draw(c: CanvasRenderingContext2D, f: Frame) {
//       c.font = font(F.display(100, 800), 140 * this.u);
//       c.textAlign = 'center';
//       c.fillStyle = rgba('fg', Math.min(1, f.lt * 3));
//       c.fillText(this.p('title', 'Hello'), W / 2, H / 2);
//       const g = this.glow;                       // the glow layer (made on first use)
//       g.fillStyle = glowInk('accent', 0.8);
//       g.fillRect(W / 2 - 200, H / 2 + 40, 400, 4); // a rule that blooms
//     }
//   }
//
// Every frame starts clean (Layer2D.clear resets the contexts), so draw() is a pure function of the frame.
// Params every Scene2D reads: background, glow (level, 0 turns the glow layer off), exit ('none' | 'fade' | 'rise' |
// 'sink', over exitDur s at the end of the shot; a block that leaves unit by unit handles its own).
import type * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides, type SceneCtx } from '../engine/scene';
import { Layer2D, W, H } from '../engine/gl';
import { GLOW_LEVEL, linearToSrgb } from '../engine/look';
import { lin, type PaletteKey } from '../engine/palette';
import type { Handles } from '../engine/transition';
import { clearBackground, need, p, type Background } from './common';
import { exitState, type Exit } from './text/fx';

export type { Frame };

/** Logical px per reference px: sizes are authored for a 1080 px short side and scale with the format. */
export const refUnit = () => Math.min(W, H) / 1080;

/** The frame is taller than wide (vertical, portrait). */
export const isTall = () => H > W;

/**
 * A colour for the glow layer: the role's (or #hex's) hue at full strength (its linear colour scaled so its brightest
 * channel is 1), as CSS, at alpha `a`. The layer is added at the glow level, so a pixel of glowInk('accent') at alpha
 * 1 adds exactly look.ts glow('accent').
 */
export function glowInk(key: PaletteKey | string, a = 1): string {
  const c = lin(key), m = Math.max(c[0], c[1], c[2], 1e-6);
  const ch = (x: number) => Math.round(255 * Math.min(1, Math.max(0, linearToSrgb(x / m))));
  return `rgba(${ch(c[0])},${ch(c[1])},${ch(c[2])},${a})`;
}

/** A rectangle in logical px. */
export interface Rect { x0: number; y0: number; x1: number; y1: number; w: number; h: number }

const rect = (x0: number, y0: number, x1: number, y1: number): Rect => ({ x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 });

/**
 * Safe areas of the frame: 'action' (93%: 3.5% in from each edge), 'title' (90%: 5% in), and 'social' (a vertical
 * feed's: clear of the header at the top, the caption and buttons along the bottom and the button column on the right;
 * in a landscape or square frame it is the title-safe area).
 */
export function safeRect(kind: 'action' | 'title' | 'social' = 'title'): Rect {
  if (kind === 'action') return rect(0.035 * W, 0.035 * H, 0.965 * W, 0.965 * H);
  if (kind === 'social' && H > W) return rect(0.06 * W, 0.09 * H, 0.86 * W, 0.76 * H);
  return rect(0.05 * W, 0.05 * H, 0.95 * W, 0.95 * H);
}

export abstract class Scene2D extends Scene {
  /** The block's own layer: full frame, logical px, cleared every frame. */
  protected layer: Layer2D;
  private glowLayer: Layer2D | null = null;
  private glowUsed = false;
  /** What `background` is when the params give none ('theme' for blocks, 'none' for overlays). */
  protected defaultBackground: Background = 'theme';
  /** True for a block that plays `exit` itself (unit by unit); otherwise the whole layer leaves. */
  protected ownExit = false;
  /** Pure functions of time can render before their start and past their end: a 'run' transition may use them. */
  override handles: Handles = { head: 0.5, tail: 0.5 };

  constructor(ctx: SceneCtx) {
    super(ctx);
    this.layer = new Layer2D();
  }

  /** Draw the frame on `c` (the block's layer, logical px). Return post overrides, if any. */
  abstract draw(c: CanvasRenderingContext2D, f: Frame): PostOverrides | void;

  /** A param, with a default. */
  protected p<T>(key: string, fallback: T): T {
    return p(this.ctx, key, fallback);
  }

  /** A required param (throws naming the shot and the key). */
  protected need<T>(key: string): T {
    return need(this.ctx, key);
  }

  /** Logical px per reference px (sizes are authored for a 1080 px short side). */
  protected get u(): number {
    return refUnit();
  }

  /** The shot's id (for wordTimes): the film's shot id, or the timeline entry's. */
  protected get shot(): string {
    return (this.ctx.params.shot as string | undefined) ?? this.ctx.id;
  }

  /**
   * The glow layer's context: made the first time it is asked for, cleared on the first ask of each frame. What is drawn
   * on it (in glowInk colours) is added over the block as light at the glow level, and blooms.
   */
  protected get glow(): CanvasRenderingContext2D {
    this.glowLayer ??= new Layer2D();
    if (!this.glowUsed) {
      this.glowLayer.clear();
      this.glowUsed = true;
    }
    return this.glowLayer.ctx;
  }

  /** The glow level the layer is added at (param `glow`; 0: no glow). */
  protected get glowLevel(): number {
    return this.p('glow', GLOW_LEVEL);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const { renderer, comp } = this.ctx;
    clearBackground(renderer, out, this.p<Background>('background', this.defaultBackground));
    this.layer.clear();
    this.glowUsed = false;
    const post = this.draw(this.layer.ctx, f);
    // the whole layer's exit (a block that leaves unit by unit plays its own)
    const ex = this.ownExit ? null : exitState(this.p<Exit>('exit', 'none'), f.t, f.end, this.p('exitDur', 0.35));
    const opacity = ex ? ex.alpha : 1;
    // an offset moves the picture by -offset (uv, y up): a rise of dy em is dy * 0.1 of the frame's height
    const offset: [number, number] = ex ? [0, (ex.dy * 0.1 * H) / H] : [0, 0];
    if (opacity > 0.001) {
      comp.draw(renderer, this.layer.upload(), out, { opacity, offset });
      const lvl = this.glowLevel;
      if (this.glowUsed && lvl > 0) comp.draw(renderer, this.glowLayer!.upload(), out, { mode: 'add', tint: [lvl, lvl, lvl], opacity, offset });
    }
    return post;
  }

  override dispose() {
    disposeLayer(this.layer);
    if (this.glowLayer) disposeLayer(this.glowLayer);
    this.glowLayer = null;
  }
}
