// What every kit block shares: how it clears its frame (its background) and how it reads its params.
//
// A kit block is a Scene configured entirely by params (film.ts `params`), so a film can use it without code. Every
// block takes `background`:
//   'theme' (default)  the theme's bg role, opaque;
//   'none'             transparent (alpha 0): the block draws only its own marks, to be stacked over another block
//                      (kit Stack) or played as an overlay (film.ts `overlays`, composited premultiplied 'normal');
//   a role or #hex     that colour, opaque;
//   { from, to, angle? } a linear gradient between two roles or colours (angle in degrees, 90 = top to bottom).
import * as THREE from 'three';
import { FSPass, clearRT } from '../engine/gl';
import { lin, type PaletteKey } from '../engine/palette';
import type { SceneCtx } from '../engine/scene';

export type Background = 'theme' | 'none' | PaletteKey | (string & {}) | { from: string; to: string; angle?: number };

let gradPass: FSPass | null = null;

/** Clear `out` to a block's background (see the header). */
export function clearBackground(renderer: THREE.WebGLRenderer, out: THREE.WebGLRenderTarget, bg: Background = 'theme') {
  if (bg === 'none') return clearRT(renderer, out, [0, 0, 0], 0);
  if (typeof bg === 'string') return clearRT(renderer, out, lin(bg === 'theme' ? 'bg' : bg), 1);
  gradPass ??= new FSPass(/* glsl */ `
    uniform vec3 a; uniform vec3 b; uniform vec2 dir;
    void main() {
      float k = clamp(dot(vUv - 0.5, dir) + 0.5, 0.0, 1.0);
      // mixed as the eye sees it (display space), then back to light
      fragColor = vec4(toLinear(mix(toSRGB(a), toSRGB(b), k * k * (3.0 - 2.0 * k))), 1.0);
    }`, { a: { value: new THREE.Vector3() }, b: { value: new THREE.Vector3() }, dir: { value: new THREE.Vector2() } });
  const r = ((bg.angle ?? 90) * Math.PI) / 180;
  (gradPass.u.a!.value as THREE.Vector3).set(...lin(bg.from));
  (gradPass.u.b!.value as THREE.Vector3).set(...lin(bg.to));
  // uv y is up: 90° (top to bottom) runs from +y to −y
  (gradPass.u.dir!.value as THREE.Vector2).set(Math.cos(r), -Math.sin(r));
  gradPass.render(renderer, out);
}

/** A param with a default: `p(this.ctx, 'title', 'Untitled')`. */
export function p<T>(ctx: Pick<SceneCtx, 'params'>, key: string, fallback: T): T {
  const v = ctx.params[key];
  return v === undefined ? fallback : (v as T);
}

/** A required param: throws naming the shot and the key when it is missing. */
export function need<T>(ctx: Pick<SceneCtx, 'params' | 'id'>, key: string): T {
  const v = ctx.params[key];
  if (v === undefined) throw new Error(`shot ${ctx.id}: param '${key}' is required`);
  return v as T;
}
