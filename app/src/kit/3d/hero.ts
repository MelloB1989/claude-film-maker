// Hero3D: an extruded headline. Lines of bevelled display type (engine/type3d.ts: satin fg, emphasis words in an accent
// whose seam glows) land unit by unit on a stagger, on the beat grid or on the shot's spoken words, with a 3D reveal on
// the house springs; a glint sweeps across the faces on the hit; the accent seams pulse on the beat; the camera pushes in
// under a slow drift with focus on the type; the words fall away, blow out at the camera or fade at the end.
//
// Params (all optional but the text; sizes in reference px of a 1080 px short side):
//   text | lines       the copy: a string ('\n' splits lines) or an array of strings / { text, at?, emphasis? }
//   size 210           the em at rest (px); lines wrap (balanced) to maxWidth (0.84 of W; 0.88 in a tall frame) and
//                      shrink to fit it; the block shrinks to fit 0.72 of H
//   role 'display', width 87.5, weight 800, tracking -0.02 (em), leading 1.0 (em), align 'center' | 'left' | 'right'
//   depth 0.16, bevel 0.012   the extrusion and its round bevel (em)
//   emphasis           words that land in the accent with a glowing seam; emphasisColor 'accent' | 'accent2'
//   reveal 'slam'      'slam' | 'rise' | 'tip' | 'drop' | 'scale' (motion3d.ts)
//   unit 'word'        'word' | 'glyph' | 'line'; stagger (s between units: word 0.09, glyph 0.035, line 0.22);
//                      cascade 0.018 (s between a word's or a line's glyphs)
//   sync 'stagger'     'stagger' | 'beats' (a unit every `every` beats, default 1) | 'vo' (on the shot's spoken words)
//   delay              when the first unit lands (TimeRef: s, { beat }, { bar }; default 0.15 s, or the first beat)
//   sweep true         a glint across the faces just after the last unit lands; false; or a list of TimeRefs
//   pulse 0.35         how much the accent seams swell on each beat (0: steady)
//   exit 'none'        'fall' | 'blow' | 'scatter' (unit by unit) | 'fade' | 'rise' | 'sink'; exitDur 0.6
//   camera 'push', az -18, el 5, fov 26, fstop 2.8, seed 1, and every Scene3D param (background, whip, glow...)
import * as THREE from 'three';
import { Type3D, Mat, DEPTH, BEVEL } from '../../engine/type3d';
import { sweepAt, withSweep, type SweepBand, type SweepPass } from '../../engine/sweep';
import { onBeat, wordTimes } from '../../engine/motion';
import { W, H } from '../../engine/gl';
import { hash, prog, ease } from '../../engine/util';
import * as fx from '../text/fx';
import { family, metrics, setToMeasure, type FaceSpec } from '../text/layout';
import { isTall } from '../scene2d';
import { Scene3D, type Frame } from './scene3d';
import { composePose, exitPose, revealPose, type Exit3D, type Reveal3D } from './motion3d';

export interface HeroLine { text: string; at?: fx.TimeRef; emphasis?: string[] }

/** World units per logical px on the type's plane: the frame is 2.4 units tall there. */
const FRAME_UNITS = 2.4;
const DEFAULT_STAGGER = { word: 0.09, glyph: 0.035, line: 0.22 } as const;

interface Unit3D { mesh: THREE.Mesh; home: THREE.Vector3; at: number; word: number; line: number; v: number; order: number }

export class Hero3D extends Scene3D {
  protected override ownExits = ['fall', 'blow', 'scatter'];
  protected override defaults: Record<string, unknown> = { camera: 'push', az: -18, el: 5, fov: 26, fstop: 2.8, key: 0.6, softbox: 0.75, rim: 1.3 };
  private lines: { type: Type3D; y: number; x: number }[] = [];
  private units: Unit3D[] = [];
  private accents: { mat: THREE.MeshPhysicalMaterial; at: number }[] = [];
  private band!: SweepBand;
  private passes: SweepPass[] = [];
  private em = 1;
  private lastAt = 0;
  private lineCentres: { at: number; c: THREE.Vector3 }[] = [];
  private group = new THREE.Group();

  protected specs(): HeroLine[] {
    const lines = this.p<(string | HeroLine)[] | undefined>('lines', undefined);
    const text = this.p<string | undefined>('text', undefined);
    const raw = lines ?? (text !== undefined ? text.split('\n') : []);
    if (!raw.length) throw new Error(`shot ${this.ctx.id}: Hero3D needs \`text\` or \`lines\``);
    return raw.map((l) => (typeof l === 'string' ? { text: l } : l));
  }

  protected build() {
    const u = this.u, tall = isTall();
    const face: FaceSpec = { role: this.p('role', 'display'), width: this.p('width', 87.5), weight: this.p('weight', 800) };
    const fam = family(face);
    const tracking = this.p('tracking', -0.02), leading = this.p('leading', 1.0);
    const maxW = this.p('maxWidth', tall ? 0.88 : 0.84) * W;
    const specs = this.specs();
    // set each spec line to the measure; one em size for the block (the smallest any line needs)
    let px = this.p('size', 210) * u;
    const set = specs.map((s) => setToMeasure(s.text, fam, px, maxW, { tracking, wrap: true, fit: 'shrink' }));
    px = Math.min(px, ...set.map((s) => s.size));
    const rows = set.flatMap((s, si) => s.lines.map((text) => ({ text, si })));
    const m = metrics(fam);
    const blockPx = (rows.length - 1) * leading * px + m.cap * px;
    px *= Math.min(1, (0.72 * H) / blockPx);
    const ppu = H / FRAME_UNITS;
    const em = (this.em = px / ppu);

    // materials: satin fg for the block, an accent per emphasis word (each flares as it lands)
    const satin = this.own(Mat.satinBone());
    this.band = withSweep(satin);
    const emphColor = this.p<'accent' | 'accent2'>('emphasisColor', 'accent');
    const emph = this.p<string[]>('emphasis', []);
    const align = this.p<'left' | 'center' | 'right'>('align', 'center');
    const depth = this.p('depth', DEPTH), bevel = this.p('bevel', BEVEL);
    const totalH = (rows.length - 1) * leading * em + m.cap * em;
    const top = totalH / 2;
    let word = 0;
    const wordMats = new Map<number, THREE.MeshPhysicalMaterial>();
    const rowWords: { line: number; word: number; text: string; emph: boolean }[] = [];
    rows.forEach((r, li) => {
      const words = fx.wordsOf(r.text);
      const isEmph = words.map((w) => fx.isOneOf(w.w, [...emph, ...(specs[r.si]!.emphasis ?? [])]));
      words.forEach((w, k) => rowWords.push({ line: li, word: word + k, text: w.w, emph: isEmph[k]! }));
      const base = word;
      const type = new Type3D(r.text, { family: fam, size: em, depth, bevel, tracking }, (g) => {
        if (!isEmph[g.word]) return satin;
        const id = base + g.word;
        let mat = wordMats.get(id);
        if (!mat) {
          mat = this.own(Mat.accent(emphColor, 0));
          withSweep(mat).value = this.band.value;
          wordMats.set(id, mat);
        }
        return mat;
      });
      const y = top - m.cap * em - li * leading * em;
      const x = align === 'center' ? -type.width / 2 : align === 'left' ? -maxW / ppu / 2 : maxW / ppu / 2 - type.width;
      type.group.position.set(x, y, 0);
      this.group.add(type.group);
      this.lines.push({ type, x, y });
      word += words.length;
    });
    this.stage.scene.add(this.group);

    // ---- timing: units (words, glyphs or lines) on a stagger, the grid or the voice
    const { audio, vo, start } = this.ctx;
    const sync = this.p<'stagger' | 'beats' | 'vo'>('sync', 'stagger');
    const unit = this.p<'word' | 'glyph' | 'line'>('unit', 'word');
    const stagger = this.p('stagger', DEFAULT_STAGGER[unit]);
    const every = this.p('every', 1);
    const cascade = this.p('cascade', unit === 'glyph' ? 0 : 0.018);
    const delay = this.p<fx.TimeRef>('delay', sync === 'beats' ? { beat: 0 } : 0.15);
    const t0 = this.at(delay);
    let spans: fx.Span[] | null = null;
    if (sync === 'vo') {
      let spoken: fx.Spoken[] = [];
      try {
        spoken = wordTimes(vo, this.shot).map((x) => x.w);
      } catch {
        spoken = [];
      }
      if (spoken.length) spans = fx.alignToVO(rowWords.map((w) => w.text), spoken, { fallback: t0 });
    }
    // the unit index of each glyph, and where each spec line starts its run
    const wordAt: number[] = [];
    const lineAt: number[] = [];
    let cursor = t0, uidx = 0;
    const glyphTimes = new Map<THREE.Mesh, number>();
    rows.forEach((r, li) => {
      const L = this.lines[li]!, spec = specs[r.si]!;
      const firstRowOfSpec = li === 0 || rows[li - 1]!.si !== r.si;
      if (firstRowOfSpec && spec.at !== undefined) cursor = this.at(spec.at), (uidx = 0);
      const lineWords = rowWords.filter((w) => w.line === li);
      const times = (n: number) => fx.staggerTimes(n, cursor, sync === 'beats' ? { every, grid: audio } : { stagger });
      if (unit === 'line') lineAt[li] = cursor;
      const wordTimesHere = unit === 'word' ? times(lineWords.length) : [];
      const nGlyph = L.type.glyphs.length;
      const glyphRun = unit === 'glyph' ? times(nGlyph) : [];
      L.type.glyphs.forEach((g, gi) => {
        const w = lineWords[g.word]!;
        let at: number;
        const inWord = L.type.glyphs.filter((h) => h.word === g.word).indexOf(g);
        if (spans) at = spans[w.word]!.start + (unit === 'glyph' ? fx.glyphTimes(spans[w.word]!, L.type.glyphs.filter((h) => h.word === g.word).length)[inWord]! - spans[w.word]!.start : inWord * cascade);
        else if (unit === 'glyph') at = glyphRun[gi]!;
        else if (unit === 'word') at = wordTimesHere[g.word]! + inWord * cascade;
        else at = lineAt[li]! + gi * cascade;
        glyphTimes.set(g.mesh, at);
        wordAt[w.word] = Math.min(wordAt[w.word] ?? Infinity, at);
      });
      const last = Math.max(...L.type.glyphs.map((g) => glyphTimes.get(g.mesh)!));
      cursor = sync === 'beats' ? audio.timeOfBeat(audio.beatAt(Math.max(cursor, last)) + every) : (unit === 'line' ? cursor + stagger : last + Math.max(stagger, 0.12));
      uidx++;
    });
    let order = 0;
    this.lines.forEach((L, li) => {
      for (const g of L.type.glyphs) {
        this.units.push({ mesh: g.mesh, home: g.home.clone(), at: glyphTimes.get(g.mesh)!, word: g.word, line: li, v: hash(this.p('seed', 1), order) * 2 - 1, order: order++ });
      }
      const at = Math.min(...L.type.glyphs.map((g) => glyphTimes.get(g.mesh)!));
      this.lineCentres.push({ at, c: new THREE.Vector3(L.x + L.type.width / 2, L.y + 0.35 * em, 0) });
    });
    for (const [id, mat] of wordMats) this.accents.push({ mat, at: wordAt[id] ?? t0 });
    this.lastAt = Math.max(...this.units.map((x) => x.at));

    // ---- the glint: across the block just after the last unit lands, or at the given times
    const sw = this.p<boolean | fx.TimeRef[]>('sweep', true);
    const x0 = Math.min(...this.lines.map((l) => l.x)) - em, x1 = Math.max(...this.lines.map((l) => l.x + l.type.width)) + em;
    const times = sw === true ? [this.lastAt + 0.12] : sw === false ? [] : sw.map((r) => this.at(r));
    this.passes = times.map((t) => ({ t0: t, t1: t + 0.75, x0, x1, y: 0 }));

    const wBlock = x1 - x0 - 2 * em, ppuDist = H / (2 * ppu * Math.tan((this.p('fov', 26) * Math.PI) / 360));
    this.frame({ centre: [0, 0, 0], w: wBlock, h: totalH, dist: ppuDist });
  }

  protected update(f: Frame): THREE.Vector3 {
    const t = f.t, reveal = this.p<Reveal3D>('reveal', 'slam');
    const exit = this.p<string>('exit', 'none');
    const own = this.ownExits.includes(exit);
    const n = this.units.length;
    const dur = this.p('exitDur', 0.6);
    const em = this.em;
    for (const u of this.units) {
      let pose = revealPose(reveal, t, u.at, u.v);
      if (own) pose = composePose(pose, exitPose(exit as Exit3D, t, f.end, u.order, n, { dur, stagger: Math.min(0.04, (0.6 * dur) / Math.max(1, n)), seed: this.p('seed', 1), x: (u.home.x + this.lines[u.line]!.x) / Math.max(1e-6, 3 * em) }));
      const m = u.mesh;
      m.visible = pose.on && pose.s > 1e-3;
      m.position.set(u.home.x + pose.dx * em, u.home.y + pose.dy * em, u.home.z + pose.dz * em);
      m.rotation.set(pose.rx, pose.ry, pose.rz);
      m.scale.setScalar(this.lines[u.line]!.type.size * pose.s);
    }
    // the accents: a flare as each lands, settling, swelling on the beat
    const pulse = this.p('pulse', 0.35), beat = onBeat(f, 0.3);
    for (const a of this.accents) a.mat.emissiveIntensity = this.glowLevel * fx.emphasisGlow(t, a.at, 0.8) * (1 + pulse * beat);
    sweepAt(this.band, t, this.passes, { width: 0.45 * em, strength: 2.0 });
    // focus: the line landing now, pulled over a quarter second
    let c = this.lineCentres[0]!.c.clone();
    for (let i = 1; i < this.lineCentres.length; i++) {
      const L = this.lineCentres[i]!;
      c.lerp(L.c, prog(t, L.at - 0.2, L.at + 0.15, ease.inOutCubic));
    }
    // once all have landed, the block
    c = c.lerp(new THREE.Vector3(0, 0, 0), prog(t, this.lastAt + 0.2, this.lastAt + 0.8, ease.inOutCubic));
    return c;
  }

  override dispose() {
    for (const l of this.lines) l.type.dispose();
    this.lines = [];
    super.dispose();
  }
}

export default Hero3D;
