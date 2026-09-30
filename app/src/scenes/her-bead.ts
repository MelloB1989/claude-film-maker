// The commit bead for `her`: a satin-glass sphere with a bore, its hash engraved round its face.
//
// Local frame: the bore runs along x (the thread passes through it), the engraving faces +z, its letters stand up
// along +y. The engraving is laid on the great circle through the bore and the face: a point of the sphere at angle
// α = atan2(x, z) round that circle and latitude β = asin(y / r) off it takes the texture coordinate
// (0.5 + (α − α0) / 2A, 0.5 + (β − β0) / 2B), so the letters keep their proportions where the band is centred (α0, β0:
// where the camera looks) and wrap round the sphere toward the bore holes, foreshortening as the surface turns away.
// Outside the band the coordinates leave [0, 1] and clamp to the texture's empty border: plain glass. (The seam where α
// wraps is at the back, −z.)
//
// Material: three's physical transmission, its body a satin glass (rough enough that the thread inside it, and its
// glowing strands, spread into a soft light filling the bead) under a clear coat that keeps the reflections and the
// rim crisp; its letters frosted (rough and opaque, so they read as the white of etched glass under the key), cut into
// the surface by a bump map whose soft edges catch the light.
import * as THREE from 'three';
import { F, font } from '../engine/type';

export interface BeadOpts {
  /** Sphere radius (world units). */
  radius: number;
  /** Bore radius: the holes at ±x where the thread goes in and out. */
  bore: number;
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

export class Bead {
  mesh: THREE.Mesh;
  material: THREE.MeshPhysicalMaterial;
  private maps: THREE.CanvasTexture[] = [];

  constructor(o: BeadOpts) {
    const [A, B] = o.span ?? [0.95, 0.3];
    const [a0, b0] = o.centre ?? [0, 0];
    const r = o.radius;
    const cap = Math.asin(Math.min(0.95, o.bore / r));
    // poles on y, opened by the bore's caps, then turned so the bore runs along x
    const geo = new THREE.SphereGeometry(r, 160, 120, 0, Math.PI * 2, cap, Math.PI - 2 * cap);
    geo.rotateZ(-Math.PI / 2);
    const pos = geo.getAttribute('position'), uv = geo.getAttribute('uv');
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
      const a = Math.atan2(x, z), b = Math.asin(Math.max(-1, Math.min(1, y / r)));
      uv.setXY(i, 0.5 + (a - a0) / (2 * A), 0.5 + (b - b0) / (2 * B));
    }
    uv.needsUpdate = true;

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
    // roughnessMap reads g, transmissionMap reads r: a satin body (r 1, g 0.72) and frosted letters (r 0, g 1);
    // bumpMap reads r: the surface at 1 and the letters cut to 0, with soft edges for the bump's slope
    const surface = paint('rgb(255, 184, 0)', 'rgb(0, 255, 0)');
    const height = paint('#fff', '#000', em * 0.03);

    this.material = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0,
      roughness: 0.7,
      roughnessMap: surface,
      transmission: 1,
      transmissionMap: surface,
      thickness: 1.6 * r,
      ior: 1.48,
      specularIntensity: 1,
      clearcoat: 1,
      clearcoatRoughness: 0.05,
      bumpMap: height,
      bumpScale: 1.6,
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
