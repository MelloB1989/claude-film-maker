// A commit bead (`her`, `repo`, `braid`): a glass sphere with a bore and chamfered lips, its hash etched round its face.
//
// Geometry: a lathe round the bore (built on y, turned onto x), one closed profile: the sphere from lip to lip, a
// 45° chamfer in to the bore at each end, and the bore's wall between them. three smooths the profile's normals across
// its corners, so the lips read as rounded bevels catching the light rather than hard black discs.
//
// Local frame: the bore runs along x (the thread passes through it), the engraving faces +z, its letters stand up
// along +y. The engraving is laid on the great circle through the bore and the face: a point of the sphere at angle
// α = atan2(x, z) round that circle and latitude β = asin(y / r) off it takes the texture coordinate
// (0.5 + (α − α0) / 2A, 0.5 + (β − β0) / 2B), so the letters keep their proportions where the band is centred (α0, β0:
// where the camera looks) and wrap round the sphere toward the bore, foreshortening as the surface turns away. Outside
// the band the coordinates leave [0, 1] and clamp to the texture's empty border: plain glass. (The seam where α wraps
// is at the back, −z; the bore and the chamfers fall outside the band.)
//
// Material: real glass through three's physical transmission (IOR 1.5, satin roughness 0.15, a faint warm attenuation
// toward bone), so the thread shows through it, refracted: its glowing cores bend inside the glass. The letters are a
// frosted etch: rough, opaque (no transmission) and white, cut a little into the surface by a bump map whose soft edges
// catch the light. A light clear coat keeps the reflections and the rim crisp over the satin.
import * as THREE from 'three';
import { F, font } from './type';
import { LIN } from './palette';

export interface BeadOpts {
  /** Sphere radius (world units). */
  radius: number;
  /** Bore radius: the hole along x the thread passes through. */
  bore: number;
  /** The chamfer at each end of the bore: how far the lip opens beyond the bore radius (world units). */
  chamfer: number;
  /** The engraving (JetBrains Mono). */
  text: string;
  /** Half the engraved band's length and height round the sphere (radians). */
  span?: [number, number];
  /**
   * Where the band is centred (radians): along the great circle from the face (+z) toward the bore's +x end, and up
   * off it. A camera that sees the bead from off its face centres the letters where it looks (the bore stays on x).
   */
  centre?: [number, number];
}

/** Texture px of the engraving band, along and across. */
const TEX_W = 2048;

/** The lathe profile (radius from the bore's axis, height along it), bottom lip to bottom lip, counter-clockwise. */
export function beadProfile(r: number, bore: number, chamfer: number, arc = 120): THREE.Vector2[] {
  const lip = Math.min(bore + chamfer, 0.9 * r), hLip = Math.sqrt(r * r - lip * lip), hBore = hLip - (lip - bore);
  const phi = Math.atan2(hLip, lip), pts: THREE.Vector2[] = [];
  for (let i = 0; i <= arc; i++) {
    const a = -phi + (2 * phi * i) / arc;
    pts.push(new THREE.Vector2(r * Math.cos(a), r * Math.sin(a)));
  }
  pts.push(new THREE.Vector2(bore, hBore), new THREE.Vector2(bore, -hBore), new THREE.Vector2(lip, -hLip));
  return pts;
}

/** The bead's shape: everything in BeadOpts but the text. */
export type BeadShape = Omit<BeadOpts, 'text'>;

/**
 * The bead's geometry: the lathe turned onto x, with the engraving band's texture coordinates (see the header).
 *
 * A triangle's UVs are interpolated across it, so two kinds of triangle would smear the band across themselves, and
 * take their own copies of the corners that need other UVs (the lathe is otherwise untouched, triangle for triangle):
 * - the back seam, where α wraps from π to −π: a triangle across it takes its −π corners round to +π, so it lies whole
 *   past the band's far end;
 * - the chamfers: an inner corner (off the sphere, plain glass at −1) of a triangle that also has a lip corner takes the
 *   UV of the lip at its angle round the bore, so the chamfer carries the lip's texel (plain glass, the band's margin)
 *   down to the bore instead of sweeping from the lip across the band to −1.
 */
export function beadGeometry(o: BeadShape): THREE.BufferGeometry {
  const [A, B] = o.span ?? [0.95, 0.3];
  const [a0, b0] = o.centre ?? [0, 0];
  const r = o.radius;
  const lip = Math.min(o.bore + o.chamfer, 0.9 * r), hLip = Math.sqrt(r * r - lip * lip); // as beadProfile
  const geo = new THREE.LatheGeometry(beadProfile(r, o.bore, o.chamfer), 160);
  geo.rotateZ(-Math.PI / 2); // the lathe's axis (y) onto the bore (x)
  const pos = geo.getAttribute('position'), nor = geo.getAttribute('normal'), uv = geo.getAttribute('uv');
  /** The band UV of a point on the sphere, `turn` added to its α. */
  const band = (x: number, y: number, z: number, turn = 0): [number, number] => {
    const a = Math.atan2(x, z) + turn, b = Math.asin(Math.max(-1, Math.min(1, y / r)));
    return [0.5 + (a - a0) / (2 * A), 0.5 + (b - b0) / (2 * B)];
  };
  const n = pos.count, on: boolean[] = [], alpha: number[] = [];
  for (let i = 0; i < n; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    on.push(Math.hypot(x, y, z) > 0.97 * r); // the bore and the chamfers stay plain glass
    alpha.push(Math.atan2(x, z));
    const [u, v] = band(x, y, z);
    uv.setXY(i, on[i] ? u : -1, on[i] ? v : -1);
  }
  // the corners that need other UVs, copied: `${why}:${vertex}` -> the copy's index
  const copies = new Map<string, number>(), extra: { src: number; uv: [number, number] }[] = [];
  const copy = (why: string, i: number, at: () => [number, number]) => {
    const key = `${why}:${i}`;
    let j = copies.get(key);
    if (j === undefined) copies.set(key, (j = n + extra.push({ src: i, uv: at() }) - 1));
    return j;
  };
  const index = Array.from(geo.getIndex()!.array);
  for (let t = 0; t < index.length; t += 3) {
    const tri = [index[t]!, index[t + 1]!, index[t + 2]!];
    const lips = tri.filter((i) => on[i]).length;
    if (lips === 3) {
      const as = tri.map((i) => alpha[i]!);
      if (Math.max(...as) - Math.min(...as) <= Math.PI) continue;
      tri.forEach((i, k) => {
        if (alpha[i]! < 0) index[t + k] = copy('seam', i, () => band(pos.getX(i), pos.getY(i), pos.getZ(i), 2 * Math.PI));
      });
    } else if (lips > 0) {
      tri.forEach((i, k) => {
        if (on[i]) return;
        const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i), k2 = lip / Math.hypot(y, z);
        index[t + k] = copy('lip', i, () => band(Math.sign(x) * hLip, y * k2, z * k2));
      });
    }
  }
  if (!extra.length) return geo;
  // the lathe's vertices as they are, then the copies
  const total = n + extra.length;
  const P = new Float32Array(total * 3), N = new Float32Array(total * 3), U = new Float32Array(total * 2);
  P.set(pos.array as Float32Array);
  N.set(nor.array as Float32Array);
  U.set(uv.array as Float32Array);
  extra.forEach((e, k) => {
    const j = n + k;
    P.set([pos.getX(e.src), pos.getY(e.src), pos.getZ(e.src)], 3 * j);
    N.set([nor.getX(e.src), nor.getY(e.src), nor.getZ(e.src)], 3 * j);
    U.set(e.uv, 2 * j);
  });
  geo.setAttribute('position', new THREE.BufferAttribute(P, 3));
  geo.setAttribute('normal', new THREE.BufferAttribute(N, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(U, 2));
  geo.setIndex(index);
  return geo;
}

export class Bead {
  mesh: THREE.Mesh;
  material: THREE.MeshPhysicalMaterial;
  private maps: THREE.CanvasTexture[] = [];

  constructor(o: BeadOpts) {
    const [A, B] = o.span ?? [0.95, 0.3];
    const geo = beadGeometry(o);

    const texH = Math.round((TEX_W * B) / A);
    // the letters: an em that fills the band's length at 64% (7 mono cells of 0.6 em), within its height
    const n = Array.from(o.text).length;
    const em = Math.min((0.64 * TEX_W) / (0.6 * n), 0.9 * texH / 0.73);
    const paint = (bg: string, fg: string, blur = 0) => {
      const cv = document.createElement('canvas');
      cv.width = TEX_W;
      cv.height = texH;
      const c = cv.getContext('2d')!;
      c.fillStyle = bg;
      c.fillRect(0, 0, TEX_W, texH);
      c.filter = blur > 0 ? `blur(${blur}px)` : 'none';
      c.font = font(F.mono(500), em);
      c.textAlign = 'center';
      c.textBaseline = 'alphabetic';
      c.fillStyle = fg;
      c.fillText(o.text, TEX_W / 2, texH / 2 + 0.365 * em); // the cap height centred in the band
      const t = new THREE.CanvasTexture(cv);
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
      t.anisotropy = 16;
      t.colorSpace = THREE.NoColorSpace; // data, not colour
      this.maps.push(t);
      return t;
    };
    // roughnessMap reads g, transmissionMap reads r: clear satin glass (r 1, g 0.15) and the frosted etch (r 0, g 0.9);
    // bumpMap reads r: the surface at 1 and the letters cut to 0, with soft edges for the bump's slope
    const surface = paint('rgb(255, 38, 0)', 'rgb(0, 230, 0)');
    const height = paint('#fff', '#000', em * 0.03);

    const warm = new THREE.Color().setRGB(...LIN.bone);
    this.material = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0,
      roughness: 1,
      roughnessMap: surface,
      transmission: 1,
      transmissionMap: surface,
      // three refracts once, on entry, along `thickness`; a sphere bends the ray back on its way out, so the radius (not
      // the diameter) gives a ball lens's look: at the full diameter the sample lands far off and the bead mirrors the
      // bright thread like chrome
      thickness: o.radius,
      ior: 1.5,
      attenuationColor: warm,
      attenuationDistance: 0.3,
      specularIntensity: 1,
      clearcoat: 0.6,
      clearcoatRoughness: 0.06,
      bumpMap: height,
      bumpScale: 0.7,
    });
    this.mesh = new THREE.Mesh(geo, this.material);
  }

  /**
   * Put the bead at `pos` with its bore along `axis` and its face turned toward `face` (made square to the bore), then
   * spun `spin` radians round the bore.
   */
  place(pos: THREE.Vector3, axis: THREE.Vector3, face: THREE.Vector3, spin = 0) {
    const x = axis.clone().normalize();
    const z = face.clone().addScaledVector(x, -face.dot(x)).normalize();
    const y = new THREE.Vector3().crossVectors(z, x);
    const m = new THREE.Matrix4().makeBasis(x, y, z);
    this.mesh.quaternion.setFromRotationMatrix(m).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), spin));
    this.mesh.position.copy(pos);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.material.dispose();
    for (const t of this.maps) t.dispose();
  }
}
