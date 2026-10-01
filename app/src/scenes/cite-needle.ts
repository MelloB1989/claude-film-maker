// The needle for `cite` (Plan 2 Task 17): the thread's tip, stiffened and polished. A slim needle of the thread's own
// bone, glazed (satin under a hard clear coat, like the film's type: it catches the studio's softboxes as a line down
// its length), its eye a slot near the head that the thread ends in, and a filament of moss light in its point: the
// thread's truth carried into the file.
//
// Geometry: a lathe in the editor's px (the mesh is scaled to the world by the scene), its axis along +x from the head
// (x = 0) to the point (x = NEEDLE.len), the eye a slot through it along z near the head. The slot is cut in the
// fragment shader (an ellipse in the needle's own frame, discarded on its near and far walls, so it is a hole you see
// the panel through), as is the forming: everything behind `front` (toward the head) is not needle yet. The moss light is
// emitted in the shader too: a filament in the point while the needle sews, and a ring of light at the forming front.
import * as THREE from 'three';
import { glow } from '../engine/look';
import { LIN } from '../engine/palette';
import { NEEDLE } from './cite-time';

/** The needle's radii (px): the shaft, the swell round the eye, the eye slot (half its length, half its width). */
export const SHAPE = { shaft: 3.2, swell: 0.7, eyeHalf: 9.5, eyeW: 1.35, taper: 70, cap: 3 } as const;

/** The lathe profile, (radius, x along the axis) from the head's pole to the point. */
export function needleProfile(): THREE.Vector2[] {
  const L = NEEDLE.len, pts: THREE.Vector2[] = [];
  const r = (x: number) => {
    // the head: a round cap; the eye's swell; the shaft; the taper to a fine point (a little concave, as a needle's is)
    const cap = x < SHAPE.cap ? Math.sqrt(Math.max(0, 1 - ((SHAPE.cap - x) / SHAPE.cap) ** 2)) : 1;
    const e = (x - NEEDLE.eye) / (SHAPE.eyeHalf + 9);
    const swell = Math.abs(e) < 1 ? SHAPE.swell * (0.5 + 0.5 * Math.cos(Math.PI * e)) : 0;
    const t0 = L - SHAPE.taper, taper = x > t0 ? Math.max(0.03, (1 - (x - t0) / SHAPE.taper) ** 1.25) : 1;
    return (SHAPE.shaft + swell) * cap * taper;
  };
  pts.push(new THREE.Vector2(0, 0));
  for (let i = 1; i <= 12; i++) {
    const x = SHAPE.cap * (1 - Math.cos((Math.PI / 2) * (i / 12)));
    pts.push(new THREE.Vector2(r(x), x));
  }
  for (let x = SHAPE.cap + 1.5; x < L - 0.4; x += x > L - SHAPE.taper - 4 ? 1.6 : 2.5) pts.push(new THREE.Vector2(r(x), x));
  pts.push(new THREE.Vector2(0.06, L - 0.15), new THREE.Vector2(0, L));
  return pts;
}

/** The needle's geometry: the lathe turned onto x (head at 0, point at NEEDLE.len), in px. */
export function needleGeometry(): THREE.BufferGeometry {
  const geo = new THREE.LatheGeometry(needleProfile(), 28);
  geo.rotateZ(-Math.PI / 2); // the lathe's axis (y) onto x
  return geo;
}

export class Needle {
  mesh: THREE.Mesh;
  material: THREE.MeshPhysicalMaterial;
  /** x: the forming front (px from the head; nothing behind it is needle yet); y: the point's moss filament; z: the
   * front's ring of light (both glow() levels); w unused. */
  private u = { value: new THREE.Vector4(0, 0, 0, 0) };

  /** `pxWorld`: world units per editor px (the scene's scale). */
  constructor(pxWorld: number) {
    const bone = new THREE.Color().setRGB(...LIN.bone);
    // satin bone under a hard clear coat, a little sheen at grazing angles: the type's surface, glazed harder
    this.material = new THREE.MeshPhysicalMaterial({
      color: bone,
      metalness: 0,
      roughness: 0.3,
      clearcoat: 1,
      clearcoatRoughness: 0.035,
      sheen: 0.45,
      sheenRoughness: 0.35,
      sheenColor: bone,
      specularIntensity: 1,
      side: THREE.DoubleSide, // the eye's slot shows the inside of the far wall
    });
    const u = this.u, moss = new THREE.Vector3(...glow('moss', 1));
    const L = NEEDLE.len.toFixed(1), EYE = NEEDLE.eye.toFixed(1);
    this.material.onBeforeCompile = (sh) => {
      sh.uniforms.uNdl = u;
      sh.uniforms.uNdlMoss = { value: moss };
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vNdl;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\n\tvNdl = position;');
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform vec4 uNdl;\nuniform vec3 uNdlMoss;\nvarying vec3 vNdl;')
        .replace('#include <clipping_planes_fragment>', /* glsl */ `#include <clipping_planes_fragment>
	if (vNdl.x < uNdl.x) discard; // not needle yet: still the thread's
	{ // the eye: an elongated slot through the needle (its near and far walls), the thread's end in it
		float ndlE = (vNdl.x - ${EYE}) / ${SHAPE.eyeHalf.toFixed(2)};
		if (abs(ndlE) < 1.0 && abs(vNdl.y) < ${SHAPE.eyeW.toFixed(3)} * sqrt(1.0 - ndlE * ndlE)) discard;
	}`)
        .replace('#include <emissivemap_fragment>', /* glsl */ `#include <emissivemap_fragment>
	{ // the moss filament in the point, and the ring of light at the forming front
		float ndlTip = smoothstep(${L} - 40.0, ${L} - 4.0, vNdl.x);
		float ndlFront = exp(-pow((vNdl.x - uNdl.x) / 5.0, 2.0));
		totalEmissiveRadiance = uNdlMoss * (uNdl.y * ndlTip + uNdl.z * ndlFront);
	}`);
    };
    this.material.customProgramCacheKey = () => 'cite-needle';
    this.mesh = new THREE.Mesh(needleGeometry(), this.material);
    this.mesh.scale.setScalar(pxWorld);
    this.mesh.frustumCulled = false;
  }

  /**
   * Place the needle: its eye's centre at `eye` (world), its point toward `dir`, the eye's slot facing `face` (made square
   * to the axis: the camera, so the eye reads). `front` 0..1: how much of it has formed, from the point (0: none) back to
   * the head (1: all); `tip` and `ring` the moss levels of the point's filament and the forming front.
   */
  set(eye: THREE.Vector3, dir: THREE.Vector3, face: THREE.Vector3, front: number, tip: number, ring: number) {
    const x = dir.clone().normalize();
    const z = face.clone().addScaledVector(x, -face.dot(x));
    if (z.lengthSq() < 1e-12) z.set(0, 0, 1).addScaledVector(x, -x.z);
    z.normalize();
    const y = new THREE.Vector3().crossVectors(z, x);
    this.mesh.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
    // the eye's centre is NEEDLE.eye px along the axis from the head (the mesh's origin)
    const s = this.mesh.scale.x;
    this.mesh.position.copy(eye).addScaledVector(x, -NEEDLE.eye * s);
    this.mesh.visible = front > 0;
    this.u.value.set(NEEDLE.len * (1 - front), tip, ring, 0);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.material.dispose();
  }
}
