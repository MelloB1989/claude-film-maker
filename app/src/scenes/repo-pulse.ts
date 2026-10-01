// Light that travels along a strand of the diff thread, for `repo` (Plan 2 Task 14): a commit's moss light rides in
// with its bead, blooms as the bead lands and runs out along the thread both ways (the progress log's Plan 3 note, "a
// flare travelling out from the bead", made here because the brief asks for the pulse).
//
// The engine's Thread lights a strand whole (setStrandGlow). StrandLight lights it along its length: a strip texture of
// LIGHT_N samples over the thread's arc fraction holds an envelope 0..1 per strand (blood in r, moss in g), and the ply
// shader reads it at the fragment's arc fraction and scales that strand's core from its level at rest (what
// setStrandGlow holds it at, DIFF_THREAD.rest) up to the lit level (DIFF_THREAD.glow) where the envelope is 1. The
// fibres keep the rest level: they carry 3% of a core's light, a lit window of them would not read.
//
// The envelope is a sum of moving lights (Glow: a centre, a half-width and a level, all in arc fraction), the brightest
// winning where they overlap; repo.ts makes them from the commits' times (commitGlows). Everything is a pure function
// of the glows handed in, so a frame renders alike in any order.
//
// It is a patch on the thread's material, chained after the engine's own (as engine/sweep.ts withSweep chains its band),
// with a program key of its own, so it names the engine's shader internals: the varying vU, the ply index thPi, and the
// place the ply's emission has been added by (after emissivemap_fragment, before lights_physical_fragment). If one is
// gone the patch throws while the shader compiles: loud, never a thread that quietly stops lighting. (Engine request in
// the task report: an envelope along the strand in Thread itself, after which this file goes.)
import * as THREE from 'three';
import type { Thread } from '../engine/thread3d';
import { clamp } from '../engine/util';

/** Samples of the strip along the thread's arc fraction. */
export const LIGHT_N = 512;

/** A light on a strand: centred at arc fraction `u`, `w` its half-width (arc fraction, where it has fallen to 1/e), `k` its level 0..1. */
export interface Glow {
  u: number;
  w: number;
  k: number;
}

/** The envelope at arc fraction u: the brightest of the glows there (0..1). */
export function envelope(u: number, glows: readonly Glow[]): number {
  let e = 0;
  for (const g of glows) {
    if (g.k <= 0 || g.w <= 0) continue;
    const x = (u - g.u) / g.w;
    if (x * x < 30) e = Math.max(e, g.k * Math.exp(-x * x));
  }
  return clamp(e);
}

const PARS = /* glsl */ `
uniform sampler2D tStrandLight;
uniform vec2 uStrandGain;`;

// the strip's texel centres span the thread: u = 0 at the first, u = 1 at the last
const MAIN = /* glsl */ `
{
  vec4 slK = texture2D(tStrandLight, vec2((clamp(vU, 0.0, 1.0) * ${LIGHT_N - 1}.0 + 0.5) / ${LIGHT_N}.0, 0.5));
  totalEmissiveRadiance *= 1.0 + (thPi == 1 ? uStrandGain.x * slK.r : thPi == 2 ? uStrandGain.y * slK.g : 0.0);
}`;

/** What the patch needs of the engine's ply shader, after the engine's own patch has run. */
const ANCHORS = ['#include <common>', 'varying float vU;', 'thPi', 'totalEmissiveRadiance +=', '#include <lights_physical_fragment>'];

/**
 * The ply fragment shader with the strip read in: its uniforms after three's common chunk, and the scaling of the
 * strand's emission (all the ply emits: the engine adds only the core's glow) just before the lights. Throws if the
 * engine's shader lacks what it reads.
 */
export function patchPlyFragment(frag: string): string {
  const missing = ANCHORS.filter((a) => !frag.includes(a));
  if (missing.length) throw new Error(`repo-pulse: the thread's ply shader has changed, it lacks ${missing.map((m) => JSON.stringify(m)).join(', ')}`);
  const at = frag.indexOf('#include <lights_physical_fragment>');
  if (frag.lastIndexOf('totalEmissiveRadiance +=') > at) throw new Error('repo-pulse: the ply adds its glow after the lights; the strip would not scale it');
  return frag.replace('#include <common>', `#include <common>\n${PARS}`).replace('#include <lights_physical_fragment>', `${MAIN}\n#include <lights_physical_fragment>`);
}

export class StrandLight {
  readonly texture: THREE.DataTexture;
  private data = new Uint8Array(LIGHT_N * 4);
  private gain: THREE.IUniform<THREE.Vector2>;

  /**
   * Patch `thread`'s ply material. `rest` and `lit` are the strand's levels (look.ts glow levels) at envelope 0 and 1;
   * the scene holds both strands at `rest` with setStrandGlow and this lights them from there.
   */
  constructor(thread: Thread, rest: number, lit: number) {
    if (!(rest > 0) || !(lit >= rest)) throw new Error(`StrandLight: needs 0 < rest <= lit (have ${rest}, ${lit})`);
    this.texture = new THREE.DataTexture(this.data, LIGHT_N, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
    this.texture.minFilter = this.texture.magFilter = THREE.LinearFilter;
    this.texture.wrapS = this.texture.wrapT = THREE.ClampToEdgeWrapping;
    this.texture.generateMipmaps = false;
    this.texture.colorSpace = THREE.NoColorSpace;
    this.texture.needsUpdate = true;
    const g = lit / rest - 1;
    this.gain = { value: new THREE.Vector2(g, g) };
    const tex = { value: this.texture };
    const m = thread.mesh.material as THREE.MeshPhysicalMaterial;
    const prev = m.onBeforeCompile.bind(m);
    const key = m.customProgramCacheKey();
    m.onBeforeCompile = (sh, r) => {
      prev(sh, r);
      sh.uniforms.tStrandLight = tex;
      sh.uniforms.uStrandGain = this.gain;
      sh.fragmentShader = patchPlyFragment(sh.fragmentShader);
    };
    m.customProgramCacheKey = () => `${key}|repo-strand-light`;
  }

  /** Light the strands along their length for this frame: moss (and blood) from their glows. */
  set(moss: readonly Glow[], blood: readonly Glow[] = []) {
    const d = this.data;
    for (let i = 0; i < LIGHT_N; i++) {
      const u = i / (LIGHT_N - 1);
      d[4 * i] = Math.round(255 * envelope(u, blood));
      d[4 * i + 1] = Math.round(255 * envelope(u, moss));
      d[4 * i + 2] = 0;
      d[4 * i + 3] = 255;
    }
    this.texture.needsUpdate = true;
  }

  dispose() {
    this.texture.dispose();
  }
}
