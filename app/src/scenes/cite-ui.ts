// The chat's two small pieces of UI for `cite` (Plan 2 Task 17): the `why?` chip and the pointer that clicks it.
//
// The chip is a pill floating a hair in front of the chat's face: panel2 with the panels' 1 px edge (lit a little along
// the top), its label flat mono type (her-type's flat: a sliver of depth, unlit). It lifts as the pointer arrives,
// presses in on the click (in, down a step, its face brighter), and once let go stays lit: the question it asked is
// open. The pointer is the classic arrow, bone with an ink keyline, flat, a little further out. Both are in the chat's
// px (y down from its top edge), placed through the chat's group.
import * as THREE from 'three';
import { Type3D } from '../engine/type3d';
import { F } from '../engine/type';
import { HEX, LIN } from '../engine/palette';

/** Flat type: a sliver of depth (em), no bevel (her-type's FLAT). */
const FLAT = { depth: 0.002, bevel: 0 } as const;

const VERT = /* glsl */ `
  uniform vec2 uSize;
  varying vec2 vPx;
  void main() {
    vPx = vec2(uv.x, 1.0 - uv.y) * uSize;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;

const FRAG = /* glsl */ `
  uniform vec2 uSize;
  uniform float uRadius, uOpacity, uLift;
  uniform vec3 uFill, uEdge, uEdgeHi, uBone;
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
    float inner = clamp(-(d + 1.0) / aa, 0.0, 1.0);
    vec3 face = mix(uFill, uBone, uLift);
    vec3 edge = mix(uEdge, uEdgeHi, 1.0 - smoothstep(0.0, uSize.y, vPx.y));
    vec3 col = (face * inner + edge * (cov - inner)) / cov;
    gl_FragColor = vec4(col, cov * uOpacity);
  }`;

/** sRGB-space mix of two palette colours, as linear RGB. */
function mixLin(a: keyof typeof HEX, b: keyof typeof HEX, k: number) {
  const pa = parseInt(HEX[a].slice(1), 16), pb = parseInt(HEX[b].slice(1), 16);
  const ch = (sh: number) => {
    const s = (((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k) / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return new THREE.Vector3(ch(16), ch(8), ch(0));
}

/** The chip: a pill `w` by `h` px with `label` set in mono at `em` px, centred. Its group's origin is the pill's centre. */
export class Chip {
  g = new THREE.Group();
  private pill: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;
  label: Type3D;
  labelMat = new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...LIN.bone), transparent: true });

  constructor(label: string, readonly w: number, readonly h: number, em: number) {
    this.u = {
      uSize: { value: new THREE.Vector2(w, h) }, uRadius: { value: h / 2 }, uOpacity: { value: 1 }, uLift: { value: 0 },
      uFill: { value: new THREE.Vector3(...LIN.panel2) }, uEdge: { value: mixLin('ruleStrong', 'bone', 0.1) },
      uEdgeHi: { value: mixLin('ruleStrong', 'bone', 0.38) }, uBone: { value: new THREE.Vector3(...LIN.bone) },
    };
    this.pill = new THREE.Mesh(new THREE.PlaneGeometry(w / 1000, h / 1000), new THREE.ShaderMaterial({ uniforms: this.u, vertexShader: VERT, fragmentShader: FRAG, transparent: true }));
    this.label = new Type3D(label, { family: F.mono(500), size: em / 1000, ...FLAT }, this.labelMat);
    // centred: the label's cap height in the pill's middle (JetBrains Mono's caps are 0.73 em)
    this.label.group.position.set(-this.label.width / 2, (-0.365 * em) / 1000, 0.6 / 1000);
    this.g.add(this.pill, this.label.group);
  }

  /** Its look at t: `opacity`, `lift` (a fraction of bone washed into its face), `edge` (its keyline brought up, 0..1). */
  set(opacity: number, lift: number, edge: number) {
    this.g.visible = opacity > 0.002;
    this.u.uOpacity!.value = opacity;
    this.u.uLift!.value = lift;
    (this.u.uEdge!.value as THREE.Vector3).copy(mixLin('ruleStrong', 'bone', 0.1 + 0.3 * edge));
    this.labelMat.opacity = opacity;
  }

  dispose() {
    this.pill.geometry.dispose();
    (this.pill.material as THREE.Material).dispose();
    this.label.dispose();
    this.labelMat.dispose();
  }
}

/** The arrow pointer (px, y down, its hot spot at the origin). */
const ARROW: [number, number][] = [[0, 0], [0, 21], [5, 16.2], [8.4, 24.2], [11.6, 22.8], [8.2, 15.2], [14.8, 15.2]];

function arrowShape(scale: number, grow = 0): THREE.Shape {
  // grown outward from its middle by `grow` px (the keyline under the fill): near enough to an offset at this size
  const c = [5.5, 13.5];
  const s = new THREE.Shape();
  ARROW.forEach(([x, y], i) => {
    const dx = x - c[0]!, dy = y - c[1]!, l = Math.hypot(dx, dy) || 1;
    const px = (x + (grow * dx) / l) * scale, py = -(y + (grow * dy) / l) * scale;
    if (i) s.lineTo(px / 1000, py / 1000);
    else s.moveTo(px / 1000, py / 1000);
  });
  s.closePath();
  return s;
}

/** The pointer: a bone arrow on an ink keyline, `scale` × the 24 px arrow. Its group's origin is the hot spot. */
export class Pointer {
  g = new THREE.Group();
  private fill: THREE.Mesh;
  private key: THREE.Mesh;
  mats = {
    fill: new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...LIN.bone), transparent: true }),
    key: new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...LIN.ink), transparent: true }),
  };

  constructor(scale: number) {
    this.key = new THREE.Mesh(new THREE.ShapeGeometry(arrowShape(scale, 1.6)), this.mats.key);
    this.fill = new THREE.Mesh(new THREE.ShapeGeometry(arrowShape(scale)), this.mats.fill);
    this.fill.position.z = 0.4 / 1000;
    this.g.add(this.key, this.fill);
  }

  set(opacity: number) {
    this.g.visible = opacity > 0.002;
    this.mats.fill.opacity = opacity;
    this.mats.key.opacity = opacity;
  }

  dispose() {
    this.key.geometry.dispose();
    this.fill.geometry.dispose();
    this.mats.fill.dispose();
    this.mats.key.dispose();
  }
}
