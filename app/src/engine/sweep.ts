// The specular sweep: a diagonal band of light that runs across hero type as it lands (her's "memory", "commit", "fact"
// and "blame"; proof's figure landing in moss), strongest on the bevels and walls, where a passing light glints, and
// faint on the face. The film's satin bone is too diffuse for a physical strip light to draw a band (its spill lights
// the whole word first), so the band is added to the material's outgoing light: neutral light, so bone stays out of the
// bloom's chroma gate however bright the glint.
//
// How a scene uses it:
//   init:    const band = withSweep(mat);
//            // one band across several materials (a word's bone and its moss accent): v.value = band.value
//            const v = withSweep(accent); v.value = band.value;
//   render:  // a pass across each hero word as it lands: half a second from 30 ms after its onset (wordTimes), the
//            // band's centre running from a band-width before the word to one after it, along its baseline
//            sweepAt(band, t, [{ t0: at + 0.03, t1: at + 0.53, x0: left - em, x1: right + em, y: baseline }], { width: 0.35 * em });
// Positions are world units (x0, x1 world x where the band crosses world height y; the band leans by `slope`). One
// sweepAt call a frame sets all of the band's state from t, so frames render alike in any order. Made for flat-faced
// type such as Type3D (the face is the geometry's +z); the material must be one the scene owns: withSweep patches it.
import * as THREE from 'three';
import { ease, lerp, prog } from './util';

/** A sweep band: (x) its centre where it crosses world y = 0, in world x, (y) half-width, (z) slope, world x per unit of
 * world y (the band leans), (w) level (0: off). Drive it with sweepAt. */
export type SweepBand = THREE.IUniform<THREE.Vector4>;

/**
 * Add a sweep band to `m`'s outgoing light and return its uniform (off until driven). Chained onto whatever the material
 * patches already (Mat.accent's diff glow), with a program cache key of its own.
 */
export function withSweep(m: THREE.MeshPhysicalMaterial): SweepBand {
  const u = { value: new THREE.Vector4(0, 0.04, 0.4, 0) };
  const prev = m.onBeforeCompile.bind(m);
  const base = m.customProgramCacheKey();
  m.onBeforeCompile = (sh, r) => {
    prev(sh, r);
    sh.uniforms.uSweep = u;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vSweepW;\nvarying vec3 vSweepN;')
      .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\n\tvSweepN = objectNormal;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\n\tvSweepW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform vec4 uSweep;\nvarying vec3 vSweepW;\nvarying vec3 vSweepN;')
      .replace('#include <opaque_fragment>', /* glsl */ `{
		float sweepS = (vSweepW.x + uSweep.z * vSweepW.y - uSweep.x) / uSweep.y;
		float sweepEdge = smoothstep(0.08, 0.55, 1.0 - abs(normalize(vSweepN).z));
		outgoingLight += vec3(uSweep.w * exp(-sweepS * sweepS) * (0.16 + 1.3 * sweepEdge));
	}
	#include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => `${base}|sweep`;
  return u;
}

/** One pass of a band: from t0 to t1 (s) its centre runs from world x0 to x1, measured at world height y. */
export interface SweepPass {
  t0: number;
  t1: number;
  x0: number;
  x1: number;
  y: number;
}

/** How a band looks: its half-width (world units), lean (world x per world y), level at the middle of a pass, easing. */
export interface SweepLook {
  width: number;
  /** Default 0.4. */
  slope?: number;
  /** Default 2.2: a glint, not a flash. */
  strength?: number;
  /** Default ease.inOutQuad. */
  ease?: (u: number) => number;
}

/**
 * Set `band` for time t: the pass running at t (of several, the last that is), eased across it, its level
 * strength·sin(πu) so it fades in and out as it crosses; off (level 0, the rest of it reset too) outside every pass.
 */
export function sweepAt(band: SweepBand, t: number, passes: readonly SweepPass[], look: SweepLook): void {
  const { width, slope = 0.4, strength = 2.2, ease: fn = ease.inOutQuad } = look;
  band.value.set(0, width, slope, 0);
  for (const p of passes) {
    const u = prog(t, p.t0, p.t1, fn);
    if (u <= 0 || u >= 1) continue;
    band.value.set(lerp(p.x0, p.x1, u) + slope * p.y, width, slope, strength * Math.sin(Math.PI * u));
  }
}
