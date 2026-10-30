// PlateShot: a Blender plate (blender/render.py) as a shot: for each film frame, the frame the plate rendered for it,
// laid in as rendered (linear, premultiplied, its own motion blur and depth of field). Stack the weather, the marks and
// the grade over it as over any picture.
//
// Params:
//   plate          the plate's shot name (default: this shot's id; the page's ?plates can swap it: plateFor)
//   f0             the plate's first film frame (default: this shot's first frame, as render.py's "scene" window takes it)
//   background 'theme'   under the plate, where it is transparent
//   missing 'slate'      a plate with no frames at all (not rendered yet) plays as a slate: its name, "not rendered" and
//                        its window, so a film whose shots are still being made plays and renders whole. 'fail' fails
//                        as any missing plate frame does. A plate that has some frames but not this one always fails
//                        an export (plates.ts): a half-rendered shot is an error, not a draft.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { FPS } from '../../engine/config';
import { Layer2D, W, H } from '../../engine/gl';
import { Plate, plateFor, plateUrl } from '../../engine/plates';
import { font } from '../../engine/type';
import type { Handles } from '../../engine/transition';
import { clearBackground, type Background } from '../common';
import { family } from '../text/layout';

/** Whether a plate has a first frame to show: its EXR or its proxy (the dev server answers 404 for neither). */
export async function plateRendered(shot: string, fetcher: typeof fetch = fetch): Promise<boolean> {
  for (const kind of ['exr', 'proxy'] as const) {
    try {
      const r = await fetcher(plateUrl(shot, 0, kind), { method: 'HEAD' });
      if (r.ok) return true;
    } catch {
      // unreachable: the same as missing
    }
  }
  return false;
}

/** The slate's lines: the plate, that it is not rendered, and the shot's window in film time and frames. */
export function slateLines(id: string, plate: string, start: number, end: number, fps: number): string[] {
  const f = (t: number) => Math.ceil(t * fps - 1e-6);
  return [
    id === plate ? id : `${id} (${plate})`,
    'not rendered',
    `${start.toFixed(2)}–${end.toFixed(2)} s · frames ${f(start)}–${f(end) - 1} · blender/render.py --shot ${plate}`,
  ];
}

/**
 * The plate's first film frame and frame count for a shot's window: render.py renders [ceil(start·fps), ceil(end·fps)).
 * The count clamps held times into the plate: a transition holds its outgoing shot at end − HOLD, which rounds to the
 * frame after the plate's last (a 404 in export), and its incoming one before start, which holds frame 0.
 */
export function plateWindow(start: number, end: number, fps: number, f0?: number): { f0: number; count: number } {
  const first = f0 ?? Math.ceil(start * fps - 1e-6);
  return { f0: first, count: Math.max(1, Math.ceil(end * fps - 1e-6) - first) };
}

export class PlateShot extends Scene {
  // a plate holds its first or last frame past its window (scene.ts): no handles of its own
  override handles: Handles = { head: 0, tail: 0 };
  private plate: Plate | null = null;
  private slate: Layer2D | null = null;

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  override async init() {
    const shot = plateFor((this.ctx.params.plate as string | undefined) ?? (this.ctx.params.shot as string | undefined) ?? this.ctx.id,
      typeof location !== 'undefined' ? location.search : '');
    const { f0, count } = plateWindow(this.ctx.start, this.ctx.end, FPS, this.ctx.params.f0 as number | undefined);
    if ((this.ctx.params.missing ?? 'slate') === 'slate' && !(await plateRendered(shot))) {
      const id = (this.ctx.params.shot as string | undefined) ?? this.ctx.id; // a Stack layer's own id is <shot>[i]
      console.warn(`plate ${shot}: not rendered, ${id} plays as a slate`);
      this.slate = this.drawSlate(slateLines(id, shot, this.ctx.start, this.ctx.end, FPS));
      return;
    }
    this.plate = new Plate(shot, f0, { count });
  }

  override async prepare(t: number) {
    await this.plate?.prepare(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    clearBackground(this.ctx.renderer, out, (this.ctx.params.background as Background | undefined) ?? 'theme');
    if (this.slate) this.ctx.comp.draw(this.ctx.renderer, this.slate.texture, out, { mode: 'replace' });
    else this.plate!.draw(this.ctx.renderer, this.ctx.comp, out, f.t);
  }

  override dispose() {
    this.plate?.dispose();
    this.plate = null;
    this.slate?.dispose();
    this.slate = null;
  }

  /** A mid-grey card with hatching, unmistakable for a picture: the plate's name large, then the rest. */
  private drawSlate(lines: string[]): Layer2D {
    const l = new Layer2D();
    const c = l.ctx;
    l.clear('#3a3d42');
    c.strokeStyle = 'rgba(255,255,255,0.06)';
    c.lineWidth = 14;
    for (let x = -H; x < W; x += 56) {
      c.beginPath();
      c.moveTo(x, H);
      c.lineTo(x + H, 0);
      c.stroke();
    }
    c.textAlign = 'center';
    c.fillStyle = '#f2efe8';
    c.font = font(family({ role: 'mono', weight: 700 }), H * 0.11);
    c.fillText(lines[0]!, W / 2, H * 0.46);
    c.fillStyle = '#e0563f';
    c.font = font(family({ role: 'mono', weight: 500 }), H * 0.05);
    c.fillText(lines[1]!.toUpperCase(), W / 2, H * 0.56);
    c.fillStyle = '#b8b4ab';
    c.font = font(family({ role: 'mono', weight: 400 }), H * 0.022);
    c.fillText(lines[2]!, W / 2, H * 0.63);
    l.upload();
    return l;
  }
}

export default PlateShot;
