// The labels of scene `graph` on the GPU (engine/glyphs.ts): each memory's name beside its bead, the dangling link's
// tag at its loose end, and the word the search finds. Mono glyph cells posed on the CPU every frame (a few hundred),
// facing the camera and keeping their size in the world, so the depth of field takes them with their beads; and since
// they write depth, the lens reads them where they stand.
import * as THREE from 'three';
import { GlyphActors, GlyphAtlas } from '../engine/glyphs';
import { F } from '../engine/type';
import type { V3 } from './graph-world';

/** A mono cell's advance (em). */
export const ADV = 0.6;

export interface TextOpts {
  /** The em (m). */
  em: number;
  /** Linear colour; opacity. */
  color: readonly [number, number, number];
  alpha: number;
  /** Characters shown, from the first (default all). */
  n?: number;
  /**
   * Per character: an offset (m, in the camera's right/up/toward), a scale of its alpha, and a scale of its colour; for
   * the tag's collapse and a word's light. Null for none.
   */
  each?: ((i: number) => { off?: V3; alpha?: number; gain?: number } | null) | null;
}

export class Labels {
  readonly atlas: GlyphAtlas;
  readonly actors: GlyphActors;
  private R = new THREE.Vector3();
  private U = new THREE.Vector3();
  private B = new THREE.Vector3();
  private o = new THREE.Vector3();

  constructor(chars: string, capacity: number) {
    this.atlas = new GlyphAtlas(chars, F.mono(500));
    this.actors = new GlyphActors(capacity, this.atlas);
    this.actors.mesh.renderOrder = 3;
  }

  /** Start a frame, facing the camera as it is. */
  begin(cam: THREE.Camera) {
    this.R.set(1, 0, 0).applyQuaternion(cam.quaternion);
    this.U.set(0, 1, 0).applyQuaternion(cam.quaternion);
    this.B.set(0, 0, 1).applyQuaternion(cam.quaternion);
    this.actors.begin();
  }

  /** The camera's right, up and toward-the-lens vectors (unit, world) for this frame. */
  get basis() {
    return { right: this.R, up: this.U, back: this.B };
  }

  /** `text` with its left end of the baseline at `origin` (world), facing the camera. */
  text(text: string, origin: THREE.Vector3 | V3, o: TextOpts) {
    if (o.alpha <= 0.002) return;
    const chars = Array.from(text);
    const n = Math.min(chars.length, o.n ?? chars.length);
    const org = Array.isArray(origin) ? this.o.set(origin[0], origin[1], origin[2]) : this.o.copy(origin);
    const right = this.R.clone().multiplyScalar(o.em), up = this.U.clone().multiplyScalar(o.em);
    for (let i = 0; i < n; i++) {
      const ch = chars[i]!;
      if (/\s/u.test(ch)) continue;
      const e = o.each?.(i) ?? null;
      const a = o.alpha * (e?.alpha ?? 1);
      if (a <= 0.002) continue;
      const g = e?.gain ?? 1;
      const p = org.clone().addScaledVector(this.R, i * ADV * o.em);
      if (e?.off) p.addScaledVector(this.R, e.off[0]).addScaledVector(this.U, e.off[1]).addScaledVector(this.B, e.off[2]);
      this.actors.add({
        origin: p, right, up,
        glyph: [this.atlas.of(ch), -1, 0, 0],
        color: [o.color[0] * g, o.color[1] * g, o.color[2] * g, a],
      });
    }
  }

  end() {
    this.actors.end();
  }

  dispose() {
    this.actors.dispose();
    this.atlas.dispose();
  }
}
