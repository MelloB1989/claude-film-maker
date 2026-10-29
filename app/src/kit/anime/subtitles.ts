// Subtitles: a dialogue's subtitles, line by line, the way an anime is subtitled: centred low in the frame, a light
// face with a dark outline and a soft shadow, each line fading in on its cue and out after it. An overlay: transparent,
// over whatever shot is on screen. The cues come from tools/ film-anime-dialogue (data/subs.json), or are written here.
//
// Params:
//   src 'data/subs.json'   the cues: [{ start, end, text, ja?, who? }] (film s); `cues` in params instead takes them inline
//   y 0.845                the line's baseline, a share of the frame's height (clear of 2.39 letterbox bars)
//   size 40                reference px; a second line sits one line above
//   role 'serif', weight 500   the film's face for it (F.role), falling back to the ui face
//   color '#f2ede3', outline '#0a0a0c', fade 0.14 (s in and out)
//   ja false               the Japanese line too, small, above the English
import { Scene2D, type Frame } from '../scene2d';
import type { Background } from '../common';
import { W, H } from '../../engine/gl';
import { filmUrl } from '../../engine/config';
import { F, font } from '../../engine/type';

export interface Cue { start: number; end: number; text: string; ja?: string; who?: string }

/** A cue's opacity at film time t: 0 before it, fading in over `fade` from its start and out over `fade` after its end. */
export function cueAlpha(c: Cue, t: number, fade: number): number {
  if (t < c.start || t >= c.end + fade) return 0;
  const i = fade > 0 ? Math.min(1, (t - c.start) / fade) : 1;
  const o = t > c.end ? 1 - (t - c.end) / fade : 1;
  return Math.max(0, Math.min(i, o));
}

export class Subtitles extends Scene2D {
  protected override defaultBackground: Background = 'none';
  private cues: Cue[] = [];
  private fam = '';
  private jaFam = '';

  override async init() {
    const inline = this.ctx.params.cues as Cue[] | undefined;
    if (inline) this.cues = inline;
    else {
      const url = filmUrl(this.p('src', 'data/subs.json'));
      const r = await fetch(url).catch(() => null);
      if (!r?.ok) throw new Error(`shot ${this.ctx.id}: subtitles ${url} did not load (tools/ film-anime-dialogue writes it)`);
      this.cues = (await r.json()) as Cue[];
    }
    const pick = (role: string, w: number, fallback: () => string) => {
      try {
        return F.role(role, w);
      } catch {
        return fallback();
      }
    };
    this.fam = pick(this.p('role', 'serif'), this.p('weight', 500), () => F.ui(500));
    this.jaFam = pick('jp', 600, () => this.fam);
  }

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const fade = this.p('fade', 0.14), size = this.p('size', 40) * this.u, y0 = this.p('y', 0.845) * H;
    const color = this.p('color', '#f2ede3'), outline = this.p('outline', '#0a0a0c');
    for (const cue of this.cues) {
      const a = cueAlpha(cue, f.t, fade);
      if (a <= 0.001) continue;
      const lines = cue.text.split('\n');
      c.save();
      c.globalAlpha = a;
      c.textAlign = 'center';
      c.textBaseline = 'alphabetic';
      c.lineJoin = 'round';
      let y = y0 - (lines.length - 1) * size * 1.25;
      const put = (text: string, fam: string, sz: number, yy: number) => {
        c.font = font(fam, sz);
        c.shadowColor = 'rgba(0,0,0,0.55)';
        c.shadowBlur = sz * 0.35;
        c.shadowOffsetY = sz * 0.05;
        c.strokeStyle = outline;
        c.lineWidth = sz * 0.16;
        c.strokeText(text, W / 2, yy);
        c.shadowColor = 'transparent';
        c.fillStyle = color;
        c.fillText(text, W / 2, yy);
      };
      if (this.p('ja', false) && cue.ja) put(cue.ja, this.jaFam, size * 0.62, y - size * 1.25);
      for (const line of lines) {
        put(line, this.fam, size, y);
        y += size * 1.25;
      }
      c.restore();
    }
  }
}

export default Subtitles;
