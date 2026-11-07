// The WhatsApp v3 shot base: a MotionScene (docs/STYLE_V3.md) that plays full frame or as a panel beside the presenter.
//
// Full: the series environment (haze, floor, dust), the camera from cam(t).
// Panel (params.layout 'panel'): the frosted card of the style guide in the panel box (x 1010-1860, y 150-930 of
// 1920x1080) scales up from 0.92 with an overshoot from the presenter's side, the 3D draws over it with no environment
// (the matte pair renders it over black and over grey), and the camera's principal point sits on the card's centre
// (a view offset), so a shot frames its subject as usual and it lands in the card.
//
// Helpers: keyed() eases a camera through keys; em(px, dist) is the world size of an em that sets type at `px` cap
// height at `dist` from the camera (Bricolage and Geist caps are ~0.7 em).
import { THREE } from '@engine/three';
import { MotionScene, type CamPose } from '@kit/motion';
import type { Frame, PostOverrides } from '@engine/scene';
import { H, Layer2D, W } from '@engine/gl';
import { disposeLayer } from '@engine/scene';
import { clearBackground, type Background } from '@kit/common';
import { clamp, ease } from '@engine/util';
import { spring } from '@kit/motion';

export { THREE };
export type V3 = [number, number, number];

/** The panel box (px of 1920x1080) and the content's lower limit inside it. */
export const PANEL = { x0: 1010, x1: 1860, y0: 150, y1: 930, contentY1: 770 };

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

export abstract class WaShot extends MotionScene {
  private card: Layer2D | null = null;

  constructor(ctx: ConstructorParameters<typeof MotionScene>[0]) {
    super(ctx);
    if (this.panel) {
      this.env = { floor: false, haze: false, dust: false };
      this.arrival = { dur: 0.42, dist: 0.1, yaw: -6, roll: 0 };
      this.basePost = { ...this.basePost, grain: 0, vignette: 0, ca: 0 };
    }
  }

  protected get panel(): boolean {
    return this.ctx.params.layout === 'panel';
  }

  /** The shot's own default: the EDL cut (params.cut) or the window. */
  protected get cut(): number {
    return (this.ctx.params.cut as number | undefined) ?? this.len;
  }

  protected override placeCamera(f: Frame) {
    super.placeCamera(f);
    const cam = this.stage.camera;
    if (this.panel) {
      // the principal point on the card's centre; the card is (x1-x0)/1920 of the width: a narrower view of the same lens
      const cx = ((PANEL.x0 + PANEL.x1) / 2 / 1920) * W, cy = ((PANEL.y0 + PANEL.contentY1) / 2 / 1080) * H;
      cam.setViewOffset(W, H, W / 2 - cx, H / 2 - cy, W, H);
    } else cam.clearViewOffset();
    cam.updateProjectionMatrix();
  }

  /** The panel card: frosted dark glass, an accent top edge, scaled up from 0.92 with an overshoot from the left. */
  private drawCard(t: number) {
    this.card ??= new Layer2D();
    const L = this.card, c = L.ctx, u = W / 1920;
    L.clear();
    const k = spring(t, 0, 0.5, 0.09), a = clamp(t / 0.12);
    const x0 = PANEL.x0 * u, x1 = PANEL.x1 * u, y0 = PANEL.y0 * u, y1 = PANEL.y1 * u;
    const s = 0.92 + 0.08 * k;
    c.save();
    c.globalAlpha = a;
    c.translate(x0, (y0 + y1) / 2);
    c.scale(s, s);
    c.translate(-x0 + (1 - k) * -30 * u, -(y0 + y1) / 2);
    c.shadowColor = 'rgba(0,0,0,0.4)';
    c.shadowBlur = 50 * u;
    c.shadowOffsetY = 16 * u;
    c.beginPath();
    c.roundRect(x0, y0, x1 - x0, y1 - y0, 18 * u);
    c.fillStyle = 'rgba(26,20,16,0.78)';
    c.fill();
    c.shadowColor = 'transparent';
    c.strokeStyle = '#3B3129';
    c.lineWidth = Math.max(1, u);
    c.stroke();
    // the accent top edge: draws on from the left
    const e = ease.outExpo(clamp((t - 0.08) / 0.5));
    c.beginPath();
    c.roundRect(x0 + 18 * u, y0 - 1.5 * u, (x1 - x0 - 36 * u) * e, 3 * u, 1.5 * u);
    c.fillStyle = '#25D366';
    c.fill();
    c.restore();
    return L.upload();
  }

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    if (!this.panel) return super.render(f, out);
    // panel: background, card, then the stage over it (no environment)
    const r = this.ctx.renderer;
    this.flat?.clear();
    const focusAt = this.update(f) ?? new THREE.Vector3(...this.base.target);
    this.placeCamera(f);
    const dof = this.p('dof', true) ? { focus: Math.max(0.05, this.stage.depthOf(focusAt)), fstop: this.p('fstop', 2.8), maxBlurPx: this.p('maxBlur', 30) } : null;
    clearBackground(r, out, this.p<Background>('background', 'theme'));
    this.ctx.comp.draw(r, this.drawCard(f.lt), out, {});
    this.stage.render(out, { dof, clear: false });
    if (this.flat) this.ctx.comp.draw(r, this.flat.upload(), out, {});
    return this.post(f.lt);
  }

  override dispose() {
    if (this.card) disposeLayer(this.card);
    this.card = null;
    super.dispose();
  }
}
