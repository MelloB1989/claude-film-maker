// Where the 3D kit's flat things stand (panels, cards), as pure functions of their sizes, the frame's aspect and, for
// cards, a fractional slot (an advance on the beat eases one slot to the next). World units; y up; the camera looks
// down −z at rest, so +z is toward it. Each placement is a position and an XYZ rotation (radians).
import type { V3 } from './camera';

export interface Placement { pos: V3; rot: V3 }
export interface Size { w: number; h: number }

export type PanelLayout = 'single' | 'pair' | 'stack' | 'fan';
export const PANEL_LAYOUTS: readonly PanelLayout[] = ['single', 'pair', 'stack', 'fan'];

const rad = (d: number) => (d * Math.PI) / 180;

/**
 * Panels in a layout: 'single' (one, turned `tilt`° toward the frame's right), 'pair' (side by side, each turned
 * inward like an open book; stacked one over the other in a tall frame), 'stack' (a cascade receding in depth, the
 * first in front), 'fan' (on an arc, each turned to face its centre; tighter in a tall frame). `gap` in world units.
 */
export function panelPlacements(layout: PanelLayout, sizes: readonly Size[], o: { aspect: number; tilt?: number; gap?: number }): Placement[] {
  const n = sizes.length, tilt = rad(o.tilt ?? 14), tall = o.aspect < 1;
  const wMax = Math.max(...sizes.map((s) => s.w)), hMax = Math.max(...sizes.map((s) => s.h));
  const gap = o.gap ?? 0.12 * wMax;
  switch (layout) {
    case 'single':
      return sizes.map((_, i) => ({ pos: [0, 0, -i * gap], rot: [0, -tilt, 0] }));
    case 'pair': {
      if (tall) {
        let y = sizes.reduce((s, z) => s + z.h, 0) / 2 + (gap * (n - 1)) / 2;
        return sizes.map((s, i) => {
          y -= s.h / 2;
          const p: Placement = { pos: [0, y, 0], rot: [(i % 2 ? -1 : 1) * 0.5 * tilt, -0.6 * tilt, 0] };
          y -= s.h / 2 + gap;
          return p;
        });
      }
      let x = -(sizes.reduce((s, z) => s + z.w * Math.cos(tilt), 0) + gap * (n - 1)) / 2;
      return sizes.map((s, i) => {
        const w = s.w * Math.cos(tilt);
        x += w / 2;
        const side = (i + 0.5) / n < 0.5 ? 1 : -1;
        const p: Placement = { pos: [x, 0, -Math.sin(tilt) * s.w * 0.5], rot: [0, side * tilt, 0] };
        x += w / 2 + gap;
        return p;
      });
    }
    case 'stack':
      return sizes.map((_, i) => ({ pos: [i * 0.07 * wMax, -i * 0.09 * hMax, -i * (0.45 * wMax)], rot: [0, -tilt, 0] }));
    case 'fan': {
      const spread = rad(tall ? 11 : 17), R = wMax * (tall ? 2.6 : 1.9);
      return sizes.map((_, i) => {
        const a = (i - (n - 1) / 2) * spread;
        return { pos: [R * Math.sin(a), (tall ? -1 : -0.25) * (i - (n - 1) / 2) * 0.12 * hMax, R * (Math.cos(a) - 1)], rot: [0, -a - 0.25 * tilt, 0] };
      });
    }
    default:
      throw new Error(`unknown panel layout '${layout as string}' (layouts: ${PANEL_LAYOUTS.join(', ')})`);
  }
}

export type CardLayout = 'carousel' | 'fan' | 'stack' | 'grid';
export const CARD_LAYOUTS: readonly CardLayout[] = ['carousel', 'fan', 'stack', 'grid'];

/**
 * Card i of n placed for a fractional slot `k` (the card in front is index round(k); k = 1.5 is half way from card 1
 * to card 2): 'carousel' (on a ring facing out, turned so card k faces the camera), 'fan' (a hand of cards, card k
 * raised and square to the camera), 'stack' (a deck: cards before k have flown off up and away, the rest recede), 'grid'
 * (rows and columns for the aspect; card k lifts toward the camera). `w`, `h`: a card's size.
 */
export function cardPlacement(layout: CardLayout, i: number, n: number, k: number, size: Size, aspect: number): Placement {
  const { w, h } = size, d = i - k;
  switch (layout) {
    case 'carousel': {
      const step = (2 * Math.PI) / Math.max(n, 9), R = (w * 0.6) / Math.tan(step / 2);
      const a = d * step;
      return { pos: [R * Math.sin(a), 0, R * (Math.cos(a) - 1)], rot: [0, a, 0] };
    }
    case 'fan': {
      const a = d * rad(9);
      const lift = Math.exp(-d * d * 2) * 0.12 * h;
      return { pos: [d * 0.42 * w, -0.9 * h * (1 - Math.cos(a)) + lift, -Math.abs(d) * 0.08 * w], rot: [0, 0, -a] };
    }
    case 'stack': {
      if (d < 0) {
        // gone: up and off to the side, turning
        const u = Math.min(1, -d);
        return { pos: [0.4 * w * u, 1.6 * h * u, 0.3 * w * u], rot: [-0.5 * u, 0.3 * u, -0.25 * u] };
      }
      return { pos: [d * 0.05 * w, -d * 0.06 * h, -d * 0.22 * w], rot: [0, 0, d * rad(1.2) * (i % 2 ? 1 : -1)] };
    }
    case 'grid': {
      const cols = Math.max(1, Math.round(Math.sqrt(n * (aspect >= 1 ? aspect : aspect * 1.4)) ) );
      const c = Math.min(cols, n), rows = Math.ceil(n / c);
      const col = i % c, row = Math.floor(i / c);
      const lift = Math.exp(-d * d * 3);
      return { pos: [(col - (c - 1) / 2) * w * 1.12, ((rows - 1) / 2 - row) * h * 1.12, lift * 0.35 * w], rot: [0, 0, 0] };
    }
    default:
      throw new Error(`unknown card layout '${layout as string}' (layouts: ${CARD_LAYOUTS.join(', ')})`);
  }
}

/** The box (w, h, centre) round placed rectangles, ignoring their turn (an upper bound good enough for framing). */
export function boundsOf(ps: readonly Placement[], sizes: readonly Size[]): { centre: V3; w: number; h: number } {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity, z = 0;
  ps.forEach((p, i) => {
    const s = sizes[Math.min(i, sizes.length - 1)]!;
    const cw = (s.w / 2) * Math.abs(Math.cos(p.rot[1])) + 1e-9;
    x0 = Math.min(x0, p.pos[0] - cw);
    x1 = Math.max(x1, p.pos[0] + cw);
    y0 = Math.min(y0, p.pos[1] - s.h / 2);
    y1 = Math.max(y1, p.pos[1] + s.h / 2);
    z += p.pos[2];
  });
  return { centre: [(x0 + x1) / 2, (y0 + y1) / 2, z / Math.max(1, ps.length)], w: x1 - x0, h: y1 - y0 };
}

/**
 * The slot at song time t for cards that advance one slot every `every` beats from beat `b0` (the shot's first), easing
 * each step on the house spring's curve in `dur` s. `beatAt` and `timeOfBeat` are the film's grid. Clamped to [0, n−1].
 */
export function slotAt(t: number, grid: { beatAt(t: number): number; timeOfBeat(b: number): number }, b0: number, every: number, n: number, dur = 0.45): number {
  const steps = Math.floor((grid.beatAt(t) - b0) / every + 1e-9);
  if (steps < 1) return 0;
  const last = Math.min(steps, n - 1);
  const tStep = grid.timeOfBeat(b0 + last * every);
  const u = Math.min(1, Math.max(0, (t - tStep) / dur));
  const e = 1 - Math.pow(1 - u, 3);
  return steps > n - 1 ? n - 1 : last - 1 + e;
}
