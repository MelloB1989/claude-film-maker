// The headline's type for `her`: diff lines set as one kerned line each, with their hero words extruded and the rest
// flat.
//
// A DiffLine builds its text twice from the same layout (Type3D, so the kerning is layout()'s): once extruded (hero
// type: satin bone, the accents with the diff glow) and once as flat type (a sliver of depth, no bevel, drawn unlit:
// crisp graphic Bricolage in the same plane), and shows each glyph from one of the two, so hero and flat words sit on
// one baseline with the line's own spacing. The gutter mark (`+` or `−`, JetBrains Mono) is flat, in its own column
// left of the text as on the site (Hero.tsx).
//
// Also here: withSweep (a specular sweep band in a hero material's own light) and Backdrop (the studio's dark wall,
// lifting softly behind the hero word).
import * as THREE from 'three';
import { Type3D, type Glyph3D } from '../engine/type3d';

/** Flat type: a sliver of depth (em), no bevel. */
export const FLAT = { depth: 0.002, bevel: 0 } as const;

export type RGB = readonly [number, number, number];

/** An unlit material in a linear colour (the stage renders linear HDR; a glow() colour past 1 blooms). */
export function unlit(rgb: RGB, opts: THREE.MeshBasicMaterialParameters = {}) {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]), ...opts });
}

export interface DiffLineOpts {
  /** The gutter mark and the line's text. */
  mark: string;
  text: string;
  family: string;
  markFamily: string;
  /** World units per em of the text. */
  size: number;
  /** Letter spacing of the text (em). */
  tracking?: number;
  /** The mark's size (em of the text) and its left edge (em of the text, from the text's origin; negative: left). */
  markSize: number;
  markX: number;
  /** Word indices set in extruded type. */
  heroes: readonly number[];
  /** Materials: an extruded word's, a flat word's, the mark's. */
  hero: (word: number) => THREE.Material;
  flat: (word: number) => THREE.Material;
  markMat: THREE.Material;
}

export class DiffLine {
  /** The text origin (left end, baseline) on the face plane. */
  group = new THREE.Group();
  solid: Type3D;
  flat: Type3D;
  mark: Type3D;
  readonly heroes: ReadonlySet<number>;
  /** Word count, and each word's glyphs from the copy that shows it. */
  readonly words: Glyph3D[][] = [];

  constructor(o: DiffLineOpts) {
    this.heroes = new Set(o.heroes);
    const tracking = o.tracking ?? 0;
    this.solid = new Type3D(o.text, { family: o.family, size: o.size, tracking }, (g) => o.hero(g.word));
    this.flat = new Type3D(o.text, { family: o.family, size: o.size, tracking, ...FLAT }, (g) => o.flat(g.word));
    this.mark = new Type3D(o.mark, { family: o.markFamily, size: o.size * o.markSize, ...FLAT }, () => o.markMat);
    this.mark.group.position.x = o.markX * o.size;
    for (const g of this.solid.glyphs) g.mesh.visible = this.heroes.has(g.word);
    for (const g of this.flat.glyphs) g.mesh.visible = !this.heroes.has(g.word);
    this.group.add(this.solid.group, this.flat.group, this.mark.group);
    const n = Math.max(0, ...this.solid.glyphs.map((g) => g.word)) + 1;
    for (let w = 0; w < n; w++) this.words.push((this.heroes.has(w) ? this.solid : this.flat).glyphs.filter((g) => g.word === w));
  }

  /** The middle of word `w` at its x-height's middle, in the line's space (for focus and lights). */
  wordCentre(w: number, target = new THREE.Vector3()) {
    const gs = this.words[w]!, a = gs[0]!, b = gs[gs.length - 1]!;
    return target.set((a.x + b.x + b.w) / 2, a.home.y, 0);
  }

  /** Left and right ends of word `w` (line space x). */
  wordSpan(w: number): [number, number] {
    const gs = this.words[w]!;
    return [gs[0]!.x, gs[gs.length - 1]!.x + gs[gs.length - 1]!.w];
  }

  dispose() {
    this.solid.dispose();
    this.flat.dispose();
    this.mark.dispose();
  }
}

/**
 * A specular sweep on hero type: a diagonal band of light that runs across a word as it lands, strongest on its bevels
 * and walls, where a passing light glints, and faint on its face. The film's satin bone is too diffuse for a physical
 * strip light to draw a band (its spill lights the whole word first), so the band is added to the material's outgoing
 * light: uniform (x) band centre in world x, (y) half-width, (z) slope (world x per unit of world y: the band leans),
 * (w) level. Chained onto whatever the material patches already (Mat.accent's diff glow), on a material this scene
 * owns. Neutral light: bone stays out of the bloom's chroma gate however bright the glint.
 */
export function withSweep(m: THREE.MeshPhysicalMaterial): THREE.IUniform<THREE.Vector4> {
  const u = { value: new THREE.Vector4(0, 0.04, 0.4, 0) };
  const prev = m.onBeforeCompile.bind(m);
  const base = m.customProgramCacheKey();
  m.onBeforeCompile = (sh, r) => {
    prev(sh, r);
    sh.uniforms.uHerSweep = u;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vHerW;\nvarying vec3 vHerN;')
      .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\n\tvHerN = objectNormal;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\n\tvHerW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform vec4 uHerSweep;\nvarying vec3 vHerW;\nvarying vec3 vHerN;')
      .replace('#include <opaque_fragment>', /* glsl */ `{
		float herS = (vHerW.x + uHerSweep.z * vHerW.y - uHerSweep.x) / uHerSweep.y;
		float herEdge = smoothstep(0.08, 0.55, 1.0 - abs(normalize(vHerN).z));
		outgoingLight += vec3(uHerSweep.w * exp(-herS * herS) * (0.16 + 1.3 * herEdge));
	}
	#include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => `${base}|her-sweep`;
  return u;
}

/**
 * The dark studio behind the headline: a wide plane far back whose ink lifts, very softly, toward `lift` in a pool
 * that follows the hero word, as a key's spill falls on a backdrop. Unlit, opaque (the depth of field reads it as the
 * far distance).
 */
export class Backdrop {
  mesh: THREE.Mesh;
  private u: { uInk: THREE.IUniform<THREE.Vector3>; uLift: THREE.IUniform<THREE.Vector3>; uCentre: THREE.IUniform<THREE.Vector2>; uRadius: THREE.IUniform<THREE.Vector2>; uLevel: THREE.IUniform<number> };

  constructor(ink: RGB, lift: RGB, size: [number, number]) {
    this.u = {
      uInk: { value: new THREE.Vector3(...ink) },
      uLift: { value: new THREE.Vector3(...lift) },
      uCentre: { value: new THREE.Vector2() },
      uRadius: { value: new THREE.Vector2(1, 0.5) },
      uLevel: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: /* glsl */ `varying vec3 vW; void main() { vW = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW, 1.0); }`,
      fragmentShader: /* glsl */ `uniform vec3 uInk, uLift; uniform vec2 uCentre, uRadius; uniform float uLevel; varying vec3 vW;
        void main() { vec2 d = (vW.xy - uCentre) / uRadius; gl_FragColor = vec4(mix(uInk, uLift, uLevel * exp(-dot(d, d))), 1.0); }`,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), mat);
  }

  /** The pool's centre (world x, y on the plane), its radii, and its strength (0: plain ink). */
  set(cx: number, cy: number, rx: number, ry: number, level: number) {
    this.u.uCentre.value.set(cx, cy);
    this.u.uRadius.value.set(rx, ry);
    this.u.uLevel.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
