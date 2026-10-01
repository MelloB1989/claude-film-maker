import { expect, test } from 'bun:test';
import { Panel, lineEnd, panelLayout, tokenize, type Lang, type PanelLine, type PanelSpec } from './panels';
import { rgba } from './palette';
import { F } from './type';

// Expected values are counted by hand from the strings (character positions, cps arithmetic), never from panels.ts.

const cls = (line: string, lang: Lang, text: string) => tokenize(line, lang).find((t) => t.text === text)?.cls;

test('tokenize ts: `const` and `new` are keywords and the // tail is one comment token', () => {
  const line = 'const memory = new Gitloom()  // reads GITLOOM_API_KEY';
  const toks = tokenize(line, 'ts');
  expect(cls(line, 'ts', 'const')).toBe('kw');
  expect(cls(line, 'ts', 'new')).toBe('kw');
  expect(cls(line, 'ts', 'memory')).toBe('id');
  expect(cls(line, 'ts', 'Gitloom')).toBe('id');
  expect(toks[toks.length - 1]).toEqual({ text: '// reads GITLOOM_API_KEY', cls: 'com' });
});

test('tokenize bash: a line starting `$ ` opens with a prompt token; a `$` elsewhere is not one', () => {
  const toks = tokenize('$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2', 'bash');
  expect(toks[0]).toEqual({ text: '$', cls: 'prompt' });
  expect(toks.filter((t) => t.cls === 'prompt')).toHaveLength(1);
  expect(tokenize('claude mcp add gitloom --scope user \\', 'bash').some((t) => t.cls === 'prompt')).toBe(false);
  expect(tokenize('echo $HOME', 'bash').some((t) => t.cls === 'prompt')).toBe(false);
});

test('tokenize bash: # starts a comment only at the start of a word, and quotes are strings', () => {
  const curl = 'curl -fsSL https://gitloom.cloud/install.sh | sh   # current: 0.3.0';
  const toks = tokenize(curl, 'bash');
  expect(toks[toks.length - 1]).toEqual({ text: '# current: 0.3.0', cls: 'com' });
  // a # inside a word (a path's anchor) is not a comment
  expect(tokenize('open facts/people/user.md#editor', 'bash').some((t) => t.cls === 'com')).toBe(false);
  expect(cls('gitloom search "where does maya live"', 'bash', '"where does maya live"')).toBe('str');
});

test('tokenize: a check mark is always its own `ok` token (JetBrains Mono has no ✔: it is drawn as a path)', () => {
  const line = 'gitloom: npx -y @gitloomhq/mcp - ✔ Connected';
  for (const lang of ['plain', 'bash', 'md'] as Lang[]) {
    const oks = tokenize(line, lang).filter((t) => t.cls === 'ok');
    expect(oks).toEqual([{ text: '✔', cls: 'ok' }]);
  }
});

test('tokenize json: keys, string values and numbers', () => {
  expect(cls('"mode": "raw"', 'json', '"mode"')).toBe('id');
  expect(cls('"mode": "raw"', 'json', '"raw"')).toBe('str');
  expect(cls('"millis": 82', 'json', '82')).toBe('num');
  expect(cls('      "args": ["-y", "@gitloomhq/mcp"],', 'json', '"@gitloomhq/mcp"')).toBe('str');
});

test('tokenize yaml and md: keys, numbers, comments, headings', () => {
  expect(cls('confidence: 0.9', 'yaml', 'confidence')).toBe('id');
  expect(cls('confidence: 0.9', 'yaml', '0.9')).toBe('num');
  expect(tokenize('# facts/people/user.md', 'yaml')).toEqual([{ text: '# facts/people/user.md', cls: 'com' }]);
  expect(cls('## Editor', 'md', 'Editor')).toBe('kw');
  expect(cls('Uses neovim. Has since 2019.', 'md', '2019')).toBeUndefined(); // prose stays one run, no number picked out
});

test('tokenize python, go and rust: comments, strings and keywords', () => {
  const py = 'openai = gitloom.wrap(OpenAI(), memory)  # ← the only setup';
  expect(tokenize(py, 'python').at(-1)).toEqual({ text: '# ← the only setup', cls: 'com' });
  const go = 'client := gitloom.New("") // reads GITLOOM_API_KEY';
  expect(tokenize(go, 'go').at(-1)).toEqual({ text: '// reads GITLOOM_API_KEY', cls: 'com' });
  expect(cls(go, 'go', '""')).toBe('str');
  expect(cls('func main() {', 'go', 'func')).toBe('kw');
  const rs = 'let client = Client::new(""); // reads GITLOOM_API_KEY';
  expect(cls(rs, 'rust', 'let')).toBe('kw');
  expect(cls(rs, 'rust', '""')).toBe('str');
  expect(tokenize(rs, 'rust').at(-1)).toEqual({ text: '// reads GITLOOM_API_KEY', cls: 'com' });
});

test('tokenize is lossless: the tokens put back together are the line, in every language', () => {
  const lines: [string, Lang][] = [
    ['claude mcp add gitloom --scope user \\', 'bash'],
    ['  -e GITLOOM_API_KEY=gl_live_... \\', 'bash'],
    ['  -- npx -y @gitloomhq/mcp', 'bash'],
    ['echo "Maya moved to Lisbon in March 2026." | gitloom write -p facts/people/maya.md --tags person -m "maya moved"', 'bash'],
    ["it's an unterminated 'quote", 'bash'],
    ['const openai = withMemory(new OpenAI(), { memory }) // ← the only setup', 'ts'],
    ['const s = `tpl ${x}` /* note */ + 0x1f + 1_000.5e3', 'ts'],
    ['      "env": { "GITLOOM_API_KEY": "gl_live_..." }', 'json'],
    ['tags: [user, prefs]', 'yaml'],
    ['updated: 2026-07-26', 'yaml'],
    ['Works with [[facts/orgs/acme.md]].', 'md'],
    ['let client = Client::new(""); // reads GITLOOM_API_KEY', 'rust'],
    ["x = f'{a}' + r\"raw\"  # tail", 'python'],
    ['gitloom: npx -y @gitloomhq/mcp - ✔ Connected', 'plain'],
    ['', 'ts'],
  ];
  for (const [line, lang] of lines) {
    const toks = tokenize(line, lang);
    expect(toks.map((t) => t.text).join('')).toBe(line);
    for (const t of toks) expect(t.text.length).toBeGreaterThan(0);
  }
});

// --------------------------------------------------------------------------------------------------- revealed

const panel = (lines: PanelLine[], kind: PanelSpec['kind'] = 'editor') => new Panel({ kind, w: 1200, h: 600, lines });
const ALPHA = 'abcdefghijklmnopqrst'; // 20 characters
/** A row opens over the 0.14 s before its line starts: a start this far after a frame time has its row begin to open 3 ms before the frame. */
const OPEN_EDGE = 0.14 - 0.003;

test('revealed: a line without `at` is shown whole at any time', () => {
  const p = panel([{ text: 'tier: facts' }, { text: '' }]);
  expect(p.revealed(-5)).toEqual([11, 0]);
  expect(p.revealed(0)).toEqual([11, 0]);
  expect(p.revealed(100)).toEqual([11, 0]);
});

test('revealed: a typed line shows its first character at `at`, then one more every 1/cps seconds', () => {
  const p = panel([{ text: ALPHA, at: 1, cps: 10 }]);
  expect(p.revealed(0)).toEqual([0]);
  expect(p.revealed(0.9)).toEqual([0]);
  expect(p.revealed(1)).toEqual([1]);
  expect(p.revealed(1.5)).toEqual([6]); // 0.5 s at 10 cps: five more after the first
  expect(p.revealed(2.8)).toEqual([19]);
  expect(p.revealed(2.9)).toEqual([20]); // the last one at 1 + 19/10
  expect(p.revealed(10)).toEqual([20]);
  expect(lineEnd({ text: ALPHA, at: 1, cps: 10 })).toBeCloseTo(2.9, 9);
});

test('revealed: a line with `at` and no cps appears whole at `at`', () => {
  const out = '1 file changed, 2 insertions(+), 2 deletions(-)'; // 47 characters
  const p = panel([{ text: out, kind: 'out', at: 2 }]);
  expect(p.revealed(1.9)).toEqual([0]);
  expect(p.revealed(2)).toEqual([47]);
  expect(lineEnd({ text: out, at: 2 })).toBe(2);
});

test('revealed: monotonic in t and capped at each line length', () => {
  const lines: PanelLine[] = [
    { text: ALPHA, at: 0.2, cps: 37 },
    { text: 'claude mcp list', at: 0.9, cps: 12.5 },
    { text: 'gitloom: npx -y @gitloomhq/mcp - ✔ Connected', kind: 'out', at: 2.35 },
    { text: 'static' },
    { text: 'Uses neovim. Has since 2019.', kind: 'add', at: 1.1, cps: 60 },
  ];
  const lens = [20, 15, 44, 6, 28];
  for (const kind of ['terminal', 'editor', 'chat'] as const) {
    const p = panel(lines, kind);
    let prev = p.revealed(-1);
    for (let t = -1; t <= 6; t += 0.005) {
      const r = p.revealed(t);
      r.forEach((n, i) => {
        expect(n).toBeGreaterThanOrEqual(prev[i]!);
        expect(n).toBeLessThanOrEqual(lens[i]!);
        expect(Number.isInteger(n)).toBe(true);
      });
      prev = r;
    }
    expect(prev).toEqual(lens);
  }
});

test('revealed: one state per output frame, however the shutter samples it', () => {
  // the 7th character is due at exactly 1.6 s, frame 48: every sub-frame of frame 48 shows it (sampling raw time,
  // the early half of the shutter would not, and the frame would blend a half-typed character); frame 47 does not
  const p = panel([{ text: ALPHA, at: 1, cps: 10 }]);
  const frame = 1 / 30;
  for (const u of [-0.49, -0.25, 0, 0.25, 0.49]) expect(p.revealed(1.6 + u * frame)).toEqual([7]);
  for (const u of [-0.25, 0, 0.25]) expect(p.revealed(1.6 - frame + u * frame)).toEqual([6]);
});

test('revealed: a terminal shows a `$ ` prompt whole once it is ready for input, then types the rest', () => {
  // '$ claude mcp list' is 17 characters: the prompt (2) and the command (15)
  const p = panel([{ text: '$ claude mcp list', kind: 'cmd', at: 1, cps: 20 }], 'terminal');
  expect(p.revealed(0)).toEqual([2]); // the first prompt waits from the start
  expect(p.revealed(1)).toEqual([3]);
  expect(p.revealed(1.5)).toEqual([13]); // 2 + 1 + 0.5 s × 20
  expect(p.revealed(9)).toEqual([17]);
  // the next prompt appears when the output before it is shown, not before
  const q = panel([
    { text: 'gitloom: npx -y @gitloomhq/mcp - ✔ Connected', kind: 'out', at: 1 },
    { text: '$ claude mcp list', kind: 'cmd', at: 3, cps: 20 },
  ], 'terminal');
  expect(q.revealed(0.5)).toEqual([0, 0]);
  expect(q.revealed(1)).toEqual([44, 2]);
  expect(q.revealed(3)).toEqual([44, 3]);
  // on a line that isn't typed input, `$ ` is ordinary text and waits for `at` like the rest
  expect(panel([{ text: '$ claude mcp list', kind: 'out', at: 1, cps: 20 }], 'terminal').revealed(0)).toEqual([0]);
});

test('struck: a deleted line keeps its text; `at` and cps time the strike through it', () => {
  const p = panel([
    { text: 'Uses VS Code.', kind: 'del' }, // 13 characters, struck from the start
    { text: 'confidence: 0.6', kind: 'del', at: 1, cps: 30 }, // 15 characters
  ]);
  expect(p.revealed(0)).toEqual([13, 15]);
  expect(p.revealed(5)).toEqual([13, 15]);
  expect(p.struck(0)).toEqual([13, 0]);
  expect(p.struck(1)).toEqual([13, 0]);
  const mid = p.struck(1.2); // 0.2 s at 30 cps: the strike runs smoothly through 6 of the 15 characters
  expect(mid[0]).toBe(13);
  expect(mid[1]!).toBeCloseTo(6, 6);
  expect(p.struck(3)).toEqual([13, 15]);
});

test('the mesh is a plane of w/1000 by h/1000 world units, built without a DOM', () => {
  const p = new Panel({ kind: 'terminal', w: 1240, h: 420, lines: [] });
  p.mesh.geometry.computeBoundingBox();
  const bb = p.mesh.geometry.boundingBox!;
  expect(bb.max.x - bb.min.x).toBeCloseTo(1.24, 6); // positions are float32
  expect(bb.max.y - bb.min.y).toBeCloseTo(0.42, 6);
  expect(bb.max.z - bb.min.z).toBe(0);
  p.dispose();
});

// ------------------------------------------------------------------------------------------------------ repaint

/** Everything paint() reads from a frame. */
const paintInputs = (p: Panel, t: number) => {
  const fr = p.frame(t);
  return { key: fr.key, paint: JSON.stringify({ st: fr.st, top: fr.top, num: fr.num, started: fr.started, cursor: fr.cursor, checks: fr.checks, marks: fr.marks }) };
};

test('two frames with the same repaint key paint the same: rows, numbers, prompts, cursor and checks', () => {
  // a row that starts to open 3 ms before a frame is open 1e-4 on it (smootherstep of 0.021: 10 x 0.021^3), a sliver
  // no rounded key can tell from shut, and the row below it moves by 0.004 px; so do rows whose strike or scroll moves
  const specs: PanelSpec[] = [
    { kind: 'editor', w: 900, h: 400, lines: [{ text: 'tier: facts' }, { text: 'opens', kind: 'out', at: 1 + OPEN_EDGE }, { text: 'below' }] },
    { kind: 'editor', w: 900, h: 400, gutter: 'diff', lines: [{ text: 'Uses VS Code.', kind: 'del', at: 0.6, cps: 40 }, { text: ALPHA, kind: 'add', at: 1.05, cps: 30 }] },
    { kind: 'terminal', w: 900, h: 300, lines: [
      { text: '$ claude mcp list', kind: 'cmd', at: 0.5, cps: 25 }, { text: 'gitloom: ✔ Connected', kind: 'out', at: 1.4 + OPEN_EDGE },
      { text: 'ls', kind: 'cmd', at: 2.2, cps: 12 }, { text: 'a b c', kind: 'out', at: 3.11 }, { text: 'd e f', kind: 'out', at: 3.9 },
      { text: 'g h i', kind: 'out', at: 4.7 + OPEN_EDGE }, { text: '', kind: 'cmd', at: Infinity },
    ] },
    { kind: 'chat', w: 900, h: 300, lines: [{ text: 'what editor?', kind: 'cmd', at: 0.4, cps: 24 }, { text: '' }, { text: 'neovim.', kind: 'out', at: 1.8 + OPEN_EDGE, cps: 14 }] },
  ];
  for (const spec of specs) {
    const p = new Panel(spec), seen = new Map<string, string>();
    for (let f = -30; f <= 240; f++) {
      const { key, paint } = paintInputs(p, f / 30);
      const had = seen.get(key);
      if (had === undefined) seen.set(key, paint);
      else expect({ kind: spec.kind, f, paint }).toEqual({ kind: spec.kind, f, paint: had });
    }
  }
});

test('a chat\'s user turn opens its row as its text starts; a terminal\'s typed input opens when it is ready for input', () => {
  const lines: PanelLine[] = [
    { text: 'first answer', kind: 'out', at: 1, cps: 20 }, // 12 characters: complete at 1 + 11/20 = 1.55
    { text: 'and my question', kind: 'cmd', at: 4, cps: 20 },
    { text: 'reply', kind: 'out', at: 6 },
  ];
  // the chat: at 3 s the answer is done and the question a second away, and its row stays shut until it is due; it
  // opens over the 0.14 s before 4 (not at 1.55, pushing the reply down to sit empty for 2.5 s)
  const chat = new Panel({ kind: 'chat', w: 900, h: 400, lines });
  expect(chat.frame(3).st[1]!.open).toBe(0);
  expect(chat.frame(3.9).st[1]!.open).toBeGreaterThan(0);
  expect(chat.frame(3.9).st[1]!.open).toBeLessThan(1);
  expect(chat.frame(4).st[1]!.open).toBe(1);
  expect(chat.frame(3).top[2]).toBe(chat.frame(3).top[1]); // the reply's row sits under the answer's
  // the terminal: the command's prompt waits from the moment the answer is complete
  const term = new Panel({ kind: 'terminal', w: 900, h: 400, lines });
  expect(term.frame(1.5).st[1]!.open).toBeLessThan(1);
  expect(term.frame(1.55).st[1]!.open).toBe(1);
  expect(term.frame(3).st[1]!.open).toBe(1);
});

test('a check mark in a row scrolled up under the title bar leaves the shader\'s slots for the canvas, drawn in its clip', () => {
  // 28 px code: rows of 45 px (1.6 em, to the half px), 278 px of them under the 52 px bar (372 - 52 - 20 - 22); with 7
  // rows open the terminal scrolls 315 - 278 = 37 px and the ✔ row's top goes from 72 to 35, its cell's baseline at
  // top + 22.5 + 0.365 x 28
  const lines: PanelLine[] = [{ text: '✔ Connected', kind: 'out', at: 0 }, ...[1, 2, 3, 4, 5, 6].map((k): PanelLine => ({ text: `line ${k}`, kind: 'out', at: k }))];
  const p = new Panel({ kind: 'terminal', w: 900, h: 372, lines });
  const six = p.frame(5.5), seven = p.frame(6);
  expect(six.top[0]).toBe(72);
  expect(six.checks).toEqual({ slot: [[28, 72 + 22.5 + 10.22]], canvas: [] });
  expect(seven.top[0]).toBe(35);
  expect(seven.checks).toEqual({ slot: [], canvas: [[28, 35 + 22.5 + 10.22]] });
  // a fifth check has no slot either, below the bar or not
  const five = new Panel({ kind: 'terminal', w: 900, h: 372, lines: [{ text: '✔ ✔ ✔ ✔ ✔', kind: 'out' }] }).frame(0);
  expect(five.checks.slot).toHaveLength(4);
  expect(five.checks.canvas).toHaveLength(1);
});

// ----------------------------------------------------------------------------------------------------- geometry

// The layout, counted by hand from the chrome's design sizes at 28 px code (a 52 px bar, 20 px above the first row,
// 22 below the last, 28 px side padding, 22 px after the line numbers), scaled by size/28 and rounded to whole px;
// rows 1.6 em to the half px; a mono cell 0.6 em; a row's baseline its top + half a row + 0.365 em (the cap height
// centred in it).

test('geometry: the layout getters (code size, advance, row height) at 28, 30 and 24 px', () => {
  const t28 = new Panel({ kind: 'terminal', w: 1120, h: 232, lines: [] });
  expect([t28.layout.size, t28.adv, t28.lineH]).toEqual([28, 16.8, 45]); // 1.6 x 28 = 44.8, to the half px
  expect(t28.layout.bar).toBe(52);
  expect(t28.layout.textX).toBe(28);
  const t30 = new Panel({ kind: 'terminal', w: 900, h: 300, size: 30, lines: [] });
  expect([t30.adv, t30.lineH, t30.layout.bar, t30.layout.padTop, t30.layout.textX]).toEqual([18, 48, 56, 21, 30]);
  // an editor at 24 px with a numbers gutter (two digits) and a diff's sign column (two cells): 24 + 2 x 14.4 + 19 + 2 x 14.4
  const ed = new Panel({ kind: 'editor', w: 640, h: 687, size: 24, gutter: 'numbers', lines: [{ text: 'a' }, { text: 'b', kind: 'del' }] });
  expect(ed.lineH).toBe(38.5); // 1.6 x 24 = 38.4
  expect(ed.adv).toBeCloseTo(14.4, 12);
  expect([ed.layout.bar, ed.layout.padTop, ed.layout.padBottom, ed.layout.padX]).toEqual([45, 17, 19, 24]);
  expect(ed.layout.numW).toBeCloseTo(47.8, 12);
  expect(ed.layout.signW).toBeCloseTo(28.8, 12);
  expect(ed.layout.textX).toBeCloseTo(100.6, 12);
});

test('geometry: panelLayout is the layout a panel would have, before there is one (no w or h needed)', () => {
  const spec = { kind: 'editor', size: 24, gutter: 'numbers', lines: [{ text: 'a' }, { text: 'b', kind: 'add' }] } as const;
  const L = panelLayout(spec);
  expect(L).toEqual(new Panel({ ...spec, w: 640, h: 400 }).layout);
  // what it reads from the lines: a sign column only with a diff in them, a gutter as wide as the last number
  expect(panelLayout({ kind: 'editor', lines: [{ text: 'a' }] }).signW).toBe(0);
  const hundred = panelLayout({ kind: 'editor', lines: Array.from({ length: 100 }, () => ({ text: '' })) });
  expect(hundred.numW).toBeCloseTo(3 * 16.8 + 22, 12);
});

test('geometry: rowTop without t is the layout with every row above open: the bar, the padding, rows of lineH', () => {
  const lines: PanelLine[] = [{ text: '$ git log', kind: 'cmd' }, { text: '', kind: 'out', at: 5 }, { text: '', kind: 'cmd', at: 5 }];
  const p = new Panel({ kind: 'terminal', w: 1120, h: 232, lines });
  expect([0, 1, 2].map((i) => p.rowTop(i))).toEqual([72, 117, 162]);
  const q = new Panel({ kind: 'terminal', w: 900, h: 300, size: 30, lines: [...lines, { text: '', kind: 'out', at: 6 }] });
  expect([0, 1, 2, 3].map((i) => q.rowTop(i))).toEqual([77, 125, 173, 221]);
});

test('geometry: rowTop at t is where the panel draws the row then: rows opening, a terminal scrolling', () => {
  const lines: PanelLine[] = [{ text: '$ ls', kind: 'cmd' }, { text: 'a', kind: 'out', at: 1 }, { text: 'b', kind: 'out', at: 2 }];
  const p = new Panel({ kind: 'terminal', w: 900, h: 400, lines });
  expect(p.rowTop(2, 0.5)).toBe(117); // row 1 not yet open (it opens over 0.86..1)
  expect(p.rowTop(2, 1.5)).toBe(162);
  expect(p.rowTop(1, 0.5)).toBe(117);
  // as frame() lays it out, for every row at every frame
  for (let f = 0; f < 90; f++) {
    const fr = p.frame(f / 30);
    for (let i = 0; i < lines.length; i++) expect(p.rowTop(i, f / 30)).toBe(fr.top[i]!);
  }
  // 7 rows of 45 in a 372 px terminal (278 px under the bar) scroll it 37 px: row 0's top from 72 to 35
  const many: PanelLine[] = [0, 1, 2, 3, 4, 5, 6].map((k): PanelLine => ({ text: `line ${k}`, kind: 'out', at: k }));
  const s = new Panel({ kind: 'terminal', w: 900, h: 372, lines: many });
  expect(s.rowTop(0, 6)).toBe(35);
  expect(s.rowTop(0)).toBe(72); // (without t: unscrolled)
});

test('geometry: textOrigin and cellOrigin: where a line\'s text, and its character col, sit on the baseline', () => {
  const p = new Panel({ kind: 'terminal', w: 1120, h: 232, lines: [{ text: '$ git log', kind: 'cmd' }, { text: 'fatal', kind: 'out' }] });
  expect(p.textOrigin(1)).toEqual({ x: 28, baseline: 117 + 22.5 + 10.22 });
  expect(p.cellOrigin(1, 0)).toEqual({ x: 28, baseline: 117 + 22.5 + 10.22 });
  expect(p.cellOrigin(1, 3).x).toBeCloseTo(28 + 3 * 16.8, 12);
  expect(p.cellOrigin(1, 2.5).x).toBeCloseTo(28 + 2.5 * 16.8, 12); // between cells (a caret, a head)
  // a terminal's typed line without a `$ ` of its own: the panel draws one before it, and its text starts 2 cells on
  const q = new Panel({ kind: 'terminal', w: 900, h: 300, lines: [{ text: 'ls', kind: 'cmd' }] });
  expect(q.textOrigin(0).x).toBeCloseTo(28 + 2 * 16.8, 12);
  expect(q.cellOrigin(0, 1).x).toBeCloseTo(28 + 3 * 16.8, 12);
  // a chat's user turn sits on the right: its 3 characters end 28 + 16 px from the right edge
  const c = new Panel({ kind: 'chat', w: 900, h: 300, lines: [{ text: 'hey', kind: 'cmd' }] });
  expect(c.textOrigin(0).x).toBeCloseTo(900 - 28 - 16 - 3 * 16.8, 12);
  // an editor's text is past its gutter; at t its baseline follows its row
  const e = new Panel({ kind: 'editor', w: 640, h: 687, size: 24, gutter: 'numbers', lines: [{ text: 'a' }, { text: 'b', kind: 'add', at: 1 }, { text: 'c' }] });
  expect(e.textOrigin(2).x).toBeCloseTo(100.6, 12);
  expect(e.textOrigin(2, 0).baseline).toBeCloseTo(62 + 38.5 + 19.25 + 8.76, 12); // row 1 shut: row 2 right under row 0
  expect(e.textOrigin(2, 1).baseline).toBeCloseTo(62 + 77 + 19.25 + 8.76, 12);
});

test('geometry: a row the panel does not have is an error, not a guess', () => {
  const p = new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'a' }, { text: 'b' }] });
  for (const i of [-1, 2, 1.5, NaN]) {
    expect(() => p.rowTop(i)).toThrow();
    expect(() => p.textOrigin(i, 1)).toThrow();
    expect(() => p.cellOrigin(i, 0)).toThrow();
  }
});

// -------------------------------------------------------------------------------------------------------- spans

// A line's characters take the highlighter's look (bone at five strengths, the prompt in bright blood) unless a span
// tones them: a token class's look (its family and colour), or an accent, blood or moss, on the character's own family.

const FATAL = "fatal: your current branch 'main' does not have any commits yet"; // "commits" is characters 52..58

test('spans: without any, every character keeps the highlighter\'s look', () => {
  const p = new Panel({ kind: 'terminal', w: 1120, h: 232, lines: [{ text: '$ git log', kind: 'cmd' }, { text: FATAL, kind: 'out' }] });
  expect(p.charStyle(0, 0)).toEqual({ family: F.mono(500), color: rgba('bloodBright') }); // the prompt
  expect(p.charStyle(0, 2)).toEqual({ family: F.mono(500), color: rgba('bone', 1) }); // `git`, the command
  expect(p.charStyle(1, 0)).toEqual({ family: F.mono(400), color: rgba('bone', 0.88) }); // output reads as plain
  expect(p.charStyle(1, 6)).toBeNull(); // a blank draws nothing
});

test('spans: an accent tones its run, on the characters\' own family; the rest of the line is untouched', () => {
  const at = FATAL.indexOf('commits');
  expect(at).toBe(52);
  const p = new Panel({ kind: 'terminal', w: 1120, h: 232, lines: [{ text: FATAL, kind: 'out', spans: [{ from: 52, to: 59, tone: 'blood' }] }] });
  for (let k = 52; k < 59; k++) expect(p.charStyle(0, k)).toEqual({ family: F.mono(400), color: rgba('bloodBright') });
  expect(p.charStyle(0, 51)).toBeNull(); // the blank before it
  expect(p.charStyle(0, 50)).toEqual({ family: F.mono(400), color: rgba('bone', 0.88) });
  expect(p.charStyle(0, 60)).toEqual({ family: F.mono(400), color: rgba('bone', 0.88) });
  const moss = new Panel({ kind: 'editor', w: 900, h: 300, lang: 'ts', lines: [{ text: 'const x = 1', spans: [{ from: 0, to: 5, tone: 'moss' }] }] });
  expect(moss.charStyle(0, 0)).toEqual({ family: F.mono(500), color: rgba('moss') }); // a keyword keeps its weight
});

test('spans: a token class tone gives its run that class\'s look; where spans overlap the later one wins', () => {
  const p = new Panel({ kind: 'editor', w: 900, h: 300, lines: [{ text: 'abcdefgh', spans: [{ from: 0, to: 6, tone: 'com' }, { from: 4, to: 8, tone: 'kw' }] }] });
  expect(p.charStyle(0, 0)).toEqual({ family: F.mono(400, true), color: rgba('boneFaint') });
  expect(p.charStyle(0, 3)).toEqual({ family: F.mono(400, true), color: rgba('boneFaint') });
  expect(p.charStyle(0, 4)).toEqual({ family: F.mono(500), color: rgba('bone', 1) });
  expect(p.charStyle(0, 7)).toEqual({ family: F.mono(500), color: rgba('bone', 1) });
});

test('spans: a check mark stays the panel\'s moss path; a span that is empty or off the line is an error', () => {
  const p = new Panel({ kind: 'terminal', w: 900, h: 300, lines: [{ text: '✔ Connected', kind: 'out', spans: [{ from: 0, to: 4, tone: 'blood' }] }] });
  expect(p.charStyle(0, 0)).toBeNull(); // drawn by the shader, not as text
  expect(p.charStyle(0, 2)).toEqual({ family: F.mono(400), color: rgba('bloodBright') });
  const bad = (from: number, to: number) => () => new Panel({ kind: 'editor', w: 900, h: 300, lines: [{ text: 'abc', spans: [{ from, to, tone: 'moss' }] }] });
  for (const [from, to] of [[2, 2], [2, 1], [-1, 2], [0, 4], [0.5, 2]] as const) expect(bad(from, to)).toThrow();
  expect(bad(0, 3)).not.toThrow();
  expect(() => p.charStyle(0, 11)).toThrow(); // past the line
});

// ----------------------------------------------------------------------------------------------------- viewport

// An editor's window on a longer file: `rows` rows tall from under the top padding, rows outside it not drawn and rows
// across its edges cut there; `scroll` (rows, fractional for a smooth scroll; constant or a pure function of time,
// read on the frame grid) moves the file up through it. At 28 px: rows of 45 from 72 (a 52 px bar and 20 px padding).

const TEN: PanelLine[] = Array.from({ length: 10 }, (_, k) => ({ text: `line ${k + 1}` }));

test('viewport: without an h, a panel of `rows` is the chrome plus its window; an h given still wins', () => {
  const p = new Panel({ kind: 'editor', w: 640, rows: 4, lines: TEN });
  expect(p.spec.h).toBe(52 + 20 + 4 * 45 + 22);
  const d = new Panel({ kind: 'editor', w: 640, size: 24, rows: 16, lines: TEN });
  expect(d.spec.h).toBe(45 + 17 + 16 * 38.5 + 19);
  expect(new Panel({ kind: 'editor', w: 640, h: 687, size: 24, rows: 16, lines: TEN }).spec.h).toBe(687); // diff's margin
  expect(() => new Panel({ kind: 'editor', w: 640, lines: TEN })).toThrow(); // neither
  for (const rows of [0, -2, NaN]) expect(() => new Panel({ kind: 'editor', w: 640, rows, lines: TEN })).toThrow();
});

test('viewport: the window rows are drawn in (px), and the whole face under the bar without one', () => {
  expect(new Panel({ kind: 'editor', w: 640, rows: 4, lines: TEN }).viewport).toEqual({ top: 72, bottom: 72 + 180 });
  expect(new Panel({ kind: 'editor', w: 640, h: 300, lines: TEN }).viewport).toEqual({ top: 52, bottom: 300 });
});

test('viewport: scroll moves the rows up through the window, constant or as a function of time on the frame grid', () => {
  const p = new Panel({ kind: 'editor', w: 640, rows: 4, scroll: 2, lines: TEN });
  expect(p.rowTop(5, 0)).toBe(72 + 3 * 45);
  expect(p.rowTop(5)).toBe(72 + 5 * 45); // (without t: the layout at rest, unscrolled)
  const q = new Panel({ kind: 'editor', w: 640, rows: 4, scroll: (t) => t, lines: TEN });
  expect(q.rowTop(0, 1)).toBe(72 - 45);
  expect(q.rowTop(0, 1.01)).toBe(72 - 45); // one state per frame: 1.01 s is frame 30
  expect(q.rowTop(0, 1.5)).toBe(72 - 1.5 * 45);
  expect(q.frame(1).key).not.toBe(q.frame(1.5).key); // a scroll repaints
});

test('viewport: a row outside the window is not drawn, a row across its edge is cut there (its checks show it)', () => {
  // a check mark per row: a row wholly in the window takes a shader slot (up to 4), one across an edge is drawn on the
  // canvas inside the window's clip, one outside it is not drawn at all
  const lines: PanelLine[] = Array.from({ length: 8 }, () => ({ text: '✔' }));
  const at = (scroll: number) => new Panel({ kind: 'editor', w: 640, rows: 3, scroll, gutter: 'none', lines }).frame(0).checks;
  const base = (row: number, scroll: number) => [28, 72 + (row - scroll) * 45 + 22.5 + 10.22] as [number, number];
  expect(at(0)).toEqual({ slot: [base(0, 0), base(1, 0), base(2, 0)], canvas: [] });
  expect(at(2)).toEqual({ slot: [base(2, 2), base(3, 2), base(4, 2)], canvas: [] });
  // half a row on: rows 2 and 5 are cut by the window's top and bottom
  expect(at(2.5)).toEqual({ slot: [base(3, 2.5), base(4, 2.5)], canvas: [base(2, 2.5), base(5, 2.5)] });
});

// --------------------------------------------------------------------------------------------------- highlights

// Bands painted on the canvas under a row's text: a line's highlights (the whole row edge to edge, or characters
// [from, to) of it; bone, moss or blood; static, or coming up at `at` and going at `until` over `fade` s, on the frame
// grid) and the selection a scene sets each frame (select(line, from, to)). At 28 px code: text from x = 28 + the
// numbers gutter (two digits: 2 x 16.8 + 22), cells of 16.8.

const TX = 28 + 2 * 16.8 + 22;

test('highlights: a whole row edge to edge, or a run of its characters, under the text (frame().marks)', () => {
  const p = new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'a' }, { text: 'Uses neovim.', highlight: {} }, { text: 'xyz', highlight: { from: 1, to: 3, tone: 'moss', alpha: 0.2 } }] });
  const m = p.frame(0).marks;
  expect(m).toHaveLength(2);
  expect(m[0]).toEqual({ i: 1, x0: 0, x1: 640, color: rgba('bone', 0.07), cells: false });
  expect(m[1]!.i).toBe(2);
  expect(m[1]!.x0).toBeCloseTo(TX + 16.8, 9);
  expect(m[1]!.x1).toBeCloseTo(TX + 3 * 16.8, 9);
  expect([m[1]!.color, m[1]!.cells]).toEqual([rgba('moss', 0.2), true]);
  // several on a line, in order; blood's default is a wash a little stronger than bone's
  const q = new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'abc', highlight: [{ tone: 'blood' }, { from: 0, to: 1 }] }] });
  expect(q.frame(0).marks.map((x) => x.color)).toEqual([rgba('blood', 0.1), rgba('bone', 0.07)]);
});

test('highlights: timed ones come up at `at` and go at `until` over `fade`, one state per frame', () => {
  const p = new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'a', highlight: { at: 1, until: 2, fade: 0.2 } }] });
  expect(p.frame(0.9).marks).toEqual([]);
  expect(p.frame(1.2).marks[0]!.color).toBe(rgba('bone', 0.07));
  const mid = p.frame(1.1).marks[0]!.color; // half way up: smootherstep(0.5) = 0.5
  expect(mid).toBe(rgba('bone', 0.07 * 0.5));
  expect(p.frame(1.1 + 0.01).marks[0]!.color).toBe(mid); // the same frame
  expect(p.frame(1.9).marks[0]!.color).toBe(rgba('bone', 0.07 * 0.5)); // going: half way down at 1.9
  expect(p.frame(2).marks).toEqual([]);
  expect(p.frame(0.9).key).not.toBe(p.frame(1.2).key); // a highlight repaints
});

test('highlights: select() is the scene\'s per-frame selection, a run of one line in the selection\'s bone; null clears it', () => {
  const p = new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'Uses VS Code.' }] });
  const k0 = p.frame(0).key;
  p.select(0, 0, 12.5); // fractional: a selection running across the line
  const m = p.frame(0).marks;
  expect(m).toHaveLength(1);
  expect([m[0]!.i, m[0]!.x0, m[0]!.color, m[0]!.cells]).toEqual([0, TX, rgba('bone', 0.14), true]);
  expect(m[0]!.x1).toBeCloseTo(TX + 12.5 * 16.8, 9);
  expect(p.frame(0).key).not.toBe(k0);
  p.select(0, 2, 4, 0.3);
  expect(p.frame(0).marks[0]!.color).toBe(rgba('bone', 0.3));
  p.select(null);
  expect(p.frame(0).marks).toEqual([]);
  expect(p.frame(0).key).toBe(k0);
  expect(() => p.select(1, 0, 1)).toThrow(); // no such line
  expect(() => p.select(0, 3, 1)).toThrow(); // backwards
});

test('highlights: a run off the line, or backwards, is an error', () => {
  const bad = (from: number, to: number) => () => new Panel({ kind: 'editor', w: 640, h: 400, lines: [{ text: 'abc', highlight: { from, to } }] });
  for (const [from, to] of [[2, 1], [-1, 2], [0, 4]] as const) expect(bad(from, to)).toThrow();
  expect(bad(0, 3)).not.toThrow();
  expect(bad(1, 1)).not.toThrow(); // empty: nothing to draw
});
