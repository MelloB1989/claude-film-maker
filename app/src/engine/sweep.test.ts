import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { sweepAt, withSweep, type SweepPass } from './sweep';
import { Mat } from './type3d';

const physical = () => ({ vertexShader: THREE.ShaderLib.physical.vertexShader, fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} as Record<string, THREE.IUniform> });

test('withSweep adds the band to a physical material\'s outgoing light, chained onto its own patches', () => {
  const m = Mat.accent('moss');
  const base = m.customProgramCacheKey();
  const band = withSweep(m);
  expect(band.value.toArray()).toEqual([0, 0.04, 0.4, 0]); // off until driven
  const sh = physical();
  m.onBeforeCompile(sh as any, null as any);
  expect(sh.uniforms.uSweep).toBe(band); // the uniform the scene drives is the one the shader reads
  expect(sh.vertexShader).toContain('vSweepN = objectNormal;');
  expect(sh.vertexShader).toContain('vSweepW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
  expect(sh.fragmentShader).toContain('uniform vec4 uSweep;');
  expect(sh.fragmentShader).toMatch(/outgoingLight \+= vec3\(uSweep\.w \* exp\(-sweepS \* sweepS\)[^\n]*\n[^\n]*\n\s*#include <opaque_fragment>/);
  // Mat.accent's own rim is still spliced in: the sweep chains onto it, it does not replace it
  expect(sh.fragmentShader).toContain('totalEmissiveRadiance *= type3dK;');
  // a program of its own (three caches programs by this key), still keyed by what it chained onto
  expect(m.customProgramCacheKey()).toBe(`${base}|sweep`);
  expect(m.customProgramCacheKey()).not.toBe(Mat.accent('moss').customProgramCacheKey());
});

test('sweepAt runs the band across a pass, eased, at strength sin(πu); off before, after and between passes', () => {
  const band = withSweep(Mat.satinBone());
  const pass: SweepPass = { t0: 2, t1: 2.5, x0: -1, x1: 3, y: 0.5 };
  const look = { width: 0.035, slope: 0.4, strength: 2.2 };
  for (const t of [0, 1.99, 2, 2.5, 3]) {
    sweepAt(band, t, [pass], look);
    expect(band.value.w).toBe(0);
  }
  // a quarter of the way through the pass: inOutQuad(0.25) = 0.125 of the way across; the band leans, so its centre
  // is set where it crosses y = 0 for it to cross the baseline at the right x
  sweepAt(band, 2.125, [pass], look);
  expect(band.value.x).toBeCloseTo(-1 + 4 * 0.125 + 0.4 * 0.5, 12);
  expect(band.value.y).toBe(0.035);
  expect(band.value.z).toBe(0.4);
  expect(band.value.w).toBeCloseTo(2.2 * Math.sin(Math.PI * 0.125), 12);
  // half way: half way across, at full strength
  sweepAt(band, 2.25, [pass], look);
  expect(band.value.x).toBeCloseTo(1 + 0.2, 12);
  expect(band.value.w).toBeCloseTo(2.2, 12);
  // the defaults are her's band: slope 0.4, strength 2.2, inOutQuad
  const d = withSweep(Mat.satinBone());
  sweepAt(d, 2.125, [pass], { width: 0.035 });
  sweepAt(band, 2.125, [pass], look);
  expect(d.value.toArray()).toEqual(band.value.toArray());
});

test('sweepAt is a pure function of t: several passes share a band, and a frame never depends on the one before', () => {
  const passes: SweepPass[] = [
    { t0: 1, t1: 1.5, x0: 0, x1: 1, y: 0 },
    { t0: 3, t1: 3.5, x0: 2, x1: 4, y: 0.2 },
  ];
  const look = { width: 0.05 };
  const at = (t: number, before?: number) => {
    const b = withSweep(Mat.satinBone());
    if (before !== undefined) sweepAt(b, before, passes, look);
    sweepAt(b, t, passes, look);
    return b.value.toArray();
  };
  for (const t of [0.5, 1.2, 2, 3.1, 3.4, 4]) for (const before of [1.25, 3.25, 9]) expect(at(t, before)).toEqual(at(t));
  expect(at(1.25)[0]).toBeCloseTo(0.5, 12); // the first pass, half way
  expect(at(3.25)[0]).toBeCloseTo(3 + 0.4 * 0.2, 12); // the second
  expect(at(2)[3]).toBe(0); // between them: off
});
