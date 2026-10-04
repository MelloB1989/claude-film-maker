// The history dock under the editor for `diff` (Plan 2 Task 16): `gitloom diff`, its stat, and the commit-history
// scrubber, whose track is the diff thread with the file's commits strung on it as glass beads (the bead string `repo`
// showed: 105ca74, a41c9d0, 8b21e04, 3f9a1c2, history to HEAD, left to right).
//
// The command and its stat are flat mono type set in the editor's plane under its bottom edge (the film's flat type:
// a sliver of depth, unlit). The scrubber floats a little in front of that plane: the thread across the dark, a bead on
// each commit with its hash under it (and the two the diff names, their messages), and the playhead: a bone hairline
// standing behind the thread, so the glass bends it when it stands in a bead. Everything is in the editor's panel px
// (y down from its top edge), placed through the editor's group; the thread and the beads live in the world (the
// thread's radius and the glass's thickness are world lengths), placed through the same transform.
import * as THREE from 'three';
import { Type3D } from '../engine/type3d';
import { F } from '../engine/type';
import { LIN } from '../engine/palette';
import { Bead, beadGeometry, type BeadShape } from '../engine/bead';
import { DIFF_THREAD, Thread } from '../engine/thread3d';

/** Flat type: a sliver of depth (em), no bevel (her-type's FLAT). */
const FLAT = { depth: 0.002, bevel: 0 } as const;

export interface DockCopy {
  cmd: string;
  stat: string;
  /** The history, oldest first: each commit's hash and, for the two the diff names, its message. */
  commits: { hash: string; msg?: string }[];
}

/** The dock's layout in the editor's px: rows under its bottom edge (y down), and the scrubber in front of its plane. */
export const DOCK = {
  /** Baselines of the command and its stat, below the editor's bottom edge; their em; their left end. */
  cmdY: 46, statY: 74, em: 17, x: 24,
  /** The thread's height below the editor's bottom edge, its depth in front of the editor's plane, its ends (x). */
  threadY: 132, z: 18, from: -330, to: 980,
  /** Where each commit sits along it (x, oldest first). */
  commitX: [50, 182, 318, 522],
  /** The labels: the hash's baseline under the thread, the message's under that, their em. */
  hashY: 40, msgY: 62, labelEm: 15,
  /** The playhead: how far it rises above the thread and falls below it, how far behind the thread it stands (px). */
  headUp: 32, headDown: 12, headBack: 26,
} as const;

/** The thread's radius and the beads' (editor px: the editor's group scale makes them world lengths). */
export const THREAD_PX = 3.6;
export const BEAD_PX = 19;

const unlit = (rgb: readonly [number, number, number], opacity = 1) =>
  new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]), transparent: true, opacity });

export class Dock {
  /** In the editor's group: the type and the playhead (panel px / 1000). Slides as one. */
  g = new THREE.Group();
  thread: Thread;
  beads: Bead[] = [];
  beadGeo: THREE.BufferGeometry;
  cmdA: Type3D;
  cmdB: Type3D;
  stat: Type3D;
  hashes: Type3D[] = [];
  msgs: (Type3D | null)[] = [];
  head = new THREE.Group();
  /** Materials by role, faded together. */
  mats = {
    prompt: unlit(LIN.bloodBright), key: unlit(LIN.bone), cmd: unlit(LIN.bone, 0.9), stat: unlit(LIN.boneDim),
    plus: unlit(LIN.moss), minus: unlit(LIN.bloodBright),
    hashOld: unlit(LIN.boneFaint), msg: unlit(LIN.boneDim), head: unlit(LIN.bone),
  };
  /** The named commits' hashes, each its own material (the one the playhead stands on is brought up). */
  hashMats: (THREE.MeshBasicMaterial | null)[] = [];
  /** Each commit's place on the thread (world), the thread's direction there, and the editor's front (world). */
  places: { pos: THREE.Vector3; tangent: THREE.Vector3 }[] = [];
  front = new THREE.Vector3();

  /**
   * `px` maps a point in the editor's px (x right, y down from its top edge, z out of its face) to the world; `front` is
   * the editor's face's direction (world); `scale` is world units per editor px.
   */
  constructor(
    copy: DockCopy,
    private panel: { w: number; h: number },
    px: (x: number, y: number, z: number) => THREE.Vector3,
    front: THREE.Vector3,
    scale: number,
  ) {
    this.front.copy(front).normalize();
    const D = DOCK, base = panel.h;
    // the command: `$ gitloom` heavier (the prompt in blood, the command word bone), the rest at the identifier's tone;
    // the stat under it at the output's, its (+) moss and its (-) blood
    const lead = '$ gitloom';
    const em = D.em / 1000;
    this.cmdA = new Type3D(lead, { family: F.mono(500), size: em, ...FLAT }, (g) => (g.i === 0 ? this.mats.prompt : this.mats.key));
    this.cmdB = new Type3D(copy.cmd.slice(lead.length), { family: F.mono(400), size: em, ...FLAT }, () => this.mats.cmd);
    const plus = copy.stat.indexOf('(+)'), minus = copy.stat.indexOf('(-)');
    this.stat = new Type3D(copy.stat, { family: F.mono(400), size: em, ...FLAT }, (g) =>
      g.i >= plus && g.i < plus + 3 ? this.mats.plus : g.i >= minus && g.i < minus + 3 ? this.mats.minus : this.mats.stat);
    this.at(this.cmdA.group, D.x, base + D.cmdY);
    this.at(this.cmdB.group, D.x + 0.6 * D.em * Array.from(lead).length, base + D.cmdY);
    this.at(this.stat.group, D.x, base + D.statY);
    this.g.add(this.cmdA.group, this.cmdB.group, this.stat.group);

    // the labels: each hash centred under its bead (the diff's two in bone, the older faint), the messages under them
    const le = D.labelEm / 1000;
    copy.commits.forEach((c, i) => {
      const x = D.commitX[i]!, named = !!c.msg;
      const hm = named ? unlit(LIN.bone) : null;
      this.hashMats.push(hm);
      const hash = new Type3D(c.hash, { family: F.mono(named ? 500 : 400), size: le, ...FLAT }, () => hm ?? this.mats.hashOld);
      this.at(hash.group, x - (hash.width * 1000) / 2, base + D.threadY + D.hashY, D.z);
      this.hashes.push(hash);
      this.g.add(hash.group);
      if (c.msg) {
        const msg = new Type3D(c.msg, { family: F.mono(400), size: le, ...FLAT }, () => this.mats.msg);
        this.at(msg.group, x - (msg.width * 1000) / 2, base + D.threadY + D.msgY, D.z);
        this.msgs.push(msg);
        this.g.add(msg.group);
      } else this.msgs.push(null);
    });

    // the playhead: a hairline standing behind the thread, a small cap on top
    const line = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.mats.head);
    line.scale.set(2 / 1000, (D.headUp + D.headDown) / 1000, 1);
    line.position.set(0, ((D.headUp - D.headDown) / 2) / 1000, 0);
    const capShape = new THREE.Shape();
    capShape.moveTo(-6, 0).lineTo(6, 0).lineTo(0, -8).closePath();
    const cap = new THREE.Mesh(new THREE.ShapeGeometry(capShape), this.mats.head);
    cap.scale.setScalar(1 / 1000);
    cap.position.set(0, (D.headUp + 8) / 1000, 0);
    this.head.add(line, cap);
    this.g.add(this.head);

    // the thread, in the world: straight across under the editor, sagging a hair between its ends
    const pts: THREE.Vector3[] = [];
    const mid = (D.from + D.to) / 2, half = (D.to - D.from) / 2;
    for (let x = D.from; x <= D.to + 1e-6; x += (D.to - D.from) / 24) {
      const sag = 7 * (1 - ((x - mid) / half) ** 2);
      pts.push(px(x, base + D.threadY + sag, D.z));
    }
    this.thread = new Thread(pts, { ...DIFF_THREAD, radius: THREAD_PX * scale, fuzz: 0.45 });
    this.thread.setStrandGlow({ blood: DIFF_THREAD.rest, moss: DIFF_THREAD.rest });

    // the beads: one shape for the four, plain glass (their hashes are under them)
    const shape: BeadShape = { radius: BEAD_PX * scale, bore: THREAD_PX * scale * 1.3, chamfer: THREAD_PX * scale * 0.7 };
    this.beadGeo = beadGeometry(shape);
    for (const x of D.commitX) {
      const u = (x - D.from) / (D.to - D.from), fr = this.thread.frameAt(u);
      this.places.push({ pos: fr.pos.clone(), tangent: fr.tangent.clone() });
      const bead = new Bead({ ...shape, text: '' }, { geometry: this.beadGeo });
      bead.place(fr.pos, fr.tangent, this.front);
      this.beads.push(bead);
    }
  }

  /** Put a group's origin at editor px (x, y, z). */
  private at(o: THREE.Object3D, x: number, y: number, z = 0) {
    const { w, h } = this.panel;
    o.position.set((x - w / 2) / 1000, (h / 2 - y) / 1000, z / 1000);
  }

  /** The playhead at editor x. */
  setHead(x: number) {
    this.at(this.head, x, this.panel.h + DOCK.threadY, DOCK.z - DOCK.headBack);
  }

  dispose() {
    for (const t of [this.cmdA, this.cmdB, this.stat, ...this.hashes, ...this.msgs]) t?.dispose();
    for (const m of this.head.children as THREE.Mesh[]) m.geometry.dispose();
    for (const m of [...Object.values(this.mats), ...this.hashMats]) m?.dispose();
    this.thread.dispose();
    for (const b of this.beads) b.dispose();
    this.beadGeo.dispose();
  }
}
