// Animatic card: one per scene until the scene's real module exists. It shows the act, the scene, what the picture
// will be, and her lines lighting word by word exactly as she says them, over a ruler of the scene's beats.
import type * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { Layer2D, W, H, clearRT } from '../engine/gl';
import { LIN, rgba } from '../engine/palette';
import { F, font, layout } from '../engine/type';
import { VO, type Line } from '../engine/vo';
import type { AudioData } from '../engine/audio';

const PICTURE: Record<string, string> = {
  thread: 'A taut bone thread hums in the dark, frays on “forgets” and snaps on “zero”.',
  ex: 'A cloud of floats. Berlin is overwritten by Lisbon. git log: fatal, no commits yet.',
  her: 'The thread re-forms with blood and moss strands. Commit bead 3f9a1c2. The hero diff.',
  repo: 'cd ~/memory && ls · git log like beads · the memory file opens.',
  loom: 'Four warps: facts, incidents (gc), rules, skills. A shuttle weaves on every beat.',
  diff: '− Uses VS Code. + Uses neovim. Has since 2019. · gitloom diff … 8b21e04 3f9a1c2',
  cite: 'what editor do I use? → neovim, stitched to facts/people/user.md#editor · L11–14',
  braid: 'lexical · body · cues braid into one rope → the result card, millis: 82',
  merkle: '10,000 leaves. Fifty glow. Unchanged subtrees fold shut, skipped by hash.',
  graph: 'A wikilink draws an edge; a dangling link heals; k8s → kubernetes.',
  honest: 'Music out. The threads find nothing: memories: [] · “I don’t know.”',
  proof: '44 → 72 → 80 → 83 → 91.4% · LongMemEval · oracle split · 456/499',
  connect: 'claude mcp add gitloom … → Connected · MCP · codex · the SDK cards', // JetBrains Mono has no ✔
  anywhere: 'The one-line install · the console: Playground, Graph, Namespaces',
  weave: 'Every thread weaves the 3D GitLoom mark · gitloom 3f9a1c2 · gitloom.cloud',
};

export default class Card extends Scene {
  private layer = new Layer2D();

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp, vo, audio } = this.ctx;
    const id = this.ctx.params.scene as string, n = this.ctx.params.n as number, act = this.ctx.params.act as string;
    clearRT(renderer, out, LIN.ink);
    const L = this.layer;
    // painted on ink, so the alphas below mix in sRGB as designed: a clear layer composites in linear light, where
    // the 6% watermark reads as a 27% grey and the 28% upcoming words as 54%
    L.clear(rgba('ink'));
    const c = L.ctx;
    c.textBaseline = 'alphabetic';

    c.font = font(F.mono(500), 15);
    c.letterSpacing = '3px';
    c.fillStyle = rgba('boneFaint');
    c.fillText(`ACT ${act} · ${(vo.acts.find((a) => a.id === act)?.name ?? '').toUpperCase()}`, 96, 120);
    c.letterSpacing = '0px';

    c.font = font(F.display(75, 800), 360);
    c.textAlign = 'right';
    c.fillStyle = rgba('bone', 0.06);
    c.fillText(String(n).padStart(2, '0'), W - 96, 400); // title-safe, on the ruler's end and the beat dot
    c.textAlign = 'left';

    c.font = font(F.display(100, 600), 88);
    c.fillStyle = rgba('bone', 0.95);
    c.fillText(id, 96, 230);

    c.font = font(F.mono(400), 22);
    c.fillStyle = rgba('boneDim', 0.9);
    c.fillText(PICTURE[id] ?? '', 96, 290);

    this.lines(c, vo.lines.filter((l) => l.scene === id), f.t);
    this.ruler(c, f, audio);
    comp.draw(renderer, L.upload(), out);
    // nothing on the card is brighter than bone, and bone never blooms (spec §6): no bloom, and no halation off it
    return { bloom: 0, halation: 0 };
  }

  /** Her lines, one per row: spoken words in bone, the word being spoken in bright blood, the rest dim. */
  private lines(c: CanvasRenderingContext2D, lines: Line[], t: number) {
    const size = 56, fam = F.display(100, 600);
    c.font = font(fam, size);
    lines.forEach((l, row) => {
      const y = 470 + row * 84; // the first row clears the numeral (ink to y 405) even when it runs full width (braid)
      const lay = layout(l.text, fam, size);
      let from = 0;
      for (const w of l.words) {
        const at = l.text.indexOf(w.w, from);
        const gi = at >= 0 ? Array.from(l.text.slice(0, at)).length : 0;
        if (at >= 0) from = at + w.w.length;
        const p = VO.wordProgress(w, t);
        c.fillStyle = t < w.start ? rgba('bone', 0.28) : p < 1 ? rgba('bloodBright') : rgba('bone', 0.96);
        c.fillText(w.w, 96 + (lay.glyphs[gi]?.x ?? 0), y);
      }
    });
  }

  /** The scene's beats (downbeats taller), a playhead, and a dot that flashes on every beat. */
  private ruler(c: CanvasRenderingContext2D, f: Frame, audio: AudioData) {
    const x0 = 96, x1 = W - 96, y = H - 110;
    const X = (t: number) => x0 + ((t - f.start) / (f.end - f.start)) * (x1 - x0);
    c.fillStyle = rgba('rule');
    c.fillRect(x0, y, x1 - x0, 1);
    for (const b of audio.beats) {
      if (b < f.start || b > f.end) continue;
      const down = audio.downbeats.some((d) => Math.abs(d - b) < 1e-3);
      c.fillStyle = down ? rgba('boneDim', 0.9) : rgba('boneFaint', 0.8);
      c.fillRect(Math.round(X(b)), y - (down ? 14 : 7), 1, down ? 14 : 7);
    }
    c.fillStyle = rgba('blood');
    c.fillRect(Math.round(X(f.t)) - 1, y - 20, 2, 26);
    const pulse = Math.exp(-f.beatPhase * 7);
    c.beginPath();
    c.arc(W - 96, 115, 6 + 4 * pulse, 0, Math.PI * 2);
    c.fillStyle = rgba('blood', 0.35 + 0.65 * pulse);
    c.fill();
    c.font = font(F.mono(400), 15);
    c.fillStyle = rgba('boneFaint');
    c.textAlign = 'right';
    c.fillText(`${f.t.toFixed(2)}s · beat ${f.beat.toFixed(2)} · bar ${f.bar.toFixed(2)}`, W - 120, 120);
    c.textAlign = 'left';
  }
}
