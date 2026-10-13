// Logo3D: the film's logo as a solid. An SVG from the film's assets (three's SVGLoader) is extruded with a round bevel,
// its neutral paths in satin fg, its coloured ones in the accent; it spins in on the house spring, sways on a slow
// turntable, a glint crosses it as it lands and its accent breathes on the beat; a tagline fades up under it (a flat
// layer). Without an SVG, the `name` is set as an extruded wordmark instead.
//
// Params (all optional, but one of logo and name):
//   logo 'assets/logo.svg'   the SVG (a path in the film's folder); paths whose fill has colour (chroma, (max − min) / max
//                      of its linear RGB, above 0.3: the bloom's gate) take the accent, the rest (whites, greys, near-whites
//                      like a warm theme's fg) satin fg
//   name               the wordmark when there is no SVG (or no logo param and the file is missing)
//   colors 'accent'    'accent': every coloured path takes the accent; 'svg': each coloured path keeps its own fill (a
//                      multi-colour mark), as a solid satin with a soft inner light (accentStyle is then 'solid')
//   accentColor 'accent' | 'accent2'; accentStyle 'solid' (accent satin, a soft inner light) | 'seam' (fg with a glowing seam)
//   depth 0.18, bevel 0.014   the extrusion and its bevel (fractions of the logo's height)
//   logoSize 0.34      the logo's height (fraction of the frame's short side... of H in a landscape frame, of W in a tall one)
//   reveal 'spin'      'spin' | 'rise' | 'scale'; landAt (TimeRef, default 0.9 s): when it lands
//   turntable 0        degrees per second of steady turn after it lands (0: a slow sway of `sway` 9 degrees instead)
//   tagline            a line under it; taglineAt (TimeRef, default 0.35 s after it lands); taglineColor 'fgDim'; taglineSize 40
//   pulse 0.3          how much the accent swells on each beat
//   camera 'push', az 0, el 2, fov 28, fstop 2.8, and every Scene3D param
import * as THREE from 'three';
import { SVGLoader } from 'three/examples/jsm/loaders/SVGLoader.js';
import { Type3D, Mat } from '../../engine/type3d';
import { sweepAt, withSweep, type SweepBand, type SweepPass } from '../../engine/sweep';
import { onBeat, slam } from '../../engine/motion';
import { filmUrl } from '../../engine/config';
import { W, H } from '../../engine/gl';
import { lin, rgba } from '../../engine/palette';
import { F, font } from '../../engine/type';
import { clamp, ease, prog } from '../../engine/util';
import type { TimeRef } from '../text/fx';
import { family } from '../text/layout';
import { isTall } from '../scene2d';
import { Scene3D, type Frame } from './scene3d';

/**
 * An extruded SVG path's geometry, unit height, centred, its face at z = 0 and its depth running back to −depth (as
 * Type3D's), with the `type3dDepth` attribute Mat.accent's seam reads. `box` is the SVG's box (y down) the shapes are
 * normalised against.
 */
export function extrudeShapes(shapes: THREE.Shape[], box: { x0: number; y0: number; x1: number; y1: number }, depth: number, bevel: number): THREE.BufferGeometry {
  const hgt = Math.max(1e-6, box.y1 - box.y0);
  const b = Math.max(0, Math.min(bevel, 0.45 * depth)) * hgt;
  const geo = new THREE.ExtrudeGeometry(shapes, {
    depth: Math.max(1e-6, depth * hgt - 2 * b), curveSegments: 18, steps: 1,
    bevelEnabled: b > 0, bevelThickness: b, bevelSize: b, bevelOffset: -b, bevelSegments: 4,
  });
  geo.deleteAttribute('uv');
  // three extrudes over [−b, depth − b] toward +z, y down from the SVG: moved to [0, depth], then turned over x (y up,
  // the cap that was at −b now the face, at z = 0 toward +z, the depth running back)
  geo.translate(-(box.x0 + box.x1) / 2, -(box.y0 + box.y1) / 2, b);
  geo.scale(1 / hgt, -1 / hgt, -1 / hgt);
  const z = geo.getAttribute('position'), behind = new Float32Array(z.count);
  for (let i = 0; i < z.count; i++) behind[i] = Math.min(depth, Math.max(0, -z.getZ(i)));
  geo.setAttribute('type3dDepth', new THREE.BufferAttribute(behind, 1));
  geo.computeBoundingBox();
  geo.computeBoundingSphere();
  return geo;
}

export class Logo3D extends Scene3D {
  protected override defaults: Record<string, unknown> = { camera: 'push', az: 0, el: 2, fov: 28, fstop: 2.8, cameraAmount: 0.8 };
  private pivot = new THREE.Group();
  private band!: SweepBand;
  private passes: SweepPass[] = [];
  private accents: THREE.MeshPhysicalMaterial[] = [];
  private seams = new Set<THREE.Material>();
  private landAt = 0;
  private aspect = 1;
  private word: Type3D | null = null;
  private tagline = '';

  protected async build() {
    const satin = this.own(Mat.satinBone());
    this.band = withSweep(satin);
    const key = this.p<'accent' | 'accent2'>('accentColor', 'accent');
    const accent = (): THREE.MeshPhysicalMaterial => {
      const seam = this.p<string>('accentStyle', 'solid') === 'seam';
      const m = this.own(seam ? Mat.accent(key, this.glowLevel) : solidAccent(key));
      if (seam) this.seams.add(m);
      withSweep(m).value = this.band.value;
      this.accents.push(m);
      return m;
    };
    const svg = await this.loadSvg();
    let w = 1;
    if (svg) {
      const data = new SVGLoader().parse(svg);
      const all = data.paths.flatMap((pth) => SVGLoader.createShapes(pth).map((s) => ({ s, pth })));
      if (!all.length) throw new Error(`shot ${this.ctx.id}: the logo SVG has no filled paths`);
      const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      for (const { s } of all) for (const pt of s.getPoints(12)) {
        box.x0 = Math.min(box.x0, pt.x); box.x1 = Math.max(box.x1, pt.x);
        box.y0 = Math.min(box.y0, pt.y); box.y1 = Math.max(box.y1, pt.y);
      }
      const depth = this.p('depth', 0.18), bevel = this.p('bevel', 0.014);
      const accentMat = accent();
      const own = this.p<string>('colors', 'accent') === 'svg', fills = new Map<string, THREE.MeshPhysicalMaterial>();
      const fillMat = (c: THREE.Color): THREE.MeshPhysicalMaterial => {
        const k = c.getHexString();
        let m = fills.get(k);
        if (!m) {
          m = this.own(solidColour([c.r, c.g, c.b], false));
          withSweep(m).value = this.band.value;
          this.accents.push(m);
          fills.set(k, m);
        }
        return m;
      };
      data.paths.forEach((pth, i) => {
        const shapes = SVGLoader.createShapes(pth);
        if (!shapes.length) return;
        const geo = this.own(extrudeShapes(shapes, box, depth, bevel));
        const mesh = new THREE.Mesh(geo, isColoured(pth.color) ? (own ? fillMat(pth.color) : accentMat) : satin);
        // a multi-colour mark's overlapping paths: each a hair in front of the one painted before it (SVG order)
        if (own) mesh.position.z = i * 0.002;
        this.pivot.add(mesh);
      });
      this.aspect = (box.x1 - box.x0) / Math.max(1e-6, box.y1 - box.y0);
      w = this.aspect;
    } else {
      const name = this.p<string | undefined>('name', undefined);
      if (!name) throw new Error(`shot ${this.ctx.id}: Logo3D needs an SVG (\`logo\`, default assets/logo.svg) or a \`name\``);
      const fam = family({ role: 'display', width: 87.5, weight: 800 });
      const accentMat = accent();
      // the wordmark: a unit cap height; its last letter takes the accent's seam
      const word = (this.word = new Type3D(name, { family: fam, size: 1.4, depth: this.p('depth', 0.16), bevel: this.p('bevel', 0.012) }, (g) => (g.i === name.length - 1 && this.p<string>('accentStyle', 'solid') === 'seam' ? accentMat : satin)));
      word.group.position.set(-word.width / 2, -0.5, 0);
      this.pivot.add(word.group);
      w = word.width;
    }
    this.stage.scene.add(this.pivot);
    this.landAt = this.at(this.p<TimeRef>('landAt', 0.9));
    this.passes = [{ t0: this.landAt + 0.05, t1: this.landAt + 0.85, x0: -w / 2 - 0.6, x1: w / 2 + 0.6, y: 0 }];
    this.tagline = this.p('tagline', '');
    // framing: the logo `logoSize` of the frame's height (of its width in a tall frame), lifted when a tagline is under it
    const frac = this.p('logoSize', 0.34) * (isTall() ? W / H : 1);
    const fov = this.p('fov', 28), tan = Math.tan((fov * Math.PI) / 360);
    // its height `frac` of the frame's, but never wider than 0.8 of its width
    const dist = Math.max(1 / (2 * tan * frac), w / (0.8 * (W / H)) / (2 * tan));
    const upp = (2 * tan * dist) / H; // world units per px on its plane
    this.lift = this.tagline ? 0.07 * H : 0; // px the logo sits above the centre
    this.frame({ centre: [0, -this.lift * upp, 0], w, h: 1, dist });
  }

  /** Px the logo sits above the frame's centre (room for the tagline). */
  private lift = 0;

  private async loadSvg(): Promise<string | null> {
    const explicit = this.ctx.params.logo as string | undefined;
    const url = filmUrl(explicit ?? 'assets/logo.svg');
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${r.status}`);
      return await r.text();
    } catch (e) {
      if (explicit || !this.ctx.params.name) throw new Error(`shot ${this.ctx.id}: can't load the logo ${url} (${(e as Error).message})`);
      return null;
    }
  }

  protected update(f: Frame): THREE.Vector3 {
    const t = f.t, reveal = this.p<'spin' | 'rise' | 'scale'>('reveal', 'spin');
    const k = slam(t, this.landAt, { freq: 2.2, damping: 0.72 });
    const P = this.pivot;
    P.visible = k > 0;
    const after = Math.max(0, t - this.landAt);
    const turn = this.p('turntable', 0);
    const sway = turn ? (turn * Math.PI / 180) * after : (this.p('sway', 9) * Math.PI / 180) * Math.sin(0.55 * after) * prog(after, 0, 1.2, ease.inOutCubic);
    P.rotation.set(0, sway, 0);
    P.position.set(0, 0, 0);
    P.scale.setScalar(1);
    if (reveal === 'spin') P.rotation.y += -2.4 * (1 - k), P.scale.setScalar(0.6 + 0.4 * clamp(k * 1.4));
    else if (reveal === 'rise') P.position.y = -0.8 * (1 - k), P.rotation.x = 0.6 * (1 - k);
    else P.scale.setScalar(Math.max(0, k));
    const beat = onBeat(f, 0.3), pulse = this.p('pulse', 0.3);
    const flare = 1 + 0.6 * Math.exp(-Math.max(0, t - this.landAt) / 0.25) * (t >= this.landAt ? 1 : 0);
    for (const m of this.accents) m.emissiveIntensity = (this.seams.has(m) ? this.glowLevel : 0.32 * this.glowLevel) * flare * (1 + pulse * beat);
    sweepAt(this.band, t, this.passes, { width: 0.22, strength: 2.4 });
    if (this.tagline) this.drawTagline(t);
    return new THREE.Vector3(0, 0, 0.05);
  }

  private drawTagline(t: number) {
    const at = this.ctx.params.taglineAt !== undefined ? this.at(this.ctx.params.taglineAt as TimeRef) : this.landAt + 0.35;
    const k = prog(t, at, at + 0.6, ease.outCubic);
    if (k <= 0) return;
    const c = this.flatLayer().ctx, u = this.u;
    const size = this.p('taglineSize', 40) * u;
    c.font = font(F.ui(500), size);
    c.textAlign = 'center';
    c.textBaseline = 'alphabetic';
    c.letterSpacing = `${0.02 * size}px`;
    c.fillStyle = rgba(this.p('taglineColor', 'fgDim'), k);
    // under the logo: its lower edge (world y −0.5) is half its height under its centre, which sits `lift` px up
    const tan = Math.tan((this.base.fov * Math.PI) / 360), ppu = H / (2 * tan * this.base.dist);
    const bottom = H / 2 - this.lift + 0.5 * ppu;
    c.fillText(this.tagline, W / 2, bottom + 1.6 * size + (1 - k) * 0.4 * size);
  }

  override dispose() {
    this.word?.dispose();
    this.word = null;
    super.dispose();
  }
}

/**
 * Whether an SVG fill is a colour (it takes the accent) rather than a neutral (satin fg): its chroma, (max − min) / max of
 * the linear colour, is above 0.3, as look.ts bloomChroma measures it. Not HSL saturation, which calls a near-white like
 * #f4ece1 47% saturated.
 */
export function isColoured(c: { r: number; g: number; b: number }): boolean {
  const hi = Math.max(c.r, c.g, c.b), lo = Math.min(c.r, c.g, c.b);
  return hi > 0.02 && (hi - lo) / hi > 0.3;
}

/** The accent as a solid satin with a soft inner light (its emissive is set per frame). */
function solidAccent(key: 'accent' | 'accent2'): THREE.MeshPhysicalMaterial {
  return solidColour(lin(key));
}

/**
 * A linear colour as a solid satin with a soft inner light: its emissive the colour at a glow() level of 1, hue kept
 * (`normalise`), or the colour itself, so a dark ink (a deep indigo) glows as little as it is bright.
 */
function solidColour(c: readonly number[], normalise = true): THREE.MeshPhysicalMaterial {
  const hi = normalise ? Math.max(c[0]!, c[1]!, c[2]!, 1e-5) : 1;
  const m = new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setRGB(c[0], c[1], c[2]), roughness: 0.32, metalness: 0, clearcoat: 0.7, clearcoatRoughness: 0.08, sheen: 0.2, sheenRoughness: 0.5 });
  m.emissive.setRGB(c[0]! / hi, c[1]! / hi, c[2]! / hi);
  return m;
}

export default Logo3D;
