// Dev harness for Blender plates and tracks (Review Focus 4). Render the test shot, then stills of film frames 43
// and 57 (t = n / 30):
//   /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot _cube --mode look --res 1920x1080
//   bun scripts/render.ts stills --module _platetest --t 1.4333333333333333,1.9
// The plate fills the frame (Blender burned its film frame number in at the lower left) and a 6 px blood dot sits on
// track.at('corner', t), the cube's top-right corner. The engine's own film frame number is set at the lower right:
// the two numbers match when plate frame n is on screen at film frame n.
import type * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { Layer2D, W, H, clearRT } from '../engine/gl';
import { LIN, rgba } from '../engine/palette';
import { Plate } from '../engine/plates';
import { Track } from '../engine/track';
import { F, font } from '../engine/type';
import { TAU, frameIdx } from '../engine/util';

const SHOT = '_cube';

export default class PlateTest extends Scene {
  private plate!: Plate;
  private track!: Track;
  private layer = new Layer2D();

  override async init() {
    this.track = await Track.load(SHOT);
    this.plate = new Plate(SHOT, this.track.f0, { count: this.track.frames });
  }

  override async prepare(t: number) {
    await this.plate.prepare(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp } = this.ctx;
    clearRT(renderer, out, LIN.ink);
    this.plate.draw(renderer, comp, out, f.t);
    const L = this.layer, c = L.ctx;
    L.clear();
    const a = this.track.at('corner', f.t);
    if (a.visible > 0) {
      c.fillStyle = rgba('blood');
      c.beginPath();
      c.arc(a.x, a.y, 3, 0, TAU);
      c.fill();
    }
    c.font = font(F.mono(700), 32);
    c.fillStyle = rgba('boneDim');
    c.textAlign = 'right';
    c.fillText(String(frameIdx(f.t)), W - 100, H - 100);
    comp.draw(renderer, L.upload(), out);
  }

  override dispose() {
    this.plate?.dispose();
  }
}
