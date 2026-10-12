// The per-scene data for the product scenes. Image coordinates are normalised: (0,0) top-left, (1,1) bottom-right of
// the screenshot. Every scene uses the real staging captures in assets/ui/ (INDEX.md lists their regions).
import type { Cfg } from './geometry';

// (relative to the film folder, so the scratch film resolves it too)
const UI = '../campx-launch/assets/ui/';
const Q1 = UI + 'control_flagged_q1.png';
const Q4 = UI + 'control_workspace_q4.png';
const Q4H = UI + 'control_hover_accept_q4.png';

/** PNG pixels (the captures are 3200x1800) to image coordinates. */
const px = (x: number, y: number): [number, number] => [x / 3200, y / 1800];
/** An INDEX.md region (x, y, w, h in PNG pixels) as [u0, v0, u1, v1]. */
const rg = (x: number, y: number, w: number, h: number): [number, number, number, number] => [x / 3200, y / 1800, (x + w) / 3200, (y + h) / 1800];


export const ingestui: Cfg = {
  images: [{ src: UI + 'ingestui_batch_stages.png' }],
  base: { w: 0.74 },
  yaw: -12,
  cam: [
    { t: 0, x: 0.5, y: 0.5, z: 1 },
    { t: 1.6, x: 0.42, y: 0.3, z: 1.55, ax: 0.52 },
    { t: 3.0, x: 0.42, y: 0.3, z: 1.55, ax: 0.52 },
    { t: 4.2, x: 0.42, y: 0.86, z: 1.6, ax: 0.52, ay: 0.6 },
    { t: 6, x: 0.44, y: 0.86, z: 1.66, ax: 0.52, ay: 0.6 },
  ],
  spots: [
    { t0: 1.2, t1: 3.4, rect: rg(560, 640, 2600, 140), dim: 0.5, pad: 0.004 },
    { t0: 3.6, t1: 6, rect: rg(600, 1390, 2560, 380), dim: 0.5, pad: 0.004 },
  ],
  callouts: [
    { t: 1.6, until: 3.4, text: 'Split per booklet', at: px(568, 685), off: [-40, -120] },
    { t: 4.0, text: 'Tamper-checked', at: px(596, 1533), off: [-60, -130] },
    { t: 4.6, text: 'Identity removed', at: px(596, 1634), off: [-60, 110] },
  ],
};

export const readui: Cfg = {
  images: [{ src: UI + 'readui_transcript_q4.png' }],
  base: { w: 0.74 },
  yaw: -12,
  cam: [
    { t: 0, x: 0.5, y: 0.5, z: 1 },
    { t: 2.0, x: 0.3, y: 0.4, z: 1.75, ax: 0.42 },
    { t: 3.9, x: 0.3, y: 0.42, z: 1.75, ax: 0.42 },
    { t: 5.2, x: 0.86, y: 0.52, z: 1.9, ax: 0.6 },
    { t: 7, x: 0.86, y: 0.54, z: 1.95, ax: 0.6 },
  ],
  spots: [
    { t0: 1.6, t1: 4.2, rect: rg(380, 520, 1700, 560), dim: 0.5, pad: 0.004 },
    { t0: 4.5, t1: 7, rect: rg(2428, 758, 706, 640), dim: 0.5, pad: 0.004 },
  ],
  boxes: [
    { t: 2.6, until: 6.9, rect: rg(392, 560, 1650, 100), tone: 'accent2' },
    { t: 5.0, until: 6.9, rect: rg(2440, 785, 560, 100), tone: 'accent2' },
  ],
  callouts: [
    { t: 2.0, until: 4.2, text: 'Mapped to Q4', at: px(366, 533), off: [-60, -110] },
    { t: 5.2, text: 'Transcribed', at: px(2422, 1000), off: [-120, 40] },
  ],
};

export const markui: Cfg = {
  images: [{ src: Q1 }, { src: Q4, from: 4.6, fade: 0.8 }],
  base: { w: 0.74 },
  yaw: -12,
  cam: [
    { t: 0, x: 0.5, y: 0.5, z: 1 },
    { t: 1.6, x: 0.86, y: 0.42, z: 2.0, ax: 0.66 },
    { t: 4.4, x: 0.86, y: 0.5, z: 2.0, ax: 0.66 },
    { t: 5.6, x: 0.86, y: 0.5, z: 2.1, ax: 0.66 },
    { t: 7, x: 0.7, y: 0.5, z: 1.3 },
  ],
  spots: [
    { t0: 1.2, t1: 4.5, rect: rg(2394, 400, 774, 640), dim: 0.5, pad: 0.004 },
    { t0: 4.7, t1: 7, rect: rg(2394, 970, 774, 300), dim: 0.5, pad: 0.004 },
  ],
  callouts: [
    { t: 1.8, until: 4.4, text: 'Suggested mark', at: px(2795, 459), off: [-300, 60] },
    { t: 3.0, until: 4.4, text: 'Point by point', at: px(2412, 690), off: [-120, 30] },
    { t: 5.2, until: 6.9, text: 'Shows exactly why', at: px(2412, 1100), off: [-120, 0] },
  ],
};

export const control: Cfg = {
  images: [{ src: Q4 }, { src: Q4H, from: 5.0, fade: 0.25 }],
  base: { w: 0.74 },
  yaw: -9,
  cam: [
    { t: 0, x: 0.5, y: 0.5, z: 1 },
    { t: 3.4, x: 0.55, y: 0.5, z: 1.08 },
    { t: 4.6, x: 0.82, y: 0.36, z: 2.0, ax: 0.64 },
    { t: 7.6, x: 0.82, y: 0.36, z: 2.0, ax: 0.64 },
    { t: 8.6, x: 0.82, y: 0.88, z: 2.1, ax: 0.64 },
    { t: 11.6, x: 0.82, y: 0.88, z: 2.1, ax: 0.64 },
    { t: 12.6, x: 0.8, y: 0.52, z: 2.1, ax: 0.62 },
    { t: 16, x: 0.7, y: 0.5, z: 1.25 },
  ],
  spots: [
    { t0: 4.4, t1: 7.8, rect: rg(2394, 400, 774, 640), dim: 0.5, pad: 0.004 },
    { t0: 8.4, t1: 11.8, rect: rg(2362, 1463, 838, 337), dim: 0.5, pad: 0.004 },
    { t0: 12.4, t1: 16, rect: rg(2394, 770, 774, 160), dim: 0.5, pad: 0.004 },
  ],
  cursor: [
    { t: 3.0, at: px(2100, 1000) },
    { t: 5.6, at: px(3054, 458), click: true },
    { t: 8.8, at: px(3054, 458) },
    { t: 10.2, at: px(2600, 1535), click: true },
    { t: 12.0, at: px(2900, 1535) },
    { t: 13.4, at: px(2960, 850) },
  ],
  boxes: [{ t: 12.7, rect: rg(2476, 822, 662, 52), tone: 'accent' }],
  chips: [{ t: 12.9, text: 'Flagged for review', at: px(2180, 851), tone: 'accent', pulse: true }],
};
