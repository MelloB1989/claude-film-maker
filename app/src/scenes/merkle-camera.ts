// The camera of `merkle`, pure (no renderer), so a transition and a test can build exactly what the scene renders:
// the dive's path and where it stands (merkle-tree.ts), the crane's keys from the clock (merkle-time.ts), the landing
// beside the file and the screen point the file holds there (landingAim), and the last push into it (diveAt).
import * as THREE from 'three';
import { CameraRig, type CamKey, type V3 } from '../engine/stage';
import { W, H } from '../engine/gl';
import { ease, prog } from '../engine/util';
import { SEED, buildTree, diveLeaf, pickChanged, pathTo, type Tree } from './merkle-tree';
import type { Times } from './merkle-time';

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

/** The tree, the dive's path (the root down to its file) and where each of them stands. */
export function divePath(tree: Tree = buildTree(pickChanged(SEED))) {
  const path = pathTo(diveLeaf(tree));
  const P = path.map((id) => v(tree.pos[id * 3]!, tree.pos[id * 3 + 1]!, tree.pos[id * 3 + 2]!));
  return { tree, path, P };
}

/** The frame of the dive's side of the tree: out from the trunk through the file, and points placed by it. */
function frameOf(P: THREE.Vector3[]) {
  const P4 = P[4]!;
  const out = v(P4.x, 0, P4.z).normalize();
  const az = Math.atan2(out.x, out.z);
  const Y = v(0, 1, 0);
  return {
    out,
    at: (a: number, r: number, y: number) => v(r * Math.sin(az + a), y, r * Math.cos(az + a)),
    // out from a node of the path and up, and a point in from it and up
    outside: (p: THREE.Vector3, r: number, h: number) => p.clone().addScaledVector(out, r).addScaledVector(Y, h),
    inside: (p: THREE.Vector3, r: number, h: number) => p.clone().addScaledVector(out, -r).addScaledVector(Y, h),
  };
}

/** The landing's last key (at the scene's end): low beside the file, looking up into the vault. */
function landed(P: THREE.Vector3[]) {
  const { outside, inside } = frameOf(P);
  const P4 = P[4]!;
  return { pos: outside(P4, 0.094, 0.018), target: inside(P4, 0.4, 0.08), fov: 60 };
}

/**
 * The crane (merkle.ts): one side of the tree, the dive's file's (`out`, from the trunk through the file). It cuts in
 * low there, looking up into the vault, rises over it as the moss climbs, and drops back down outside the lit branch
 * to land low beside the file, looking up into the same vault with only the fifty paths left in it.
 */
export function rigKeys(T: Times, P: THREE.Vector3[]): CamKey[] {
  const [, P1, P2, P3, P4] = P as [THREE.Vector3, THREE.Vector3, THREE.Vector3, THREE.Vector3, THREE.Vector3];
  const key = (t: number, pos: THREE.Vector3, target: THREE.Vector3, fov?: number, e?: (x: number) => number): CamKey =>
    ({ t, pos: pos.toArray() as V3, target: target.toArray() as V3, fov, ease: e });
  const { at, outside, inside } = frameOf(P);
  const d = THREE.MathUtils.degToRad;
  const apex = at(d(1), 0.9, 1.0), apexAt = v(0, 0.32, 0);
  const crest = apex.clone().lerp(outside(P1, 0.34, 0.16), 0.3), crestAt = apexAt.clone().lerp(inside(P1, 0.06, -0.13), 0.45);
  const end = landed(P);
  return [
    // low at the tree's edge, looking up into the vault; the crane rises and pulls back over it
    key(T.start, at(d(-12), 0.86, 0.04), v(0, 0.46, 0), 44),
    key(T.fifty + 0.55, at(d(10), 1.42, 0.7), v(0, 0.215, 0), 34, ease.inOutQuad),
    // high over the lit tree as the moss reaches the root, then easing in for the walk
    key(T.root, at(d(4), 1.04, 1.06), v(0, 0.31, 0), 34, ease.inOutCubic),
    key(T.walk[0]!, apex, apexAt, 36, ease.inOutCubic),
    // the crest: through "I only" it all but holds, pushing in over the lit branch while the top two levels' unchanged
    // subtrees fold shut around it and take their stamps (still enough to read them)
    key(T.walk[2]! - 0.04, crest, crestAt, 38, ease.inOutQuad),
    // the plunge on "look at": down outside the lit branch, level by level, the comet leading, tipping up from the
    // drop to the vault as it lands with "fifty."
    key(T.walk[3]! - 0.04, outside(P2, 0.2, 0.05), inside(P3, 0.0, 0.0), 44, ease.inQuad),
    key(T.walk[3]! + 0.08, outside(P3, 0.13, 0.012), inside(P4, 0.12, 0.08), 48, ease.linear),
    key(T.land + 0.01, outside(P4, 0.1, 0.016), inside(P4, 0.4, 0.075), 60, ease.outCubic),
    key(T.end, end.pos, end.target, end.fov, ease.linear),
  ];
}

/** A world point on screen (logical px) through a camera. */
export function onScreen(cam: THREE.PerspectiveCamera, p: THREE.Vector3): [number, number] {
  const q = p.clone().project(cam);
  return [((q.x + 1) / 2) * W, ((1 - q.y) / 2) * H];
}

/**
 * The dive into the file (merkle → graph's zoom-through, transitions/merkle-graph.ts): after "fifty." has landed and
 * the counter has slammed, the camera drives at the file along its line of sight, so the file holds its place in the
 * frame while the vault streams out past the lens; the zoom-through then pushes on through that same point.
 * `from` before the scene's end (s), and how far toward the file it has gone by the end (share of the distance).
 */
export const DIVE = { from: 0.4, reach: 0.35 };

/** How far into the dive the camera is at t (0..1 of its reach), in-cubic: it gathers speed into the cut. */
export const diveAt = (t: number, T: Pick<Times, 'end'>) => DIVE.reach * ease.inCubic(prog(t, T.end - DIVE.from, T.end));

/** The landed camera (its last key) and where the file stands on screen through it, logical px. */
export function landingAim(P: THREE.Vector3[] = divePath().P): { world: THREE.Vector3; screen: [number, number] } {
  const end = landed(P);
  const cam = new THREE.PerspectiveCamera(end.fov, W / H, 0.004, 20);
  new CameraRig([{ t: 0, pos: end.pos.toArray() as V3, target: end.target.toArray() as V3, fov: end.fov }]).apply(cam, 0);
  return { world: P[4]!.clone(), screen: onScreen(cam, P[4]!) };
}

/**
 * The camera at t: the rig, then the dive (pos and target carried together toward the file, so the view's direction,
 * and the file's place in the frame, do not change while the rest of the vault rushes past).
 */
export function aimAt(cam: THREE.PerspectiveCamera, rig: CameraRig, t: number, T: Pick<Times, 'end'>, file: THREE.Vector3) {
  rig.apply(cam, t);
  const k = diveAt(t, T);
  if (k <= 0) return;
  const step = file.clone().sub(cam.position).multiplyScalar(k);
  cam.position.add(step);
  cam.updateMatrixWorld();
}
