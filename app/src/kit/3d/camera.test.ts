import { expect, test } from 'bun:test';
import { CAMERA_MOVES, MOVE, basis, combine, fitDistance, moveAt, moved, orbitPos, unitsPerPx, whipOut, WHIP } from './camera';
import { REVEALS_3D, EXITS_3D, composePose, exitPose, revealPose, REST } from './motion3d';

const len = (v: number[]) => Math.hypot(...v);

test('moves: push closes the distance by MOVE.push over the shot, pull opens it, both through the framing at p = 0.5', () => {
  expect(moveAt('push', 0, 0).dist).toBeCloseTo(1 + MOVE.push.dist / 2, 9);
  expect(moveAt('push', 0.5, 0).dist).toBeCloseTo(1, 9);
  expect(moveAt('push', 1, 0).dist).toBeCloseTo(1 - MOVE.push.dist / 2, 9);
  expect(moveAt('pull', 1, 0).dist).toBeCloseTo(1 + MOVE.push.dist / 2, 9);
  // amount scales
  expect(moveAt('push', 1, 0, 2).dist).toBeCloseTo(1 - MOVE.push.dist, 9);
  // monotonic
  let prev = Infinity;
  for (let p = 0; p <= 1; p += 0.05) {
    const d = moveAt('push', p, 0).dist;
    expect(d).toBeLessThanOrEqual(prev + 1e-12);
    prev = d;
  }
});

test('moves: orbit swings the azimuth, dolly slides, crane rises, static holds; every move is clamped outside the shot', () => {
  expect(moveAt('orbit', 0, 0).az).toBeCloseTo(-MOVE.orbit.az / 2, 9);
  expect(moveAt('orbit', 1, 0).az).toBeCloseTo(MOVE.orbit.az / 2, 9);
  expect(moveAt('dolly', 1, 0).slide[0]).toBeCloseTo(MOVE.dolly.slide / 2, 9);
  expect(moveAt('crane', 1, 0).el).toBeCloseTo(MOVE.crane.el / 2, 9);
  expect(moveAt('static', 0.3, 2)).toEqual({ dist: 1, az: 0, el: 0, roll: 0, slide: [0, 0] });
  for (const m of CAMERA_MOVES) {
    expect(moveAt(m, -0.5, 1)).toEqual(moveAt(m, 0, 1));
    expect(moveAt(m, 1.5, 1).az).toBeCloseTo(moveAt(m, 1, 1).az, 9);
  }
  expect(() => moveAt('zoomy' as never, 0, 0)).toThrow(/unknown camera move/);
});

test('moves: the drift is a pure function of time, small and slow', () => {
  for (let t = 0; t < 20; t += 0.37) {
    const a = moveAt('drift', t / 20, t), b = moveAt('drift', t / 20, t);
    expect(a).toEqual(b);
    expect(Math.abs(a.az)).toBeLessThanOrEqual(MOVE.drift.az + 1e-9);
    expect(Math.abs(a.el)).toBeLessThanOrEqual(MOVE.drift.el + 1e-9);
  }
  const c = combine(moveAt('push', 1, 0), moveAt('orbit', 1, 0));
  expect(c.dist).toBeCloseTo(1 - MOVE.push.dist / 2, 9);
  expect(c.az).toBeCloseTo(MOVE.orbit.az / 2, 9);
});

test('orbit: the camera stands `dist` from its target, on the side its azimuth and elevation say', () => {
  const o = { target: [1, 2, 3] as [number, number, number], az: 0, el: 0, dist: 5, fov: 30 };
  expect(orbitPos(o)).toEqual([1, 2, 8]);
  const right = orbitPos({ ...o, az: 90 });
  expect(right[0]).toBeCloseTo(6, 9);
  const above = orbitPos({ ...o, el: 90 });
  expect(above[1]).toBeCloseTo(7, 9);
  for (const [az, el] of [[0, 0], [30, 10], [-50, -20]]) {
    const { back, right: r, up } = basis(az!, el!);
    expect(len(back)).toBeCloseTo(1, 9);
    expect(len(r)).toBeCloseTo(1, 9);
    expect(len(up)).toBeCloseTo(1, 9);
    expect(back[0] * r[0] + back[1] * r[1] + back[2] * r[2]).toBeCloseTo(0, 9);
    expect(up[1]).toBeGreaterThan(0);
  }
  // a dolly slides the target along the view's right
  const m = moved(o, { dist: 1, az: 0, el: 0, roll: 0, slide: [0.1, 0] });
  expect(m.target[0]).toBeCloseTo(1.5, 9);
});

test('fitDistance: the tighter of width and height decides, so the same box stands further off in a tall frame', () => {
  const land = fitDistance(4, 1, 30, 16 / 9, 0.1), tall = fitDistance(4, 1, 30, 9 / 16, 0.1), sq = fitDistance(4, 1, 30, 1, 0.1);
  expect(tall).toBeGreaterThan(sq);
  expect(sq).toBeGreaterThan(land);
  // at that distance the box's width spans exactly the frame less its margins
  const halfW = Math.tan((30 * Math.PI) / 360) * (16 / 9) * land;
  expect(4 / (2 * halfW)).toBeCloseTo(0.8, 9);
  // a tall box in a landscape frame: the height decides
  const d = fitDistance(1, 4, 30, 16 / 9, 0.1);
  expect(4 / (2 * Math.tan((30 * Math.PI) / 360) * d)).toBeCloseTo(0.8, 9);
  expect(unitsPerPx(30, d, 1080) * 1080).toBeCloseTo(2 * Math.tan((30 * Math.PI) / 360) * d, 9);
});

test('whipOut: nothing before its window, the whole turn on the cut, accelerating into it', () => {
  expect(whipOut(9, 10, 'left')).toEqual({ yaw: 0, pitch: 0 });
  expect(whipOut(10, 10, 'left').yaw).toBeCloseTo(WHIP.deg, 9);
  expect(whipOut(10, 10, 'right').yaw).toBeCloseTo(-WHIP.deg, 9);
  expect(whipOut(10, 10, 'up').pitch).toBeCloseTo(WHIP.deg, 9);
  expect(whipOut(10 - WHIP.dur / 2, 10, 'left').yaw).toBeLessThan(WHIP.deg / 4);
  expect(WHIP.dur).toBeGreaterThanOrEqual(0.06);
  expect(WHIP.dur).toBeLessThanOrEqual(0.12);
});

test('reveals: hidden before launch, exactly at rest once settled, and every reveal reaches its landing at `at`', () => {
  for (const r of REVEALS_3D) {
    expect(revealPose(r, 0, 5).on).toBe(false);
    const late = revealPose(r, 20, 5);
    expect(late.on).toBe(true);
    expect(late.dx).toBeCloseTo(0, 6);
    expect(late.dy).toBeCloseTo(0, 6);
    expect(late.dz).toBeCloseTo(0, 6);
    expect(late.rx).toBeCloseTo(0, 6);
    expect(late.s).toBeCloseTo(1, 6);
    // the spring first arrives on `at`: shown, and within a hair of rest
    const hit = revealPose(r, 5, 5);
    expect(hit.on).toBe(true);
    expect(Math.abs(hit.s - 1)).toBeLessThan(1e-6);
  }
  expect(() => revealPose('bounce' as never, 0, 0)).toThrow(/unknown 3D reveal/);
});

test('exits: rest until their stagger starts, deterministic, gone or away by the end', () => {
  for (const e of EXITS_3D) {
    expect(exitPose(e, 0, 10, 0, 5)).toEqual(REST);
    expect(exitPose(e, 9.9, 10, 2, 5, { seed: 3 })).toEqual(exitPose(e, 9.9, 10, 2, 5, { seed: 3 }));
    const end = exitPose(e, 10, 10, 4, 5);
    expect(Math.abs(end.dx) + Math.abs(end.dy) + Math.abs(end.dz)).toBeGreaterThan(1);
  }
  // the first unit leaves first
  expect(exitPose('fall', 9.6, 10, 0, 5).dy).toBeLessThan(exitPose('fall', 9.6, 10, 4, 5).dy);
  const c = composePose({ ...REST, dy: 1, s: 2 }, { ...REST, dy: 2, s: 0.5, on: false });
  expect(c).toEqual({ ...REST, dy: 3, s: 1, on: false });
});
