// The cracked word of scene `thread`: "zero." as extruded satin bone that splits in two along a jagged crack when the
// thread snaps. One word, built twice (two Type3D lines with the same glyphs), each with a material that keeps only
// its side of the crack; posed alike they are exactly the whole word, and after the snap each half rides its own
// broken end of the thread.
//
// The crack is a polyline in the word's own space (its group: x along the line from the text origin, y up from the
// baseline, world units). Each half's material discards the fragments on the other side of it. Where a half is cut
// open, its back faces show through the cut: they are shaded as the fracture face, with the normal of the crack segment
// they sit behind (turned by the half's pose), rough and in shadow, so the half reads as solid bone broken through, not a
// hollow shell, and a broken e does not close up into a whole letter.
import * as THREE from 'three';
import { Mat } from '../engine/type3d';

/** The crack in em: (x from the reference, the middle of the gap between the e and the r; y from the baseline), bottom
 * to top. Its teeth bite alternately into the e's tail and bowl and the r's stem (Bricolage 600: the gap is 0.06 em,
 * the strokes about 0.09), so each half carries chunks of the other's letter, the way brittle type breaks, while the
 * word still parts at its syllables: ze, ro. */
export const CRACK_EM: readonly (readonly [number, number])[] = [
  [0.0, -0.35], [0.012, -0.05], [-0.095, 0.045], [0.07, 0.13], [-0.015, 0.2], [0.115, 0.29], [-0.105, 0.4],
  [0.06, 0.48], [-0.03, 0.56], [0.0, 0.66], [0.0, 1.0],
];
const N = CRACK_EM.length;

export interface CrackUniforms {
  uWordInv: { value: THREE.Matrix4 };
  uWordToView: { value: THREE.Matrix3 };
  uCrack: { value: THREE.Vector2[] };
  uSide: { value: number };
}

const GLSL_DECL = /* glsl */ `
uniform mat4 uWordInv;
uniform mat3 uWordToView;
uniform vec2 uCrack[${N}];
uniform float uSide;
varying vec3 vWordP;`;

const GLSL_CRACK = /* glsl */ `
// x of the crack at height y, and the normal (pointing +x) of the segment there
float crackAt( float y, out vec2 n ) {
	vec2 a = uCrack[0], b = uCrack[1];
	for ( int i = 1; i < ${N}; i ++ ) {
		a = uCrack[ i - 1 ]; b = uCrack[ i ];
		if ( y <= b.y ) break;
	}
	vec2 d = b - a;
	n = normalize( vec2( d.y, - d.x ) );
	float k = clamp( ( y - a.y ) / max( d.y, 1e-6 ), 0.0, 1.0 );
	return mix( a.x, b.x, k );
}`;

/**
 * Satin bone that keeps one side of the crack: `side` -1 the left, +1 the right. Its uniforms (returned with it) take
 * the half's pose each frame (setPose). DoubleSide, so the cut shows the fracture face.
 */
export function crackMaterial(side: -1 | 1): { mat: THREE.MeshPhysicalMaterial; u: CrackUniforms } {
  const mat = Mat.satinBone();
  mat.side = THREE.DoubleSide;
  const u: CrackUniforms = {
    uWordInv: { value: new THREE.Matrix4() },
    uWordToView: { value: new THREE.Matrix3() },
    uCrack: { value: CRACK_EM.map(() => new THREE.Vector2()) },
    uSide: { value: side },
  };
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>\n${GLSL_DECL}`)
      .replace('#include <project_vertex>', '#include <project_vertex>\n\tvWordP = ( uWordInv * modelMatrix * vec4( transformed, 1.0 ) ).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\n${GLSL_DECL}\n${GLSL_CRACK}`)
      .replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
	vec2 crackN;
	float crackX = crackAt( vWordP.y, crackN );
	if ( uSide * ( vWordP.x - crackX ) < 0.0 ) discard;`)
      .replace('#include <normal_fragment_begin>', `#include <normal_fragment_begin>
	if ( ! gl_FrontFacing ) {
		normal = normalize( uWordToView * vec3( - uSide * crackN, 0.0 ) );
		nonPerturbedNormal = normal;
	}`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
	if ( ! gl_FrontFacing ) roughnessFactor = 0.85;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
	if ( ! gl_FrontFacing ) diffuseColor.rgb *= 0.16;`)
      .replace('#include <lights_physical_fragment>', `#include <lights_physical_fragment>
	if ( ! gl_FrontFacing ) {
		#ifdef USE_CLEARCOAT
			material.clearcoat = 0.0;
		#endif
		#ifdef USE_SHEEN
			material.sheenColor = vec3( 0.0 );
		#endif
		material.specularColor *= 0.3;
		material.specularColorBlended *= 0.3;
	}`);
  };
  mat.customProgramCacheKey = () => 'thread-crack';
  return { mat, u };
}

/** Sets the crack (em -> the word's world units, from reference x `x0`) on a half's uniforms. */
export function setCrack(u: CrackUniforms, x0: number, em: number) {
  CRACK_EM.forEach(([x, y], i) => u.uCrack.value[i]!.set(x0 + x * em, y * em));
}

/** A half's pose for its material: the word space is its group's; directions from it to the camera's view space. */
export function setPose(u: CrackUniforms, group: THREE.Object3D, camera: THREE.Camera) {
  group.updateWorldMatrix(true, false); // its ancestors too: the half's pivot has just moved
  camera.updateMatrixWorld();
  u.uWordInv.value.copy(group.matrixWorld).invert();
  const m = new THREE.Matrix4().multiplyMatrices(camera.matrixWorldInverse, group.matrixWorld);
  u.uWordToView.value.setFromMatrix4(m);
}
