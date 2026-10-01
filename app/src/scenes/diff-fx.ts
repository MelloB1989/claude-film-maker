// The studio and the camera for `diff` (Plan 2 Task 16): the wall behind the editor (Backdrop) and the camera's framing
// (fitKey). The light on the editor itself (the blade, the glows, the signs, the washes and the romance's pool) is the
// engine's: engine/panel-light.ts.
import * as THREE from 'three';
import { LIN } from '../engine/palette';
import type { CamKey, V3 } from '../engine/stage';

/**
 * The studio behind the editor: a wide plane far back whose ink lifts softly toward `lift` in a pool (unlit and
 * opaque, so the depth of field reads it as the far distance). The romance warms it: the pool comes up behind the
 * struck line.
 */
export class Backdrop {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(size: [number, number]) {
    this.u = {
      uInk: { value: new THREE.Vector3(...LIN.ink) }, uLift: { value: new THREE.Vector3(...LIN.panel2) },
      uCentre: { value: new THREE.Vector2() }, uRadius: { value: new THREE.Vector2(1, 1) }, uLevel: { value: 0 },
    };
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: /* glsl */ `varying vec2 vP; void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `uniform vec3 uInk, uLift; uniform vec2 uCentre, uRadius; uniform float uLevel; varying vec2 vP;
        void main() { vec2 d = (vP - uCentre) / uRadius; gl_FragColor = vec4(mix(uInk, uLift, uLevel * exp(-dot(d, d))), 1.0); }`,
    }));
  }

  /** The pool's centre and radii (the plane's own units) and its strength (0: plain ink). */
  set(cx: number, cy: number, rx: number, ry: number, level: number) {
    (this.u.uCentre!.value as THREE.Vector2).set(cx, cy);
    (this.u.uRadius!.value as THREE.Vector2).set(rx, ry);
    this.u.uLevel!.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

// ---------------------------------------------------------------------------------------------------- framing

export interface Fit {
  /** Degrees round the subject's y axis from its front (+z): + to its right. */
  az: number;
  /** Degrees above it. */
  el: number;
  fov: number;
  /** Fraction of the half-frame left empty each side, across and up. */
  margin?: [number, number];
  /** Where the box sits, in fractions of the half-frame (+x right, +y up). */
  bias?: [number, number];
  roll?: number;
}

/**
 * A camera key that fits world points in frame from a direction, to a margin, placed by `bias`: projected, measured in
 * the view's plane, the distance scaled and the target shifted until the framing holds (perspective makes one pass
 * inexact). `frame` is the subject's frame (its right, up and front in the world): az and el are taken in it.
 */
export function fitKey(t: number, pts: readonly THREE.Vector3[], o: Fit, frame: THREE.Matrix4, ease?: (x: number) => number): CamKey {
  const [mx, my] = o.margin ?? [0.12, 0.12];
  const [bx, by] = o.bias ?? [0, 0];
  const az = THREE.MathUtils.degToRad(o.az), el = THREE.MathUtils.degToRad(o.el);
  const R = new THREE.Vector3(), U = new THREE.Vector3(), Fz = new THREE.Vector3();
  frame.extractBasis(R, U, Fz);
  const back = Fz.clone().multiplyScalar(Math.cos(az) * Math.cos(el)).addScaledVector(R, Math.sin(az) * Math.cos(el)).addScaledVector(U, Math.sin(el)).normalize();
  const f = back.clone().negate();
  const r = new THREE.Vector3().crossVectors(f, new THREE.Vector3(0, 1, 0)).normalize();
  const u = new THREE.Vector3().crossVectors(r, f);
  const ty = Math.tan(THREE.MathUtils.degToRad(o.fov) / 2), tx = ty * (16 / 9);
  const centre = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(Math.max(1, pts.length));
  let D = 1;
  for (let it = 0; it < 32; it++) {
    const cam = centre.clone().addScaledVector(back, D);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) {
      const v = p.clone().sub(cam), z = v.dot(f);
      const x = v.dot(r) / z, y = v.dot(u) / z;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const s = Math.max((x1 - x0) / (2 * tx * (1 - mx) * (1 - Math.abs(bx))), (y1 - y0) / (2 * ty * (1 - my) * (1 - Math.abs(by))));
    const cx = (x0 + x1) / 2 - bx * tx * (1 - mx) * s, cy = (y0 + y1) / 2 - by * ty * (1 - my) * s;
    centre.addScaledVector(r, cx * D).addScaledVector(u, cy * D);
    D *= s;
  }
  const pos = centre.clone().addScaledVector(back, D);
  return { t, pos: pos.toArray() as V3, target: centre.toArray() as V3, fov: o.fov, roll: o.roll, ease };
}
