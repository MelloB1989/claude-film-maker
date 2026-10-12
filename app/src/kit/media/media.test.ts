import { expect, test } from 'bun:test';
import { cropRect, entryState, kenBurns, layoutBox } from './frame';
import { clipFrame, framePath, isVideo, mediaName } from './paths';
import { deviceLayout, scrollAt } from './device';

test('layoutBox: cover fills the box, contain takes the picture\'s aspect', () => {
  const o = { cx: 0.5, cy: 0.5, w: 0.5, h: 0.5, W: 1920, H: 1080 };
  expect(layoutBox({ ...o, fit: 'cover', aspect: 1 })).toEqual({ x: 480, y: 270, w: 960, h: 540 });
  const c = layoutBox({ ...o, fit: 'contain', aspect: 1 });
  expect([c.w, c.h, c.x + c.w / 2, c.y + c.h / 2]).toEqual([540, 540, 960, 540]);
  const d = layoutBox({ ...o, fit: 'contain', aspect: 4 });
  expect([d.w, d.h]).toEqual([960, 240]);
});

test('cropRect: the box\'s aspect, inside the picture, zoomed and panned by the slack', () => {
  const r = cropRect(1600, 1000, 16 / 9);
  expect(r.sw).toBe(1600);
  expect(r.sh).toBeCloseTo(900, 9);
  expect(r.sy).toBeCloseTo(50, 9); // centred
  expect(cropRect(1600, 1000, 16 / 9, 1, 0, -1).sy).toBe(0); // top
  expect(cropRect(1600, 1000, 16 / 9, 1, 0, 1).sy).toBeCloseTo(100, 9); // bottom
  const z = cropRect(1000, 1000, 1, 2, 1, -1);
  expect(z).toEqual({ sx: 500, sy: 0, sw: 500, sh: 500 });
  // tall box in a wide picture: full height, cropped sides; pans clamp
  const t = cropRect(2000, 1000, 0.5, 1, 5, 0);
  expect([t.sw, t.sh, t.sx]).toEqual([500, 1000, 1500]);
  for (const [z2, px, py] of [[1, 0, 0], [1.3, -1, 1], [3, 0.4, -0.7]] as const) {
    const q = cropRect(1234, 777, 1.7, z2, px, py);
    expect(q.sx).toBeGreaterThanOrEqual(0);
    expect(q.sy).toBeGreaterThanOrEqual(0);
    expect(q.sx + q.sw).toBeLessThanOrEqual(1234 + 1e-9);
    expect(q.sy + q.sh).toBeLessThanOrEqual(777 + 1e-9);
    expect(q.sw / q.sh).toBeCloseTo(1.7, 9);
  }
});

test('kenBurns: from at 0, to at 1, eased (no jump at either end)', () => {
  const a = { zoom: 1.2, x: -0.5 }, b = { zoom: 1, x: 0.5, y: 0.2 };
  expect(kenBurns(a, b, 0)).toEqual({ zoom: 1.2, x: -0.5, y: 0 });
  const e = kenBurns(a, b, 1);
  expect(e.zoom).toBeCloseTo(1, 12);
  expect(e.y).toBeCloseTo(0.2, 12);
  expect(kenBurns(a, b, 0.5).x).toBeCloseTo(0, 12);
  expect(Math.abs(kenBurns(a, b, 0.001).zoom - 1.2)).toBeLessThan(1e-5);
});

test('entryState: hidden before, shown after, every kind; throws on an unknown one', () => {
  for (const k of ['fade', 'rise', 'scale', 'wipe'] as const) {
    const before = entryState(k, -0.1), after = entryState(k, 3);
    expect(Math.min(before.alpha, before.wipe)).toBe(0);
    expect(after.alpha).toBe(1);
    expect(after.wipe).toBe(1);
    expect(after.scale).toBeCloseTo(1, 3);
    expect(Math.abs(after.dy)).toBeLessThan(0.5);
  }
  expect(entryState('none', -1)).toEqual({ alpha: 1, dy: 0, scale: 1, wipe: 1 });
  expect(entryState('rise', 0.1).dy).toBeGreaterThan(0);
  expect(() => entryState('zoom' as never, 0)).toThrow(/entry is/);
});

test('clipFrame: the clip runs from offset at the shot start, at rate, on the film\'s frame grid; loops or holds', () => {
  const o = { start: 10, fps: 30, count: 90, filmFps: 30 };
  expect(clipFrame(10, o)).toBe(0);
  expect(clipFrame(11, o)).toBe(30);
  expect(clipFrame(13, o)).toBe(0); // looped
  expect(clipFrame(13, { ...o, loop: false })).toBe(89);
  expect(clipFrame(11, { ...o, rate: 0.5 })).toBe(15);
  expect(clipFrame(10, { ...o, offset: 1.5 })).toBe(45);
  expect(clipFrame(9, o)).toBe(60); // before the shot: the loop runs backwards
  expect(clipFrame(9, { ...o, loop: false })).toBe(0);
  // every sub-frame of a film frame shows one clip frame
  const n = clipFrame(11 + 1 / 30, o);
  for (const u of [-0.24, -0.1, 0.1, 0.24]) expect(clipFrame(11 + (1 + u) / 30, o)).toBe(n);
});

test('media paths: clips by extension, names without assets/ and extension', () => {
  expect(isVideo('assets/a.mp4')).toBe(true);
  expect(isVideo('assets/a.MOV')).toBe(true);
  expect(isVideo('assets/a.png')).toBe(false);
  expect(mediaName('assets/clip.mp4')).toBe('clip');
  expect(mediaName('./assets/demos/run 1.webm')).toBe('demos__run 1');
  expect(framePath('clip', 7)).toBe('media/clip/0007.jpg');
});

test('deviceLayout: inside the frame in every format; the screen inside the body', () => {
  for (const [W, H] of [[1920, 1080], [1080, 1920], [1080, 1080]]) {
    for (const kind of ['browser', 'phone'] as const) {
      const { body, screen } = deviceLayout(kind, { cx: 0.5, cy: 0.5, W, H });
      expect(body.x).toBeGreaterThanOrEqual(0);
      expect(body.y).toBeGreaterThanOrEqual(0);
      expect(body.x + body.w).toBeLessThanOrEqual(W);
      expect(body.y + body.h).toBeLessThanOrEqual(H);
      expect(screen.x).toBeGreaterThanOrEqual(body.x);
      expect(screen.y + screen.h).toBeLessThanOrEqual(body.y + body.h + 1e-9);
    }
  }
  const b = deviceLayout('browser', { cx: 0.5, cy: 0.5, W: 1920, H: 1080 });
  expect(b.screen.w / b.screen.h).toBeCloseTo(1.6, 9);
});

test('scrollAt: a number holds; [from, to] eases over its span', () => {
  expect(scrollAt(0.3, 5, [1, 2])).toBe(0.3);
  expect(scrollAt([0, 1], 0.5, [1, 3])).toBe(0);
  expect(scrollAt([0, 1], 2, [1, 3])).toBeCloseTo(0.5, 12);
  expect(scrollAt([0.2, 0.8], 9, [1, 3])).toBeCloseTo(0.8, 12);
});
