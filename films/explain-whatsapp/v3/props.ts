// The WhatsApp explainer's 3D props (round 7, v3): plain three.js builders, posed by the scenes each frame as pure
// functions of time. A phone with a live chat screen (a canvas texture redrawn per frame), a server tower with LED
// strips, a chat bubble with extruded ticks, a lock, a key and a blob store. Sizes are in world units: a phone is
// 1.5 tall. Glows are HDR colours (above the bloom threshold, so they bloom in the post); bodies stay dark and glossy so
// the studio's softboxes draw their edges.
import { THREE, RoundedBoxGeometry } from '@engine/three';
import { hexToLinear } from '@engine/util';
import { F, font } from '@engine/type';

export const GREEN = '#25D366';
export const BLUE = '#53BDEB';
export const BONE = '#F2ECE4';
export const DIM = '#A89E92';

/** A linear THREE.Color of `hex` times `k` (k > ~1.3 blooms). */
export function hdr(hex: string, k = 1): THREE.Color {
  const [r, g, b] = hexToLinear(hex);
  return new THREE.Color().setRGB(r * k, g * k, b * k, THREE.LinearSRGBColorSpace);
}

/** Everything a prop made, to free with it. */
export class Bag {
  private xs: { dispose(): void }[] = [];
  own<T extends { dispose(): void }>(x: T): T {
    this.xs.push(x);
    return x;
  }
  dispose() {
    for (const x of this.xs.splice(0)) x.dispose();
  }
}

export const mats = {
  /** Dark glossy body (warm black, clearcoat: the softboxes draw its edges). */
  body: (bag: Bag, hex = '#17110d') => bag.own(new THREE.MeshPhysicalMaterial({ color: hdr(hex), roughness: 0.32, metalness: 0.55, clearcoat: 1, clearcoatRoughness: 0.18 })),
  /** Light that blooms: an unlit colour at HDR level k. */
  glow: (bag: Bag, hex: string, k = 3) => bag.own(new THREE.MeshBasicMaterial({ color: hdr(hex, k), toneMapped: false })),
  /** Satin bone (labels, icons on dark). */
  bone: (bag: Bag) => bag.own(new THREE.MeshPhysicalMaterial({ color: hdr(BONE), roughness: 0.4, clearcoat: 0.3, clearcoatRoughness: 0.15 })),
  /** A lit coloured solid with an emissive core. */
  lit: (bag: Bag, hex: string, emissive = 0.6) => bag.own(new THREE.MeshPhysicalMaterial({ color: hdr(hex), emissive: hdr(hex), emissiveIntensity: emissive, roughness: 0.3, clearcoat: 0.6, clearcoatRoughness: 0.15 })),
};

// ----------------------------------------------------------------------------------------------------------- phone

/** A canvas texture to draw a screen on (sRGB, redrawn when `draw` is called). */
export class Screen {
  canvas = document.createElement('canvas');
  ctx: CanvasRenderingContext2D;
  tex: THREE.CanvasTexture;
  constructor(public w: number, public h: number) {
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx = this.canvas.getContext('2d')!;
    this.tex = new THREE.CanvasTexture(this.canvas);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    this.tex.anisotropy = 8;
  }
  draw(fn: (c: CanvasRenderingContext2D, w: number, h: number) => void) {
    const c = this.ctx;
    c.reset();
    c.clearRect(0, 0, this.w, this.h);
    fn(c, this.w, this.h);
    this.tex.needsUpdate = true;
  }
  dispose() {
    this.tex.dispose();
    this.canvas.width = this.canvas.height = 0;
  }
}

export const PHONE = { w: 0.74, h: 1.5, d: 0.08 };

export interface ChatMsg {
  text: string;
  /** Mine (right, green) or theirs (left, grey). */
  mine?: boolean;
  /** 0..1 entrance. */
  k?: number;
  /** 0 none, 1 one tick, 2 two ticks, 3 two blue ticks. */
  ticks?: number;
  /** A lock glyph before the text. */
  lock?: boolean;
  /** A photo tile (0..1 sealed: scrambled). */
  photo?: number;
}

export interface ScreenState {
  /** 0 off (black glass), 1 on. */
  on: number;
  /** Contact name in the header. */
  name?: string;
  /** Header status line ('online', 'last seen…'). */
  status?: string;
  msgs?: ChatMsg[];
  /** A big glyph over the screen (a key, a lock): drawn by the scene. */
  overlay?: (c: CanvasRenderingContext2D, w: number, h: number) => void;
}

/** A phone: a rounded glossy slab with a screen, its front facing +z, centred on the group's origin. */
export class Phone {
  group = new THREE.Group();
  screen = new Screen(512, 1040);
  private bag = new Bag();
  private glass: THREE.MeshBasicMaterial;
  constructor() {
    const { w, h, d } = PHONE;
    const body = new THREE.Mesh(this.bag.own(new RoundedBoxGeometry(w, h, d, 6, 0.11)), mats.body(this.bag));
    this.group.add(body);
    this.glass = this.bag.own(new THREE.MeshBasicMaterial({ map: this.screen.tex, toneMapped: false, transparent: true }));
    const sw = w - 0.06, sh = h - 0.06;
    const scr = new THREE.Mesh(this.bag.own(roundedPlane(sw, sh, 0.085)), this.glass);
    scr.position.z = d / 2 + 0.0015;
    this.group.add(scr);
    this.bag.own(this.screen);
  }

  /** Redraw the screen. `level` scales its light (1: paper white at 1.0; above ~1.3 the greens bloom). */
  set(s: ScreenState, level = 1.15) {
    this.glass.color.setScalar(level * s.on);
    this.screen.draw((c, W, H) => drawChat(c, W, H, s));
  }

  dispose() {
    this.bag.dispose();
  }
}

/** A plane with rounded corners (uv 0..1 over its box). */
export function roundedPlane(w: number, h: number, r: number): THREE.ShapeGeometry {
  const s = roundRectShape(w, h, r);
  const g = new THREE.ShapeGeometry(s, 8);
  const uv = g.attributes.uv!, pos = g.attributes.position!;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / w + 0.5, pos.getY(i) / h + 0.5);
  return g;
}

export function roundRectShape(w: number, h: number, r: number, cx = 0, cy = 0): THREE.Shape {
  const s = new THREE.Shape(), x = cx - w / 2, y = cy - h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

function rr(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.roundRect(x, y, w, h, r);
}

/** The chat UI on a 512 x 1040 canvas: dark wallpaper, a header, bubbles from the bottom up. */
function drawChat(c: CanvasRenderingContext2D, W: number, H: number, s: ScreenState) {
  // wallpaper
  const g = c.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#0f1a15');
  g.addColorStop(1, '#0a120e');
  c.fillStyle = g;
  c.fillRect(0, 0, W, H);
  c.globalAlpha = 0.05;
  c.fillStyle = '#ffffff';
  for (let y = 150; y < H; y += 46) for (let x = (y / 46) % 2 ? 20 : 43; x < W; x += 46) c.fillRect(x, y, 3, 3);
  c.globalAlpha = 1;
  // header
  c.fillStyle = '#16231d';
  c.fillRect(0, 0, W, 132);
  c.fillStyle = '#2b3d34';
  c.beginPath();
  c.arc(62, 84, 30, 0, Math.PI * 2);
  c.fill();
  c.fillStyle = BONE;
  c.font = font(F.ui(600), 44);
  c.textBaseline = 'alphabetic';
  c.fillText(s.name ?? 'Friend', 108, 80);
  if (s.status) {
    c.fillStyle = s.status === 'online' ? GREEN : DIM;
    c.font = font(F.ui(500), 30);
    c.fillText(s.status, 108, 118);
  }
  // bubbles from the bottom up
  let y = H - 120;
  const msgs = [...(s.msgs ?? [])].reverse();
  for (const m of msgs) {
    const k = m.k ?? 1;
    if (k <= 0) continue;
    c.font = font(F.ui(600), 46);
    const lines = wrap(c, m.text, 360);
    const ph = m.photo !== undefined ? 230 : 0;
    const bw = Math.max(200, ...lines.map((l) => c.measureText(l).width + (m.lock ? 40 : 0))) + 44;
    const bh = lines.length * 56 + 64 + ph;
    const x = m.mine ? W - 24 - bw : 24;
    y -= bh;
    c.save();
    c.globalAlpha = Math.min(1, k * 1.4);
    const sc = 0.6 + 0.4 * backOut(k);
    c.translate(m.mine ? x + bw : x, y + bh);
    c.scale(sc, sc);
    c.translate(-(m.mine ? x + bw : x), -(y + bh));
    c.fillStyle = m.mine ? '#0e6b47' : '#26302b';
    rr(c, x, y, bw, bh, 22);
    c.fill();
    let ty = y + 60;
    if (ph) {
      drawPhoto(c, x + 14, y + 14, bw - 28, ph - 10, m.photo!);
      ty += ph;
    }
    c.fillStyle = BONE;
    lines.forEach((l, i) => {
      let lx = x + 22;
      if (m.lock && i === 0) {
        lockGlyph(c, lx + 14, ty + i * 56 - 15, 17, GREEN);
        lx += 38;
      }
      c.fillText(l, lx, ty + i * 56);
    });
    // time + ticks
    c.font = font(F.ui(500), 20);
    c.fillStyle = 'rgba(242,236,228,0.6)';
    const tx = x + bw - (m.mine ? 70 : 20);
    c.textAlign = 'right';
    c.fillText('9:41', tx, y + bh - 14);
    c.textAlign = 'left';
    if (m.mine && (m.ticks ?? 0) > 0) tickGlyph(c, tx + 10, y + bh - 22, m.ticks!);
    c.restore();
    y -= 18;
  }
  if (s.overlay) s.overlay(c, W, H);
}

function backOut(x: number) {
  const s = 1.70158;
  return 1 + (s + 1) * Math.pow(x - 1, 3) + s * Math.pow(x - 1, 2);
}

function wrap(c: CanvasRenderingContext2D, text: string, max: number): string[] {
  const out: string[] = [];
  let cur = '';
  for (const w of text.split(' ')) {
    const t = cur ? cur + ' ' + w : w;
    if (c.measureText(t).width > max && cur) {
      out.push(cur);
      cur = w;
    } else cur = t;
  }
  if (cur) out.push(cur);
  return out;
}

/** Ticks on the chat canvas: n = 1 one grey, 2 two grey, 3 two blue. */
export function tickGlyph(c: CanvasRenderingContext2D, x: number, y: number, n: number) {
  c.save();
  c.strokeStyle = n >= 3 ? BLUE : 'rgba(242,236,228,0.75)';
  c.lineWidth = 3.5;
  c.lineCap = 'round';
  c.lineJoin = 'round';
  const one = (dx: number) => {
    c.beginPath();
    c.moveTo(x + dx, y);
    c.lineTo(x + dx + 6, y + 6);
    c.lineTo(x + dx + 18, y - 8);
    c.stroke();
  };
  one(0);
  if (n >= 2) one(10);
  c.restore();
}

export function lockGlyph(c: CanvasRenderingContext2D, x: number, y: number, s: number, color: string) {
  c.save();
  c.strokeStyle = color;
  c.fillStyle = color;
  c.lineWidth = s * 0.28;
  c.beginPath();
  c.arc(x, y - s * 0.2, s * 0.55, Math.PI, 0);
  c.stroke();
  rr(c, x - s * 0.85, y - s * 0.2, s * 1.7, s * 1.3, s * 0.25);
  c.fill();
  c.restore();
}

/** A photo tile: a sunset over hills; `sealed` 0..1 scrambles it into noise blocks. */
export function drawPhoto(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, sealed: number) {
  c.save();
  rr(c, x, y, w, h, 14);
  c.clip();
  const g = c.createLinearGradient(0, y, 0, y + h);
  g.addColorStop(0, '#f6a35c');
  g.addColorStop(0.55, '#d8577a');
  g.addColorStop(1, '#3a2a5c');
  c.fillStyle = g;
  c.fillRect(x, y, w, h);
  c.fillStyle = '#ffd98a';
  c.beginPath();
  c.arc(x + w * 0.62, y + h * 0.48, h * 0.16, 0, Math.PI * 2);
  c.fill();
  c.fillStyle = '#2a1d3d';
  c.beginPath();
  c.moveTo(x, y + h);
  c.lineTo(x, y + h * 0.7);
  c.quadraticCurveTo(x + w * 0.3, y + h * 0.5, x + w * 0.55, y + h * 0.72);
  c.quadraticCurveTo(x + w * 0.8, y + h * 0.6, x + w, y + h * 0.66);
  c.lineTo(x + w, y + h);
  c.fill();
  if (sealed > 0) {
    const n = 12, cw = w / n, ch = h / 8;
    for (let i = 0; i < n; i++)
      for (let j = 0; j < 8; j++) {
        const hsh = Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;
        const r = hsh - Math.floor(hsh);
        if (r > sealed * 1.05) continue;
        const v = Math.floor(20 + r * 60);
        c.fillStyle = `rgb(${v * 0.4},${v},${v * 0.7})`;
        c.fillRect(x + i * cw, y + j * ch, cw + 1, ch + 1);
      }
  }
  c.restore();
}

// ---------------------------------------------------------------------------------------------------------- server

export const SERVER = { w: 1.5, u: 0.3, gap: 0.05, d: 1.1 };

/** A server tower: `n` rack units stacked from y = 0 up, each with an LED strip and a row of status lights. */
export class Server {
  group = new THREE.Group();
  /** Each unit's strip material (animate .color for activity). */
  strips: THREE.MeshBasicMaterial[] = [];
  lights: THREE.InstancedMesh;
  height: number;
  private bag = new Bag();
  private n: number;
  constructor(n = 5) {
    this.n = n;
    const { w, u, gap, d } = SERVER;
    const geo = this.bag.own(new RoundedBoxGeometry(w, u, d, 4, 0.04));
    const body = mats.body(this.bag, '#1b1511');
    const stripGeo = this.bag.own(new THREE.BoxGeometry(w * 0.55, 0.022, 0.01));
    for (let i = 0; i < n; i++) {
      const m = new THREE.Mesh(geo, body);
      m.position.y = u / 2 + i * (u + gap);
      this.group.add(m);
      const sm = mats.glow(this.bag, GREEN, 1.6);
      this.strips.push(sm);
      const s = new THREE.Mesh(stripGeo, sm);
      s.position.set(-w * 0.12, m.position.y, d / 2 + 0.006);
      this.group.add(s);
    }
    // status lights: 4 per unit at the right of the face
    const dot = this.bag.own(new THREE.SphereGeometry(0.018, 10, 8));
    this.lights = new THREE.InstancedMesh(dot, mats.glow(this.bag, GREEN, 3), n * 4);
    for (let i = 0; i < n; i++)
      for (let j = 0; j < 4; j++) {
        const mtx = new THREE.Matrix4().makeTranslation(w * 0.28 + j * 0.06, u / 2 + i * (u + gap), d / 2 + 0.01);
        this.lights.setMatrixAt(i * 4 + j, mtx);
        this.lights.setColorAt(i * 4 + j, new THREE.Color(1, 1, 1));
      }
    this.group.add(this.lights);
    this.height = n * u + (n - 1) * gap;
  }

  /** Pose for time t: strips breathe at `activity` (0..1), lights blink. */
  pose(t: number, activity = 0.5, hex = GREEN) {
    this.strips.forEach((m, i) => {
      const k = 0.5 + activity * (1.2 + 0.9 * Math.sin(t * 5 + i * 1.7) ** 2);
      m.color.copy(hdr(hex, k));
    });
    const c = new THREE.Color();
    for (let i = 0; i < this.n * 4; i++) {
      const on = Math.sin(t * (7 + (i % 5)) + i * 2.3) > 0.2 - activity * 0.6 ? 1 : 0.08;
      this.lights.setColorAt(i, c.setScalar(on));
    }
    this.lights.instanceColor!.needsUpdate = true;
  }

  dispose() {
    this.lights.dispose();
    this.bag.dispose();
  }
}

// ---------------------------------------------------------------------------------------------- bubble and ticks

/** A chat bubble outline (tail at the lower right), centred. */
export function bubbleShape(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w + r * 0.55, y);
  s.quadraticCurveTo(x + w, y + r * 0.35, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/** A check mark as a thick polyline outline (centred near the origin, ~1 wide). */
export function tickShape(th = 0.17): THREE.Shape {
  const a = new THREE.Vector2(-0.5, 0.02), b = new THREE.Vector2(-0.15, -0.33), c = new THREE.Vector2(0.5, 0.36);
  const n1 = new THREE.Vector2(b.y - a.y, a.x - b.x).normalize().multiplyScalar(th / 2);
  const n2 = new THREE.Vector2(c.y - b.y, b.x - c.x).normalize().multiplyScalar(th / 2);
  const s = new THREE.Shape();
  s.moveTo(a.x + n1.x, a.y + n1.y);
  s.lineTo(b.x + n1.x * 0.2 + n2.x * 0.2, b.y + (n1.y + n2.y) * 1.4);
  s.lineTo(c.x + n2.x, c.y + n2.y);
  s.lineTo(c.x - n2.x, c.y - n2.y);
  s.lineTo(b.x - (n1.x + n2.x) * 0.9, b.y - (n1.y + n2.y) * 0.9);
  s.lineTo(a.x - n1.x, a.y - n1.y);
  s.closePath();
  return s;
}

export function extrude(bag: Bag, shape: THREE.Shape | THREE.Shape[], depth: number, bevel: number): THREE.ExtrudeGeometry {
  const g = bag.own(new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 4, curveSegments: 16 }));
  g.translate(0, 0, -depth / 2);
  return g;
}

// --------------------------------------------------------------------------------------------------- lock and key

/** A padlock, ~0.6 tall, centred on its body; `open` (0..1) lifts the shackle. */
export class Lock {
  group = new THREE.Group();
  shackle: THREE.Mesh;
  body: THREE.Mesh;
  private bag = new Bag();
  constructor(hex = GREEN) {
    this.body = new THREE.Mesh(this.bag.own(new RoundedBoxGeometry(0.5, 0.4, 0.2, 4, 0.06)), mats.lit(this.bag, hex, 0.9));
    this.group.add(this.body);
    this.shackle = new THREE.Mesh(this.bag.own(new THREE.TorusGeometry(0.15, 0.04, 12, 32, Math.PI)), mats.body(this.bag, '#c9c2b8'));
    const legGeo = this.bag.own(new THREE.CylinderGeometry(0.04, 0.04, 0.14, 12));
    for (const sx of [-1, 1]) {
      const leg = new THREE.Mesh(legGeo, this.shackle.material);
      leg.position.set(sx * 0.15, -0.07, 0);
      this.shackle.add(leg);
    }
    this.group.add(this.shackle);
    const hole = new THREE.Mesh(this.bag.own(new THREE.CylinderGeometry(0.04, 0.04, 0.02, 16)), mats.body(this.bag, '#0b0806'));
    hole.rotation.x = Math.PI / 2;
    hole.position.set(0, 0.02, 0.105);
    this.group.add(hole);
    this.pose(0);
  }
  pose(open: number) {
    this.shackle.position.y = 0.2 + 0.08 + open * 0.16;
    this.shackle.rotation.y = open * 0.9;
  }
  dispose() {
    this.bag.dispose();
  }
}

/** A key: a ring bow and a toothed blade along +x, ~1 long, extruded. */
export class Key {
  group = new THREE.Group();
  mat: THREE.MeshPhysicalMaterial;
  private bag = new Bag();
  constructor(hex = GREEN, emissive = 1.4) {
    const s = new THREE.Shape();
    s.absarc(0, 0, 0.2, 0, Math.PI * 2, false);
    const hole = new THREE.Path();
    hole.absarc(0, 0, 0.09, 0, Math.PI * 2, true);
    s.holes.push(hole);
    const blade = new THREE.Shape();
    blade.moveTo(0.17, -0.045);
    blade.lineTo(0.95, -0.045);
    blade.lineTo(0.95, -0.17);
    blade.lineTo(0.85, -0.17);
    blade.lineTo(0.85, -0.11);
    blade.lineTo(0.75, -0.11);
    blade.lineTo(0.75, -0.19);
    blade.lineTo(0.64, -0.19);
    blade.lineTo(0.64, -0.045);
    blade.lineTo(0.64, 0.045);
    blade.lineTo(0.17, 0.045);
    blade.closePath();
    this.mat = mats.lit(this.bag, hex, emissive);
    const g = extrude(this.bag, [s, blade], 0.06, 0.015);
    g.translate(-0.45, 0, 0);
    this.group.add(new THREE.Mesh(g, this.mat));
  }
  dispose() {
    this.bag.dispose();
  }
}

// ------------------------------------------------------------------------------------------------------ blob store

/** A blob store: three stacked database discs with glowing rims, ~1.2 tall, its base at y = 0. */
export class BlobStore {
  group = new THREE.Group();
  rims: THREE.MeshBasicMaterial[] = [];
  private bag = new Bag();
  constructor(hex = GREEN) {
    const disc = this.bag.own(new THREE.CylinderGeometry(0.62, 0.62, 0.32, 64, 1));
    const rim = this.bag.own(new THREE.TorusGeometry(0.62, 0.012, 8, 96));
    const body = mats.body(this.bag, '#1b1511');
    for (let i = 0; i < 3; i++) {
      const m = new THREE.Mesh(disc, body);
      m.position.y = 0.16 + i * 0.4;
      this.group.add(m);
      const rm = mats.glow(this.bag, hex, 2);
      this.rims.push(rm);
      const r = new THREE.Mesh(rim, rm);
      r.rotation.x = Math.PI / 2;
      r.position.y = 0.32 + i * 0.4;
      this.group.add(r);
    }
  }
  pose(t: number, activity = 0.4, hex = GREEN) {
    this.rims.forEach((m, i) => m.color.copy(hdr(hex, 0.8 + activity * (1.4 + Math.sin(t * 4 - i * 1.2) ** 2 * 1.4))));
  }
  dispose() {
    this.bag.dispose();
  }
}
