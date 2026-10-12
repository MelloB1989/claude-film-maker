// MeshGradient: soft blobs of colour drifting over the base, blended into one another the way a designer's mesh
// gradient is (mixed as the eye sees them), with a slow domain warp so their edges breathe instead of sliding. The calm
// default behind type; pulse swells them on the grid.
//
// Params (and every background param, base.ts):
//   colors          up to 6 inks, roles or #hex (default: color, color2, 'accentDim', 'accent2Dim')
//   blobs 5         how many blobs (they take the inks in turn)
//   size 0.55       a blob's radius, in units of the frame's short side (times scale)
//   warp 0.35       how much the domain warps (0: round blobs)
//   depth 0.6       how far the blobs sink toward the base between them (0: a flat wash of colour)
import * as THREE from 'three';
import { BgScene } from './base';
import { lin } from '../../engine/palette';
import type { Frame } from '../../engine/scene';

export class MeshGradient extends BgScene {
  protected override defaults = { intensity: 1 };
  private own = {
    uInks: { value: Array.from({ length: 6 }, () => new THREE.Vector3()) },
    uInkCount: { value: 4 }, uBlobs: { value: 5 }, uSize: { value: 0.55 }, uWarp: { value: 0.35 }, uDepth: { value: 0.6 },
  };

  protected override uniforms() {
    return this.own;
  }

  override init() {
    const inks = this.ctx.params.colors;
    if (inks !== undefined && !(Array.isArray(inks) && inks.length > 0 && inks.length <= 6 && inks.every((c) => typeof c === 'string'))) {
      throw new Error(`shot ${this.ctx.id}: MeshGradient colors is 1 to 6 roles or #hex colours`);
    }
    super.init();
  }

  protected override update(_f: Frame) {
    const inks = this.k<string[]>('colors', [this.k('color', 'accent'), this.k('color2', 'accent2'), 'accentDim', 'accent2Dim']);
    inks.forEach((c, i) => this.own.uInks.value[i]!.set(...lin(c)));
    this.own.uInkCount.value = inks.length;
    this.own.uBlobs.value = Math.max(1, Math.min(8, Math.round(this.k('blobs', 5))));
    this.own.uSize.value = this.k('size', 0.55);
    this.own.uWarp.value = this.k('warp', 0.35);
    this.own.uDepth.value = this.k('depth', 0.6);
  }

  protected effect() {
    return /* glsl */ `
uniform vec3 uInks[6]; uniform int uInkCount, uBlobs; uniform float uSize, uWarp, uDepth;

vec3 inkAt(int i) {
  int k = i - (i / uInkCount) * uInkCount;
  vec3 c = uInks[0];
  for (int j = 1; j < 6; j++) if (j == k) c = uInks[j];
  return c;
}

vec4 effect(vec2 p, vec2 uv) {
  float t = uTime * 0.11;
  vec2 q = p / uScale;
  // a slow warp of the domain: the blobs' edges breathe
  vec2 w = vec2(fbm(vec3(q * 0.9, t * 0.6 + uSeed), 3), fbm(vec3(q * 0.9 + 5.2, t * 0.6 - uSeed), 3));
  q += uWarp * 0.45 * w;
  vec2 hf = 0.5 * uRes / min(uRes.x, uRes.y) / uScale;
  vec3 sum = vec3(0.0);
  float S = 0.0;
  for (int i = 0; i < 8; i++) {
    if (i >= uBlobs) break;
    float fi = float(i), s = uSeed * 3.17 + fi * 1.618;
    // Lissajous drift, spread over the frame
    vec2 c = vec2(sin(t * (0.7 + 0.13 * fi) + s * 2.3), cos(t * (0.53 + 0.11 * fi) + s * 1.7)) * hf * 0.75;
    c += (hash22(vec2(fi, uSeed)) - 0.5) * hf * 0.5;
    float r = uSize * (0.75 + 0.5 * hash12(vec2(fi * 3.1, uSeed + 1.0))) * (1.0 + 0.25 * uPulse);
    float d2 = dot(q - c, q - c) / (r * r);
    float wgt = exp(-2.2 * d2);
    sum += wgt * toSRGB(inkAt(i));
    S += wgt;
  }
  // the inks at a deep display level (saturation kept), the base showing through between the blobs
  vec3 col = toLinear(sum / max(S, 1e-4) * 0.62 * uIntensity * (1.0 + 0.35 * uPulse));
  float a = sat(1.0 - exp(-1.3 * S)) * (1.0 - 0.35 * uDepth);
  return vec4(col * a, a);
}`;
  }
}

export default MeshGradient;
