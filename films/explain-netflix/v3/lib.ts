// Netflix v3 props, shared by the shots: the play mark, the Open Connect box (a server with LED strips), the cloud,
// the house with a TV, chunk blocks, curves. Built from @kit/motion pieces in the film's palette (STYLE_V3.md §2).
import { THREE, RoundedBoxGeometry } from '@engine/three';
import { F } from '@engine/type';
import { Mat } from '@engine/type3d';
import { Beam, KineticText, Label, glowMat, hdr, surfaceMat, MotionScene, type CamPose } from '@kit/motion';

export { THREE, F, Mat };
export const FPS = 24;

/** A closed circle in the XY plane (centre c, radius r) starting at 12 o'clock, clockwise. */
export class Circle extends THREE.Curve<THREE.Vector3> {
  constructor(private c: THREE.Vector3, private r: number, private turns = 1, private start = Math.PI / 2) { super(); }
  override getPoint(u: number, out = new THREE.Vector3()) {
    const a = this.start - u * this.turns * Math.PI * 2;
    return out.set(this.c.x + Math.cos(a) * this.r, this.c.y + Math.sin(a) * this.r, this.c.z);
  }
}

/** An arc from a to b lifted by `lift` (world units) at its middle along `up` (default +y). */
export function arc(a: THREE.Vector3, b: THREE.Vector3, lift: number, up = new THREE.Vector3(0, 1, 0)): THREE.QuadraticBezierCurve3 {
  const m = a.clone().add(b).multiplyScalar(0.5).addScaledVector(up, lift);
  return new THREE.QuadraticBezierCurve3(a.clone(), m, b.clone());
}

export const v = (x: number, y: number, z = 0) => new THREE.Vector3(x, y, z);

/** A rounded play triangle, extruded, pointing +x, centred on its centroid; `r` is the centre-to-tip distance. */
export function playGeometry(r: number, depth: number): THREE.BufferGeometry {
  const s = new THREE.Shape();
  const pts = [0, 1, 2].map((i) => { const a = (i * 2 * Math.PI) / 3; return new THREE.Vector2(Math.cos(a) * r, Math.sin(a) * r); });
  const rad = r * 0.18;
  for (let i = 0; i < 3; i++) {
    const p = pts[i]!, prev = pts[(i + 2) % 3]!, next = pts[(i + 1) % 3]!;
    const a = p.clone().add(prev.clone().sub(p).setLength(rad * 1.6)), b = p.clone().add(next.clone().sub(p).setLength(rad * 1.6));
    if (i === 0) s.moveTo(a.x, a.y); else s.lineTo(a.x, a.y);
    s.quadraticCurveTo(p.x, p.y, b.x, b.y);
  }
  s.closePath();
  const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: true, bevelThickness: depth * 0.25, bevelSize: r * 0.04, bevelSegments: 4, curveSegments: 10 });
  g.translate(0, 0, -depth / 2);
  return g;
}

/** The Open Connect box: a 1U-style server slab, dark, with a row of drive bays and an accent LED strip. */
export class ServerBox {
  readonly group = new THREE.Group();
  readonly leds: THREE.Mesh[] = [];
  readonly ledMat: THREE.MeshBasicMaterial;
  readonly ledOff: THREE.MeshBasicMaterial;
  private mats: THREE.Material[] = [];
  private geos: THREE.BufferGeometry[] = [];
  constructor(w = 1.6, h = 0.34, d = 1.0, units = 3) {
    const body = surfaceMat('surface', { rough: 0.38, coat: 0.8 });
    const face = surfaceMat('#2a211b', { rough: 0.5, coat: 0.4 });
    this.ledMat = glowMat('accent', 5);
    this.ledOff = glowMat('accentDim', 0.6);
    this.mats.push(body, face, this.ledMat, this.ledOff);
    for (let u = 0; u < units; u++) {
      const y = (u - (units - 1) / 2) * (h + 0.03);
      const g = new RoundedBoxGeometry(w, h, d, 3, 0.04);
      this.geos.push(g);
      const m = new THREE.Mesh(g, body);
      m.position.y = y;
      this.group.add(m);
      // drive bays
      const bay = new RoundedBoxGeometry(w * 0.105, h * 0.62, 0.02, 2, 0.008);
      this.geos.push(bay);
      for (let i = 0; i < 7; i++) {
        const b = new THREE.Mesh(bay, face);
        b.position.set(-w * 0.42 + i * w * 0.115, y, d / 2 + 0.006);
        this.group.add(b);
      }
      const led = new THREE.BoxGeometry(w * 0.12, h * 0.12, 0.01);
      this.geos.push(led);
      const l = new THREE.Mesh(led, this.ledMat);
      l.position.set(w * 0.4, y, d / 2 + 0.012);
      this.leds.push(l);
      this.group.add(l);
    }
  }
  /** LEDs blink (a busy box) from time t, seeded per LED. */
  blink(t: number, on = true) {
    this.leds.forEach((l, i) => {
      const lit = on && Math.sin(t * (9 + i * 3.7) + i * 2.1) > -0.3;
      l.material = lit ? this.ledMat : this.ledOff;
    });
  }
  dispose() { this.geos.forEach((g) => g.dispose()); this.mats.forEach((m) => m.dispose()); }
}

/** A soft 3D cloud from overlapping spheres (matte, warm grey, a faint amber rim from the rig). */
export class Cloud {
  readonly group = new THREE.Group();
  private geo = new THREE.SphereGeometry(1, 32, 20);
  readonly mat: THREE.MeshPhysicalMaterial;
  constructor(scale = 1, role: '#3a2e26' | string = '#3a2e26') {
    this.mat = surfaceMat(role as `#${string}`, { rough: 0.7, coat: 0.1 });
    const blobs: [number, number, number, number][] = [[-0.55, -0.05, 0, 0.42], [0, 0.18, 0, 0.55], [0.55, 0, 0, 0.45], [0.25, -0.15, 0.2, 0.38], [-0.25, -0.18, 0.2, 0.36]];
    for (const [x, y, z, r] of blobs) {
      const m = new THREE.Mesh(this.geo, this.mat);
      m.position.set(x * scale, y * scale, z * scale);
      m.scale.setScalar(r * scale);
      this.group.add(m);
    }
  }
  dispose() { this.geo.dispose(); this.mat.dispose(); }
}

/** A simple house with a lit window (the viewer): box body, a prism roof, a glowing TV-blue? no: warm window. */
export class House {
  readonly group = new THREE.Group();
  readonly win: THREE.MeshBasicMaterial;
  private geos: THREE.BufferGeometry[] = [];
  private mats: THREE.Material[] = [];
  constructor(s = 1) {
    const wall = surfaceMat('#2c231d', { rough: 0.6, coat: 0.2 });
    const roof = surfaceMat('#3b2d24', { rough: 0.5, coat: 0.3 });
    this.win = glowMat('accent2', 2.2);
    this.mats.push(wall, roof, this.win);
    const body = new RoundedBoxGeometry(0.9 * s, 0.62 * s, 0.7 * s, 2, 0.03 * s);
    const rs = new THREE.Shape(); rs.moveTo(-0.52 * s, 0); rs.lineTo(0, 0.4 * s); rs.lineTo(0.52 * s, 0); rs.closePath();
    const rg = new THREE.ExtrudeGeometry(rs, { depth: 0.78 * s, bevelEnabled: false });
    rg.translate(0, 0.31 * s, -0.39 * s);
    const wg = new THREE.PlaneGeometry(0.42 * s, 0.26 * s);
    this.geos.push(body, rg, wg);
    this.group.add(new THREE.Mesh(body, wall), new THREE.Mesh(rg, roof));
    const w = new THREE.Mesh(wg, this.win); w.position.set(0, -0.02 * s, 0.351 * s); this.group.add(w);
  }
  dispose() { this.geos.forEach((g) => g.dispose()); this.mats.forEach((m) => m.dispose()); }
}

/** Big flat label helper: px cap height → world em at the framing distance. */
export function emFor(px: number, dist: number, fov: number) {
  return (px / 0.72) * ((2 * dist * Math.tan((fov * Math.PI) / 360)) / 1080);
}

export { Beam, KineticText, Label, glowMat, hdr, surfaceMat, MotionScene, type CamPose };
