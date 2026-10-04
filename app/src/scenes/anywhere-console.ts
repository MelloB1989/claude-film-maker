// The cloud's console for scene `anywhere` (Plan 2 Task 24): the Playground, the Memory Graph and Namespaces, recreated
// from the real console's layouts (gitloom web/src/app: Playground.tsx, Graph.tsx, Namespaces.tsx, ui.tsx), not its
// pixels, in the film's palette and type: page titles in Bricolage (the console's font-display), the conversation in
// Geist, the machine's words (tool names, namespaces) in JetBrains Mono.
//
// A Card is a console card in the film's panel finish (engine/panels.ts): a plane w/1000 by h/1000 world units whose
// rounded corners and 1 px edge (lit a little along the top) are cut in the fragment shader from a signed distance, its
// face a Canvas2D texture painted at 2x, mipmapped, a soft drop shadow behind it. It repaints only when the state it
// shows changes (a key), on the output frame grid, so a frame shows one state across its whole shutter.
//
// What each card shows:
// - Playground: the title, the user's turn in its bubble on the right (Geist), the assistant's two tool calls as the
//   console's collapsed tool rows (a chevron, a wrench in moss or blood, the tool's name in mono, `rounded-well` with a
//   rule border on ink: ToolCall), each opening on its beat, and the blood streaming caret where the reply will come;
//   the composer at the foot (its squircle and the blood send button).
// - Memory Graph: the title and the graph's canvas (the graph itself is anywhere-graph.ts, drawn over it).
// - Namespaces: the title and the list (a box icon and the name, rule hairlines between rows), the first row opening on
//   "One".
// Every word comes from anywhere.strings.json; icons are drawn paths (lucide's, as the console uses), not text.
import * as THREE from 'three';
import { Layer2D } from '../engine/gl';
import { HEX, LIN, rgba } from '../engine/palette';
import { F, font, measure } from '../engine/type';
import { FPS, frameIdx, smootherstep } from '../engine/util';

type Ctx = CanvasRenderingContext2D;

// ------------------------------------------------------------------------------------------------ the card

const VERT = /* glsl */ `
  uniform vec2 uSize;
  varying vec2 vPx;
  void main() {
    vPx = vec2(uv.x, 1.0 - uv.y) * uSize;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;

const FRAG = /* glsl */ `
  uniform sampler2D uMap;
  uniform vec2 uSize;
  uniform float uRadius, uOpacity;
  uniform vec3 uEdge, uEdgeHi;
  varying vec2 vPx;
  float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
  }
  void main() {
    vec2 h = 0.5 * uSize;
    float d = sdRoundRect(vPx - h, h, uRadius);
    float aa = max(fwidth(d), 1e-4);
    float cov = clamp(-d / aa, 0.0, 1.0);
    if (cov <= 0.0) discard;
    vec3 face = texture2D(uMap, vec2(vPx.x / uSize.x, 1.0 - vPx.y / uSize.y)).rgb;
    float inner = clamp(-(d + 1.0) / aa, 0.0, 1.0);
    vec3 edge = mix(uEdge, uEdgeHi, 1.0 - smoothstep(0.0, 2.0 * uRadius, vPx.y));
    gl_FragColor = vec4((face * inner + edge * (cov - inner)) / cov, cov * uOpacity);
  }`;

const SHADOW_VERT = /* glsl */ `
  uniform vec2 uSize;
  uniform float uPad;
  varying vec2 vPx;
  void main() {
    vPx = vec2(uv.x, 1.0 - uv.y) * (uSize + 2.0 * uPad) - uPad;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;

const SHADOW_FRAG = /* glsl */ `
  uniform vec2 uSize;
  uniform float uRadius, uBlur, uOpacity, uOffset;
  varying vec2 vPx;
  float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
  }
  void main() {
    vec2 h = 0.5 * uSize;
    float d = sdRoundRect(vPx - h - vec2(0.0, uOffset), h, uRadius);
    float a = 1.0 - smoothstep(-0.35 * uBlur, uBlur, d);
    gl_FragColor = vec4(0.0, 0.0, 0.0, a * a * uOpacity);
  }`;

/** sRGB-space mix of two palette colours, as linear RGB (the edge's highlight: ruleStrong lifted toward bone). */
function mixLin(a: keyof typeof HEX, b: keyof typeof HEX, k: number) {
  const pa = parseInt(HEX[a].slice(1), 16), pb = parseInt(HEX[b].slice(1), 16);
  const ch = (sh: number) => {
    const s = (((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k) / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return new THREE.Vector3(ch(16), ch(8), ch(0));
}

/** The panels' drop shadow: offset (px, down), softness (px), strength. */
const SHADOW = { offset: 12, blur: 60, opacity: 0.58 };

export class Card {
  /** The card's frame: its origin is the card's centre, in panel px / 1000 (put overlays in it beside the face). */
  group = new THREE.Group();
  mesh: THREE.Mesh;
  shadow: THREE.Mesh;
  /** 0..1, set before draw(). */
  opacity = 1;
  readonly layer: Layer2D;
  private mat: THREE.ShaderMaterial;
  private shadowMat: THREE.ShaderMaterial;
  private key = '';

  constructor(readonly w: number, readonly h: number, readonly radius = 16) {
    this.layer = new Layer2D(w, h, 2);
    const tex = this.layer.texture;
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.anisotropy = 16;
    this.mat = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG, transparent: true, side: THREE.DoubleSide,
      uniforms: {
        uMap: { value: tex }, uSize: { value: new THREE.Vector2(w, h) }, uRadius: { value: radius }, uOpacity: { value: 1 },
        uEdge: { value: new THREE.Vector3(...LIN.ruleStrong) }, uEdgeHi: { value: mixLin('ruleStrong', 'bone', 0.22) },
      },
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(w / 1000, h / 1000), this.mat);
    const pad = SHADOW.blur + SHADOW.offset;
    this.shadowMat = new THREE.ShaderMaterial({
      vertexShader: SHADOW_VERT, fragmentShader: SHADOW_FRAG, transparent: true, depthWrite: false,
      uniforms: {
        uSize: { value: new THREE.Vector2(w, h) }, uPad: { value: pad }, uOffset: { value: SHADOW.offset }, uRadius: { value: radius },
        uBlur: { value: SHADOW.blur }, uOpacity: { value: SHADOW.opacity },
      },
    });
    this.shadow = new THREE.Mesh(new THREE.PlaneGeometry((w + 2 * pad) / 1000, (h + 2 * pad) / 1000), this.shadowMat);
    this.shadow.position.z = -0.004;
    this.group.add(this.mesh, this.shadow);
    // a first face, so the card never samples an empty texture
    this.layer.clear(HEX.panel);
    this.layer.upload();
  }

  /** Repaint with `paint` when `key` (everything the face shows) differs from the last; set the opacity either way. */
  draw(key: string, paint: (c: Ctx) => void) {
    this.mat.uniforms.uOpacity!.value = this.opacity;
    this.shadowMat.uniforms.uOpacity!.value = SHADOW.opacity * this.opacity;
    this.group.visible = this.opacity > 0.002;
    if (key === this.key) return;
    this.key = key;
    this.layer.clear(HEX.panel);
    const c = this.layer.ctx;
    c.textBaseline = 'alphabetic';
    paint(c);
    this.layer.upload();
  }

  /** A point on the card (px from its top left, y down; z px off its face) in its group's space. */
  local(x: number, y: number, z = 0, target = new THREE.Vector3()) {
    return target.set((x - this.w / 2) / 1000, (this.h / 2 - y) / 1000, z / 1000);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.mat.dispose();
    this.shadow.geometry.dispose();
    this.shadowMat.dispose();
    this.layer.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ icons

/** Lucide's icons (24-unit squares, 2-unit strokes), as the console draws them. */
const ICON = {
  chevron: ['m9 18 6-6-6-6'],
  wrench: ['M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z'],
  arrowUp: ['m5 12 7-7 7 7', 'M12 19V5'],
  box: ['M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z', 'm3.3 7 8.7 5 8.7-5', 'M12 22V12'],
} as const;
const PATHS = new Map<string, Path2D[]>();

/** Icon `name` `size` px square, its top left at (x, y), stroked in `color`. */
export function icon(c: Ctx, name: keyof typeof ICON, x: number, y: number, size: number, color: string, weight = 2) {
  let ps = PATHS.get(name);
  if (!ps) PATHS.set(name, (ps = ICON[name].map((d) => new Path2D(d))));
  c.save();
  c.translate(x, y);
  c.scale(size / 24, size / 24);
  c.strokeStyle = color;
  c.lineWidth = weight;
  c.lineCap = c.lineJoin = 'round';
  for (const p of ps) c.stroke(p);
  c.restore();
}

// ------------------------------------------------------------------------------------------------ the cards' copy

export interface ConsoleCopy {
  playground: string;
  graph: string;
  namespaces: string;
  /** The user's turn. */
  message: string;
  retrieve: string;
  remember: string;
  /** The first namespace's name. */
  first: string;
}

/** A card's title, as the console's page titles (font-display, h3): Bricolage, bone. */
export const TITLE = { px: 23, x: 24, base: 39, rule: 60 } as const;

function title(c: Ctx, text: string, w: number) {
  c.font = font(F.display(100, 600), TITLE.px);
  c.fillStyle = rgba('bone');
  c.fillText(text, TITLE.x, TITLE.base);
  c.fillStyle = HEX.rule;
  c.fillRect(0, TITLE.rule, w, 1);
}

// ------------------------------------------------------------------------------------------------ Playground

/** The Playground card's layout (card px). */
export const PLAY = {
  w: 436, h: 430,
  /** The user's bubble: its top, height, the text's px (Geist), its padding, its right inset. */
  bubble: { y: 88, h: 46, px: 18, pad: 17, right: 24, r: 20 },
  /** The tool rows: their left, tops, height, corner, the mono px of the name, the icons' size. */
  tool: { x: 24, y: [152, 202], h: 40, r: 10, px: 16, icon: 15 },
  /** The streaming caret (blood, 2 px): its place after the rows. */
  caret: { y: 258, h: 18 },
  /** The composer: its box (from the bottom), corner, the send button's diameter. */
  composer: { inset: 22, h: 92, r: 24, send: 34 },
} as const;

/** A tool row's width (px) for a name: chevron, wrench, the name, its padding. */
export function toolWidth(name: string) {
  const t = PLAY.tool;
  return 12 + t.icon + 8 + t.icon + 10 + Array.from(name).length * 0.6 * t.px + 16;
}

export interface PlayState {
  /** 0..1: the bubble's opening (on the frame grid). */
  bubble: number;
  /** 0..1 each: the two tool rows' opening. */
  tools: [number, number];
  /** The streaming caret shown this frame. */
  caret: boolean;
}

/** One state per output frame: an opening's progress sampled at the frame's own time. */
export const frameT = (t: number) => frameIdx(t) / FPS;
/** How far a row has opened at t (on the frame grid): over `dur` s from `at`. */
export const opening = (t: number, at: number, dur = 0.1) => smootherstep(at, at + dur, frameT(t));

export function playKey(s: PlayState) {
  const r = (x: number) => Math.round(x * 1000) / 1000;
  return `${r(s.bubble)}|${r(s.tools[0])}|${r(s.tools[1])}|${s.caret ? 1 : 0}`;
}

/** The tool row's box (card px) for row k. */
export function toolBox(k: 0 | 1, name: string) {
  const t = PLAY.tool;
  return { x: t.x, y: t.y[k], w: toolWidth(name), h: t.h };
}

export function paintPlayground(c: Ctx, copy: ConsoleCopy, s: PlayState) {
  const P = PLAY;
  title(c, copy.playground, P.w);
  // the user's turn: a quiet bubble on the right (ink-700 on the canvas: a step up from the card), Geist, rising in
  if (s.bubble > 0) {
    const b = P.bubble;
    c.font = font(F.ui(400), b.px);
    const tw = measure(copy.message, F.ui(400), b.px);
    const bw = tw + 2 * b.pad, x = P.w - b.right - bw, y = b.y + (1 - s.bubble) * 10;
    c.globalAlpha = s.bubble;
    c.fillStyle = HEX.panel2;
    c.beginPath();
    c.roundRect(x, y, bw, b.h, b.r);
    c.fill();
    c.fillStyle = rgba('bone');
    c.fillText(copy.message, x + b.pad, y + b.h / 2 + 0.35 * b.px);
    c.globalAlpha = 1;
  }
  // the tool calls: the console's collapsed ToolCall rows
  ([copy.retrieve, copy.remember] as const).forEach((name, k) => {
    const open = s.tools[k]!;
    if (open <= 0) return;
    const t = P.tool, box = toolBox(k as 0 | 1, name);
    const tone = k === 0 ? rgba('moss') : rgba('bloodBright');
    c.save();
    c.globalAlpha = open;
    c.translate(0, (1 - open) * 8);
    c.fillStyle = HEX.ink;
    c.beginPath();
    c.roundRect(box.x, box.y, box.w, box.h, t.r);
    c.fill();
    c.strokeStyle = HEX.rule;
    c.lineWidth = 1;
    c.beginPath();
    c.roundRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, t.r);
    c.stroke();
    const iy = box.y + (box.h - t.icon) / 2;
    icon(c, 'chevron', box.x + 12, iy, t.icon, rgba('boneFaint'));
    icon(c, 'wrench', box.x + 12 + t.icon + 8, iy, t.icon, tone, 2.2);
    c.font = font(F.mono(500), t.px);
    c.fillStyle = tone;
    c.fillText(name, box.x + 12 + 2 * t.icon + 18, box.y + box.h / 2 + 0.36 * t.px);
    c.restore();
  });
  // the reply about to stream: the console's blood caret, blinking on the frame grid
  if (s.caret) {
    c.fillStyle = rgba('blood');
    c.fillRect(P.tool.x + 2, P.caret.y, 2, P.caret.h);
  }
  // the composer: a squircle on ink-700 with a rule border, and the blood send button
  const k = P.composer, x0 = k.inset, y0 = P.h - k.inset - k.h, w = P.w - 2 * k.inset;
  c.fillStyle = HEX.panel2;
  c.beginPath();
  c.roundRect(x0, y0, w, k.h, k.r);
  c.fill();
  c.strokeStyle = HEX.ruleStrong;
  c.lineWidth = 1;
  c.beginPath();
  c.roundRect(x0 + 0.5, y0 + 0.5, w - 1, k.h - 1, k.r);
  c.stroke();
  const sx = x0 + w - 14 - k.send, sy = y0 + k.h - 14 - k.send;
  c.fillStyle = HEX.blood;
  c.beginPath();
  c.arc(sx + k.send / 2, sy + k.send / 2, k.send / 2, 0, Math.PI * 2);
  c.fill();
  icon(c, 'arrowUp', sx + (k.send - 17) / 2, sy + (k.send - 17) / 2, 17, rgba('bone'), 2.4);
}

// ------------------------------------------------------------------------------------------------ Memory Graph

export const GRAPH = {
  w: 336, h: 430,
  /** Where the graph is drawn (card px). */
  area: { x0: 6, y0: 66, x1: 330, y1: 426 },
} as const;

export function paintGraph(c: Ctx, copy: ConsoleCopy) {
  title(c, copy.graph, GRAPH.w);
}

// ------------------------------------------------------------------------------------------------ Namespaces

export const NS = {
  w: 790, h: 156,
  /** List rows: the first's top, height, the name's mono px, the icon's size, the left inset. */
  row: { y: 64, h: 50, px: 17, icon: 17, x: 24 },
} as const;

export interface NsState {
  /** 0..1: the first row's opening. */
  first: number;
}

export function paintNamespaces(c: Ctx, copy: ConsoleCopy, s: NsState) {
  title(c, copy.namespaces, NS.w);
  if (s.first <= 0) return;
  const r = NS.row, y = r.y + (1 - s.first) * 8;
  c.globalAlpha = s.first;
  icon(c, 'box', r.x, y + (r.h - r.icon) / 2, r.icon, rgba('boneFaint'));
  c.font = font(F.mono(400), r.px);
  c.fillStyle = rgba('bone');
  c.fillText(copy.first, r.x + r.icon + 12, y + r.h / 2 + 0.36 * r.px);
  c.fillStyle = HEX.rule;
  c.fillRect(0, r.y + r.h, NS.w, 1);
  c.globalAlpha = 1;
}
