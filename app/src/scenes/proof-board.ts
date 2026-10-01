// The board under the figure in `proof`: the sparkline that climbs with the odometer, its round tags, the six
// per-category bars that flash on the downbeat, and the two footnotes. All of it is flat (unlit planes and flat
// Type3D, a sliver deep with no bevel: crisp graphic type and hairlines in the figure's own plane), so it stands in the
// same world as the drums and the camera reveals it as one object; only the drums are hero type.
//
// Layout in em of the figure, from its origin (the figure's left end on the baseline), y up:
//   the rule        a hairline under the figure, the figure's whole width, drawn on at the slam
//   the bars        left: label | well and fill | value, a row per category, top down
//   the sparkline   right: a node per round, evenly spaced, at its score; tags under the nodes. While the figure has
//                   two digits it is the chart beside it, climbing away to the right under the space .4% will fill
//   the footnotes   two lines under it all, the source and the quote
// Colour by meaning: the line and its tags bone (dim, the current round's brightest); the moss is the gain only, the
// line's head as it climbs, the v7 node, the bars' fills as they flash in and settle.
import * as THREE from 'three';
import { Type3D } from '../engine/type3d';
import { F } from '../engine/type';
import { LIN } from '../engine/palette';
import { glow } from '../engine/look';
import { clamp, ease, lerp, prog, pulse } from '../engine/util';

type RGB = readonly [number, number, number];
/** Flat type: a sliver of depth (em), no bevel. */
const FLAT = { depth: 0.002, bevel: 0 } as const;

const unlit = (rgb: RGB) => new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]) });
/** A colour `k` of the way from ink to `rgb` (the board fades in against the ink it stands on). */
function fromInk(m: THREE.MeshBasicMaterial, rgb: RGB, k: number) {
  const i = LIN.ink;
  m.color.setRGB(lerp(i[0], rgb[0], k), lerp(i[1], rgb[1], k), lerp(i[2], rgb[2], k));
}

/** The board's geometry (em). `width` is the figure's (the final figure's advance). */
export function boardLayout(width: number) {
  const top = -0.27;
  return {
    rule: { y: -0.13, x0: 0, x1: width, h: 0.0042 },
    bars: { x0: 0, top, pitch: 0.082, label: 0.042, labelW: 0.66, h: 0.013, valueW: 0.13, x1: 1.44 },
    spark: { x0: 1.74, x1: width - 0.1, y0: -0.66, y1: top + 0.01, lo: 40, hi: 100, line: 0.005, node: 0.015, tag: 0.045, tagY: -0.8 },
    notes: { size: 0.048, y1: -0.94, y2: -1.04 },
  };
}
export type BoardLayout = ReturnType<typeof boardLayout>;

/** How far above its place on the board the chart stands beside a two-digit figure (em): its tags just over the
 * rule, its top level with the figure's cap. */
export const BESIDE = 0.86;

/** A node's place on the sparkline (em): evenly spaced rounds, the score up the chart. */
export function sparkPoint(L: BoardLayout, i: number, n: number, value: number): [number, number] {
  const s = L.spark;
  return [lerp(s.x0, s.x1, n > 1 ? i / (n - 1) : 0), lerp(s.y0, s.y1, (value - s.lo) / (s.hi - s.lo))];
}

/** When each element of the board moves (song seconds). */
export interface BoardTimes {
  /** The first node and its tag, as the first figure is said. */
  first: number;
  /** The rule draws on. */
  rule: number;
  /** The chart drops from beside the figure to under its % (from, to). */
  drop: readonly [number, number];
  /** Each round's roll (kick, landing): the line's head runs to its node. */
  kicks: readonly number[];
  lands: readonly number[];
  /** The bars flash in; the footnotes type. */
  bars: number;
  note1: number;
  note2: number;
}

interface Row { label: Type3D; value: Type3D; well: THREE.Mesh; fill: THREE.Mesh; flash: THREE.Mesh; v: number; mats: THREE.MeshBasicMaterial[] }

export class Board {
  readonly group = new THREE.Group();
  /** The sparkline and its tags: beside the figure while it has two digits, under its % once it has five. */
  readonly chart = new THREE.Group();
  private mats: THREE.Material[] = [];
  private geos: THREE.BufferGeometry[] = [];
  private types: Type3D[] = [];
  private rule!: THREE.Mesh;
  private ruleMat!: THREE.MeshBasicMaterial;
  private segs: THREE.Mesh[] = [];
  private segMat!: THREE.MeshBasicMaterial;
  private nodes: THREE.Mesh[] = [];
  private nodeMats: THREE.MeshBasicMaterial[] = [];
  private head!: THREE.Mesh;
  private tags: { type: Type3D; mat: THREE.MeshBasicMaterial }[] = [];
  private rows: Row[] = [];
  private notes: { type: Type3D; mat: THREE.MeshBasicMaterial; n: number }[] = [];
  private pts: [number, number][] = [];
  readonly L: BoardLayout;

  /**
   * `size`: world units per em. `rounds`: each round's tag and score. `bars`: each category's label and score, as
   * shown. `notes`: the two footnotes. `width`: the figure's width (em).
   */
  constructor(
    readonly size: number,
    rounds: readonly { tag: string; value: number }[],
    bars: readonly { label: string; value: string }[],
    notes: readonly [string, string],
    width: number,
  ) {
    const L = (this.L = boardLayout(width));
    this.group.add(this.chart);
    const plane = this.geo(new THREE.PlaneGeometry(1, 1).translate(0.5, 0, 0)); // grows from its left end
    const disc = this.geo(new THREE.CircleGeometry(1, 32));
    const mat = (rgb: RGB) => this.mat(unlit(rgb));
    const flat = (text: string, family: string, em: number, m: THREE.Material) => {
      const t = new Type3D(text, { family, size: em * size, ...FLAT }, m);
      this.types.push(t);
      this.group.add(t.group);
      return t;
    };

    // the rule under the figure
    this.ruleMat = mat(LIN.ruleStrong);
    this.rule = new THREE.Mesh(plane, this.ruleMat);
    this.rule.position.set(L.rule.x0 * size, L.rule.y * size, 0);
    this.group.add(this.rule);

    // the sparkline: a segment per climb, a node per round, the head that writes it, a tag under each node
    this.pts = rounds.map((r, i) => sparkPoint(L, i, rounds.length, r.value));
    this.segMat = mat(LIN.boneDim);
    for (let i = 1; i < rounds.length; i++) {
      const s = new THREE.Mesh(plane, this.segMat);
      const [x0, y0] = this.pts[i - 1]!, [x1, y1] = this.pts[i]!;
      s.position.set(x0 * size, y0 * size, 0.0004);
      s.rotation.z = Math.atan2(y1 - y0, x1 - x0);
      this.segs.push(s);
      this.chart.add(s);
    }
    rounds.forEach((r, i) => {
      const m = mat(LIN.bone);
      const n = new THREE.Mesh(disc, m);
      n.position.set(this.pts[i]![0] * size, this.pts[i]![1] * size, 0.0008);
      this.nodes.push(n);
      this.nodeMats.push(m);
      this.chart.add(n);
      const tm = mat(LIN.boneFaint);
      const tag = flat(r.tag, F.mono(500), L.spark.tag, tm);
      this.chart.add(tag.group);
      tag.group.position.set(this.pts[i]![0] * size - tag.width / 2, L.spark.tagY * size, 0);
      this.tags.push({ type: tag, mat: tm });
    });
    this.head = new THREE.Mesh(disc, mat(glow('moss', 3)));
    this.chart.add(this.head);

    // the bars: label, well and fill, value
    const B = L.bars, barX = B.x0 + B.labelW, barW = B.x1 - B.valueW - barX;
    bars.forEach((b, k) => {
      const y = B.top - k * B.pitch;
      const lm = mat(LIN.boneDim), vm = mat(LIN.bone), wm = mat(LIN.panel2), fm = mat(LIN.moss), gm = mat(glow('moss', 3));
      const label = flat(b.label, F.mono(400), B.label, lm);
      // (the label's x-height centred on the bar: JetBrains Mono's x-height is 0.55 em)
      label.group.position.set(B.x0 * size, (y - 0.275 * B.label) * size, 0);
      const value = flat(b.value, F.mono(500), B.label, vm);
      value.group.position.set(B.x1 * size - value.width, (y - 0.275 * B.label) * size, 0);
      const well = new THREE.Mesh(plane, wm), fill = new THREE.Mesh(plane, fm), flash = new THREE.Mesh(plane, gm);
      for (const [m, z] of [[well, 0], [fill, 0.0004], [flash, 0.0008]] as const) {
        m.position.set(barX * size, y * size, z);
        m.scale.set(barW * size, B.h * size, 1);
        this.group.add(m);
      }
      this.rows.push({ label, value, well, fill, flash, v: Number(b.value), mats: [lm, vm, wm, fm, gm] });
    });

    // the footnotes
    notes.forEach((text, i) => {
      const m = mat(LIN.boneDim);
      const type = flat(text, i === 0 ? F.mono(400) : F.mono(400, true), L.notes.size, m);
      type.group.position.set(0, (i === 0 ? L.notes.y1 : L.notes.y2) * size, 0);
      this.notes.push({ type, mat: m, n: type.glyphs.length });
    });
  }

  private mat<M extends THREE.Material>(m: M): M {
    this.mats.push(m);
    return m;
  }

  private geo<G extends THREE.BufferGeometry>(g: G): G {
    this.geos.push(g);
    return g;
  }

  /**
   * The board at t. `round` and `u` are the odometer's (drumsAt): the round rolling or shown and its roll's progress,
   * eased as the drums are (`climb`), so the line's head reaches each node as its figure lands.
   */
  update(t: number, T: BoardTimes, round: number, climb: number, beat: number) {
    const s = this.size, L = this.L;
    // the chart: beside the figure, then down under the % as the last round brings in its decimal
    this.chart.position.y = BESIDE * (1 - prog(t, T.drop[0], T.drop[1], ease.inOutCubic)) * s;
    // the rule: drawn on from the left at the slam
    const rk = prog(t, T.rule, T.rule + 0.45, ease.outExpo);
    this.rule.visible = rk > 0;
    this.rule.scale.set(Math.max(1e-4, rk * (L.rule.x1 - L.rule.x0) * s), L.rule.h * s, 1);

    // the line: the segments climbed so far, the one climbing now up to its head
    let hx = 0, hy = 0, headK = 0;
    this.segs.forEach((g, i) => {
      const r = i + 1; // the round this segment climbs to
      const k = r < round ? 1 : r === round ? climb : 0;
      const [x0, y0] = this.pts[i]!, [x1, y1] = this.pts[r]!;
      const len = Math.hypot(x1 - x0, y1 - y0);
      g.visible = k > 0;
      g.scale.set(Math.max(1e-4, k * len * s), L.spark.line * s, 1);
      if (r === round && k < 1) {
        hx = lerp(x0, x1, k);
        hy = lerp(y0, y1, k);
        headK = 1;
      }
    });
    // the head: a moss light writing the climb, gone as the node lands
    this.head.visible = headK > 0;
    this.head.position.set(hx * s, hy * s, 0.0012);
    this.head.scale.setScalar(L.spark.node * 0.85 * s);

    // the nodes and tags: each pops as its figure lands (the first as it is said); the current tag brightest
    const at = (i: number) => (i === 0 ? T.first : T.lands[i - 1]!);
    const last = this.nodes.length - 1;
    this.nodes.forEach((n, i) => {
      const k = clamp(prog(t, at(i) - 0.02, at(i) + 0.14, ease.outBack));
      n.visible = k > 0;
      n.scale.setScalar(Math.max(1e-4, k) * L.spark.node * s * (1 + 0.6 * pulse(t, at(i), 0.08)));
      // the v7 node is the gain: moss, flaring as it lands
      if (i === last) {
        const g = glow('moss', 1 + 1.6 * pulse(t, at(i), 0.18));
        this.nodeMats[i]!.color.setRGB(g[0], g[1], g[2]);
      }
      const tag = this.tags[i]!, on = prog(t, at(i) - 0.02, at(i) + 0.1);
      const current = i === Math.min(round, last) || (i === last && round >= last);
      fromInk(tag.mat, current ? LIN.bone : LIN.boneFaint, on);
      tag.type.group.visible = on > 0;
    });

    // the bars: a 64th note apart from the downbeat, each fill shooting out to its score with a moss flash at its
    // head, the row's type coming up with it, then the whole bar flashing once and settling
    const stagger = beat / 16;
    this.rows.forEach((r, k) => {
      const t0 = T.bars + k * stagger;
      const on = prog(t, t0 - 0.02, t0 + 0.12);
      const grow = prog(t, t0, t0 + 0.32, ease.outExpo);
      const visible = on > 0;
      for (const m of [r.well, r.fill, r.flash]) m.visible = visible;
      r.label.group.visible = r.value.group.visible = visible;
      if (!visible) return;
      const full = r.well.scale.x;
      r.fill.scale.x = Math.max(1e-4, (grow * r.v) / 100) * full;
      fromInk(r.mats[2]!, LIN.panel2, on);
      fromInk(r.mats[0]!, LIN.boneDim, on);
      fromInk(r.mats[1]!, LIN.bone, prog(t, t0 + 0.12, t0 + 0.24));
      // the flash: the fill's own length, burning moss as it lands and dying back to the fill
      const fl = 0.5 * Math.sin(Math.PI * clamp(grow * 1.2)) + 1.4 * pulse(t, t0 + 0.2, 0.09);
      r.flash.visible = fl > 0.01;
      r.flash.scale.x = r.fill.scale.x;
      const g = glow('moss', 2.2);
      (r.flash.material as THREE.MeshBasicMaterial).color.setRGB(g[0] * fl, g[1] * fl, g[2] * fl);
    });

    // the footnotes, typed
    this.notes.forEach((n, i) => {
      const t0 = i === 0 ? T.note1 : T.note2, cps = 120;
      const shown = Math.floor(clamp((t - t0) * cps, 0, n.n));
      n.type.glyphs.forEach((g, j) => (g.mesh.visible = j < shown));
      n.type.group.visible = shown > 0;
    });
  }

  dispose() {
    for (const t of this.types) t.dispose();
    for (const g of this.geos) g.dispose();
    for (const m of this.mats) m.dispose();
  }
}
