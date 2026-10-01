// The odometer of `proof` in three.js: extruded Bricolage digits (Type3D) mounted round wheels that turn on one shaft,
// as a counter's drums are, seen through a window.
//
// The counter's frame: its origin is the figure's left end on the baseline, its digits' faces at z = 0 (Type3D's
// convention), so a figure at rest sits exactly where a flat kerned line would set it. The shaft runs along x behind
// the faces, at the digits' middle height (CENTRE em above the baseline) and RADIUS em deep. A drum is a wheel on the
// shaft at a digit's centre (mid-advance); slot k of its ring stands at k·(2π/slots) round the shaft below the window,
// face out, so turning the wheel by one slot brings the next digit up into the window, as a counting odometer does.
//
// The window: there is no housing. A digit is seen only within a band round its drum's axle, fading out past WINDOW[0]
// and gone by WINDOW[1] (radians from square to the viewer), so a figure at rest stands alone in the dark and a rolling
// drum shows its digits wheeling up through the band. Each drum carries its own window (measured in its own frame), so
// a drum that hops or tilts takes its window with it; only turning its wheel moves a face through the band. The fade is
// an ordered dither (a 4×4 Bayer screen) rather than alpha: the type stays opaque, depth stays whole for the depth of
// field, and the stage's four supersampling taps and the motion blur's sub-frames average the dither into a smooth fade
// as a face wheels through. (Nothing should rest in the band: a still face there would show the screen.)
import * as THREE from 'three';
import { Type3D, type Glyph3D } from '../engine/type3d';

/** The drums' radius (em): round enough that a turning digit visibly wheels, big enough that the neighbours of a digit
 * at rest stand clear of the window. */
export const RADIUS = 1.6;
/** The digits' middle above the baseline (em): Bricolage's figures run from −0.014 to 0.674 em. */
export const CENTRE = 0.33;
/** The window (radians from square to the viewer): whole within the first, gone by the second. A digit at rest spans
 * ±0.235 rad (its back included), so the detent's click (a few degrees) keeps it whole; its neighbours start 0.393 rad
 * out. */
export const WINDOW: readonly [number, number] = [0.28, 0.385];

/** A drum's window uniforms. */
export interface WindowUniforms {
  /** World → the drum's frame (its axle the frame's x axis). */
  uWinInv: THREE.IUniform<THREE.Matrix4>;
  /** (axle y, axle z) in that frame, then the window's two angles. */
  uWin: THREE.IUniform<THREE.Vector4>;
}

export function windowUniforms(): WindowUniforms {
  return { uWinInv: { value: new THREE.Matrix4() }, uWin: { value: new THREE.Vector4(0, 0, WINDOW[0], WINDOW[1]) } };
}

/**
 * Patch `m` (a Type3D material the scene owns, Mat.accent's or not, with or without a sweep) so it shows only within
 * a drum's window, times `presence` (0..1: a drum fading in). Chained onto the material's patches so far. Returns the
 * presence uniform.
 */
export function withWindow(m: THREE.MeshPhysicalMaterial, win: WindowUniforms): THREE.IUniform<number> {
  const presence = { value: 1 };
  const prev = m.onBeforeCompile.bind(m);
  const base = m.customProgramCacheKey();
  m.onBeforeCompile = (sh, r) => {
    prev(sh, r);
    sh.uniforms.uWinInv = win.uWinInv;
    sh.uniforms.uWin = win.uWin;
    sh.uniforms.uWinPresence = presence;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWinW;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\n\tvWinW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', /* glsl */ `#include <common>
uniform mat4 uWinInv;
uniform vec4 uWin;
uniform float uWinPresence;
varying vec3 vWinW;
const float WIN_BAYER[16] = float[16](0., 8., 2., 10., 12., 4., 14., 6., 3., 11., 1., 9., 15., 7., 13., 5.);`)
      .replace('#include <clipping_planes_fragment>', /* glsl */ `#include <clipping_planes_fragment>
	{
		vec3 winP = (uWinInv * vec4(vWinW, 1.0)).xyz;
		float winA = abs(atan(winP.y - uWin.x, winP.z - uWin.y));
		float winK = (1.0 - smoothstep(uWin.z, uWin.w, winA)) * uWinPresence;
		ivec2 winQ = ivec2(mod(gl_FragCoord.xy, 4.0));
		if (winK < (WIN_BAYER[winQ.x + 4 * winQ.y] + 0.5) / 16.0) discard;
	}`);
  };
  m.customProgramCacheKey = () => `${base}|proof-window`;
  return presence;
}

/**
 * A drum: a wheel on the counter's shaft carrying `slots` (a character per slot, '' for a blank face), extruded in
 * `family` at `size` world units per em with `material` (the scene's, patched withWindow). `group` stands at the drum's
 * centre on the shaft; place it along x with `at(x)` and turn it with `turn(position)`, position in slots (slot p square
 * to the window; rising positions bring the slots below up into it).
 */
export class Drum {
  readonly group = new THREE.Group();
  readonly wheel = new THREE.Group();
  readonly faces: { slot: number; glyph: Glyph3D }[] = [];
  /** The drum's window: set its frame each render with `frame()`. */
  readonly win = windowUniforms();
  private type: Type3D;
  readonly step: number;

  constructor(readonly slots: readonly string[], family: string, readonly size: number, material: THREE.Material) {
    this.step = (2 * Math.PI) / slots.length;
    const chars = slots.filter((c) => c);
    this.type = new Type3D(chars.join(''), { family, size }, material);
    let gi = 0;
    slots.forEach((c, k) => {
      if (!c) return;
      const g = this.type.glyphs[gi++]!;
      this.wheel.add(g.mesh);
      this.faces.push({ slot: k, glyph: g });
    });
    this.group.add(this.wheel);
    this.group.position.set(0, CENTRE * size, -RADIUS * size);
    this.place();
  }

  /** Every face on its slot, square and upright on the ring. */
  place() {
    const s = this.size;
    for (const { slot, glyph } of this.faces) {
      const a = slot * this.step;
      // the glyph's pivot (mid-advance, half its x-height, mid-depth) at the front slot: its face on the drum's skin,
      // its figure's middle on the axle's height
      const y = glyph.home.y - CENTRE * s, z = RADIUS * s + glyph.home.z;
      glyph.mesh.position.set(0, y * Math.cos(a) - z * Math.sin(a), y * Math.sin(a) + z * Math.cos(a));
      glyph.mesh.rotation.set(a, 0, 0);
      glyph.mesh.scale.setScalar(s);
    }
  }

  /** Point the window at the drum where it stands now (after the scene has placed it and its parents). */
  frame() {
    this.group.updateWorldMatrix(true, false);
    this.win.uWinInv.value.copy(this.group.matrixWorld).invert();
  }

  /** The drum's centre along the counter's x (world units in the counter frame). */
  at(x: number) {
    this.group.position.x = x;
  }

  /** Turn the wheel to `position` (slots). */
  turn(position: number) {
    this.wheel.rotation.x = -position * this.step;
  }

  dispose() {
    this.type.dispose();
  }
}

/** The ten figures on a drum's ring, 0 to 9. */
export const DIGITS = Array.from('0123456789');
