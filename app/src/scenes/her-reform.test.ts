// B03's plate and her's engine see through one camera: Blender's tracked join point (data/track/b03_reform.json, the
// shot rendered through its Python port of the rig) lands where three's CameraRig, built from the same keys
// (her-reform.ts), projects it, on every frame of the plate. A plate re-rendered from changed keys, or keys changed
// without re-rendering the plate, fail here.
import { describe, expect, test } from 'bun:test';
import * as THREE from 'three';
import { CameraRig } from '../engine/stage';
import { ReformWorld, reformCues, reformKeys, REFORM } from './her-reform';
import TRACK from '../../../data/track/b03_reform.json';
import VO from '../../../data/vo.json';
import AUDIO from '../../../data/audio.json';

function cues() {
  const scene = VO.scenes.find((s) => s.id === 'her')!;
  const l06 = VO.lines.find((l) => l.id === 'L06')!;
  const [not, me] = [l06.words[0]!.start, l06.words[1]!.start];
  const down = AUDIO.downbeats.find((d: number) => d > me)!;
  return reformCues(scene.start, not, me, down);
}

describe('the re-form plate and her share a camera', () => {
  test('the plate covers her from its first frame to the one before the whip', () => {
    const c = cues();
    expect(TRACK.f0).toBe(Math.ceil(c.start * 30));
    const frames = TRACK.anchors.join.length;
    expect((TRACK.f0 + frames - 1) / 30).toBeLessThan(c.hand - 0.5 / 60); // its last frame's shutter ends before the whip
    expect((TRACK.f0 + frames) / 30 + 0.5 / 60).toBeGreaterThan(c.hand); // and the next frame's touches it
    expect(c.hand).toBeCloseTo(c.down - REFORM.whip / 2, 12);
  });

  test("the tracked join is where her's rig projects it, within half a pixel, on every plate frame", () => {
    const w = new ReformWorld();
    const rig = new CameraRig(reformKeys(w, cues()));
    const cam = new THREE.PerspectiveCamera(30, 16 / 9, 0.005, 50);
    let worst = 0;
    TRACK.anchors.join.forEach(([x, y, vis], i) => {
      rig.apply(cam, (TRACK.f0 + i) / 30);
      const p = w.join.clone().project(cam);
      const px = ((p.x + 1) / 2) * 1920, py = ((1 - p.y) / 2) * 1080;
      expect(vis).toBe(1);
      worst = Math.max(worst, Math.hypot(px - x, py - y));
    });
    expect(worst).toBeLessThan(0.5);
  });
});
