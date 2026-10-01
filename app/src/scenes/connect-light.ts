// Light on scene `connect`'s panels (Plan 2 Task 23), in the manner of engine/panel-light.ts: planes a hair in front of a
// Panel's face, placed in panel px (from its top left, y down), drawn after it with no depth write; add each mesh to the
// object the Panel's mesh is in, beside it, so they share a transform. Set them from t every frame.
//
// - Tick: the ✔ of `✔ Connected`, drawn as a moss path by a pen. The Panel draws its answer with a blank in the ✔'s cell
//   and this draws the ✔ there: the Panel's own check mark (the same two strokes, weight and moss, sharp at any zoom
//   from a signed distance), but drawn on, the pen setting down, running the short arm and flicking up the long one,
//   its head hot, the stroke lit as it lands and settling to a low glow. Only moss glows here.
// - Sheen: a soft diagonal band of neutral light across a card's face as it comes round into the light (a glossy face
//   turning through the key's reflection), with a glint along its edge where the band crosses it. Bone light, far under
//   the bloom's opening on the face; the glint is brighter but neutral, so the chroma gate keeps it out of the bloom.
import * as THREE from 'three';
import { glow } from '../engine/look';
import { LIN } from '../engine/palette';
import { OVER } from '../engine/panel-light';

const UV_VERT = /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

/** The Panel's check mark in em from its cell's left end of the baseline, y up (engine/panels.ts CHECK_PTS, CHECK_W). */
export const CHECK = { pts: [[0.05, 0.37], [0.225, 0.075], [0.565, 0.7]] as const, w: 0.12 };
/** Where the check's middle is (em from its cell's left end of the baseline, y up): the light's centre. */
export const CHECK_MID = { x: 0.3, y: 0.38 };

const v2 = (p: readonly [number, number]) => `vec2(${p[0].toFixed(4)}, ${p[1].toFixed(4)})`;

/**
 * The ✔, drawn on by a pen. `set` takes how far the pen is along the path (0..1), its head's heat (0..1), the stroke's
 * light (a glow() level: LIN.moss's own, 0.42, is the Panel's flat moss; above about 1.25 it blooms), and the soft halo
 * round the drawn stroke.
 */
export class Tick {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;
  /** The plane's half-size round the check's middle (em). */
  private static readonly HALF = { x: 1.6, y: 1.3 };

  /** On a panel `panel` px big, its code `em` px to the em, the ✔'s cell's left end of the baseline at (x, y) px. */
  constructor(private panel: { w: number; h: number }, private em: number, x: number, y: number) {
    const { pts, w } = CHECK;
    const size = new THREE.Vector2(2 * Tick.HALF.x * em, 2 * Tick.HALF.y * em);
    const mid = { x: x + CHECK_MID.x * em, y: y - CHECK_MID.y * em };
    this.u = {
      uSize: { value: size },
      // the cell's origin in the plane's px (from its top left, y down)
      uO: { value: new THREE.Vector2(x - (mid.x - size.x / 2), y - (mid.y - size.y / 2)) },
      uEm: { value: em }, uDraw: { value: 0 }, uHeat: { value: 0 }, uLevel: { value: 0 }, uHalo: { value: 0 },
      uColor: { value: new THREE.Vector3(...glow('moss', 1)) },
    };
    const frag = /* glsl */ `
      uniform vec2 uSize, uO;
      uniform float uEm, uDraw, uHeat, uLevel, uHalo;
      uniform vec3 uColor;
      varying vec2 vUv;
      float sdSeg(vec2 p, vec2 a, vec2 b) {
        vec2 pa = p - a, ba = b - a;
        return length(pa - ba * clamp(dot(pa, ba) / max(dot(ba, ba), 1e-9), 0.0, 1.0));
      }
      void main() {
        const vec2 P0 = ${v2(pts[0])}, P1 = ${v2(pts[1])}, P2 = ${v2(pts[2])};
        vec2 q = (vec2(vUv.x, 1.0 - vUv.y) * uSize - uO) / uEm * vec2(1.0, -1.0); // em, y up
        float l0 = length(P1 - P0), l1 = length(P2 - P1), s = uDraw * (l0 + l1);
        vec2 head = s <= l0 ? mix(P0, P1, s / l0) : mix(P1, P2, (s - l0) / l1);
        float d = min(sdSeg(q, P0, s <= l0 ? head : P1), s > l0 ? sdSeg(q, P1, head) : 1e3);
        float on = step(1e-5, uDraw);
        // the stroke, its edge anti-aliased by its screen rate (centred: it keeps its weight), as the Panel's
        float e = (d - ${(w / 2).toFixed(4)}) * uEm;
        float c = clamp(0.5 - e / max(fwidth(e), 1e-4), 0.0, 1.0) * on;
        // the halo round what is drawn; the pen's head, hot, a little longer along its way than across
        float halo = uHalo * exp(-d * d / 0.08) * on;
        vec2 hd = (q - head) / 0.1;
        float hot = uHeat * exp(-dot(hd, hd)) * on;
        // premultiplied: the stroke covers the face, its light is added
        gl_FragColor = vec4(uColor * (uLevel * c + halo + 3.4 * hot), c);
      }`;
    const m = new THREE.ShaderMaterial({ uniforms: this.u, vertexShader: UV_VERT, fragmentShader: frag, transparent: true, depthWrite: false });
    m.blending = THREE.CustomBlending;
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = THREE.OneFactor;
    m.blendDst = THREE.OneMinusSrcAlphaFactor;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), m);
    this.mesh.position.set((mid.x - panel.w / 2) / 1000, (panel.h / 2 - mid.y) / 1000, 0.6 / 1000);
    this.mesh.scale.set(size.x / 1000, size.y / 1000, 1);
    this.mesh.renderOrder = OVER + 1;
    this.mesh.frustumCulled = false;
  }

  set(draw: number, heat: number, level: number, halo: number) {
    this.mesh.visible = draw > 0;
    this.u.uDraw!.value = Math.min(1, Math.max(0, draw));
    this.u.uHeat!.value = heat;
    this.u.uLevel!.value = level;
    this.u.uHalo!.value = halo;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/**
 * A band of neutral light across a panel's face, leaning a little, and a glint on its 1 px edge where the band crosses
 * it. `set` takes the band's centre (px along the face's middle row, from its left end), half-width (px), level (a
 * fraction of bone: 0.04 is a glossy sheen) and the edge glint's level.
 */
export class Sheen {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(private panel: { w: number; h: number }, radius = 16, slope = 0.45) {
    this.u = {
      uSize: { value: new THREE.Vector2(panel.w, panel.h) }, uX: { value: 0 }, uHalf: { value: 100 },
      uSlope: { value: slope }, uLevel: { value: 0 }, uEdge: { value: 0 }, uRadius: { value: radius },
      uColor: { value: new THREE.Vector3(...LIN.bone) },
    };
    const frag = /* glsl */ `
      uniform vec2 uSize; uniform float uX, uHalf, uSlope, uLevel, uEdge, uRadius; uniform vec3 uColor;
      varying vec2 vUv;
      float sdRoundRect(vec2 p, vec2 b, float r) { vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
      void main() {
        vec2 p = vec2(vUv.x, 1.0 - vUv.y) * uSize;
        float s = (p.x + uSlope * (p.y - 0.5 * uSize.y) - uX) / uHalf;
        float band = exp(-s * s);
        float d = sdRoundRect(p - 0.5 * uSize, 0.5 * uSize, uRadius);
        float aa = max(fwidth(d), 1e-4);
        float inside = clamp(-d / aa, 0.0, 1.0);
        float rim = clamp(1.0 - abs(d + 0.75) / (1.2 * aa + 0.6), 0.0, 1.0); // the 1 px edge
        float edgeBand = exp(-s * s * 0.35); // the glint runs a little wider than the band along the edge
        gl_FragColor = vec4(uColor * (uLevel * band * inside + uEdge * edgeBand * rim), 1.0);
      }`;
    this.mesh = new THREE.Mesh(
      new THREE.PlaneGeometry(panel.w / 1000, panel.h / 1000),
      new THREE.ShaderMaterial({ uniforms: this.u, vertexShader: UV_VERT, fragmentShader: frag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }),
    );
    this.mesh.position.z = 0.5 / 1000;
    this.mesh.renderOrder = OVER;
    this.mesh.frustumCulled = false;
  }

  set(x: number, half: number, level: number, edge = 0) {
    this.mesh.visible = level > 1e-4 || edge > 1e-4;
    this.u.uX!.value = x;
    this.u.uHalf!.value = half;
    this.u.uLevel!.value = level;
    this.u.uEdge!.value = edge;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
