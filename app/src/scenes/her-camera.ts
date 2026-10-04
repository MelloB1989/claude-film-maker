// Framing for `her`: camera keys composed by what they show rather than by coordinates.
//
// fitCamera places a camera looking from a direction (azimuth round the world's y axis from +z, elevation above the
// horizon) so a set of world points fills the frame to a margin, centred where `bias` says. It iterates: project the
// points, measure their extent in the view's tangent plane, scale the distance and shift the target, until the
// framing holds (perspective makes one pass inexact: nearer points grow faster than farther ones as it closes in).
import * as THREE from 'three';
import type { CamKey, V3 } from '../engine/stage';

export interface Fit {
  /** Degrees: + puts the camera to the right of the subject (x+), looking back to the left. */
  az: number;
  /** Degrees: + above the subject, looking down. */
  el: number;
  /** Vertical field of view (degrees). */
  fov: number;
  /** Fraction of the half-frame left empty on each side, horizontally and vertically. */
  margin?: [number, number];
  /** Where the points' box is centred, in fractions of the half-frame (+x right, +y up). */
  bias?: [number, number];
  aspect?: number;
}

export function fitCamera(pts: readonly THREE.Vector3[], o: Fit): { pos: V3; target: V3; fov: number } {
  const aspect = o.aspect ?? 16 / 9;
  const [mx, my] = o.margin ?? [0.12, 0.12];
  const [bx, by] = o.bias ?? [0, 0];
  const az = THREE.MathUtils.degToRad(o.az), el = THREE.MathUtils.degToRad(o.el);
  const back = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
  const f = back.clone().negate();
  const r = new THREE.Vector3().crossVectors(f, new THREE.Vector3(0, 1, 0)).normalize();
  const u = new THREE.Vector3().crossVectors(r, f);
  const ty = Math.tan(THREE.MathUtils.degToRad(o.fov) / 2), tx = ty * aspect;
  const centre = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(Math.max(1, pts.length));
  let D = 1;
  for (let it = 0; it < 24; it++) {
    const cam = centre.clone().addScaledVector(back, D);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) {
      const v = p.clone().sub(cam), z = v.dot(f);
      const x = v.dot(r) / z, y = v.dot(u) / z;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    // the box fits the frame less its margins, off centre by the bias and still inside them
    const s = Math.max((x1 - x0) / (2 * tx * (1 - mx) * (1 - Math.abs(bx))), (y1 - y0) / (2 * ty * (1 - my) * (1 - Math.abs(by))));
    // move the centre so the box sits at the bias, at the distance of the subject
    const cx = (x0 + x1) / 2 - bx * tx * (1 - mx) * s, cy = (y0 + y1) / 2 - by * ty * (1 - my) * s;
    centre.addScaledVector(r, cx * D).addScaledVector(u, cy * D);
    D *= s;
  }
  const pos = centre.clone().addScaledVector(back, D);
  return { pos: pos.toArray() as V3, target: centre.toArray() as V3, fov: o.fov };
}

/** A camera key from a fit. */
export function fitKey(t: number, pts: readonly THREE.Vector3[], o: Fit, ease?: (x: number) => number): CamKey {
  const k = fitCamera(pts, o);
  return { t, pos: k.pos, target: k.target, fov: k.fov, ease };
}
