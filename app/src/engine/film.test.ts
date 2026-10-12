import { afterEach, expect, test } from 'bun:test';
import { AudioData } from './audio';
import { FORMATS, H, W, FPS, configure, filmUrl, resolveFormat } from './config';
import { applyFilm, defineFilm, filmDuration, filmTimeline, filmTransitions, lengthEnd, shotWindows } from './film';
import { HEX, LIN, ROLES, THEME, THEME_PRESETS, resolveTheme, setTheme } from './palette';
import { Scene } from './scene';
import { transitionEntries } from './transition';
import { F, fontDefs, resetFonts } from './type';
import { VO } from './vo';

class Blank extends Scene {
  render() {}
}

afterEach(() => {
  configure({ format: 'landscape', fps: 30, film: 'showcase' });
  setTheme('noir');
  resetFonts();
});

const grid = AudioData.grid({ duration: 120, bpm: 120 });

test('a synthetic grid: a beat every 60/bpm s, a downbeat every beatsPerBar beats', () => {
  expect(grid.beats.slice(0, 5)).toEqual([0, 0.5, 1, 1.5, 2]);
  expect(grid.downbeats.slice(0, 3)).toEqual([0, 2, 4]);
  expect(grid.beatAt(1.25)).toBeCloseTo(2.5, 9);
  expect(grid.barAt(3)).toBeCloseTo(1.5, 9);
  expect(grid.timeOfBar(2)).toBeCloseTo(4, 9);
  expect(grid.nearestDownbeat(4.9)).toBe(4);
  const waltz = AudioData.grid({ duration: 10, bpm: 90, offset: 0.2, beatsPerBar: 3 });
  expect(waltz.beatsPerBar).toBe(3);
  expect(waltz.downbeats[1]).toBeCloseTo(0.2 + 3 * (60 / 90), 6);
  expect(() => AudioData.grid({ duration: 10, bpm: 0 })).toThrow('bpm');
});

test('lengths: seconds, beats and bars, counted on the grid from wherever the shot starts', () => {
  expect(lengthEnd(2.5, 1)).toBe(3.5);
  expect(lengthEnd({ beats: 4 }, 0, grid)).toBeCloseTo(2, 9);
  expect(lengthEnd({ beats: 1 }, 0.25, grid)).toBeCloseTo(0.75, 9);
  expect(lengthEnd({ bars: 2 }, 0, grid)).toBeCloseTo(4, 9);
  expect(() => lengthEnd(0, 0)).toThrow('positive');
  expect(() => lengthEnd({ beats: 2 }, 0)).toThrow('beat grid');
});

test('shots play back to back; an absolute window resets the clock; ids are unique; every shot has a length', () => {
  const film = defineFilm({
    id: 'x',
    scenes: [
      { id: 'a', scene: Blank, length: 2 },
      { id: 'b', scene: Blank, length: { bars: 1 } },
      { id: 'c', scene: Blank, start: 10, end: 11.5 },
      { id: 'd', scene: Blank, length: { beats: 3 } },
    ],
  });
  expect(shotWindows(film, grid)).toEqual([
    { id: 'a', start: 0, end: 2 },
    { id: 'b', start: 2, end: 4 },
    { id: 'c', start: 10, end: 11.5 },
    { id: 'd', start: 11.5, end: 13 },
  ]);
  expect(() => shotWindows({ scenes: [{ id: 'a', scene: Blank, length: 1 }, { id: 'a', scene: Blank, length: 1 }] })).toThrow('twice');
  expect(() => shotWindows({ scenes: [{ id: 'a', scene: Blank }] })).toThrow('needs a length');
  expect(() => shotWindows({ scenes: [{ id: 'a', scene: Blank, start: 2, end: 1 }] })).toThrow('empty');
});

test("timing 'vo' takes every window from the voiceover's scenes", () => {
  const vo = new VO({ duration: 9, lines: [], acts: [], scenes: [{ id: 'one', act: 'I', start: 0, end: 4 }, { id: 'two', act: 'I', start: 4, end: 9 }] });
  expect(shotWindows({ timing: 'vo', scenes: [{ id: 'one', scene: Blank }, { id: 'two', scene: Blank }] }, grid, vo)).toEqual([
    { id: 'one', start: 0, end: 4 },
    { id: 'two', start: 4, end: 9 },
  ]);
  expect(() => shotWindows({ timing: 'vo', scenes: [{ id: 'three', scene: Blank }] }, grid, vo)).toThrow("no scene 'three'");
});

test('the timeline: shots with their params, then overlays over the whole film; the duration is the last shot end', async () => {
  const film = defineFilm({
    id: 'x',
    scenes: [{ id: 'a', scene: Blank, length: 1, params: { title: 'T' } }, { id: 'b', scene: () => Promise.resolve({ default: Blank }), length: 2 }],
    overlays: [{ id: 'cap', scene: Blank }],
  });
  const tl = filmTimeline(film, grid);
  expect(tl.map((e) => [e.id, e.start, e.end, e.kind ?? 'scene'])).toEqual([['a', 0, 1, 'scene'], ['b', 1, 3, 'scene'], ['cap', 0, 3, 'overlay']]);
  expect(tl[0]!.params).toEqual({ title: 'T', shot: 'a', n: 1 });
  expect((await tl[0]!.load()).default).toBe(Blank);
  expect((await tl[1]!.load()).default).toBe(Blank);
  expect(filmDuration(film, tl)).toBe(3);
  expect(filmDuration({ duration: 5 }, tl)).toBe(5);
  expect(() => filmTimeline({ id: 'x', scenes: [{ id: 'a', scene: Blank, length: 1 }], overlays: [{ id: 'a', scene: Blank }] })).toThrow('also a shot');
});

test('inline transitions come from the shot before; a kind alone takes the default window; they validate', () => {
  const film = defineFilm({
    id: 'x',
    scenes: [
      { id: 'a', scene: Blank, length: 2 },
      { id: 'b', scene: Blank, length: 2, transition: 'xfade' },
      { id: 'c', scene: Blank, length: 2, transition: { kind: 'whip', dir: [0, 1], pre: 0.1 } },
      { id: 'd', scene: Blank, length: 2, transition: 'cut' },
    ],
  });
  const specs = filmTransitions(film);
  expect(specs).toEqual([
    { kind: 'xfade', from: 'a', to: 'b', pre: 0.25, post: 0.25 },
    { kind: 'whip', dir: [0, 1], from: 'b', to: 'c', pre: 0.1, post: 0.25 },
    { kind: 'cut', from: 'c', to: 'd', pre: 0, post: 0 },
  ]);
  const shots = shotWindows(film, grid).map((w) => ({ ...w, act: '' }));
  expect(transitionEntries(specs, shots, []).map((e) => [e.id, e.cut, e.start, e.end])).toEqual([
    ['a-b', 2, 1.75, 2.25],
    ['b-c', 4, 3.9, 4.25],
    ['c-d', 6, 6, 6],
  ]);
  expect(() => filmTransitions({ scenes: [{ id: 'a', scene: Blank, length: 1, transition: 'xfade' }] })).toThrow('first');
});

test('captions: words timed as given, or spread over the line by length; lines take the shot on screen', () => {
  const vo = VO.fromCaptions([
    { text: 'Every frame is code.', start: 1, end: 3 },
    { text: 'Cut it.', start: 4, words: [{ w: 'Cut', start: 4, end: 4.2 }, { w: 'it.', start: 4.3, end: 4.6 }] },
  ], (t) => (t < 3.5 ? 'a' : 'b'));
  expect(vo.lines.map((l) => [l.text, l.scene, l.start])).toEqual([['Every frame is code.', 'a', 1], ['Cut it.', 'b', 4]]);
  const w = vo.lines[0]!.words;
  expect(w.map((x) => x.w)).toEqual(['Every', 'frame', 'is', 'code.']);
  expect(w[0]!.start).toBe(1);
  for (let i = 1; i < w.length; i++) expect(w[i]!.start).toBeGreaterThan(w[i - 1]!.end);
  expect(w[3]!.end).toBeLessThanOrEqual(3);
  expect(vo.lines[1]!.words[1]!.start).toBe(4.3);
  expect(vo.lineAt(4.1)?.text).toBe('Cut it.');
  expect(vo.duration).toBe(4.64);
  expect(() => VO.fromCaptions([{ text: 'x', start: 2, end: 1 }])).toThrow('not after');
  expect(VO.empty().words).toEqual([]);
});

test('formats: presets and sizes, even and positive; configure sets the live bindings', () => {
  expect(resolveFormat('vertical')).toEqual({ width: 1080, height: 1920 });
  expect(resolveFormat({ width: 800, height: 600 })).toEqual({ width: 800, height: 600 });
  expect(() => resolveFormat('widescreen')).toThrow('unknown format');
  expect(() => resolveFormat({ width: 801, height: 600 })).toThrow('even');
  for (const f of Object.values(FORMATS)) expect(f.width % 2 + f.height % 2).toBe(0);
  configure({ format: 'square', fps: 24, film: 'demo' });
  expect([W, H, FPS]).toEqual([1080, 1080, 24]);
  expect(filmUrl('data/vo.json')).toBe('films/demo/data/vo.json');
  expect(filmUrl('/abs.png')).toBe('/abs.png');
  expect(() => configure({ fps: 0 })).toThrow('fps');
});

test('themes: every preset defines every role; overrides extend a preset; setTheme updates HEX and LIN in place', () => {
  for (const [name, t] of Object.entries(THEME_PRESETS)) {
    const r = resolveTheme(name);
    for (const k of ROLES) expect(r[k]).toBe(t[k]);
  }
  const custom = resolveTheme({ extends: 'midnight', accent: '#ff0080' });
  expect(custom.accent).toBe('#ff0080');
  expect(custom.fg).toBe(THEME_PRESETS.midnight!.fg);
  expect(() => resolveTheme('neon')).toThrow('unknown theme');
  expect(() => resolveTheme({ accent: 'red' })).toThrow('#rrggbb');
  const hex = HEX, lin = LIN;
  setTheme('paper');
  expect(HEX).toBe(hex);
  expect(LIN).toBe(lin);
  expect(HEX.bg).toBe(THEME_PRESETS.paper!.bg);
  expect(THEME.kind).toBe('light');
});

test('applyFilm puts the format, fps, folder, theme and fonts in force', () => {
  applyFilm({ id: 'demo', format: 'portrait', fps: 25, theme: 'ember', fonts: { faces: [{ family: 'Serif-400', url: 'fonts/s.ttf', role: 'display', weight: 400 }], replace: ['display'] } });
  expect([W, H, FPS]).toEqual([1080, 1350, 25]);
  expect(HEX.accent).toBe(THEME_PRESETS.ember!.accent);
  expect(F.display(100, 800)).toBe('Serif-400');
  expect(fontDefs().find((d) => d.family === 'Serif-400')!.url).toBe('films/demo/fonts/s.ttf');
  // a second apply starts from the default faces again
  applyFilm({ id: 'demo' });
  expect(F.display(100, 800)).toBe('Bricolage-1000-800');
});
