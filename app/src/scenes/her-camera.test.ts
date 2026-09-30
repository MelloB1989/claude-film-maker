// fitCamera frames world points to a margin, off centre by a bias, from any azimuth and elevation: checked by projecting
// the points through a real three camera placed at the fit.
import { describe, expect, test } from 'bun:test';
import * as THREE from 'three';
import { fitCamera, type Fit } from './her-camera';

/** A headline-sized box: 1.5 m of type, 0.3 m tall, lying in the z = 0 plane. */
const BOX = [[-0.3, -0.15], [1.2, -0.15], [-0.3, 0.12], [1.2, 0.12]].map(([x, y]) => new THREE.Vector3(x, y, 0));

function ndc(pts: THREE.Vector3[], o: Fit) {
  const k = fitCamera(pts, o);
  const cam = new THREE.PerspectiveCamera(o.fov, 16 / 9, 0.01, 100);
  cam.position.set(...k.pos);
  cam.lookAt(...k.target);
  cam.updateMatrixWorld();
  cam.updateProjectionMatrix();
  const p = pts.map((v) => v.clone().project(cam));
  const xs = p.map((v) => v.x), ys = p.map((v) => v.y);
  return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys), k };
}

describe('fitCamera', () => {
  test('fills the frame to the margin on the axis that binds, and centres the box', () => {
    const r = ndc(BOX, { az: 0, el: 0, fov: 24, margin: [0.1, 0.24] });
    expect(r.x0).toBeCloseTo(-0.9, 3);
    expect(r.x1).toBeCloseTo(0.9, 3);
    expect(Math.abs(r.y0 + r.y1)).toBeLessThan(1e-3);
    expect(r.y1).toBeLessThan(0.76);
  });

  test('from the side and below, the box still fits the margin (perspective included)', () => {
    for (const [az, el] of [[16, 2], [30, -9], [-15, 5]]) {
      const r = ndc(BOX, { az, el, fov: 22, margin: [0.08, 0.3] });
      expect(Math.max(-r.x0, r.x1)).toBeLessThan(0.92 + 1e-3);
      expect(Math.max(-r.y0, r.y1)).toBeLessThan(0.7 + 1e-3);
      expect(Math.max(-r.x0, r.x1, -r.y0 / 0.7 * 0.92, r.y1 / 0.7 * 0.92)).toBeGreaterThan(0.9); // it binds somewhere
    }
  });

  test('a bias moves the box off centre and keeps it inside the margins', () => {
    const m = 0.1, b = 0.3;
    const r = ndc(BOX, { az: 27, el: -8, fov: 20, margin: [m, 0.3], bias: [b, 0] });
    expect(r.x1).toBeLessThan(1 - m + 1e-3);
    expect(r.x0).toBeGreaterThan(-(1 - m) - 1e-3);
    expect((r.x0 + r.x1) / 2).toBeCloseTo(b * (1 - m), 2);
  });

  test('the camera looks from the requested direction', () => {
    const { k } = ndc(BOX, { az: 30, el: -9, fov: 22 });
    const back = new THREE.Vector3(...k.pos).sub(new THREE.Vector3(...k.target)).normalize();
    expect(THREE.MathUtils.radToDeg(Math.atan2(back.x, back.z))).toBeCloseTo(30, 6);
    expect(THREE.MathUtils.radToDeg(Math.asin(back.y))).toBeCloseTo(-9, 6);
  });
});
