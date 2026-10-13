// The per-scene data for the product scenes. Image coordinates are normalised: (0,0) top-left, (1,1) bottom-right of
// the screenshot. Every scene uses the real staging captures in assets/ui/ (INDEX.md lists their regions).
import type { Cfg } from './geometry';

// (relative to the film folder, so the scratch film resolves it too)
const UI = '../campx-launch/assets/ui/';
const Q1 = UI + 'control_flagged_q1.png';
const Q4 = UI + 'control_workspace_q4.png';
const Q4H = UI + 'control_hover_accept_q4.png';

/** PNG pixels to image coordinates, for a capture `h` px tall (the captures are 3200 wide; most are 1800 tall). */
const pxOf = (h: number) => (x: number, y: number): [number, number] => [x / 3200, y / h];
/** An INDEX.md region (x, y, w, h in PNG pixels) as [u0, v0, u1, v1], for a capture `ih` px tall. */
const rgOf = (ih: number) => (x: number, y: number, w: number, h: number): [number, number, number, number] => [x / 3200, y / ih, (x + w) / 3200, (y + h) / ih];
const px = pxOf(1800), rg = rgOf(1800);
const pxT = pxOf(2500), rgT = rgOf(2500);

// Times are the scene's local seconds, set on the VO words (data/vo.json; film time = scene start + t).

// ingestui (film 29-35): 'and checks each script for tampering' 29.44-31.6, 'before an evaluator ever sees it' 32.0-34.1.
// Opens close on the tall capture's Ingestion pipeline (row text about 24 px on a 1080p frame): the seven stage
// circles light one after another, 0.18 s apart from 29.4, as if each script passes every stage; then on 'before
// an evaluator ever sees it' a slow pull back and up to the green 'All scripts processed' banner.
// Every callout points at a row that says it.
const STAGE_Y = [1430, 1530, 1630, 1730, 1830, 1930, 2029]; // the stage circles' centres (x 646, radius about 20 px)
export const ingestui: Cfg = {
  images: [{ src: UI + 'ingestui_batch_stages_tall.png' }],
  base: { h: 0.9 },
  yaw: -12,
  cam: [
    { t: -0.4, x: 0.325, y: 0.688, z: 2.2, ax: 0.4, ay: 0.52 },
    { t: 3.0, x: 0.335, y: 0.694, z: 2.38, ax: 0.4, ay: 0.52 },
    { t: 5.3, x: 0.565, y: 0.3, z: 1.78, ax: 0.5, ay: 0.44 },
    { t: 6.4, x: 0.565, y: 0.3, z: 1.72, ax: 0.5, ay: 0.44 },
  ],
  spots: [
    // the pipeline rows, then the banner above them
    { t0: -0.7, t1: 4.9, rect: rgT(592, 1262, 2532, 800), pad: 0.004 },
    { t0: 3.3, t1: 6.8, rect: rgT(566, 628, 2574, 152), pad: 0.004 },
  ],
  ticks: STAGE_Y.map((y, i) => ({ t: 0.4 + 0.18 * i, at: pxT(646, y), r: 21 / 3200, until: 4.7, tone: 'accent' as const })),
  callouts: [
    // 'Page preparation & tamper checks': the leader lands at 29.6 on 'checks'
    { t: 1.2, until: 4.3, text: 'Tamper-checked', at: pxT(1250, 1830), off: [150, -70] },
    // 'Anonymisation', in by 30.55
    { t: 1.4, until: 4.4, text: 'Identity removed', at: pxT(980, 1930), off: [380, 60] },
    // 'This ZIP held 2 scripts: ...'
    { t: 4.2, text: 'Split per booklet', at: pxT(925, 764), off: [150, 90] },
  ],
};

// readui (film 42-49): 'even when an answer runs across pages' 43.1-45.0. Q1's card says
// 'Where this answer sits / Check: page 11 may belong to 1 or 7'; then the page beside its transcription.
export const readui: Cfg = {
  images: [{ src: Q1 }, { src: UI + 'readui_transcript_q4.png', from: 3.7, fade: 0.9 }],
  base: { w: 0.74 },
  yaw: -12,
  cam: [
    { t: 0, x: 0.55, y: 0.45, z: 0.96 },
    { t: 1.6, x: 0.82, y: 0.32, z: 2.45, ax: 0.58 },
    { t: 3.4, x: 0.82, y: 0.33, z: 2.5, ax: 0.58 },
    { t: 5.0, x: 0.56, y: 0.46, z: 1.04, ax: 0.5 },
    { t: 7, x: 0.57, y: 0.47, z: 1.08, ax: 0.5 },
  ],
  spots: [
    // (they overlap, so the crossfade between the captures happens on the dark stage)
    { t0: 0.7, t1: 4.1, rect: rg(2426, 512, 713, 106), pad: 0.006 },
    { t0: 3.5, t1: 7.4, rect: rg(380, 520, 2760, 900), pad: 0.004 },
  ],
  boxes: [
    { t: 4.6, until: 6.9, rect: rg(392, 560, 1650, 100), tone: 'accent2' },
    { t: 5.0, until: 6.9, rect: rg(2440, 785, 560, 100), tone: 'accent2' },
  ],
  callouts: [
    { t: 1.1, until: 3.7, text: 'Pages mapped to questions', at: px(2418, 565), off: [-150, 90] },
    { t: 4.8, until: 7.0, text: 'Transcribed', at: px(2422, 1000), off: [-120, 40] },
  ],
};

// markui (film 55-62): 'Medha suggests a mark' 54.6-55.6, 'and shows exactly why' 55.6-56.5. Opens on the
// written reasoning (lands about t=1.0), then lets the card breathe: the suggested mark and the point-by-point ticks.
export const markui: Cfg = {
  images: [{ src: Q4 }],
  base: { w: 0.74 },
  yaw: -12,
  cam: [
    { t: 0, x: 0.78, y: 0.56, z: 1.3, ax: 0.6 },
    { t: 1.1, x: 0.86, y: 0.59, z: 2.4, ax: 0.62 },
    { t: 3.4, x: 0.86, y: 0.59, z: 2.45, ax: 0.62 },
    { t: 5.0, x: 0.84, y: 0.5, z: 1.75, ax: 0.6 },
    { t: 7, x: 0.83, y: 0.5, z: 1.68, ax: 0.58 },
  ],
  spots: [
    // 'Identifies high-rise buildings...' with its written reasoning
    { t0: 0.2, t1: 3.9, rect: rg(2394, 880, 774, 370), pad: 0.004 },
    { t0: 3.9, t1: 7.6, rect: rg(2394, 400, 774, 1040), pad: 0.004 },
  ],
  callouts: [
    { t: 0.35, until: 3.9, text: 'Shows exactly why', at: px(2412, 990), off: [-130, 0] },
    { t: 4.4, text: 'Suggested mark', at: px(2800, 459), off: [-300, 60] },
    { t: 5.2, text: 'Point by point', at: px(2412, 660), off: [-130, 40] },
  ],
};

// control (film 62-78): 'Evaluators see the script and Medha's suggestions side by side' 65.6-69.6 (t 3.6-7.6),
// 'Accept' 70.31 (t 8.31), 'adjust' 71.04 (t 9.04), 'override' 71.91 (t 9.91), 'in seconds' 72.4-73.0,
// 'Anything uncertain is flagged for a closer look' 73.52-76.1, 'flagged' 74.79 (t 12.79).
// No capture shows a changed mark, so 'adjust' and 'override' are clicks into the empty marks field: no number.
export const control: Cfg = {
  images: [{ src: Q4 }, { src: Q4H, from: 7.9, fade: 0.25 }],
  base: { w: 0.74 },
  yaw: -9,
  cam: [
    // the hero: the whole workspace floating crisp in the dark, under a slow parallax push (the frame turns
    // a few degrees against the far lights) through 'side by side' (t 3.6-7.6)
    { t: 0, x: 0.5, y: 0.5, z: 0.88, yaw: 3 },
    { t: 3.6, x: 0.5, y: 0.5, z: 0.93, yaw: 2 },
    { t: 7.5, x: 0.53, y: 0.5, z: 1.06, yaw: -1.5 },
    // then across to Medha's panel: Accept, the marks field
    // a decisive push onto Accept as it is spoken (70.25), then down to the marks field for 'adjust, or override'
    { t: 8.05, x: 0.88, y: 0.3, z: 2.2, ax: 0.6 },
    { t: 8.6, x: 0.88, y: 0.31, z: 2.25, ax: 0.6 },
    { t: 9.3, x: 0.8, y: 0.68, z: 2.1, ax: 0.6 },
    { t: 11.0, x: 0.8, y: 0.68, z: 2.15, ax: 0.6 },
    // uncertain
    { t: 12.3, x: 0.8, y: 0.46, z: 2.5, ax: 0.6 },
    { t: 16, x: 0.8, y: 0.46, z: 2.35, ax: 0.6 },
  ],
  spots: [
    { t0: 7.4, t1: 9.4, rect: rg(2424, 426, 714, 64), pad: 0.008 },
    { t0: 8.7, t1: 11.4, rect: rg(2362, 1463, 838, 337), pad: 0.004 },
    { t0: 11.5, t1: 16.6, rect: rg(2394, 740, 774, 130), pad: 0.004 },
  ],
  cursor: [
    { t: 6.0, at: px(2100, 1000) },
    { t: 8.31, at: px(3054, 458), click: true },
    { t: 9.04, at: px(2560, 1537), click: true },
    { t: 9.91, at: px(2590, 1530), click: true },
    { t: 11.2, at: px(2840, 1537) },
  ],
  boxes: [
    { t: 8.95, until: 11.4, rect: rg(2493, 1499, 216, 77), tone: 'accent' },
    { t: 12.3, rect: rg(2476, 822, 662, 52), tone: 'accent' },
  ],
  // the pulse peaks 0.31 s after `t`: on 'flagged'
  chips: [{ t: 12.48, text: 'Flagged for review', at: px(2180, 851), tone: 'accent', pulse: true }],
};
