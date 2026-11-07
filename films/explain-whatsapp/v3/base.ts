// The WhatsApp v3 shot base: a MotionScene (docs/STYLE_V3.md). The kit plays a shot full frame (the series
// environment: haze, floor, dust) or, with params.layout 'panel', as the frosted card in the presenter shot's panel box
// with the camera's principal point on the card (MotionScene's panel mode).
//
// Helpers: keyed() eases a camera through keys; em(px, dist) is the world size of an em that sets type at `px` cap
// height at `dist` from the camera (Bricolage and Geist caps are ~0.7 em).
import { THREE } from '@engine/three';
import { MotionScene, type CamPose } from '@kit/motion';
import type { Frame, PostOverrides } from '@engine/scene';
import { disposeLayer } from '@engine/scene';
import { H, Layer2D, W } from '@engine/gl';
import { clamp, ease } from '@engine/util';

export { THREE };
export { PANEL } from '@kit/motion';
export type V3 = [number, number, number];

export interface CamKey { t: number; pos: V3; target: V3; fov?: number; ease?: (x: number) => number }

/** The camera through keys: each segment eased (inOutCubic by default) from the key before to the key it heads to. */
export function keyed(t: number, ks: CamKey[]): CamPose {
  if (t <= ks[0]!.t) return { pos: ks[0]!.pos, target: ks[0]!.target, fov: ks[0]!.fov };
  for (let i = 1; i < ks.length; i++) {
    const a = ks[i - 1]!, b = ks[i]!;
    if (t < b.t) {
      const k = (b.ease ?? ease.inOutCubic)(clamp((t - a.t) / (b.t - a.t)));
      const l = (x: V3, y: V3): V3 => [x[0] + (y[0] - x[0]) * k, x[1] + (y[1] - x[1]) * k, x[2] + (y[2] - x[2]) * k];
      return { pos: l(a.pos, b.pos), target: l(a.target, b.target), fov: (a.fov ?? 30) + ((b.fov ?? a.fov ?? 30) - (a.fov ?? 30)) * k };
    }
  }
  const z = ks[ks.length - 1]!;
  return { pos: z.pos, target: z.target, fov: z.fov };
}

/** World units per em for type of cap height `px` (1080p px) at `dist` from a camera of vertical fov `fov`. */
export function em(px: number, dist: number, fov = 30): number {
  return ((px / 0.7) * 2 * dist * Math.tan((fov * Math.PI) / 360)) / 1080;
}

/**
 * The caption band's soft darkening (GFX.md: the bottom 15 % stays free of text and key visuals, a soft darkening there
 * is fine): full-frame shots fade to near black from BAND.from to BAND.to (px of 1080), so whatever the 3D camera
 * carries through the band (a floor, a server's base) reads as a calm dark ground under the captions, and the
 * caption-band gate (high-passed brightness under y 900) stays quiet.
 */
export const BAND = { from: 815, to: 905, floor: 0.06 };

export abstract class WaShot extends MotionScene {
  private band: Layer2D | null = null;

  /** The shot's EDL cut (params.cut), else its window. */
  protected get cut(): number {
    return (this.ctx.params.cut as number | undefined) ?? this.len;
  }

  private bandLayer() {
    if (this.band) return this.band.texture;
    this.band = new Layer2D();
    const c = this.band.ctx, u = H / 1080;
    const g = c.createLinearGradient(0, BAND.from * u, 0, BAND.to * u);
    for (let i = 0; i <= 8; i++) {
      const k = i / 8, a = (1 - BAND.floor) * k * k * (3 - 2 * k);
      g.addColorStop(k, `rgba(0,0,0,${a.toFixed(4)})`);
    }
    c.fillStyle = g;
    c.fillRect(0, BAND.from * u, W, (BAND.to - BAND.from) * u);
    c.fillStyle = `rgba(0,0,0,${1 - BAND.floor})`;
    c.fillRect(0, BAND.to * u, W, H - BAND.to * u);
    return this.band.upload();
  }

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const post = super.render(f, out);
    if (!this.panel) this.ctx.comp.draw(this.ctx.renderer, this.bandLayer(), out, {});
    return post;
  }

  override dispose() {
    if (this.band) disposeLayer(this.band);
    this.band = null;
    super.dispose();
  }
}
