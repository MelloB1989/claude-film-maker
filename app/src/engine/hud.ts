// Global overlay: the crop-mark frame. Off unless a scene asks for it (post.frame > 0).
import * as THREE from 'three';
import { Layer2D, W, H } from './gl';
import { rgba } from './palette';
import { disposeLayer } from './scene';
import { clamp, ease, lerp } from './util';

export interface HudState {
  opacity: number;
  /** 0..1 the crop-mark frame: 1 in place, 0 flown out past the edges. */
  frame: number;
  /** 0..1: the frame is light — draw the marks in ink. */
  paper: number;
}

export class Hud {
  /** The marks' full-frame layer, made the first time they show: until then the HUD holds no frame-sized canvas. */
  private layer: Layer2D | null = null;
  /** What post composites while the marks are off: one clear texel (post skips a HUD texel of alpha 0). */
  private none = new THREE.DataTexture(new Uint8Array(4), 1, 1);

  constructor() {
    this.none.needsUpdate = true;
  }

  draw(_t: number, st: HudState) {
    if (!(st.opacity > 0.001 && st.frame > 0.001)) return this.none;
    const L = (this.layer ??= new Layer2D());
    L.clear();
    L.ctx.globalAlpha = st.opacity;
    this.cropMarks(L.ctx, st.frame, st.paper > 0.5);
    return L.upload();
  }

  dispose() {
    if (this.layer) disposeLayer(this.layer);
    this.layer = null;
    this.none.dispose();
  }

  /** Corner marks; as `k` drops they fly out along the diagonals and past the edges. */
  private cropMarks(c: CanvasRenderingContext2D, k: number, ink: boolean) {
    const e = ease.inOutCubic(clamp(k));
    c.save();
    c.globalAlpha *= clamp(k * 3);
    c.strokeStyle = ink ? rgba('ink', 0.45) : rgba('bone', 0.34);
    c.lineWidth = 1.25;
    const m = lerp(-40, 36, e), l = 22;
    c.beginPath();
    for (const [x, y, sx, sy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]] as const) {
      c.moveTo(x + sx * l, y + 0.5 * sy); c.lineTo(x, y + 0.5 * sy); c.lineTo(x, y + sy * l);
    }
    c.stroke();
    c.restore();
  }
}
