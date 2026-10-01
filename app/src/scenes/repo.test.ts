// Scene `repo`: its times against the film's own voiceover and beat grid (repo.ts timesOf), its copy against the facts
// sheet, the commits' glide and light, the chips' pop (repo-chips.ts), and the strand light's shader patch on the real
// thread shader (repo-pulse.ts).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { EMBER, FILE, LOG, commitGlows, fileSwing, glideU, timesOf } from './repo';
import { LIGHT_N, StrandLight, envelope, patchPlyFragment } from './repo-pulse';
import { LAUNCH, POP, chipGeometry, chipPop, layoutChips, recoil } from './repo-chips';
import { DIFF_THREAD, Thread } from '../engine/thread3d';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import S from './repo.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'repo')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'repo').flatMap((l) => l.words);
const at = (w: string) => words.find((x) => norm(x.w) === norm(w))!.start;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);

describe('repo: its times come from the data', () => {
  test('the listing pops on the downbeat she reaches "git repo" on, a chip a 32nd note', () => {
    expect(onGrid(T.pop, audio.downbeats)).toBe(true);
    expect(T.pop).toBeGreaterThan(at("i'm"));
    expect(T.pop).toBeLessThan(at('repo'));
    T.chips.forEach((c, i) => expect(c).toBeCloseTo(T.pop + (i * 60) / audio.bpm / 8, 9));
  });

  test('`cd` types with "I\'m just a…" and is done before the pop; `git log` types in the pause and is done before "You"', () => {
    expect(T.cd.at).toBe(at("i'm"));
    expect(T.cd.end).toBeLessThan(T.pop);
    expect(T.log.at).toBeGreaterThan(at('repo'));
    expect(T.log.end).toBeLessThan(T.enter);
    expect(T.enter).toBeLessThan(T.cross);
    expect(T.cross).toBeLessThan(at('you'));
  });

  test('the four commits land on the four beats from "You", newest first; the file on the beat after; all in the window', () => {
    expect(T.beads).toHaveLength(4);
    for (const b of T.beads) expect(onGrid(b, audio.beats)).toBe(true);
    expect(T.beads[0]!).toBeCloseTo(at('you'), 1);
    for (let i = 1; i < 4; i++) expect(T.beads[i]! - T.beads[i - 1]!).toBeCloseTo(60 / audio.bpm, 6);
    expect(onGrid(T.fileLand, audio.beats)).toBe(true);
    expect(T.fileLand - T.beads[3]!).toBeCloseTo(60 / audio.bpm, 6);
    expect(T.note).toBeCloseTo(at('read') - 0.02, 9);
    for (const t of [T.pop, T.cross, ...T.beads, T.note, T.fileLand]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end - 0.5);
    }
  });
});

describe('repo: the copy is the facts sheet\'s', () => {
  const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[] };
  test('the memory file is spec §11.4 line for line, its blank lines included', () => {
    const file = FILE.map((l) => l.text).join('\n');
    expect(facts.verbatim.map((e) => e.text)).toContain(file);
    expect(FILE).toHaveLength(18);
  });

  test('the log is spec §4\'s four entries, newest first, each a seven-hex hash and its message', () => {
    expect(LOG.map((l) => l.line)).toEqual(S.slice(3, 7));
    expect(LOG.map((l) => l.hash)).toEqual(['3f9a1c2', '8b21e04', 'a41c9d0', '105ca74']);
    for (const l of LOG) expect(facts.copy.map((e) => e.text)).toContain(l.line);
  });
});

describe('repo: a commit glides in and clicks into place', () => {
  const len = 2;
  test('it comes from nearer the camera, lands on its mark on its beat, overshoots a hair and settles', () => {
    const u = 0.5, land = 10;
    expect(glideU(land - 0.5, u, land, len).s).toBe(0);
    expect(glideU(land - 0.06, u, land, len).u).toBeLessThan(u);
    expect(glideU(land, u, land, len).u).toBeCloseTo(u, 9);
    let most = 0;
    for (let t = land; t < land + 0.5; t += 0.002) most = Math.max(most, glideU(t, u, land, len).u - u);
    expect(most).toBeGreaterThan(0);
    expect(most * len).toBeLessThan(0.012); // the click: under 12 mm past its mark
    expect(Math.abs(glideU(land + 0.6, u, land, len).u - u) * len).toBeLessThan(1e-4);
  });

  test('its light rides in with it, blooms to full on the landing, runs out both ways and leaves an ember', () => {
    const c = [{ u: 0.5, at: 10 }];
    const peak = (t: number) => envelope(0.5, commitGlows(t, c, len));
    expect(commitGlows(9, c, len)).toEqual([]);
    expect(peak(10)).toBeCloseTo(1, 6);
    expect(peak(12)).toBeCloseTo(EMBER, 2);
    // the ripple's two fronts move apart
    const front = (t: number) => {
      let best = 0.5, k = 0;
      for (let u = 0.52; u < 0.9; u += 0.001) {
        const e = envelope(u, commitGlows(t, c, len));
        if (e > k + 1e-9) (k = e), (best = u);
      }
      return best;
    };
    expect(front(10.3)).toBeGreaterThan(front(10.15));
    for (let t = 9.8; t < 11; t += 0.05) for (let u = 0; u <= 1; u += 0.01) expect(envelope(u, commitGlows(t, c, len))).toBeLessThanOrEqual(1);
    // a pure function of t
    expect(commitGlows(10.2, c, len)).toEqual(commitGlows(10.2, c, len));
  });

  test('the file swings in, all but there on its beat, and at rest after', () => {
    expect(fileSwing(9, 10)).toBe(0);
    expect(fileSwing(10, 10)).toBeGreaterThan(0.98);
    expect(fileSwing(10.2, 10)).toBe(1);
  });
});

describe('repo: the ls chips', () => {
  test('each as wide as its name in mono cells plus padding, a gap between', () => {
    const c = layoutChips(['facts/', 'incidents/'], 30, 15.6, 15, 16);
    expect(c[0]).toEqual({ name: 'facts/', x: 30, w: 6 * 15.6 + 30 });
    expect(c[1]!.x).toBeCloseTo(30 + c[0]!.w + 16, 9);
  });

  test('a chip launches LAUNCH before its note, lands on it, overshoots inside the motion language and rights itself', () => {
    expect(chipPop(10 - LAUNCH - 0.01, 10).on).toBe(false);
    expect(chipPop(10, 10).lift).toBeCloseTo(1, 9);
    let most = 0;
    for (let t = 10; t < 10.5; t += 0.001) most = Math.max(most, chipPop(t, 10).lift);
    expect(most - 1).toBeGreaterThan(0.03);
    expect(most - 1).toBeLessThan(0.12);
    expect(chipPop(10, 10).tilt).toBeGreaterThan(0);
    expect(chipPop(10.6, 10).tilt).toBeCloseTo(0, 3);
    expect(chipPop(10.6, 10).scale).toBeCloseTo(1, 6);
    for (const s of [POP.lift, POP.right]) {
      expect(s.freq).toBeGreaterThanOrEqual(4);
      expect(s.freq).toBeLessThanOrEqual(6);
      expect(s.damping).toBeGreaterThanOrEqual(0.5);
      expect(s.damping).toBeLessThanOrEqual(0.7);
    }
  });

  test('the panel takes the kick of each launch and comes back to rest', () => {
    expect(recoil(9, [10, 10.075])).toBe(0);
    expect(recoil(10 - LAUNCH + 0.02, [10])).toBeGreaterThan(0);
    expect(Math.abs(recoil(11, [10, 10.075]))).toBeLessThan(1e-4);
  });

  test('a chip is a rounded tile: its face at z = 0, its back at −depth, its normals unit and the face\'s +z', () => {
    const g = chipGeometry(120, 46, 13, 12, 3);
    g.computeBoundingBox();
    const b = g.boundingBox!;
    expect(b.min.x).toBeCloseTo(-60, 6);
    expect(b.max.y).toBeCloseTo(23, 6);
    expect(b.max.z).toBeCloseTo(0, 9);
    expect(b.min.z).toBeCloseTo(-12, 9);
    const P = g.getAttribute('position'), N = g.getAttribute('normal');
    for (let i = 0; i < N.count; i++) {
      expect(Math.hypot(N.getX(i), N.getY(i), N.getZ(i))).toBeCloseTo(1, 5);
      if (Math.abs(P.getZ(i)) < 1e-9 && Math.abs(P.getX(i)) < 50 && Math.abs(P.getY(i)) < 15) expect(N.getZ(i)).toBeCloseTo(1, 9);
    }
    // every triangle faces out: its winding agrees with its vertices' normals
    const I = g.getIndex()!;
    const v = (k: number) => new THREE.Vector3(P.getX(k), P.getY(k), P.getZ(k));
    for (let t = 0; t < I.count; t += 3) {
      const [a, b2, c] = [I.getX(t), I.getX(t + 1), I.getX(t + 2)];
      const n = new THREE.Vector3().crossVectors(v(b2).sub(v(a)), v(c).sub(v(a)));
      if (n.lengthSq() < 1e-12) continue;
      const avg = new THREE.Vector3(N.getX(a) + N.getX(b2) + N.getX(c), N.getY(a) + N.getY(b2) + N.getY(c), N.getZ(a) + N.getZ(b2) + N.getZ(c));
      expect(n.dot(avg)).toBeGreaterThan(0);
    }
  });
});

describe('repo: light along the strand', () => {
  test('the envelope is the brightest glow at a point, 0 away from them, never past 1', () => {
    const gs = [{ u: 0.3, w: 0.02, k: 0.5 }, { u: 0.32, w: 0.02, k: 1.4 }];
    expect(envelope(0.32, gs)).toBe(1);
    expect(envelope(0.3, [gs[0]!])).toBeCloseTo(0.5, 9);
    expect(envelope(0.8, gs)).toBe(0);
    expect(envelope(0.5, [])).toBe(0);
  });

  test('the patch reads the strip in the real thread shader, after the strand\'s glow and before the lights', () => {
    const th = new Thread([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.5, 0.02, 0), new THREE.Vector3(1, 0, 0)], { ...DIFF_THREAD, radius: 0.004 });
    const light = new StrandLight(th, DIFF_THREAD.rest, DIFF_THREAD.glow);
    const m = th.mesh.material as THREE.MeshPhysicalMaterial;
    const sh = { vertexShader: THREE.ShaderLib.physical.vertexShader, fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} as Record<string, THREE.IUniform> };
    m.onBeforeCompile(sh as any, null as any);
    const f = sh.fragmentShader;
    const glowAt = f.lastIndexOf('totalEmissiveRadiance +='), patchAt = f.indexOf('tStrandLight, vec2'), lightsAt = f.indexOf('#include <lights_physical_fragment>');
    expect(glowAt).toBeGreaterThan(0);
    expect(patchAt).toBeGreaterThan(glowAt);
    expect(lightsAt).toBeGreaterThan(patchAt);
    expect(sh.uniforms.tStrandLight!.value).toBe(light.texture);
    expect((sh.uniforms.uStrandGain!.value as THREE.Vector2).y).toBeCloseTo(DIFF_THREAD.glow / DIFF_THREAD.rest - 1, 9);
    expect(m.customProgramCacheKey()).toContain('repo-strand-light');
    // the strip: blood in r, moss in g, LIGHT_N texels with u = 0 and 1 at the first and last
    light.set([{ u: 1, w: 0.01, k: 1 }], [{ u: 0, w: 0.01, k: 0.5 }]);
    const d = light.texture.image.data as Uint8Array;
    expect(d.length).toBe(4 * LIGHT_N);
    expect(d[1]).toBe(0);
    expect(d[0]).toBe(128);
    expect(d[4 * (LIGHT_N - 1) + 1]).toBe(255);
    light.dispose();
    th.dispose();
  });

  test('a shader without what the patch reads fails loudly', () => {
    expect(() => patchPlyFragment('#include <common>\nvoid main() {}')).toThrow(/repo-pulse/);
  });
});
