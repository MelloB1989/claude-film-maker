// Scene 02 `ex`: "It's not you… it's your vector store." / "It overwrites what it knew… and never tells you why." /
// "Commitment issues." (Plan 2 Task 13; spec §4 02.) The ex is the vector store, and the joke is how beautiful she was.
//
// One world, every time from the data (her measured onsets, the score's beats and downbeats):
// - The match cut in (transitions/thread-ex.ts): the cold open's freed fibres become the first numerals. A seed sits on
//   each fibre's tracked screen point (B01's fibre_* track, ex-cloud.ts fibreSeeds) as a bright stroke of seven dashes
//   that morph into a float's cells, then glides into the cloud's face onto the numeral it becomes, dimming to its
//   strength, as the camera pulls back; the cloud itself comes up out of the dark around them.
// - The float cloud (ex-cloud.ts, ex-glyphs.ts on engine/glyphs.ts): about six thousand mono float numerals in a jittered lattice filling a
//   thick shell of a loose spheroid, lit from the upper left, a crisp band where the shell crosses the focus plane and
//   the rest falling away into soft depth. The cut lands close and soft (the thread's fibres were); the camera pulls
//   back to reveal it, a band of light sweeping across it on the downbeat, then orbits it slowly.
// - L03: "It's not you…" and "it's your" in flat Bricolage on the left, each word on its onset; "vector store" in
//   extruded mono (the machine), satin bone with the blood diff glow (the film's minus), slamming in from depth; under
//   it the file's label, `vectors.bin · 1536 dims · 0 commits`, typed in, its zero in blood. Then the camera pushes
//   into the cloud through the type.
// - L04: the card `Maya lives in Berlin.` flies in and lands on the downbeat as she says "It"; its letters melt into
//   three floats that drop into their row. `Maya moved to Lisbon in March 2026.` arrives; its letters melt into five
//   floats that dive into the same row, and the region split-flaps to new values, the flaps landing on the beats:
//   the row on "knew", the rows around it on the next. Berlin is gone without a trace: a ghost `berlin?` pings the
//   cloud and nothing answers. Blood stamps hit on successive beats, `− no history`, `− no provenance`, `− one flat
//   bag`, shaking the frame and sending a shockwave through the lattice; on "why" a `why?` pings the cloud and gets back
//   only a lit numeral and a tooltip: `cosine 0.8127`, a score, not a reason.
// - L05: on "Commitment" the cloud drops: every numeral falls under gravity into one line, which flickers as they land
//   and, on the downbeat, resolves into a terminal: `$ git log` → `fatal: your current branch 'main' does not have any
//   commits yet`. Deadpan, bone-dim; a beat later "commits" turns blood.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, type CamKey, type V3 } from '../engine/stage';
import { H, Layer2D, W, makeRT } from '../engine/gl';
import { Panel } from '../engine/panels';
import { F } from '../engine/type';
import { HEX, LIN, rgba } from '../engine/palette';
import { glow } from '../engine/look';
import { onBeat, wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';
import type { AudioData } from '../engine/audio';
import { clamp, ease, hash, keys, lerp, prog, pulse } from '../engine/util';
import { GlyphActors, GlyphAtlas, flapAt, flapDigit } from '../engine/glyphs';
import { CloudField, type CloudCell } from './ex-glyphs';
import { Track } from '../engine/track';
import {
  ADV, BERLIN_SLOTS, CELLS, EM, MINUS, SPHEROID, buildCloud, cardFloats, cells, fall, fallOf, fibreSeeds, morphTargets,
  type Cloud, type Numeral,
} from './ex-cloud';
import { HeroWord, drawBrackets, drawQuery, drawStamp, drawStampGlow, drawTooltip, drawTyped, drawWords, stampPose } from './ex-type';
import S from './ex.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [L03A, L03B, HERO, LABEL, BERLIN, LISBON, BERLIN_Q, WHY_Q, COSINE, STAMP1, STAMP2, STAMP3, GITLOG, FATAL, N1, N2, N3] = S as [
  string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string,
];
const STAMPS = [STAMP1, STAMP2, STAMP3];
/** The spec's three numerals, as floats (they sit in the row above the Maya region). */
const NAMED = [N1, N2, N3].map((s) => Number(s.replace(MINUS, '-')));
/** Where "commits" is in the fatal line. */
const COMMITS = { at: FATAL.indexOf('commits'), n: 'commits'.length };

// ------------------------------------------------------------------------------------------------ layout (1080p px)

const X0 = 150;
const L03 = { fam: F.display(100, 600), px: 84, y1: 372, y2: 468 };
/** "vector store": px per em of the extruded mono, and its baseline; the label under it. */
const HERO_PX = 150;
const HERO_Y = 640;
const LABEL_Y = 724;
const LABEL_PX = 26;
/** Where the camera's push heads as the type clears (px): the flat type zooms out from it, as the hero flies past. */
const ZOOM_AT = { x: 1760, y: 470 };
/** The why? chip, from the numeral it lights (px). */
const WHY_CHIP = { dx: -360, dy: -128 };
/** The stamps' baselines (their left ends are on X0) and their turns (rad). */
const STAMP_Y = [436, 534, 632];
const STAMP_TILT = [-0.035, 0.022, -0.014];

// ------------------------------------------------------------------------------------------------ the world (m)

/** One flap of a split-flap cell (s). */
const FLAP = 0.07;
/** Gravity in the collapse (m/s²): the cloud's top lands about half a second after the drop. */
const GRAVITY = 6;
/** The cards' and the terminal's text size (panel px per em): one panel px is EM / 28 m, so it is the cloud's em. */
const CARD_PX = 28;
const PANEL_SCALE = (EM / CARD_PX) * 1000;
/** The terminal: its size (panel px) and the row the fatal line is on. */
const TERM = { w: 1120, h: 232, size: 28, row: 1 };
/** The lens: a short tele (18° vertical fov, a 64 mm on the full-frame gate). */
const FOV = 18;

/**
 * The match cut in: the cold open's shot (its fibre track), and the seeds. Each lands as a fibre-length stroke (em px on
 * screen; its seven rules one line like the fibre), turns into its numeral's cells from the left (`cascade` s apart,
 * each over `cell` s) from the cut, holds,
 * then glides into the cloud over [glide0, glide1] s, handing over to the numeral it lands on by `gone`. The cloud
 * comes up from `cloud0` of its strength over `rise` s, so at the cut the seeds are the bright points.
 */
const SEED_SHOT = 'b01_thread';
/** A seed's stroke: the box-drawing rule, which runs the whole cell, so seven of them make one unbroken line. */
const RULE = '─';
const SEED = { em: 30, glide0: 0.1, glide1: 0.62, gone: 0.7, tilt: 0.16, cloud0: 0.1, rise: 0.5, cascade: 0.012, cell: 0.05 };

/** A display-space mix of ink to bone by b, as linear light (what the cloud's shader gives a numeral). */
const sToL = (x: number) => (x < 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4));
const sRGB = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
function boneAt(b: number): [number, number, number] {
  const i = sRGB(HEX.ink), o = sRGB(HEX.bone);
  return [0, 1, 2].map((k) => sToL(i[k]! + (o[k]! - i[k]!) * clamp(b))) as [number, number, number];
}

const Y = new THREE.Vector3(0, 1, 0);

// ------------------------------------------------------------------------------------------------ timing

/** Every time the scene keys on, from her onsets and the score's grid (song seconds). */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'ex').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`ex: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const beatAfter = (t: number) => audio.beats.find((b) => b > t + 1e-6) ?? t + beat;
  const downAfter = (t: number) => audio.downbeats.find((b) => b > t + 1e-6) ?? t + 4 * beat;
  const store = word('store'), overwrites = word('overwrites'), knew = word('knew'), why = word('why');
  const commitment = word('commitment');
  // the drop is on the beat she says "Commitment" on (or the next one)
  const drop = audio.beats.find((b) => b >= commitment.start - 0.08) ?? commitment.start;
  const berlin = downAfter(store.end);
  const wave1 = beatAfter(overwrites.start + 0.55);
  const stamp0 = downAfter(knew.end);
  const stamps = [stamp0, beatAfter(stamp0), beatAfter(beatAfter(stamp0))];
  if (!(stamps[2]! < drop)) throw new Error('ex: the stamps must land before the drop');
  const resolve = downAfter(drop);
  return {
    start, end,
    its: word('its', 0).start, not: word('not').start, you: word('you', 0).start,
    its2: word('its', 1).start, your: word('your').start, vector: word('vector').start, store: store.start,
    /** The cloud is revealed and a band of light sweeps it, on the first downbeat. */
    reveal: downAfter(start + 0.2),
    /** The type clears as the camera pushes in; the Berlin card flies in and lands on the downbeat ("It"). */
    typeOut: store.end + 0.05, berlin,
    /** Its letters melt, its floats drop into their row, and the cloud takes them over. */
    berlinMorph: berlin + 0.02, berlinSettle: berlin + 0.42,
    /** Lisbon flies in during "overwrites", its letters melt and dive into the row; the flaps land on the beats. */
    lisbonIn: berlin + 0.26, lisbonMorph: wave1 - 0.48, lisbonDive: wave1 - 0.31, wave1, wave2: beatAfter(wave1),
    /** The ghost query, after the overwrite (gone before the first stamp). */
    query: beatAfter(wave1) + 0.06,
    stamps, why: why.start, drop, resolve,
    /** "commits" turns blood a beat after the fatal line. */
    punch: beatAfter(resolve),
  };
}
type Times = ReturnType<typeof timesOf>;

// ------------------------------------------------------------------------------------------------ the scene

interface Card {
  chars: string[];
  /** The cells its characters melt into (its floats' cells end to end). */
  targets: string[];
  floats: number[];
  panel: Panel;
  group: THREE.Group;
}

export default class Ex extends Scene {
  private T!: Times;
  private stage!: Stage;
  private atlas!: GlyphAtlas;
  private cloud!: Cloud;
  private field!: CloudField;
  private actors!: GlyphActors;
  private hero!: HeroWord;
  private layer = new Layer2D();
  /** The stamps' glow: drawn soft and white, added as blood light. */
  private glowLayer = new Layer2D(1920, 1080, 1);
  private berlin!: Card;
  private lisbon!: Card;
  private term!: Panel;
  private termGroup = new THREE.Group();
  private rig!: CameraRig;
  /** The region's centre (world), and the numeral why? lights (pickWhy). */
  private R = new THREE.Vector3();
  private whyNumeral!: Numeral;
  /** The fatal line's first cell (origin on the baseline) and the terminal's centre (world). */
  private line = new THREE.Vector3();
  private P = new THREE.Vector3();
  /** Per cell of the line, the times numerals land in it (sorted). */
  private arrivals: number[][] = [];
  /** The stamps' shock centres (world), fixed at their impacts. */
  private shocks: THREE.Vector3[] = [];
  private scratch = new THREE.PerspectiveCamera();
  /** Where the why? ping starts (world). */
  private whyAt = new THREE.Vector3();

  /** The match cut's seeds: the fibre's screen point at the cut, the numeral it lands on, its tilt (rad). */
  private seeds: { p: { x: number; y: number }; n: Numeral; tilt: number }[] = [];

  override async init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    const track = await Track.load(SEED_SHOT);
    const T = (this.T = timesOf(vo, audio, start, end));
    this.stage = new Stage(renderer, { fov: FOV, near: 0.02, far: 20 });
    this.atlas = new GlyphAtlas('0123456789.' + MINUS + BERLIN + LISBON + FATAL + RULE, F.mono(400));

    // the cards and their floats; the cloud, with Berlin's floats in their slots of the region's centre row
    this.berlin = this.card(BERLIN, 7);
    this.lisbon = this.card(LISBON, 11);
    this.cloud = buildCloud(NAMED);
    const mid = this.cloud.region[1]!;
    BERLIN_SLOTS.forEach((s, k) => {
      const n = mid[s]!;
      n.v = this.berlin.floats[k]!;
      n.text = cells(n.v);
    });
    const centre = mid[2]!;
    this.R.set(centre.x + (CELLS / 2) * ADV, centre.y + 0.365 * EM, centre.z);

    // the terminal, below where the cloud was: the line the cloud falls into is its output row
    this.P.set(0, -SPHEROID.ry - 0.11, 0.12);
    this.term = new Panel({
      kind: 'terminal', w: TERM.w, h: TERM.h, size: TERM.size,
      // (the output row is the fatal line, drawn by the actors; it lands on the resolve, and the fresh prompt with it)
      lines: [{ text: GITLOG, kind: 'cmd' }, { text: '', kind: 'out', at: T.resolve }, { text: '', kind: 'cmd', at: T.resolve }],
    });
    this.termGroup.position.copy(this.P);
    this.termGroup.scale.setScalar(PANEL_SCALE);
    this.termGroup.add(this.term.mesh);
    this.term.mesh.renderOrder = 1;
    this.stage.scene.add(this.termGroup);
    // the output row's first cell, on its baseline, a hair in front of the panel's face
    const cell = this.term.cellOrigin(TERM.row, 0);
    this.line.copy(this.panelPoint(this.term, this.termGroup, cell.x, cell.baseline, 0.6));

    this.buildRig();
    this.pickSeeds(fibreSeeds(track, start));
    this.buildField();
    this.actors = new GlyphActors(256, this.atlas);
    this.actors.mesh.renderOrder = 2;
    this.stage.scene.add(this.actors.mesh);

    this.hero = new HeroWord(renderer, HERO, F.mono(700), HERO_PX, X0, HERO_Y);
    this.shocks = T.stamps.map((t, i) => this.unproject(t, X0 + 260, STAMP_Y[i]! - 16, this.R.z - 0.1));
    this.pickWhy();
    this.warmUp();
  }

  /**
   * Draw everything once before the first frame: the shaders compile for the stages' targets, and the atlas (with its
   * mip chain), the panels' canvases and the actors' buffers upload. Without it the first frame an export renders read
   * a few pixels differently from any later render of the same time (the far shots sample the atlas's mips). Nothing it
   * sets outlives it: render() sets all state from t on every frame.
   */
  private warmUp() {
    const T = this.T, st = this.stage, rt = makeRT(W, H);
    st.compile();
    this.hero.stage.compile();
    this.ctx.renderer.initTexture(this.atlas.texture);
    for (const c of [this.berlin, this.lisbon]) {
      c.panel.mesh.visible = true;
      c.panel.draw(T.berlin);
    }
    this.term.mesh.visible = true;
    this.term.draw(T.resolve);
    this.actors.begin();
    this.poseLine(T.resolve);
    this.actors.end();
    this.rig.apply(st.camera, T.reveal);
    st.render(rt, { dof: { focus: 2.4, fstop: 2 } });
    this.hero.update(T.store + 1, [T.vector, T.store], [1e9, 1e9 + 1], { x: 960, y: 540 });
    this.hero.render(rt);
    rt.dispose();
  }

  /** A sentence card: a Panel card in the cloud's em; its letters are actors (they melt into numerals). */
  private card(text: string, seed: number): Card {
    const chars = Array.from(text), floats = cardFloats(text, seed);
    const w = Math.ceil(2 * CARD_PX + chars.length * 0.6 * CARD_PX);
    const panel = new Panel({ kind: 'card', w, h: 88, size: CARD_PX, lines: [{ text: '' }] });
    const group = new THREE.Group();
    group.scale.setScalar(PANEL_SCALE);
    group.add(panel.mesh);
    panel.mesh.renderOrder = 1;
    this.stage.scene.add(group);
    return { chars, targets: morphTargets(text, floats), floats, panel, group };
  }

  /** Every cell of the cloud, with its overwrite (the region's flaps) and its fall; and when the line's cells fill. */
  private buildField() {
    const T = this.T, out: CloudCell[] = [];
    const region = this.cloud.region;
    // the region's new values: Lisbon's five floats on the centre row, fresh ones on the rows around it
    const next = new Map<Numeral, { v: number; land: number }>();
    region[1]!.forEach((n, s) => next.set(n, { v: this.lisbon.floats[s]!, land: T.wave1 }));
    for (const r of [0, 2]) {
      region[r]!.forEach((n) => next.set(n, { v: Math.round((hash(n.seed, 77) - 0.5) * 5000) / 1e4 || 0.0101, land: T.wave2 }));
    }
    const slots: number[][] = Array.from({ length: FATAL.length }, () => []);
    for (const n of this.cloud.numerals) {
      const fl = fallOf(n), nx = next.get(n);
      const now = Array.from(n.text), then = nx ? Array.from(cells(nx.v)) : now;
      const berlinSlot = n.regionRow === 1 && (BERLIN_SLOTS as readonly number[]).includes(n.slot);
      now.forEach((ch, ci) => {
        const g = this.atlas.of(ch), g2 = this.atlas.of(then[ci]!);
        if (g < 0 && g2 < 0) return;
        // in the overwrite a digit turns two to five flaps, a sign that changes turns one, and "0." stays
        const steps = !nx ? 0 : ci > 2 ? 2 + Math.floor(hash(n.seed, 51 + ci) * 4) : ch !== then[ci] ? 1 : 0;
        out.push({
          x: n.x + ci * ADV, y: n.y, z: n.z, glyph: g, id: n.id, bright: n.bright, cell: ci,
          flags: (n.regionRow >= 0 ? 1 : 0) + (berlinSlot ? 2 : 0),
          flipFrom: g, flipTo: g2, land: nx ? nx.land : 0, steps,
          slot: fl.slot, delay: fl.delay, rn: n.rn, seed: hash(n.seed, 99), // (0..1: the GPU's float can't hold the raw seed)
        });
      });
      // when its numeral lands in the line (the shader's fall, ex-glyphs.ts: its centre down to the line's cap middle)
      slots[Math.floor(fl.slot * (FATAL.length - 1) + 0.5)]!.push(T.drop + fl.delay + fall(0, n.y - this.line.y, GRAVITY).dur);
    }
    this.arrivals = slots.map((s) => s.sort((a, b) => a - b));
    this.field = new CloudField(out, this.atlas);
    const u = this.field.u;
    u.uEm.value = EM;
    u.uAdv.value = ADV;
    u.uStep.value = FLAP;
    u.uSpheroid.value.set(SPHEROID.rx, SPHEROID.ry, SPHEROID.rz);
    u.uKey.value.set(...(new THREE.Vector3(-0.55, 0.62, 0.56).normalize().toArray() as V3), 0.7);
    u.uRegion.value.set(0, T.berlinSettle, 0.0004, 0);
    u.uLine.value.set(this.line.x, this.line.y, this.line.z, ADV);
    u.uCollapse.value.set(T.drop, GRAVITY, FATAL.length, 0.05);
    u.uPingK.value.set(0.95, 0.04, 0.34, 0.95);
    this.stage.scene.add(this.field.mesh);
  }

  /** A point on a panel (px from its top left; z: panel px in front of its face), in the world. */
  private panelPoint(p: Panel, g: THREE.Object3D, x: number, y: number, z = 0) {
    g.updateMatrixWorld(true);
    return new THREE.Vector3(x / 1000 - p.spec.w / 2000, p.spec.h / 2000 - y / 1000, z / 1000).applyMatrix4(g.matrixWorld);
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** A key looking at `at` from azimuth and elevation (degrees) and distance, `at` shifted across the frame by sx, sy. */
  private orbit(t: number, at: THREE.Vector3, az: number, el: number, d: number, sx = 0, sy = 0, e?: (x: number) => number): CamKey {
    const a = THREE.MathUtils.degToRad(az), b = THREE.MathUtils.degToRad(el);
    const right = new THREE.Vector3(Math.cos(a), 0, -Math.sin(a));
    const back = new THREE.Vector3(Math.sin(a) * Math.cos(b), Math.sin(b), Math.cos(a) * Math.cos(b));
    const target = at.clone().addScaledVector(right, -sx).addScaledVector(Y, -sy);
    return { t, pos: target.clone().addScaledVector(back, d).toArray() as V3, target: target.toArray() as V3, ease: e };
  }

  private buildRig() {
    const T = this.T, O = new THREE.Vector3(0, 0, 0), P = this.P;
    // close on the region with room above it for the cards: the row low in the frame
    const close = this.R.clone().add(new THREE.Vector3(0.03, 0.03, 0));
    this.rig = new CameraRig([
      // the cut: close on the cloud's face and soft, pulling back to reveal it on the downbeat
      { ...this.orbit(T.start, this.R.clone().add(new THREE.Vector3(0.05, 0.02, 0)), -6, 3, 0.42), fov: FOV },
      this.orbit(T.reveal, O, -24, 7, 2.45, 0.42, 0.0, ease.outCubic),
      // L03: a slow orbit round to the right, pushing in
      this.orbit(T.typeOut, O, -15, 5.5, 1.95, 0.37, 0.02, ease.inOutQuad),
      // the push into the cloud behind the Berlin card, landing on the downbeat
      this.orbit(T.berlin, close, -9, 4, 0.66, 0, 0, ease.inOutCubic),
      // close on the region through the overwrite, drifting
      this.orbit(T.wave2, close, -3, 3, 0.62, 0, 0, ease.linear),
      // back out for the query and the stamps: the cloud on the right, the stamps' column on the left
      this.orbit(T.stamps[0]! - 0.1, O, -14, 4, 1.62, 0.36, 0.02, ease.inOutCubic),
      this.orbit(T.drop, O, -8, 3.5, 1.56, 0.34, 0.02, ease.linear),
      // the collapse: the camera cranes down and back as the cloud falls, to see it pour into the line, then settles
      // square to the terminal as it resolves: deadpan
      this.orbit(T.drop + 0.32, new THREE.Vector3(0, -0.2, 0.08), 0, 2, 2.05, 0, 0, ease.inOutCubic),
      this.orbit(T.resolve, P, 0, 0, 0.84, 0, 0, ease.inOutCubic),
      this.orbit(T.end, P, 0, 0, 0.8, 0, 0, ease.linear),
    ]);
  }

  /** A scratch camera where the rig has the stage's at t. */
  private camAt(t: number) {
    const cam = this.scratch;
    cam.aspect = 16 / 9;
    cam.near = 0.02;
    cam.far = 20;
    this.rig.apply(cam, t);
    return cam;
  }

  /** The world point at logical px (x, y) on the plane z (world), the camera where the rig has it at t. */
  private unproject(t: number, x: number, y: number, z: number) {
    const cam = this.camAt(t);
    const p = new THREE.Vector3((x / 1920) * 2 - 1, 1 - (y / 1080) * 2, 0.5).unproject(cam);
    const dir = p.sub(cam.position).normalize();
    return cam.position.clone().addScaledVector(dir, (z - cam.position.z) / dir.z);
  }

  /**
   * The numeral why? lights: one on the cloud's face, at the depth the focus holds then (the region's), that the camera
   * shows right of the frame's middle when she asks; and where the ping starts (under the chip, up and left of it).
   */
  private pickWhy() {
    const cam = this.camAt(this.T.why + 0.25), want = { x: 1220, y: 600 };
    const depth = (p: THREE.Vector3) => -p.clone().applyMatrix4(cam.matrixWorldInverse).z;
    const dR = depth(this.R);
    let best = this.cloud.numerals[0]!, bd = Infinity;
    for (const n of this.cloud.numerals) {
      const c = new THREE.Vector3(n.x + (CELLS / 2) * ADV, n.y + 0.365 * EM, n.z);
      if (Math.abs(depth(c) - dR) > 0.02 || n.regionRow >= 0) continue;
      const p = c.clone().project(cam);
      const d = Math.hypot((p.x + 1) * 960 - want.x, (1 - p.y) * 540 - want.y);
      if (d < bd) (bd = d), (best = n);
    }
    this.whyNumeral = best;
    const c = new THREE.Vector3(best.x + (CELLS / 2) * ADV, best.y + 0.365 * EM, best.z), px = c.clone().project(cam);
    this.whyAt = this.unproject(this.T.why + 0.25, (px.x + 1) * 960 + WHY_CHIP.dx + 40, (1 - px.y) * 540 + WHY_CHIP.dy - 10, best.z);
  }

  /** A world point as logical px, through the stage's camera as it is now. */
  private toPx(p: THREE.Vector3) {
    const v = p.clone().project(this.stage.camera);
    return { x: (v.x + 1) * 960, y: (1 - v.y) * 540 };
  }

  // ---------------------------------------------------------------------------------------------- render

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, u = this.field.u;
    this.rig.apply(st.camera, t);

    // the cloud's clock and light: the sweep on the reveal, a breath of light on every beat, the region lifting while
    // the camera is on it, the pings, the numeral why? lights
    u.uTime.value = t;
    // (two sweeps: the reveal's, and one as "store" lands, with the hero's own)
    const sw1 = prog(t, T.reveal - 0.08, T.reveal + 0.62, ease.inOutCubic), sw2 = prog(t, T.store + 0.02, T.store + 0.6, ease.inOutCubic);
    const sw = sw1 > 0 && sw1 < 1 ? sw1 : sw2;
    u.uSweep.value.set(0.94, 0.12, 0.32, lerp(-0.9, 0.9, sw));
    u.uSweepK.value.set(0.07, sw > 0 && sw < 1 ? (sw1 > 0 && sw1 < 1 ? 0.28 : 0.2) * Math.sin(Math.PI * sw) : 0, 0, 0);
    // (at the cut the cloud is dark round the seeds, and comes up as they glide in)
    u.uFade.value.set(lerp(SEED.cloud0, 1, prog(t, T.start, T.start + SEED.rise, ease.inOutCubic)), 0.85, 0.03 * onBeat(f, 0.25), 0);
    u.uRegion.value.x = prog(t, T.berlin - 0.3, T.berlin + 0.2) * (1 - prog(t, T.stamps[0]! - 0.4, T.stamps[0]!));
    u.uRegion.value.w = 0.06 * pulse(t, T.berlinSettle, 0.25);
    u.uPing.value[0]!.set(this.R.x, this.R.y, this.R.z, T.query + 0.12);
    u.uPing.value[1]!.set(this.whyAt.x, this.whyAt.y, this.whyAt.z, T.why + 0.06);
    u.uLit.value.set(this.whyNumeral.id, prog(t, T.why + 0.2, T.why + 0.32) * (1 - prog(t, T.drop - 0.02, T.drop + 0.1)), 0, 0);
    // shockwaves: the Berlin card's landing, and the stamps
    u.uShock.value[0]!.set(this.R.x, this.R.y, this.R.z, T.berlin);
    u.uShockK.value[0]!.set(0.004, 0.5, 0.03, 4);
    this.shocks.forEach((c, i) => {
      u.uShock.value[i + 1]!.set(c.x, c.y, c.z, T.stamps[i]!);
      u.uShockK.value[i + 1]!.set(0.014, 1.1, 0.07, 3.2);
    });

    // the actors: the cards' letters, and the fatal line
    this.actors.begin();
    this.poseCard(this.berlin, t, true);
    this.poseCard(this.lisbon, t, false);
    this.poseLine(t);
    this.poseSeeds(t);
    this.actors.end();
    this.term.opacity = prog(t, T.resolve - 0.2, T.resolve + 0.06, ease.outCubic);
    this.term.mesh.visible = this.term.opacity > 0;
    if (this.term.mesh.visible) this.term.draw(t);

    // focus, in diopters, as a focus ring turns: the cloud's face, the card, the region, the line
    const focus = 1 / this.focusDiopters(t);
    // (the soft haze off the focus plane steps back from the start; at the cut it is lower still, round the seeds)
    u.uFocus.value.set(focus, 0.012, 0.07, lerp(1, 0.34, prog(t, T.start + 0.05, T.start + 0.45)) * lerp(0.55, 1, prog(t, T.start, T.start + SEED.rise)));
    st.render(out, { dof: { focus, fstop: t < T.drop ? 1.2 : 2.4 } });

    // L03's hero over the cloud
    if (t < T.typeOut + 0.4 && this.hero.update(t, [T.vector, T.store], [T.typeOut, T.typeOut + 0.34], ZOOM_AT)) this.hero.render(out);

    // the 2D layer: L03's flat type and label, the queries, the tooltip, the stamps
    this.draw2D(t);
    const { comp, renderer } = this.ctx;
    comp.draw(renderer, this.glowLayer.upload(), out, { mode: 'add', tint: glow('blood', 2.2) });
    comp.draw(renderer, this.layer.upload(), out);

    // the stamps jolt the frame; the landing and the resolve punch in a hair
    let shake = 0, zoom = 0;
    for (const at of T.stamps) {
      if (t < at) continue;
      const dt = t - at;
      shake += 7 * Math.exp(-dt * 22) * Math.cos(dt * 2 * Math.PI * 11);
      zoom += 0.012 * pulse(t, at, 0.07);
    }
    zoom += 0.007 * pulse(t, T.berlin, 0.1) + 0.006 * pulse(t, T.resolve, 0.12);
    return { shake: [0, shake], zoom: 1 + zoom };
  }

  private focusDiopters(t: number) {
    const T = this.T, st = this.stage;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const face = inv(new THREE.Vector3(-0.08, 0.02, SPHEROID.rz * 0.93));
    const cardAt = inv(this.berlin.group.position), lis = inv(this.lisbon.group.position);
    const region = inv(this.R), lineAt = inv(this.line);
    return keys(t, [
      [T.start, face * 1.9],
      [T.start + 0.32, face, ease.outCubic],
      [T.typeOut, face],
      [T.typeOut + 0.25, cardAt, ease.inOutCubic],
      [T.berlin, cardAt],
      [T.berlin + 0.3, region, ease.inOutCubic],
      [T.lisbonIn, region],
      [T.lisbonIn + 0.12, lis, ease.outCubic],
      [T.lisbonDive, lis],
      [T.lisbonDive + 0.2, region, ease.inOutCubic],
      [T.drop, region],
      [T.drop + 0.35, lineAt, ease.inOutCubic],
      [T.end, lineAt],
    ]);
  }

  // ---------------------------------------------------------------------------------------------- the match cut in

  /**
   * The numeral each seed lands on: the one on the cloud's face (the focus's depth once it has racked there) that the
   * camera shows nearest the seed's fibre at the cut, each its own; not the region's or the named three (they have
   * their own business).
   */
  private pickSeeds(pts: { x: number; y: number }[]) {
    const T = this.T, cam = this.camAt(T.start);
    const depth = (p: THREE.Vector3) => -p.clone().applyMatrix4(cam.matrixWorldInverse).z;
    const face = depth(new THREE.Vector3(-0.08, 0.02, SPHEROID.rz * 0.93));
    const taken = new Set<number>(this.cloud.named.map((n) => n.id));
    const centreOf = (n: Numeral) => new THREE.Vector3(n.x + (CELLS / 2) * ADV, n.y + 0.365 * EM, n.z);
    const near = this.cloud.numerals.filter((n) => n.regionRow < 0 && Math.abs(depth(centreOf(n)) - face) < 0.03).map((n) => {
      const v = centreOf(n).project(cam);
      return { n, x: (v.x + 1) * 960, y: (1 - v.y) * 540 };
    });
    this.seeds = pts.map((p, i) => {
      let best = near[0]!, bd = Infinity;
      for (const c of near) {
        if (taken.has(c.n.id)) continue;
        const d = Math.hypot(c.x - p.x, c.y - p.y);
        if (d < bd) (bd = d), (best = c);
      }
      taken.add(best.n.id);
      return { p, n: best.n, tilt: SEED.tilt * (2 * hash(i, 4041) - 1) };
    });
  }

  /**
   * The seeds: on its fibre's point at the cut, sharp (at the focus) and bright, a stroke of dashes morphing into its
   * numeral's cells; then each glides on screen from the fibre's point to its numeral's, in depth from the focus to the
   * numeral, growing to the cloud's em and dimming to the numeral's strength, and is gone as it arrives (the numeral is
   * there, the same text).
   */
  private poseSeeds(t: number) {
    const T = this.T, st = this.stage, cam = st.camera, dt = t - T.start;
    if (dt > SEED.gone || !this.seeds.length) return;
    const pxPerM = (d: number) => H / 2 / (d * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2));
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion), up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    const focus = 1 / this.focusDiopters(t);
    const k = prog(dt, SEED.glide0, SEED.glide1, ease.inOutCubic);
    const dash = this.atlas.of(RULE);
    this.seeds.forEach((s, i) => {
      const n = s.n, Q = new THREE.Vector3(n.x + (CELLS / 2) * ADV, n.y + 0.365 * EM, n.z);
      const dQ = st.depthOf(Q), q = this.toPx(Q);
      // where it is on screen and in depth, and its em on screen
      const x = lerp(s.p.x, q.x, k), y = lerp(s.p.y, q.y, k), d = lerp(focus, dQ, k);
      const emPx = lerp(SEED.em, EM * pxPerM(dQ), k);
      const m2w = 1 / pxPerM(d);
      const c = cam.position.clone().addScaledVector(fwd, d).addScaledVector(right, (x - W / 2) * m2w).addScaledVector(up, (H / 2 - y) * m2w);
      // its em, turned in the screen's plane by its tilt (the fibre's slant), which straightens as it glides
      const a = s.tilt * (1 - k), em = emPx * m2w;
      const r = right.clone().multiplyScalar(Math.cos(a)).addScaledVector(up, Math.sin(a)).multiplyScalar(em);
      const u = up.clone().multiplyScalar(Math.cos(a)).addScaledVector(right, -Math.sin(a)).multiplyScalar(em);
      const origin = c.addScaledVector(r, -(CELLS / 2) * 0.6).addScaledVector(u, -0.365);
      // bright on the cut, settling to the numeral's strength as it lands; gone as it arrives
      // the stroke turns into its cells from the left, one after another: on the cut half line, half numeral
      const m0 = 0.012 * hash(i, 4042);
      const col = boneAt(lerp(1, n.bright, k));
      const alpha = 1 - prog(dt, SEED.glide1 - 0.06, SEED.gone, ease.inOutQuad);
      Array.from(n.text).forEach((ch, ci) => {
        const g = this.atlas.of(ch);
        if (g < 0 && ch === ' ') return;
        const m = prog(dt, m0 + ci * SEED.cascade, m0 + ci * SEED.cascade + SEED.cell, ease.inOutCubic);
        this.actors.add({
          origin: origin.clone().addScaledVector(r, ci * 0.6), right: r, up: u,
          glyph: m >= 1 ? [g, -1, 0, 0] : [dash, g, m, 2], color: [...col, alpha],
        });
      });
    });
  }

  // ---------------------------------------------------------------------------------------------- the cards

  /**
   * A card's flight and its letters: it rides in just ahead of the camera, facing it, then breaks away, turns square
   * and settles over the region as the camera arrives; its letters melt into the cells of its floats (a cascade, left
   * to right) as the card fades; then Berlin's floats drop into their slots of the row (where the cloud takes them over)
   * and Lisbon's dive into the row and are gone as it flips.
   */
  private poseCard(c: Card, t: number, isB: boolean) {
    const T = this.T, g = c.group, mid = this.cloud.region[1]!;
    const t0 = isB ? T.typeOut - 0.02 : T.lisbonIn, t1 = isB ? T.berlin : T.lisbonMorph + 0.05;
    const morph0 = isB ? T.berlinMorph : T.lisbonMorph;
    const gone = isB ? T.berlinSettle : T.wave1 - 0.2;
    if (t < t0 || t > gone + 0.05) {
      c.panel.mesh.visible = false;
      return;
    }
    // where it hangs: its text line over the row, a little in front of it (Lisbon higher, over Berlin's floats)
    const first = mid[isB ? BERLIN_SLOTS[0] : 0]!;
    const rest = new THREE.Vector3(first.x - 0.004, first.y + (isB ? 0.034 : 0.05), first.z + 0.016);
    // carried into the cloud: it rides just ahead of the camera, then breaks away and settles over the row
    const cam = this.stage.camera;
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion), side = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion);
    // (Berlin comes in on the cloud's side as the type leaves on the other; Lisbon a little further off)
    const ride = cam.position.clone().addScaledVector(fwd, isB ? 0.36 : 0.48).addScaledVector(side, isB ? 0.035 : 0.0).addScaledVector(Y, 0.004);
    const k = prog(t, t0, t1, ease.inOutCubic);
    const pos = ride.lerp(rest, k).add(new THREE.Vector3(0.006 * prog(t, t0, gone), 0, 0));
    g.quaternion.copy(cam.quaternion).slerp(new THREE.Quaternion(), ease.inOutQuad(k));
    g.position.copy(pos);
    // the panel hangs about the text: its row's left end, on the baseline, at `pos`
    const { x: x0, baseline: base } = c.panel.textOrigin(0);
    g.position.sub(this.panelPoint(c.panel, g, x0, base).sub(g.position));
    g.updateMatrixWorld(true);
    // the card fades as its letters melt
    const fade = prog(t, morph0 + 0.08, morph0 + 0.32, ease.inOutCubic);
    c.panel.mesh.visible = fade < 1;
    c.panel.opacity = (1 - fade) * prog(t, t0, t0 + 0.08);
    if (c.panel.mesh.visible) c.panel.draw(t);
    // its letters
    const right = new THREE.Vector3(1, 0, 0).transformDirection(g.matrixWorld).multiplyScalar(EM);
    const up = new THREE.Vector3(0, 1, 0).transformDirection(g.matrixWorld).multiplyScalar(EM);
    const bone = boneAt(0.92), cloudCol = boneAt(0.64);
    for (let i = 0; i < c.chars.length; i++) {
      const a = this.atlas.of(c.chars[i]!), b = this.atlas.of(c.targets[i]!);
      if (a < 0 && b < 0) continue;
      // (its cell on the card's mono grid: (i·0.6)·size, not cellOrigin's i·adv, which can differ in the last bit)
      const at = this.panelPoint(c.panel, g, x0 + i * 0.6 * CARD_PX, base, 0.6);
      // the melt: a cascade from the left, each letter over 0.16 s
      const m = prog(t, morph0 + 0.011 * i, morph0 + 0.011 * i + 0.16, ease.inOutCubic);
      // then the float this cell belongs to goes to the row: Berlin's to its slot, Lisbon's into its slot and gone
      const fi = Math.floor(i / CELLS), ci = i % CELLS;
      const slotN = mid[isB ? BERLIN_SLOTS[fi]! : fi]!;
      const target = new THREE.Vector3(slotN.x + ci * ADV, slotN.y, slotN.z);
      const go0 = isB ? T.berlinMorph + 0.2 + 0.03 * fi : T.lisbonDive + 0.025 * fi;
      const go = prog(t, go0, go0 + (isB ? 0.18 : 0.13), isB ? ease.inOutCubic : ease.inQuad);
      const p = at.lerp(target, go);
      const r = right.clone().lerp(new THREE.Vector3(EM, 0, 0), go), uu = up.clone().lerp(new THREE.Vector3(0, EM, 0), go);
      // each cell brightens for an instant as it turns (the letter's meaning going into the number), then settles to
      // the cloud's own strength
      const flare = 0.22 * Math.sin(Math.PI * m);
      const col = [0, 1, 2].map((j) => Math.min(LIN.bone[j]!, lerp(bone[j]!, cloudCol[j]!, Math.max(m, go)) + flare)) as [number, number, number];
      let alpha = prog(t, t0, t0 + 0.06);
      // Berlin's cells hand over to the cloud's own as they settle; Lisbon's are gone as they reach the row
      alpha *= isB ? (t < T.berlinSettle ? 1 : 0) : 1 - prog(t, go0 + 0.1, go0 + 0.15);
      this.actors.add({ origin: p, right: r, up: uu, glyph: m >= 1 ? [b, -1, 0, 0] : [a, b, m, m > 0 ? 2 : 0], color: [...col, alpha] });
    }
  }

  // ---------------------------------------------------------------------------------------------- the line

  /**
   * The fatal line, cell by cell: a cell lights when the first numeral lands in it and shows a new digit with each
   * landing; then its last flaps come down on its character on the resolve's downbeat. Bone-dim; "commits" turns blood
   * a beat later.
   */
  private poseLine(t: number) {
    const T = this.T;
    if (t < T.drop) return;
    const right = new THREE.Vector3(EM, 0, 0), up = new THREE.Vector3(0, EM, 0);
    const dim = LIN.boneDim, blood = glow('bloodBright', 1.45);
    Array.from(FATAL).forEach((ch, s) => {
      const arr = this.arrivals[s]!;
      let landed = 0;
      while (landed < arr.length && arr[landed]! <= t) landed++;
      const g = this.atlas.of(ch);
      const step = 0.042 + 0.03 * hash(s, 62), steps = 2 + Math.floor(hash(s, 61) * 3);
      const origin = this.line.clone().add(new THREE.Vector3(s * ADV, 0, 0));
      if (t >= T.resolve) {
        if (g < 0) return;
        const blooded = s >= COMMITS.at && s < COMMITS.at + COMMITS.n ? prog(t, T.punch - 0.03, T.punch + 0.08, ease.outCubic) : 0;
        const flash = 0.12 * pulse(t, T.resolve, 0.12);
        const col = [0, 1, 2].map((j) => lerp(dim[j]!, blood[j]!, blooded) + flash) as [number, number, number];
        this.actors.add({ origin, right, up, glyph: [g, -1, 0, 0], color: [...col, 1] });
        return;
      }
      // until its last flaps: the digit of its latest landing, flashing as each lands; its last flaps come down on its
      // character on the resolve's downbeat, each cell's own speed (out of phase, landing together)
      const run = flapAt(t, T.resolve, steps, step);
      if (landed === 0 && run.k < 0) return;
      const now = String(Math.floor(hash(s, 7, landed) * 10));
      const b = boneAt(0.5 + 0.35 * pulse(t, landed ? arr[landed - 1]! : T.resolve - steps * step, 0.05));
      if (run.k >= 0) {
        const at = (k: number) => (k <= 0 ? now : flapDigit(s * 31 + 7, k, now, ch));
        const from = this.atlas.of(at(run.k)), to = run.k === steps - 1 ? g : this.atlas.of(at(run.k + 1));
        this.actors.add({ origin, right, up, glyph: [from, to, run.p * run.p, 1], color: [...b, 1] });
      } else this.actors.add({ origin, right, up, glyph: [this.atlas.of(now), -1, 0, 0], color: [...b, 1] });
    });
  }

  // ---------------------------------------------------------------------------------------------- 2D

  private draw2D(t: number) {
    const T = this.T, c = this.layer.ctx, gc = this.glowLayer.ctx;
    this.layer.clear();
    this.glowLayer.clear();

    // L03: the flat lines and the label, zooming through as the camera pushes into the cloud
    if (t < T.typeOut + 0.4) {
      const out = prog(t, T.typeOut, T.typeOut + 0.34, ease.inCubic);
      c.save();
      const s = 1 / (1 - 0.93 * out); // the hero's own spread (ex-type.ts): the whole block flies past as one
      c.translate(ZOOM_AT.x, ZOOM_AT.y);
      c.scale(s, s);
      c.translate(-ZOOM_AT.x, -ZOOM_AT.y);
      if (out > 0) c.filter = `blur(${(out * 14).toFixed(2)}px)`;
      const a = 1 - prog(out, 0.1, 0.6);
      const [w1, w2, w3] = L03A.split(' ') as [string, string, string];
      const [v1, v2] = L03B.split(' ') as [string, string];
      drawWords(c, t, [{ text: w1, at: T.its }, { text: w2, at: T.not }, { text: w3, at: T.you }], L03.fam, L03.px, X0, L03.y1, rgba('bone'), a);
      drawWords(c, t, [{ text: v1, at: T.its2 }, { text: v2, at: T.your }], L03.fam, L03.px, X0, L03.y2, rgba('bone'), a * 0.72);
      // the label, typed in with "vector": the file, and its zero commits, the zero in blood
      const zero = LABEL.lastIndexOf('0 ');
      drawTyped(c, t, T.vector - 0.04, [
        { text: LABEL.slice(0, zero), color: rgba('boneDim') },
        { text: LABEL.slice(zero, zero + 1), color: rgba('bloodBright') },
        { text: LABEL.slice(zero + 1), color: rgba('boneDim') },
      ], F.mono(400), LABEL_PX, X0 + 4, LABEL_Y, a, 72);
      c.restore();
    }

    // the ghost query: berlin?, in the clear on the left, aimed at the region along a dashed hairline; a ping goes
    // through the cloud from there; nothing answers, the line draws back and the chip flickers out
    const q = prog(t, T.query, T.query + 0.12, ease.outCubic) * (1 - prog(t, T.query + 0.34, T.query + 0.46, ease.inOutCubic));
    if (q > 0) {
      const R2 = this.toPx(this.R);
      const flick = t > T.query + 0.28 && t < T.query + 0.4 ? 0.45 + 0.55 * Math.abs(Math.cos((t - T.query) * 60)) : 1;
      const qx = X0, qy = 560, w = drawQuery(c, BERLIN_Q, qx, qy, q * flick, true);
      const reach = prog(t, T.query + 0.02, T.query + 0.14, ease.outCubic) * (1 - prog(t, T.query + 0.26, T.query + 0.38, ease.inCubic));
      if (reach > 0) {
        const x0 = qx + w + 10, y0 = qy - 11, x1 = lerp(x0, R2.x - 8, reach), y1 = lerp(y0, R2.y, reach);
        c.save();
        c.globalAlpha = q * flick;
        c.setLineDash([5, 6]);
        c.strokeStyle = rgba('boneDim', 0.8);
        c.lineWidth = 1.5;
        c.beginPath();
        c.moveTo(x0, y0);
        c.lineTo(x1, y1);
        c.stroke();
        c.restore();
      }
    }

    // the stamps, on successive beats, then falling with the cloud
    STAMPS.forEach((s, i) => {
      const p = stampPose(t, T.stamps[i]!, T.drop + 0.05 * (2 - i), X0, STAMP_Y[i]!, STAMP_TILT[i]!, 900 + i);
      if (p.dy > 1300) return;
      drawStamp(c, s, p);
      drawStampGlow(gc, s, p, 1.3 * p.glow);
    });

    // why?: a chip at the left of the cloud pings it; one numeral lights, and its tooltip gives a score
    const live = 1 - prog(t, T.drop - 0.05, T.drop + 0.06);
    const wk = prog(t, T.why - 0.06, T.why + 0.1, ease.outCubic) * live;
    if (wk > 0) {
      const n = this.whyNumeral;
      const o = this.toPx(new THREE.Vector3(n.x, n.y, n.z));
      drawQuery(c, WHY_Q, o.x + WHY_CHIP.dx, o.y + WHY_CHIP.dy, wk, false);
      const p0 = this.toPx(new THREE.Vector3(n.x + ADV, n.y - 0.1 * EM, n.z)), p1 = this.toPx(new THREE.Vector3(n.x + CELLS * ADV, n.y + 0.8 * EM, n.z));
      drawBrackets(c, p0.x, p1.y, p1.x, p0.y, prog(t, T.why + 0.2, T.why + 0.34, ease.outCubic) * live);
      drawTooltip(c, COSINE, p1.x + 70, p1.y - 34, p1.x + 10, (p0.y + p1.y) / 2, prog(t, T.why + 0.3, T.why + 0.46, ease.outCubic) * live);
    }
  }

  override dispose() {
    this.field?.dispose();
    this.actors?.dispose();
    this.atlas?.dispose();
    this.hero?.dispose();
    for (const card of [this.berlin, this.lisbon]) card?.panel.dispose();
    this.term?.dispose();
    disposeLayer(this.layer);
    disposeLayer(this.glowLayer);
    this.stage?.dispose();
  }
}
