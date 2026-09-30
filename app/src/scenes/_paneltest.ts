// Dev harness for the panels (render.ts stills --module _paneltest --t 2). Every string comes from
// _paneltest.strings.json (the facts gate).
//
// 0–8 s, the acceptance shot: a terminal types the Claude Code command (spec §11.1), then `claude mcp list` to its
// ✔ Connected; behind it an editor shows the diff (§11.5), the old confidence struck, "Uses VS Code." struck through
// at 0.6 s and "Uses neovim. Has since 2019." typing in. The typing starts before 0, so it is under way in the first
// frames and the whole exchange is on screen at 2 s. Both hang tilted in the dark studio, the camera sliding round
// them on a slow push-in, focused on the command until 3.6 s, then racked to the diff.
// 8 s on, the other kinds: the memory file (§11.4) in an editor with line numbers and its YAML front matter, the MCP
// config (§11.2) as JSON, a chat turn (§4 cite) and an SDK card (§4 connect).
import * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { CameraRig, Stage } from '../engine/stage';
import { Panel, lineEnd, type PanelLine } from '../engine/panels';
import { ease, keys } from '../engine/util';
import S from './_paneltest.strings.json';

// the strings in the file's order: the terminal, the diff (its path, then its lines), the memory file's non-empty
// lines, the MCP config, a chat turn, an SDK card
let at = 0;
const take = (n: number) => (S as string[]).slice(at, (at += n));
const [CMD1, CMD2, CMD3, LIST, CONNECTED] = take(5);
const [PATH, TIER, CONF_OLD, CONF_NEW, VSCODE, NEOVIM] = take(6);
const MEMORY = take(13);
const MCP = take(9);
const [ASK, ANSWER] = take(2);
const [GO, GO_LINE] = take(2);

const FOV = 26;
const CPS = 46; // brisk film typing
const BREAK = 0.09; // the beat at each `\` line break
const GALLERY = 8; // when the second shot starts

/** The command, typed line after line; `claude mcp list` after a pause at the fresh prompt; its output; a new prompt. */
function terminalLines(): PanelLine[] {
  const lines: PanelLine[] = [];
  let t = -1.45; // under way at t = 0 (early stills catch it typing), done with its output by t = 2
  for (const text of [CMD1!, CMD2!, CMD3!]) {
    const l: PanelLine = { text, kind: 'cmd', at: t, cps: CPS };
    lines.push(l);
    t = lineEnd(l) + BREAK;
  }
  const list: PanelLine = { text: LIST!, kind: 'cmd', at: t + 0.45, cps: CPS };
  const out: PanelLine = { text: CONNECTED!, kind: 'out', at: lineEnd(list) + 0.28 };
  // an empty command that is never typed: the prompt waiting after the output
  return [...lines, list, out, { text: '', kind: 'cmd', at: Infinity }];
}

const DIFF: PanelLine[] = [
  { text: TIER!, kind: 'ctx' },
  { text: CONF_OLD!, kind: 'del' },
  { text: CONF_NEW!, kind: 'add' },
  { text: '', kind: 'ctx' },
  { text: VSCODE!, kind: 'del', at: 0.6, cps: 40 },
  { text: NEOVIM!, kind: 'add', at: 1.05, cps: 30 },
];

/** The memory file's 18 lines: its non-empty lines, and the blank ones between them (-1). */
const FILE = [0, 1, 2, 3, 4, 5, -1, 6, 7, -1, 8, -1, 9, -1, 10, -1, 11, 12].map((i): PanelLine => ({ text: i < 0 ? '' : MEMORY[i]! }));

export default class PanelTest extends Scene {
  private stage!: Stage;
  private term!: Panel;
  private edit!: Panel;
  private gallery: Panel[] = [];
  private rig = new CameraRig([
    { t: 0, pos: [-0.7, 0.28, 2.22], target: [0.02, -0.03, -0.08], fov: FOV },
    { t: 7, pos: [-0.4, 0.18, 1.84], target: [0.06, -0.05, -0.08], ease: ease.inOutCubic },
  ]);
  private rig2 = new CameraRig([
    { t: GALLERY, pos: [0.16, 0.1, 2.36], target: [0, -0.01, 0], fov: FOV },
    { t: GALLERY + 6, pos: [-0.06, 0.04, 2.24], target: [0, -0.01, 0], ease: ease.inOutCubic },
  ]);

  override init() {
    this.stage = new Stage(this.ctx.renderer, { fov: FOV });
    this.edit = new Panel({ kind: 'editor', title: PATH, w: 840, h: 372, lang: 'yaml', gutter: 'diff', lines: DIFF });
    this.term = new Panel({ kind: 'terminal', w: 900, h: 372, lines: terminalLines() });
    this.place(this.edit, [0.27, 0.17, -0.2], 0.06);
    this.place(this.term, [-0.2, -0.17, 0.02], 0.1);

    const t0 = GALLERY + 0.4;
    const file = new Panel({ kind: 'editor', title: PATH, w: 700, h: 780, lang: 'md', gutter: 'numbers', size: 24, lines: FILE });
    const json = new Panel({ kind: 'json', w: 740, h: 392, size: 22, lines: MCP.map((text) => ({ text })) });
    const chat = new Panel({
      kind: 'chat', w: 740, h: 184, size: 22,
      lines: [{ text: ASK!, kind: 'cmd', at: t0, cps: 24 }, { text: '' }, { text: ANSWER!, kind: 'out', at: t0 + 1.4, cps: 14 }],
    });
    const card = new Panel({ kind: 'card', title: GO, w: 740, h: 116, size: 22, lang: 'go', lines: [{ text: GO_LINE! }] });
    this.place(file, [-0.44, 0, 0], 0.12);
    this.place(json, [0.43, 0.2, -0.04], -0.1);
    this.place(chat, [0.43, -0.13, -0.04], -0.1);
    this.place(card, [0.43, -0.34, -0.04], -0.1);
    this.gallery = [file, json, chat, card];
  }

  private place(p: Panel, pos: [number, number, number], yaw: number) {
    p.mesh.position.set(...pos);
    p.mesh.rotation.set(-0.04, yaw, 0);
    this.stage.scene.add(p.mesh);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const st = this.stage, second = f.t >= GALLERY;
    for (const p of [this.term, this.edit]) p.mesh.visible = !second;
    for (const p of this.gallery) p.mesh.visible = second;
    for (const p of second ? this.gallery : [this.term, this.edit]) p.draw(f.t);
    if (second) {
      this.rig2.apply(st.camera, f.t);
      st.render(out, { dof: { focus: st.depthOf(this.gallery[0]!.mesh.position), fstop: 4 } });
      return;
    }
    this.rig.apply(st.camera, f.t);
    // focus in diopters: the terminal's command line while it types, racked to the diff's new line after
    const onTerm = 1 / st.depthOf(this.term.mesh.localToWorld(new THREE.Vector3(-0.05, 0.02, 0)));
    const onDiff = 1 / st.depthOf(this.edit.mesh.localToWorld(new THREE.Vector3(-0.1, -0.1, 0)));
    const D = keys(f.t, [[0, onTerm], [3.6, onTerm], [4.6, onDiff]]);
    st.render(out, { dof: { focus: 1 / D, fstop: 2.8 } });
  }

  override dispose() {
    for (const p of [this.term, this.edit, ...this.gallery]) p.dispose();
    this.stage.dispose();
  }
}
