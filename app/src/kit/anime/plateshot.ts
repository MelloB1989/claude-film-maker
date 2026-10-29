// PlateShot: a Blender plate (blender/render.py) as a shot: for each film frame, the frame the plate rendered for it,
// laid in as rendered (linear, premultiplied, its own motion blur and depth of field). Stack the weather, the marks and
// the grade over it as over any picture.
//
// Params:
//   plate          the plate's shot name (default: this shot's id; the page's ?plates can swap it: plateFor)
//   f0             the plate's first film frame (default: this shot's first frame, as render.py's "scene" window takes it)
//   background 'theme'   under the plate, where it is transparent
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { FPS } from '../../engine/config';
import { Plate, plateFor } from '../../engine/plates';
import type { Handles } from '../../engine/transition';
import { clearBackground, type Background } from '../common';

export class PlateShot extends Scene {
  // a plate holds its first or last frame past its window (scene.ts): no handles of its own
  override handles: Handles = { head: 0, tail: 0 };
  private plate: Plate | null = null;

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  override init() {
    const shot = (this.ctx.params.plate as string | undefined) ?? (this.ctx.params.shot as string | undefined) ?? this.ctx.id;
    const f0 = (this.ctx.params.f0 as number | undefined) ?? Math.ceil(this.ctx.start * FPS - 1e-6);
    this.plate = new Plate(plateFor(shot, typeof location !== 'undefined' ? location.search : ''), f0);
  }

  override async prepare(t: number) {
    await this.plate!.prepare(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    clearBackground(this.ctx.renderer, out, (this.ctx.params.background as Background | undefined) ?? 'theme');
    this.plate!.draw(this.ctx.renderer, this.ctx.comp, out, f.t);
  }

  override dispose() {
    this.plate?.dispose();
    this.plate = null;
  }
}

export default PlateShot;
