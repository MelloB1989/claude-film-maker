// Scene 08 `braid`: "Your words. What you meant. How you'd ask... braided into one answer." (Plan 2 Task 18; spec §4
// 08.) GitLoom's retrieval: three arms searched at once, fused into one ranking, expanded along the graph, in
// milliseconds and with no model call.
//
// The picture is Blender shot B08 (blender/shots/b08_braid.py): a dark void hung with glass commit beads. Three diff
// threads race in from the left, the top and the right, each landing on her naming it with a twang and a hit of light,
// and hang there with their tips apart: lexical dead straight, body in a long bow, cues with a lilt running down it. On
// "braided" they are plaited, and the plait is pulled toward the camera as a braiding machine pulls it, new plait forming
// where the arms whip round each other, while the camera swings back to watch it come; side threads shoot off it
// through the bores of three neighbouring beads (graph expansion), and on "one" its head lands on the card's hinge and
// the rope pulls taut. This module composites that plate and sets everything else, every time from the data
// (braid-time.ts), in the plate's own world and through its own camera (data/look/b08_braid.json):
//   - the query `what camera did I buy`, typed in at the top right as the scene opens;
//   - the labels on their arms (tracked), lit in the order she names them, her words lighting in them as she says them;
//     on "braided" each name slides down its arm into the braid and comes out of the plait's head to ride beside it
//     (braid-type.ts);
//   - the result card, an engine Panel hung on the rope's end at the hinge: it swings open as the head lands, the path
//     types in, and on the downbeat of "answer" the three names slide into its `matched: lexical · cue · body` row as
//     the row lands (their words bright in it: Panel spans), a sheen crosses it, then `mode: raw` and `millis: 82`
//     (spec §11.6, verbatim);
//   - the footnote under it: Ranked memories, no model call. Milliseconds.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage } from '../engine/stage';
import { H, Layer2D, W, clearRT } from '../engine/gl';
import { LIN } from '../engine/palette';
import { Plate } from '../engine/plates';
import { Track } from '../engine/track';
import { Panel, panelLayout, type PanelLine, type PanelSpec } from '../engine/panels';
import { spring } from '../engine/motion';
import { FPS, clamp, ease, frameIdx, lerp, prog, pulse } from '../engine/util';
import { ARMS, SHOT, WORLD, braidKeys, braidTimes, cardTimes, landOf, type Arm, type BraidTimes, type CardTimes } from './braid-time';
import { LBL, NOTE, RIDE, drawLabel, drawName, drawNote, drawQuery, drawSheen, flight, flightPoint, rowWord, splitLabel, steadyAt } from './braid-type';
import S from './braid.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [QUERY, LEXICAL, BODY, CUES, PATH, MATCHED, MODE, MILLIS, NOTE_TEXT] = S as string[] as [string, string, string, string, string, string, string, string, string];
// (the strings file ends with the bead hashes B08 engraves: blender/shots/b08_braid.py reads them from it)
const LABEL: Record<Arm, string> = { lexical: LEXICAL, body: BODY, cues: CUES };
/** The card's rows (spec §11.6): the path, then what matched, the mode and the time. */
const ROW = { path: 0, matched: 1, mode: 2, millis: 3 } as const;

// ------------------------------------------------------------------------------------------------ the card

const CARD_SIZE = 24; // code px on the panel
/** How far the card stands swung away (radians about its hinge) before the rope's head lands and opens it. */
const SWING0 = -1.32;

/** The card's spec: §11.6's fields as rows, each landing at its moment. */
export function cardSpec(C: CardTimes): PanelSpec {
  const n = Array.from(PATH).length;
  // the three arms' words in the matched row stand out bright (the keyword tone: the names that land in them are)
  const spans = ARMS.map((arm) => {
    const { word, col } = rowWord(splitLabel(LABEL[arm]).head, MATCHED);
    return { from: col, to: col + Array.from(word).length, tone: 'kw' as const };
  });
  const lines: PanelLine[] = [
    { text: PATH, at: C.path.at, cps: (n - 1) / (C.path.end - C.path.at) },
    { text: MATCHED, at: C.matched, spans },
    { text: MODE, at: C.mode },
    { text: MILLIS, at: C.millis },
  ];
  const g = panelLayout({ kind: 'card', size: CARD_SIZE, lines });
  const w = Math.ceil((g.textX + n * g.adv + g.padX) / 2) * 2;
  const h = Math.ceil(g.bar + g.padTop + lines.length * g.lineH + g.padBottom);
  return { kind: 'card', lang: 'yaml', size: CARD_SIZE, w, h, lines };
}

export default class Braid extends Scene {
  private plate!: Plate;
  private track!: Track;
  private stage!: Stage;
  private rig!: CameraRig;
  private card!: Panel;
  /** The card hangs from this, at the hinge: its local z faces the camera's end pose, its y is up; it swings about y. */
  private hinge = new THREE.Group();
  private layer = new Layer2D();
  private T!: BraidTimes;
  private C!: CardTimes;
  private v = new THREE.Vector3();
  /** The hinge's basis with the card open. */
  private rest = new THREE.Quaternion();

  override async init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = braidTimes(vo, audio, start, end);
    this.C = cardTimes(this.T);
    for (const arm of ARMS) {
      const n = splitLabel(LABEL[arm]).words.length;
      if (n !== this.T.phrase[arm].length) throw new Error(`braid: the ${arm} label has ${n} words, her phrase ${this.T.phrase[arm].length}`);
    }
    this.track = await Track.load(SHOT);
    this.plate = new Plate(SHOT, this.track.f0, { count: this.track.frames });
    this.stage = new Stage(renderer, { fov: WORLD.camera[0]!.fov });
    this.rig = new CameraRig(braidKeys(this.T));

    // the card, hung by its left edge's middle from the hinge, facing the way the plate's card faces
    const spec = cardSpec(this.C);
    this.card = new Panel(spec);
    const s = WORLD.card.width / (spec.w / 1000);
    this.card.mesh.scale.setScalar(s);
    this.card.mesh.position.set(WORLD.card.width / 2, 0, 0);
    this.hinge.add(this.card.mesh);
    // its face turned a little from the landing camera (its right side away), upright as that camera sees it
    const z = new THREE.Vector3(...(WORLD.card.facing as [number, number, number])).normalize();
    const up = new THREE.Vector3(...(WORLD.card.up as [number, number, number]));
    const x = new THREE.Vector3().crossVectors(up, z).normalize();
    const y = new THREE.Vector3().crossVectors(z, x);
    this.rest.setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
    this.hinge.quaternion.copy(this.rest);
    this.hinge.position.set(...(WORLD.card.hinge as [number, number, number]));
    this.stage.scene.add(this.hinge);
    this.stage.compile();
  }

  override async prepare(t: number) {
    await this.plate.prepare(t);
  }

  /** The card at t: its swing about the hinge (0 open) and its opacity. */
  private swing(t: number) {
    const C = this.C;
    return { angle: SWING0 * (1 - spring(t - C.swing, 6, 0.62)), opacity: prog(t, C.swing, C.swing + 0.07) };
  }

  /** Hang the card open (`open`), or as it hangs at t: its hinge's basis, turned about its y by the swing. */
  private hang(open: boolean, t: number) {
    this.hinge.quaternion.copy(this.rest);
    if (!open) this.hinge.rotateY(this.swing(t).angle);
    this.hinge.updateMatrixWorld(true);
  }

  /** A point on the card as it hangs (panel px from its top left, y down) on screen (logical px), through the camera. */
  private onScreen(px: number, py: number): { x: number; y: number } {
    const { w, h } = this.card.spec;
    const p = this.v.set(px / 1000 - w / 2000, h / 2000 - py / 1000, 0);
    this.card.mesh.localToWorld(p).project(this.stage.camera);
    return { x: ((p.x + 1) * W) / 2, y: ((1 - p.y) * H) / 2 };
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx;
    const t = f.t, T = this.T, C = this.C;
    clearRT(renderer, out, LIN.ink);
    this.plate.draw(renderer, comp, out, t);

    // ---- the card, in the plate's world through the plate's camera
    const st = this.stage;
    this.rig.apply(st.camera, t);
    // where the names land: the row's cells with the card open (it is, by then), and the card's code size on screen
    this.hang(true, t);
    const cells = {} as Record<Arm, { x: number; y: number; px: number; drop: number }>;
    for (const arm of ARMS) {
      const head = splitLabel(LABEL[arm]).head;
      const { word, col } = rowWord(head, MATCHED);
      const a = this.card.cellOrigin(ROW.matched, col), b = this.card.cellOrigin(ROW.matched, col + 1);
      const pa = this.onScreen(a.x, a.baseline), pb = this.onScreen(b.x, b.baseline);
      cells[arm] = { x: pa.x, y: pa.y, px: Math.hypot(pb.x - pa.x, pb.y - pa.y) / 0.6, drop: head.length - word.length };
    }
    const corner = this.onScreen(this.card.layout.textX, this.card.spec.h);
    // the card as it hangs now, and its face's corners on screen (for the sheen)
    this.hang(false, t);
    const { w: cw, h: ch } = this.card.spec;
    const quad = [this.onScreen(0, 0), this.onScreen(cw, 0), this.onScreen(cw, ch), this.onScreen(0, ch)];
    const sw = this.swing(t);
    if (sw.opacity > 0) {
      this.card.opacity = sw.opacity;
      this.card.draw(t);
      st.render(out, { clear: false });
    }

    // ---- the type
    const L = this.layer, c = L.ctx;
    L.clear();
    c.textBaseline = 'alphabetic';
    drawQuery(c, t, QUERY, T.start + 0.06, lerp(1, 0.55, prog(t, T.one, T.one + 0.4)));
    const head = this.track.at('head', t), p0 = this.track.at('p0', t);
    for (const arm of ARMS) {
      const fl = flight(t, arm, T.zip, C.matched);
      const fade = 1 - prog(t, T.zip + 0.02, T.zip + 0.24);
      const anchor = `lbl_${arm}`, dot = this.track.at(anchor, t);
      const chip = drawLabel(c, t, arm, LABEL[arm], dot, steadyAt(this.track, anchor, t), landOf(T, arm), T.phrase[arm], fade, fl.absorb <= 0);
      // a name hands over to the card's row on the frame the row lands (the panel shows one state a frame, whatever
      // the shutter samples)
      if (fl.absorb <= 0 || frameIdx(t) / FPS >= C.matched) continue;
      const cell = cells[arm];
      const ride = { x: head.x + RIDE[arm].dx, y: head.y + RIDE[arm].dy };
      const p = flightPoint(fl, { x: chip.x, y: chip.base }, dot, p0, head, ride, cell);
      const name = splitLabel(LABEL[arm]).head;
      const px = fl.emerge > 0 ? lerp(LBL.px, cell.px, fl.land) : lerp(LBL.px, 0.75 * LBL.px, prog(fl.absorb, 0.35, 1));
      drawName(c, name, p, px, p.alpha, cell.drop, prog(fl.land, 0.2, 0.7));
    }
    if (sw.opacity > 0) drawSheen(c, quad, prog(t, C.matched - 0.12, C.matched + 0.32, ease.inOutCubic));
    drawNote(c, t, NOTE_TEXT, C.note, corner.x, corner.y + NOTE.below);
    comp.draw(renderer, L.upload(), out);

    // a breath of a punch as each arm lands, on every downbeat, and hardest as the answer lands on its downbeat
    let punch = 0;
    for (const arm of ARMS) punch += pulse(t, landOf(T, arm), 0.09);
    for (const d of T.downbeats) punch += (d === C.matched ? 1.4 : 0.7) * pulse(t, d, 0.11);
    return { zoom: 1 + 0.004 * clamp(punch, 0, 2) };
  }

  override dispose() {
    this.plate?.dispose();
    this.card?.dispose();
    this.stage?.dispose();
    disposeLayer(this.layer);
  }
}
