import { describe, expect, test } from 'bun:test';
import { LIN } from './palette';
import { DEFAULT_POST, isGraded, type PostParams } from './post';
import { LOOK, bloomKey } from './look';
import { LETTERBOX_MAX, LOOKS, LOOK_KEYS, NEUTRAL_GRADE, filmLookPost, letterboxAspect, letterboxBar, lookPost, shotLookPost } from './looks';
import { filmTimeline, type FilmSpec } from './film';
import { AudioData } from './audio';
import type { Scene } from './scene';

/** A frame's post as the engine resolves it: DEFAULT_POST, the film's look and post, the entry's, the scene's. */
const resolve = (film: Pick<FilmSpec, 'look' | 'post'>, entry?: Partial<PostParams>, scene?: Partial<PostParams>): PostParams =>
  ({ ...DEFAULT_POST, ...filmLookPost(film), ...(entry ?? {}), ...(scene ?? {}) }) as PostParams;

describe('the grade is neutral by default', () => {
  test('DEFAULT_POST carries the neutral grade and the film look, and grades nothing', () => {
    expect(DEFAULT_POST).toMatchObject(NEUTRAL_GRADE);
    expect(DEFAULT_POST).toMatchObject(LOOK);
    expect(isGraded(DEFAULT_POST)).toBe(false);
    expect(isGraded({ ...DEFAULT_POST, contrast: 1.1 })).toBe(true);
    // letterbox is drawn by its bars, not the grade: off at 0
    expect(letterboxBar(DEFAULT_POST.letterbox, 1920, 1080)).toBe(0);
  });
  test("a film with no look renders as before: 'film' over DEFAULT_POST changes nothing", () => {
    expect(resolve({})).toEqual(DEFAULT_POST);
    expect(lookPost()).toEqual(LOOKS.film);
  });
});

describe('presets', () => {
  test('each sets every look key and nothing else', () => {
    for (const [name, v] of Object.entries(LOOKS)) {
      expect(Object.keys(v).sort()).toEqual([...LOOK_KEYS].sort());
      for (const k of ['fade', 'flash', 'shake', 'zoom', 'hud', 'frame', 'paper', 'invert']) expect(k in v, `${name}.${k}`).toBe(false);
    }
  });
  test('only accents glow in every look: fg never blooms, an accent at the glow level does', () => {
    for (const v of Object.values(LOOKS)) {
      for (const level of [1, 2, 4, 40]) expect(bloomKey(LIN.fg.map((x) => (x * level) / Math.max(...LIN.fg)) as [number, number, number], v.bloomThreshold, v.bloomKnee)).toBe(0);
      expect(bloomKey(LIN.accent.map((x) => (x * 3) / Math.max(...LIN.accent)) as [number, number, number], v.bloomThreshold, v.bloomKnee)).toBeGreaterThan(0.5);
    }
  });
  test('cinematic letterboxes at 2.39; an unknown look names the presets', () => {
    expect(LOOKS.cinematic.letterbox).toBe(2.39);
    expect(() => lookPost('vaporwave')).toThrow(/unknown look 'vaporwave'.*cinematic/);
  });
});

describe('resolution order (looks.ts header)', () => {
  test('film look < film post < shot look (+ film post again) < shot post < scene', () => {
    const film = { look: 'cinematic', post: { grain: 0.2 } };
    expect(resolve(film).letterbox).toBe(2.39);
    expect(resolve(film).grain).toBe(0.2);
    // a shot's look replaces the film's whole look, the film's post still on top
    const shot = shotLookPost(film, { id: 's', look: 'clean', post: { vignette: 0.9 } })!;
    const p = resolve(film, shot);
    expect(p.letterbox).toBe(0);
    expect(p.bloom).toBe(LOOKS.clean.bloom);
    expect(p.grain).toBe(0.2);
    expect(p.vignette).toBe(0.9);
    // the scene's own overrides win over all of it
    expect(resolve(film, shot, { vignette: 0.1, letterbox: 1.85 })).toMatchObject({ vignette: 0.1, letterbox: 1.85 });
    // a shot without a look keeps the film's: its post alone
    expect(shotLookPost(film, { id: 's', post: { zoom: 1.1 } })).toEqual({ zoom: 1.1 });
    expect(shotLookPost(film, { id: 's' })).toBeUndefined();
  });
  test('filmTimeline puts a shot\'s look on its entry, and names the shot of an unknown one', () => {
    class S { render() {} }
    const scene = S as unknown as new () => Scene;
    const film = { id: 'f', look: 'neon', post: { ca: 0 }, scenes: [{ id: 'a', scene, length: 1 }, { id: 'b', scene, length: 1, look: 'retro' }] } as unknown as FilmSpec;
    const [a, b] = filmTimeline(film, AudioData.grid({ duration: 4 }));
    expect(a!.post).toBeUndefined();
    expect(b!.post).toMatchObject({ scanlines: LOOKS.retro.scanlines, ca: 0 });
    const bad = { ...film, scenes: [{ id: 'x', scene, length: 1, look: 'sepia' }] } as unknown as FilmSpec;
    expect(() => filmTimeline(bad)).toThrow(/shot x: unknown look 'sepia'/);
  });
});

describe('letterbox', () => {
  test('2.39 in 16:9 covers 12.8% of the height each side; a frame already that wide, none', () => {
    expect(letterboxBar(2.39, 1920, 1080)).toBeCloseTo((1080 - 1920 / 2.39) / 2 / 1080, 12);
    expect(letterboxBar(2.39, 1920, 1080)).toBeCloseTo(0.1281, 4);
    expect(letterboxBar(1.5, 1920, 1080)).toBe(0);
    expect(letterboxBar(2.39, 1920, 804)).toBeLessThan(0.001);
    expect(letterboxBar(0, 1920, 1080)).toBe(0);
  });
  test('vertical and square frames get cinematic bars, never a slot: at most 13% of the short side', () => {
    expect(letterboxBar(2.39, 1080, 1920) * 1920).toBeCloseTo(LETTERBOX_MAX * 1080, 9);
    expect(letterboxBar(2.39, 1080, 1080) * 1080).toBeCloseTo(LETTERBOX_MAX * 1080, 9);
  });
  test('letterboxAspect inverts it (for animating bars), and bar 0 is the frame itself', () => {
    for (const [w, h] of [[1920, 1080], [1080, 1920], [1080, 1080]] as const) {
      for (const bar of [0, 0.03, 0.06]) expect(letterboxBar(letterboxAspect(bar, w, h), w, h)).toBeCloseTo(bar, 9);
    }
    expect(letterboxAspect(0, 1920, 1080)).toBeCloseTo(1920 / 1080, 12);
  });
});
