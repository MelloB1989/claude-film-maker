// her's opening beat is Blender's B03, the re-form (blender/shots/b03_reform.py): the ends of the thread that snapped
// in the cold open drawn back together on "Not", born again as the diff thread. The plate and her's engine thread share
// one world, data/look/b03_reform.json, read by both renderers: the thread's line and radius, the join where the ends
// meet, the whip's length, the lens's f-number, and the camera's keys (cue times, offsets from the join in thread radii
// along the thread, its side and world up, a roll, a vertical fov). B03 renders through this rig (ported to Python),
// and her drives its whip from it, so the plate hands off to the engine thread inside the whip on the downbeat with
// nothing to match by eye. her-reform.test.ts holds the plate's tracked join to the engine's projection of it.
import * as THREE from 'three';
import type { CamKey, V3 } from '../engine/stage';
import { ease } from '../engine/util';
import SPEC from '../../../data/look/b03_reform.json';

/** The Blender shot whose plate her composites for its opening beat. */
export const PLATE = 'b03_reform';
export const REFORM = SPEC;

/** The re-form's moments (song seconds): the scene's start, "Not", "me.", the downbeat after it, and the hand-off. */
export interface ReformCues {
  start: number;
  not: number;
  me: number;
  down: number;
  /** The whip's first instant (its centre is the downbeat): the plate shows the frames before it, the engine the rest. */
  hand: number;
}

export function reformCues(start: number, not: number, me: number, down: number): ReformCues {
  return { start, not, me, down, hand: down - SPEC.whip / 2 };
}

const Y = new THREE.Vector3(0, 1, 0);

/** The thread's world: its line A to B and radius, its direction, the horizontal square to it on the viewer's side. */
export class ReformWorld {
  readonly A = new THREE.Vector3(...(SPEC.thread.a as V3));
  readonly B = new THREE.Vector3(...(SPEC.thread.b as V3));
  readonly R = SPEC.thread.radius;
  readonly dir = new THREE.Vector3().subVectors(this.B, this.A).normalize();
  readonly side = new THREE.Vector3(-this.dir.z, 0, this.dir.x).normalize();
  /** Where the ends meet: arc fraction `join` of the way from A to B. */
  readonly join = this.A.clone().lerp(this.B, SPEC.join);

  /** The join plus offsets in thread radii along (dir, side, up). */
  at([a, b, c]: readonly number[]): THREE.Vector3 {
    return this.join.clone().addScaledVector(this.dir, a! * this.R).addScaledVector(this.side, b! * this.R).addScaledVector(Y, c! * this.R);
  }
}

type EaseName = keyof typeof ease;

/** B03's camera keys as a CameraRig takes them (stage.ts): each at its cue's time plus its offset. */
export function reformKeys(w: ReformWorld, cues: ReformCues): CamKey[] {
  return SPEC.camera.map((k) => {
    const name = ((k as { ease?: string }).ease ?? 'inOutCubic') as EaseName;
    const fn = ease[name];
    if (typeof fn !== 'function') throw new Error(`b03_reform.json: no ease '${name}'`);
    const cue = cues[k.cue as keyof ReformCues];
    if (cue === undefined) throw new Error(`b03_reform.json: no cue '${k.cue}'`);
    return {
      t: cue + ((k as { dt?: number }).dt ?? 0),
      pos: w.at(k.eye).toArray() as V3,
      target: w.at(k.look).toArray() as V3,
      fov: (k as { fov?: number }).fov,
      roll: k.roll,
      ease: (x: number) => (fn as (x: number) => number)(x),
    };
  });
}
