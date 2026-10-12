// three.js for films: a film's own scenes import it from here (`import { THREE } from '@engine/three'`), so they share
// the engine's one copy and resolve from films/ without a node_modules of their own. The loaders and helpers a scene
// most often reaches for come along.
import * as THREE from 'three';

export { THREE };
export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
export { SVGLoader } from 'three/examples/jsm/loaders/SVGLoader.js';
export { EXRLoader } from 'three/examples/jsm/loaders/EXRLoader.js';
export { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
export { mergeGeometries, mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
export { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
