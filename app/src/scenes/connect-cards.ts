// The faces of scene `connect`'s carousel (Plan 2 Task 23), as engine Panels (engine/panels.ts): the terminal the
// command is typed into, and the six cards that flip in after it, one a beat (spec §4 13, §11.1–11.3). Every string is
// connect.strings.json's, verbatim (the scene hands them over: copyOf); this module only cuts them into lines and tones.
//
// All seven are one size (a carousel's faces are), their code one size: the longest line, TypeScript's, sets the width.
// A card shorter than the face sits in its middle (the Panel's `scroll`, negative: rows pushed down), except the terminal,
// which fills from the top as a terminal does. The two agent cards are windows, as the terminal is (the MCP config, the
// install); the four SDK cards are plain cards whose name stands on them in 3D (connect.ts sets it, at NAME), its install
// line and its one line of setup under it.
//
// The ✔ is not the Panel's: the answer is drawn with a blank in its cell, and connect-light.ts's Tick draws the ✔ there,
// a moss pen stroke (its draw-on is the shot). What is on screen is the line verbatim.
import { lineEnd, panelLayout, type PanelInput, type PanelLine, type PanelSpan } from '../engine/panels';
import { BREAK, type Times } from './connect-time';

// ------------------------------------------------------------------------------------------------ the copy

const cps = (s: string) => Array.from(s);
const len = (s: string) => cps(s).length;

/** The copy, from connect.strings.json in its order: the command, `claude mcp list` and its answer, the MCP config, the
 * install and its hosts, and the four SDKs (each its language, install line and line of setup). */
export function copyOf(strings: readonly string[]) {
  let at = 0;
  const take = (n: number) => strings.slice(at, (at += n));
  const [cmd1, cmd2, cmd3, list, connected] = take(5) as [string, string, string, string, string];
  const mcp = take(9);
  const [install, hosts] = take(2) as [string, string];
  const sdks = (['ts', 'python', 'go', 'rust'] as const).map((hl) => {
    const [lang, line, setup] = take(3) as [string, string, string];
    return { lang, install: line, setup, hl };
  });
  if (at !== strings.length) throw new Error(`connect: connect.strings.json has ${strings.length} strings, the scene takes ${at}`);
  const tick = cps(connected).indexOf('✔');
  if (tick < 0) throw new Error('connect: the answer has no ✔');
  return {
    cmd: [cmd1, cmd2, cmd3] as const, list, connected, mcp, install, hosts, sdks,
    /** The ✔'s cell in the answer (a code point index), and the answer as the Panel draws it: a blank in that cell. */
    tick,
    connectedBlank: cps(connected).map((ch, i) => (i === tick ? ' ' : ch)).join(''),
  };
}
export type Copy = ReturnType<typeof copyOf>;

/** The code points [from, to) of the first `sub` in `s` at or after code point `after`. */
export function runOf(s: string, sub: string, after = 0): [number, number] {
  const c = cps(s), n = len(sub);
  for (let i = after; i + n <= c.length; i++) if (c.slice(i, i + n).join('') === sub) return [i, i + n];
  throw new Error(`connect: no "${sub}" in "${s}"`);
}

// ------------------------------------------------------------------------------------------------ the faces (panel px)

/** Code size (px per em) on every face. */
export const SIZE = 34;

/**
 * Every face's size (panel px): wide enough for the longest line (TypeScript's setup) with the side padding and a
 * margin, tall enough for the MCP config's nine rows under a window's title bar.
 */
export function faceOf(copy: Copy) {
  const card = panelLayout({ kind: 'card', size: SIZE, title: 'x', lines: [] });
  const widest = Math.max(...copy.sdks.map((s) => len(s.setup)), ...copy.mcp.map(len), len(copy.connected), len(copy.cmd[0]) + 2);
  const json = panelLayout({ kind: 'json', size: SIZE, lines: copy.mcp.map(() => ({})) });
  return {
    w: Math.ceil((2 * card.padX + widest * card.adv) / 10) * 10 + 40,
    h: Math.ceil(json.bar + json.padTop + copy.mcp.length * json.lineH + json.padBottom + 24),
  };
}

/**
 * An SDK card's name, set in 3D on the card (Bricolage 600, extruded; connect.ts builds it): its size (px per em), its
 * cap height (em: Bricolage's), and the room between its baseline and the top of the first code row (px: its
 * descenders fall in it).
 */
export const NAME = { px: 132, cap: 0.66, gap: 60 };

/**
 * Where an SDK card's name stands (its origin: the code's left edge, its baseline, px from the card's top left) and how
 * far its rows are pushed down (a negative scroll) so the name and the three rows under it sit in the middle of a card
 * `h` tall.
 */
export function sdkLayout(h: number) {
  const g = panelLayout({ kind: 'card', size: SIZE, lines: [{}, {}, {}] });
  const cap = NAME.cap * NAME.px;
  const base = (h - (cap + NAME.gap + 3 * g.lineH)) / 2 + cap;
  return { x: g.textX, base, scroll: -(base + NAME.gap - g.bar - g.padTop) / g.lineH };
}

/** Rows to push a face's rows down by so they sit in the middle of a face `h` tall (a negative scroll). */
function centred(spec: Pick<PanelInput, 'kind' | 'title' | 'lines'>, h: number): number {
  const g = panelLayout({ ...spec, size: SIZE });
  const free = h - g.bar - g.padTop - g.padBottom - spec.lines.length * g.lineH;
  return -Math.max(0, free / 2) / g.lineH;
}

/** The terminal's rows: the command (three lines), the blank its Enter leaves, `claude mcp list`, its answer, a prompt. */
export const ROW = { cmd: [0, 1, 2] as const, list: 4, out: 5, prompt: 6 } as const;

/**
 * The terminal's lines, timed from the clock: the command types from "One" at an even pace, a breath at each `\`, its
 * last key just before Enter; Enter on the downbeat opens a blank row and the prompt; `claude mcp list` types in the
 * pause; its answer prints whole (the ✔ drawn after, by the Tick) and the prompt comes back.
 */
export function terminalLines(copy: Copy, T: Pick<Times, 'type' | 'enter' | 'list' | 'out'>): PanelLine[] {
  // keys typed: every character but the first of each line (it lands on `at`)
  const keys = copy.cmd.reduce((n, s) => n + len(s) - 1, 0);
  const rate = keys / (T.type.end - T.type.at - BREAK * (copy.cmd.length - 1));
  const lines: PanelLine[] = [];
  let t = T.type.at;
  for (const text of copy.cmd) {
    const l: PanelLine = { text, kind: 'cmd', at: t, cps: rate };
    lines.push(l);
    t = lineEnd(l) + BREAK;
  }
  lines.push({ text: '', kind: 'out', at: T.enter });
  lines.push({ text: copy.list, kind: 'cmd', at: T.list.at, cps: (len(copy.list) - 3) / (T.list.end - T.list.at) });
  lines.push({ text: copy.connectedBlank, kind: 'out', at: T.out });
  lines.push({ text: '', kind: 'cmd', at: Infinity }); // the prompt, back: never typed into
  return lines;
}

export function terminalSpec(copy: Copy, T: Pick<Times, 'type' | 'enter' | 'list' | 'out'>): PanelInput {
  const face = faceOf(copy);
  return { kind: 'terminal', w: face.w, h: face.h, size: SIZE, lines: terminalLines(copy, T) };
}

/**
 * `gitloom install codex --write`, and the hosts it installs into as a row of chips under it (a band of light behind
 * each name), codex lit: the one the command names.
 */
function installLines(copy: Copy): PanelLine[] {
  const { hosts, install } = copy;
  const spans: PanelSpan[] = [], marks: { from: number; to: number; alpha: number }[] = [];
  let from = 0;
  for (const h of hosts.split(' · ')) {
    const [a, b] = runOf(hosts, h, from);
    const lit = h === 'codex';
    spans.push({ from: a, to: b, tone: lit ? 'kw' : 'str' });
    marks.push({ from: Math.max(0, a - 0.45), to: Math.min(len(hosts), b + 0.45), alpha: lit ? 0.16 : 0.06 });
    from = b;
  }
  cps(hosts).forEach((ch, i) => ch === '·' && spans.push({ from: i, to: i + 1, tone: 'punc' }));
  const [c0, c1] = runOf(install, 'codex');
  return [
    { text: install, kind: 'cmd', spans: [{ from: c0, to: c1, tone: 'kw' }] },
    { text: '', kind: 'out' },
    { text: hosts, kind: 'out', spans, highlight: marks.map((m) => ({ ...m, tone: 'bone' as const })) },
  ];
}

/**
 * An SDK card's rows: its install line, quiet, and the one line of setup under it (its name stands above, in 3D). The setup
 * line's comment is the point (`← the only setup`, `reads GITLOOM_API_KEY`): its words come up from the comment's faint
 * tone to read, its arrow in blood, the accent.
 */
function sdkLines(sdk: Copy['sdks'][number]): PanelLine[] {
  const [, m1] = runOf(sdk.setup, sdk.hl === 'python' ? '#' : '//');
  const spans: PanelSpan[] = [{ from: m1, to: len(sdk.setup), tone: 'str' }];
  if (sdk.setup.includes('←')) {
    const [a0, a1] = runOf(sdk.setup, '←');
    spans.push({ from: a0, to: a1, tone: 'blood' });
  }
  return [
    { text: sdk.install, spans: [{ from: 0, to: len(sdk.install), tone: 'com' }] },
    { text: '' },
    { text: sdk.setup, spans },
  ];
}

/** The six cards, in the order they flip in: the MCP config, `gitloom install`, then TypeScript, Python, Go and Rust. */
export function cardSpecs(copy: Copy): PanelInput[] {
  const { w, h } = faceOf(copy);
  const json: PanelInput = { kind: 'json', w, h, size: SIZE, lang: 'json', lines: copy.mcp.map((text) => ({ text })) };
  const install: PanelInput = { kind: 'terminal', w, h, size: SIZE, lines: installLines(copy) };
  const sdks = copy.sdks.map((s): PanelInput => ({ kind: 'card', w, h, size: SIZE, lang: s.hl, lines: sdkLines(s), scroll: sdkLayout(h).scroll }));
  return [...[json, install].map((spec) => ({ ...spec, scroll: centred(spec, h) })), ...sdks];
}
