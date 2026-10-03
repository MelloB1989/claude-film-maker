# GitLoom launch film, Plan 3: transitions, sound effects and the final mix (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (the user's method in
> Plans 1 and 2) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the film its transitions and its sound. The engine learns to hold two scenes on screen across a cut.
The 14 cuts are designed and built. A sound-effects library is generated and placed from the timing data. The voice
gets its processing chain, and the final mix is built with stems. The whole film is rendered at 1080p with the
Instagram 16:9 and 4:5 variants, then checkpoint C5.

**Architecture:**
- **Engine** (`app/src/engine/`):
  - `transition.ts` is the pure layer: specs, windows, side times, state over the shutter, validation.
  - `transition-gl.ts` is one shader pass that composites two scene textures.
  - `engine.ts` composes a frame as a list of layers (scene, transition or overlay). This replaces the overlap
    crossfade that M13 found broken.
- **Transitions** (`app/src/transitions/<from>-<to>.ts`): one file per cut, each default-exporting a
  `TransitionSpec`. The timeline globs them the way it globs scenes, so parallel tasks never share a registry file.
  A pair with no file stays a hard cut.
- **Cues** (`app/src/sfx/`): one cue module per scene. Each derives its events from the scene's own time module,
  the voice onsets, the beat grid and the Blender tracks. `app/scripts/cues.ts` writes the cue sheet,
  `data/sfx.json`.
- **Python** (`tools/gitloom_film/`):
  - `sfxlib.py` generates and caches the sound library through ElevenLabs.
  - `sfx.py` renders the cue sheet into an SFX bus.
  - `vochain.py` processes the voice.
  - `mix.py` builds the stems and the master.
  - `deliver.py` renders the film in segments and encodes the deliverables.

**Tech stack:** as Plan 2: bun, TypeScript, three.js, Vite and headless Chrome for the engine; Python 3.12 (uv),
numpy, scipy, soundfile, librosa and ffmpeg for the audio. ElevenLabs `POST /v1/sound-generation`.

**Spec:** `docs/specs/2026-09-30-gitloom-launch-film-design.md`:
- §4: the scene treatments and their transitions;
- §5.1: the voice processing;
- §5.3: sound effects;
- §5.4: mix and master;
- §6: visual and motion;
- §8.3 and §9: checkpoint C5;
- §11: facts.

**The rulings that bind this plan:**
- Plan 1's ledger: `docs/ledgers/2026-09-30-plan-1-ledger.md`.
- Plan 2's ledger: `.superpowers/sdd/2026-10-01-plan-2-look-development/progress.md`.
- The engine review: `.superpowers/sdd/2026-10-01-plan-2-look-development/interim-review-engine-findings.md`. Its M13
  is fixed here.

This is **Plan 3 of 4**:
- Plan 1 (done): voice, score, timing, animatic.
- Plan 2 (done, C4 locked): look, all 15 scenes.
- Plan 3 (this one): transitions, SFX, voice chain, final mix, the 1080p film, C5.
- Plan 4: 4K finals and deliverables.

**Out of scope:**
- The sung-hook A/B (spec §5.2, C5). The user did not ask for it.
- Per-scene pacing re-cuts. The edit in `data/vo.json` stays locked.
- 4K.

## Global Constraints

**Carried over from Plans 1 and 2** (the full text is in Plan 2's Global Constraints; it all still binds):
- **Repo:** `~/Developer/code/gitloom-film`. **Branch:** continue on `plan-2-look`, or branch `plan-3-sound` from it.
  Each task commits on that branch.
- **Palette:** the 15 tokens only (ink `#110d10` … moss `#4aad63`). Blood is the accent, moss is gain.
  **Only blood and moss may glow; bone never blooms.**
- **Fonts and copy:**
  - Bricolage Grotesque, JetBrains Mono and Geist only, always kerned.
  - Display text uses typographic punctuation.
  - Every new on-screen string passes `film-facts`.
- **Determinism:** scenes, transitions and cue modules are pure functions of time and data. There is no
  `Math.random`, `Date` or `performance.now()` for anything that renders or sounds; use seeded `hash`/`mulberry32`
  only. Rendering the same `t` twice, in any order, gives byte-identical frames.
- **Timing data is locked:** `data/vo.json` and `data/audio.json` do not change in this plan. `film-sync` must still
  pass, with the same 3 waived act cuts. Every time comes from the data (word onsets, beats, downbeats, scene
  windows, Blender tracks); **never hard-code seconds**.
- **Cut-aware shutter (E1):**
  - A frame never mixes the two sides of a hard cut.
  - Scene boundaries sit 8 ms after a frame time, so the first frame of scene B is `ceil(cut·30)`.
  - A transition is the only thing allowed to put two scenes in one frame, and only inside its own window.
- **The frame grid:** type changes state on output frames (`frameIdx`), one state per shutter. Review stills are
  taken at frame times `n/30`, never within 0.1 frame of `n + 0.5` (`render.ts stills` warns).
- **Secrets:** the key in `~/11labs` is read at runtime only. It is never printed, logged, put in a manifest,
  repr or exception, or committed. Every API call logs its `character-cost` to `audio/credits.log`.
- **Loudness:** −14 LUFS integrated (±0.5) and true peak ≤ −1.0 dBTP, at 48 kHz / 24-bit. The music ducks 6–9 dB
  under the voice.
- **Commits:**
  - End each message with a blank line, then `Co-Authored by MelloB's coding agent <build@mellob.in>`.
  - Stage by explicit path. Never `git add -A`, never `git clean`.
  - Renders live in `out/` (gitignored). Audio stems and the sound library WAVs live under gitignored `audio/` paths;
    their manifests are committed.

**New in Plan 3:**
- **Transition windows:**
  - Each side is at most 0.5 s, and at most 25% of that side's scene window.
  - **No voice word onset may fall inside `[cut − pre, cut + post + 1/30)`**: a word is never spoken while its scene
    is mid-whip.
  - The cut instant (the moment B takes over) is the scene boundary from `vo.json`, so the cut stays on its beat.
- **Do not steal read time** (Plan 2's pacing notes):
  - braid's result card is on screen only 0.6 s before its cut, and cite's settled chain only 0.2 s, so their `pre`
    is ≤ 0.1 s.
  - connect's cards get about 0.35 s each; its `pre` is ≤ 0.1 s.
- **Plate scenes cannot run past their plates.** thread (B01), her (B03, its first 34 frames), loom (B05), braid
  (B08) and weave (B15) hold their first or last frame inside a transition (`'hold'`). Only engine-built content may
  `'run'`, and only within the scene's declared `handles`.
- **SFX:**
  - Every cue is tied to an anchor: a word, a beat, a downbeat, a track event, a scene event from its time module, or
    a transition.
  - A one-shot sound's hit (its transient, or for risers its peak) lands on the cue time within one sample.
  - The library stays within the spec's 4–8k credits. `film-sfx-lib gen` refuses a run whose estimate exceeds
    `--budget` (default 8000).
- **Operational rules** (learned in Plan 2):
  - Wrap every long render (Blender, or a `render.ts video` over about 2 min) in `caffeinate -i`. The Mac idle-sleeps
    otherwise, and a Cycles GPU fault across sleep/wake blacked out loom's threads.
  - **Never block-wait more than about 4 minutes.** Run long jobs in the background. Poll `<out>.progress`
    (render.ts) or the output's growth in short calls, or end the turn and let the controller verify. Give the user
    an ETA and the `.progress` path.
  - **Commit checkpoints early.** Commit after each green test cycle and before any long render; uncommitted work
    died with agents twice in Plan 2.
  - **One Cycles job at a time.** Never run Blender alongside an engine export: Chrome silently falls back to
    SwiftShader under GPU load, and render.ts now fails on that.
  - **Verify on a clean worktree.** Render deliverable stills and clips only after the task's last commit, then
    re-run the tests in a fresh worktree:
    `git worktree add ../gitloom-film-verify HEAD && cd ../gitloom-film-verify/app && bun install && bun test src && bun run typecheck`,
    and remove the worktree afterwards.
  - **Parallelism:** at most two engine tasks render at once (GPU), and they touch disjoint files. Python tasks may
    run beside them. If git reports `index.lock`, wait 2 s and retry.

## Review Focus

These are the failure modes most likely to bite, each pinned by a test in its owning task.

1. **The cache re-spends credits.** Re-running `film-sfx-lib gen` after a crash, a palette edit to one sound, or with
   a different working directory must call the API only for requests not already on disk. An unchanged request is
   never paid for twice. Tested in Task 2.
2. **Cues drift from the data.** If every word, beat, scene window and track frame shifts by +0.5 s, every cue must
   shift by exactly +0.5 s. A cue whose anchor word no longer exists must fail loudly, not vanish. Tested in Task 8.
3. **Hot SFX transients break the master.** A mix whose SFX bus carries full-scale transients still meets −14 LUFS
   ±0.5 and ≤ −1.0 dBTP, still keeps the drawn arc, and the stems still sum to the pre-limiter mix. Tested in Task 9.
4. **A transition asks a scene for a time it can't render.** A plate scene inside a transition never has `prepare`
   or `render` called outside its window. A `'run'` side is clamped to the scene's declared handles, so the export
   never fails on a missing plate frame. Tested in Task 1.
5. **The deliverables drift against the picture.** Every encode starts its audio and video at 0. The film is 2808
   frames at 30 fps, and the audio is 93.6 s ±1 frame. A snap cue in the mix lands within one frame of the snap in
   the picture. Tested in Task 10.

## File map

```
app/src/engine/transition.ts       pure: specs, windows, side times, states over the shutter, validation       (Task 1)
app/src/engine/transition-gl.ts    one compositing pass: whip / zoom / match / xfade / dip, shutter taps         (Task 1)
app/src/engine/engine.ts           layers per sub-frame (scene | transition | overlay), M13 fixed               (Task 1)
app/src/engine/scene.ts            Scene.handles; Frame.under/tin/tout and handlesTransition removed            (Task 1)
app/src/engine/transition.test.ts  engine.test.ts (additions)                                                     (Task 1)
app/src/timeline.ts main.ts        makeTransitions (glob of transitions/*.ts); ?transition=<file>               (Task 1)
app/scripts/render.ts              --transition <name> [--frames ±k]                                              (Task 1)
app/src/transitions/_probe-*.ts    dev probes (excluded from the film's glob)                                     (Task 1)
app/src/transitions/<a>-<b>.ts     the 14 cuts, one file each, plus group tests                                   (Tasks 4–7)
tools/gitloom_film/elevenlabs.py   + ElevenLabs.sound() for /v1/sound-generation                                  (Task 2)
data/sfx_palette.json              the sound palette: prompts, durations, alignment, gains (hand-edited)         (Task 2)
tools/gitloom_film/sfxlib.py       film-sfx-lib: plan | gen | qc | sheet; cache + manifest                        (Task 2)
audio/sfx/manifest.json           committed; audio/sfx/lib/** is gitignored                                     (Task 2)
tools/gitloom_film/vochain.py      film-vo-chain: the §5.1 processing → audio/vo/vo-chain.wav                    (Task 3)
app/src/sfx/cue.ts sheet.ts        cue types, helpers, the sheet builder                                         (Task 8)
app/src/sfx/scenes/<id>.ts         one cue module per scene (15)                                                 (Task 8)
app/src/sfx/transitions.ts         whooshes for whips and zoom-throughs                                          (Task 8)
app/scripts/cues.ts                writes data/sfx.json                                                           (Task 8)
tools/gitloom_film/sfx.py          film-sfx: data/sfx.json → audio/sfx/sfx.wav (bus), ducks                      (Task 9)
tools/gitloom_film/mix.py          mix_stems: vo + music + sfx → audio/mix/{mix,vo,music,sfx}.wav               (Task 9)
tools/gitloom_film/deliver.py      film-deliver: segments | render | assemble | check                            (Task 10)
out/rough.mp4, out/film/*, out/instagram/*, out/review/c5/                                                       (Tasks 10–11)
```

---
## Part A: foundations (Tasks 1–3, which may run in parallel: Task 1 is TypeScript, Tasks 2–3 are Python)

### Task 1: Transitions and overlays in the engine (fixes M13)

**Time:** about 4 h (Opus; the engine is the riskiest code in the plan).

**Files:**
- Create: `app/src/engine/transition.ts`, `app/src/engine/transition-gl.ts`, `app/src/engine/transition.test.ts`,
  `app/src/transitions/_probe-whip.ts`, `app/src/transitions/_probe-zoom.ts`, `app/src/transitions/_probe-match.ts`,
  `app/src/transitions/_probe-xfade.ts`, `app/src/transitions/_probe-dip.ts`
- Modify:
  - `app/src/engine/engine.ts`: `onScreen`, `shutterPlan` (kept, wrapped), `prepare`, `releaseEnded`,
    `exportFrames`, `render`, `composite`; the `xfade` pass is removed.
  - `app/src/engine/scene.ts`: add `handles`; remove `Frame.under`, `tin`, `tout` and `handlesTransition`.
    `grep -rn "under\|tin\b\|tout\|handlesTransition" app/src/scenes` must be empty first. Plan 2 left no user.
  - `app/src/engine/engine.test.ts`, `app/src/timeline.ts`, `app/src/main.ts`, `app/scripts/render.ts`.

**Interfaces:**
```ts
// transition.ts (pure: no three.js, bun-testable)
export type TransitionKind = 'cut' | 'whip' | 'match' | 'zoom' | 'xfade' | 'dip';
export type SideMode = 'hold' | 'run';
export interface Handles { head: number; tail: number }          // s a scene may render before its start / after its end
export interface TransitionSpec {
  from: string; to: string; kind: TransitionKind;                 // adjacent scene ids in vo.json
  pre: number; post: number;                                       // s of window before / after the cut (0, 0 for 'cut')
  fromMode?: SideMode; toMode?: SideMode;                          // default 'hold'
  dir?: [number, number];        // whip: unit direction the CAMERA travels (logical px axes: +x right, +y down);
                                 //       the picture moves the other way
  distance?: number;             // whip: logical px the picture travels over the window (default: the frame's extent along dir)
  center?: [number, number];     // zoom: logical px the camera pushes through (A) and emerges from (B)
  scale?: number;                // zoom: A's scale at the cut (default 5); B starts at `bFrom` (default 1.6) and settles to 1
  bFrom?: number;
  soft?: number;                 // match: luma-key softness (default 0.12)
  ease?: 'inOutQuart' | 'inOutCubic' | 'outExpo';                 // default 'inOutQuart'
}
export interface TransitionEntry { id: string; spec: TransitionSpec; cut: number; start: number; end: number } // id = `${from}-${to}`
export interface Xform { tx: number; ty: number; s: number; cx: number; cy: number }   // logical px; s about (cx, cy)
export interface TransitionState {
  wB: number;        // B's weight 0..1 ('both' kinds); 0 or 1 for frame-sided kinds
  a: Xform; b: Xform;
  ink: number;       // 0..1 dip toward ink
  match: number;     // match: luma threshold 1 → 0 (1 = all A); other kinds: -1
}
export function transitionEntries(specs: TransitionSpec[], scenes: SceneSpan[], words: { start: number; w?: string }[]): TransitionEntry[]; // validates; throws naming the pair
export function sideTime(mode: SideMode, t: number, w: { start: number; end: number }, h: Handles): { time: number; held: boolean };
export function stateAt(e: TransitionEntry, t: number): TransitionState;
export function shutterTaps(e: TransitionEntry, t: number, dt: number, shutter: number, n: number): TransitionState[]; // n states evenly over [t − dt·shutter/2, t + dt·shutter/2]
export function tapCount(e: TransitionEntry, t: number, dt: number, shutter: number, pxScale: number): number; // 1..MAX_TAPS: ceil(max physical streak px / 1.5)
export function matchWeight(threshold: number, lumaA: number, soft: number): number;    // smoothstep(threshold − soft, threshold + soft, lumaA): B's weight
export const MAX_TAPS = 96;
// transition-gl.ts
export class TransitionPass { render(r: THREE.WebGLRenderer, a: THREE.Texture, b: THREE.Texture, taps: TransitionState[], out: THREE.WebGLRenderTarget): void; dispose(): void }
// engine.ts
export interface TimelineEntry { /* … as now … */ kind?: 'scene' | 'overlay' }   // default 'scene'
export type Layer<E extends Span = TimelineEntry> =
  | { kind: 'scene'; at: EntryAt<E> }
  | { kind: 'transition'; tr: TransitionEntry; a: EntryAt<E>; b: EntryAt<E> }
  | { kind: 'overlay'; at: EntryAt<E> };
export function framePlan<E extends Span & { id: string; kind?: 'scene' | 'overlay' }>(timeline: readonly E[], transitions: readonly TransitionEntry[], t: number, dt: number, shutter: number, offsets: readonly number[], handles?: (id: string) => Handles): Layer<E>[][];
export function lastUse(e: Span & { id: string }, transitions: readonly TransitionEntry[]): number;   // max(e.end, end of any transition from e)
export function firstUse(e: Span & { id: string }, transitions: readonly TransitionEntry[]): number;  // min(e.start, start of any transition into e)
// Engine: constructor(canvas, makeTimeline, makeTransitions?: (vo: VO) => TransitionSpec[]); transitions: TransitionEntry[]
// scene.ts: abstract class Scene { handles: Handles = { head: 0, tail: 0 } … }
// timeline.ts
export function makeTransitions(vo: VO): TransitionSpec[];   // eager glob of ./transitions/*.ts, excluding _*.ts and *.test.ts
```

**Behaviour:**
- **Validation** (`transitionEntries`). For each spec:
  - `from` and `to` are adjacent in `vo.scenes`, and `cut` is the boundary between them.
  - `0 ≤ pre, post ≤ 0.5`, `pre ≤ 0.25·|A|` and `post ≤ 0.25·|B|`.
  - `'cut'` has `pre = post = 0`.
  - At most one spec per pair, and no two windows overlap.
  - No word onset in `words` falls in `[cut − pre, cut + post + 1/30)`.

  The error names the pair and the rule, for example `transition loom-diff: word "Change" (37.971) starts inside
  [37.708, 37.941)`.
- **The frame plan** (`framePlan`). For the frame at `t`:
  - If `t` lies in a transition's `[start, end)`, the pair is replaced by one transition layer. Its `a` and `b`
    times per sub-frame come from `sideTime(mode, s, window, handles(id))`. `'hold'` clamps into the scene's own
    window: before the start it is the start, and at or past the end it is `end − HOLD`. `'run'` clamps into
    `[start − head, end + tail)` instead.
  - Otherwise the plan is exactly `shutterPlan`'s, as scene layers.
  - Overlay entries come last, in start order, at their own times, and are never crossfaded.
  - The transition's own motion is evaluated at the frame's `t` (see Shutter, below), never per sub-frame.
- **Shutter: motion-blur aware, without double smear:**
  - The scenes inside a transition render at their sub-frame times as usual, so their content keeps the engine's
    sub-frame blur.
  - The transition's own motion (whip translation, zoom scale, weights) is **not** sampled per sub-frame. Every
    sub-frame composites with the same `shutterTaps(e, t, dt, shutter, n)` (with `n = tapCount(…)`): the
    transition's analytic blur over the whole shutter. So a whip streaks continuously even at 4 sub-frames, and the
    adaptive sampler converges on the scenes' own motion, not on the whip's.
  - `tapCount` uses the physical streak, so a 4K render (`--scale 2`) gets twice the taps. That is Plan 4's need.
- **Kinds** (`stateAt`; `u = (t − start)/(end − start)` and `uc = pre/(pre + post)`):
  - **`cut`:** no window. It exists so the registry and the cues know the cut was designed.
  - **`whip`:** `e(u)` runs in-ease over `[0, uc] → [0, 0.5]` and out-ease over `[uc, 1] → [0.5, 1]`. A moves by
    `−dir·distance·e(u)` and B by `dir·distance·(1 − e(u))`, so the two pictures abut like a pan across one strip.
    `wB` is 1 where B covers a pixel and 0 where A does (the shader decides from the rect). At the cut they meet
    half way.
  - **`zoom`:**
    - Before the cut, A scales from 1 to `scale` about `center`, in-quart.
    - After the cut, B scales from `bFrom` to 1 about `center`, out-quart.
    - The side is chosen by the frame's `t` (`wB` is 0 or 1). The taps give the radial blur.
  - **`match`:**
    - A and B are both shown through the window.
    - B's weight per pixel is `matchWeight(threshold(u), luma(A_display), soft)`, where `threshold` runs from 1 at
      `start` to 0 at `end`, through 0.5 at the cut. B appears first where A is brightest: fibres become numerals.
  - **`xfade`:** `wB = ease.inOutCubic(u)`, in linear light.
  - **`dip`:** A fades to ink over `[start, cut)` and B fades in from ink over `[cut, end)`. The side is chosen by
    the frame's `t`, so A and B never mix. Set `post = 0` for a hard in.
- **GL** (`TransitionPass`):
  - One full-screen pass that reads A and B. Taps go in as a uniform array (≤ 96 states, packed).
  - Per tap it samples A and B through their transforms. Outside a texture it shows ink. It applies the kind's
    weights and averages the taps.
  - Bone stays below the bloom threshold: the pass does not brighten anything.
  - The output is HDR linear into a dedicated target.
- **Targets (M13):**
  - Each layer renders into its own target: the transition's A, B and output, and the overlay's ping-pong pair. No
    pass ever reads the target it writes.
  - The old `mixRT` crossfade path is deleted. Overlapping scene windows without a transition are an error at
    `init`.
- **Lifecycle:**
  - `prepare(t)` prepares both sides of a transition at each sub-frame's side time.
  - `releaseEnded` disposes a scene only when `lastUse(entry) ≤ t`.
  - `exportFrames`' pre-flight loads a scene for any frame where it is a transition side.
  - The "adaptive needs stateless scenes" check covers transition sides too.
- **Review tooling:**
  - `main.ts`: `?transition=<file>` loads `transitions/<file>.ts` as the only transition (an `_probe-*` file too),
    with `only=<from>,<to>`.
  - `render.ts stills|video|sheet --transition <file>`:
    - the range defaults to `[start − 1, end + 1]` (`cut ± 1` for `'cut'`);
    - `--frames -3,-2,-1,0,1,2` gives stills at film frames relative to B's first frame `F = ceil(cut·30)`;
    - the default output is `out/transitions/<file>/` (stills) or `out/transitions/<file>.mp4` (video).
- **Probes:** `_probe-whip.ts` is `{ from: 'cite', to: 'braid', kind: 'whip', pre: 0.1, post: 0.15, dir: [1, 0] }`.
  The other probes use the same pair with their own kind. They are dev harnesses only.

**Tests (bun, `transition.test.ts` and `engine.test.ts`):**
```ts
import { describe, expect, test } from 'bun:test';
import { MAX_TAPS, matchWeight, shutterTaps, sideTime, stateAt, tapCount, transitionEntries, type TransitionSpec } from './transition';
import { framePlan, lastUse, shutterOffsets, shutterPlan } from './engine';

const scenes = [{ id: 'a', act: 'I', start: 0, end: 4.008 }, { id: 'b', act: 'I', start: 4.008, end: 8.008 }, { id: 'c', act: 'I', start: 8.008, end: 12 }];
const whip: TransitionSpec = { from: 'a', to: 'b', kind: 'whip', pre: 0.1, post: 0.1, dir: [1, 0] };
const [W] = transitionEntries([whip], scenes, []);
const tl = scenes.map((s) => ({ ...s }));

describe('validation', () => {
  test('a word spoken inside the window fails, naming the pair and the word time', () =>
    expect(() => transitionEntries([whip], scenes, [{ start: 4.05 }])).toThrow(/a-b.*4\.05/));
  test('non-adjacent pairs, long sides and a cut with a window fail', () => {
    expect(() => transitionEntries([{ ...whip, to: 'c' }], scenes, [])).toThrow(/adjacent/);
    expect(() => transitionEntries([{ ...whip, pre: 0.6 }], scenes, [])).toThrow(/0\.5/);
    expect(() => transitionEntries([{ ...whip, kind: 'cut' }], scenes, [])).toThrow(/cut/);
  });
});

describe('side times (Review Focus 4)', () => {
  test('hold clamps into the window; run clamps to the handles', () => {
    expect(sideTime('hold', 4.05, scenes[0]!, { head: 0, tail: 0 })).toEqual({ time: 4.008 - 1e-6, held: true });
    expect(sideTime('hold', 3.95, scenes[1]!, { head: 0, tail: 0 })).toEqual({ time: 4.008, held: true });
    const r = sideTime('run', 4.05, scenes[0]!, { head: 0, tail: 0.02 });
    expect(r.held).toBe(true); expect(r.time).toBeCloseTo(4.028, 5);   // clamped just inside end + tail
    expect(sideTime('run', 4.02, scenes[0]!, { head: 0, tail: 0.02 })).toEqual({ time: 4.02, held: false });
  });
  test('a plate scene in a transition is never asked for a time outside its window', () => {
    const offs = shutterOffsets({ min: 4, max: 324, tol: 3 });
    for (let n = 118; n < 125; n++) for (const sub of framePlan(tl, [W!], n / 30, 1 / 30, 0.5, offs))
      for (const l of sub) if (l.kind === 'transition') {
        expect(l.a.time).toBeLessThan(4.008); expect(l.b.time).toBeGreaterThanOrEqual(4.008);
      }
  });
});

describe('frame plan', () => {
  test('outside every transition it is shutterPlan, as scene layers', () => {
    const offs = shutterOffsets(12);
    const p = framePlan(tl, [W!], 2, 1 / 30, 0.5, offs), q = shutterPlan(tl, 2, 1 / 30, 0.5, offs);
    expect(p.map((s) => s.map((l) => l.kind === 'scene' && l.at))).toEqual(q.map((s) => s.map((x) => x)));
  });
  test('inside a transition the pair is one layer, and overlays come last', () => {
    const ov = { id: 'ov', act: '', start: 0, end: 12, kind: 'overlay' as const };
    const [sub] = framePlan([...tl, ov], [W!], 4.0, 1 / 30, 0.5, [0]);
    expect(sub!.map((l) => l.kind)).toEqual(['transition', 'overlay']);
  });
  test('a scene lives until the end of its outgoing transition', () => expect(lastUse(tl[0]!, [W!])).toBeCloseTo(4.108, 9));
});

describe('motion over the shutter', () => {
  test('taps are centred on t and span dt·shutter', () => {
    const s = shutterTaps(W!, 4.008, 1 / 30, 0.5, 9).map((x) => x.a.tx);
    expect((s[0]! + s[8]!) / 2).toBeCloseTo(stateAt(W!, 4.008).a.tx, 0);
  });
  test('the whip streak at the cut needs more taps at 4K, capped', () => {
    const k1 = tapCount(W!, 4.008, 1 / 30, 0.5, 1), k2 = tapCount(W!, 4.008, 1 / 30, 0.5, 2);
    expect(k2).toBeGreaterThan(k1); expect(k2).toBeLessThanOrEqual(MAX_TAPS);
    expect(tapCount(W!, 2, 1 / 30, 0.5, 1)).toBe(1);   // outside the window: no streak
  });
  test('A and B meet half way at the cut, and abut', () => {
    const s = stateAt(W!, 4.008);
    expect(s.a.tx).toBeCloseTo(-960, 0); expect(s.b.tx).toBeCloseTo(960, 0);
  });
  test('match: B shows first where A is brightest', () => {
    expect(matchWeight(0.7, 0.9, 0.12)).toBeGreaterThan(matchWeight(0.7, 0.3, 0.12));
    expect(matchWeight(1, 0.99, 0.12)).toBeLessThan(0.5);
  });
});
```
Also in `engine.test.ts`: a fake-scene engine harness (no WebGL, as the existing tests model the plan) records
`prepare` times. It checks that a `'hold'` plate scene's recorded times all lie inside its window across the frames
of a transition.

**Visual acceptance:**
- **Regression.** With no transition files (only the probes, which the film excludes), the 15 hero stills are
  byte-identical to the pre-task commit:
  `bun scripts/render.ts stills --t 5.6,9,19.65,25.98,32.1,39.83,46.7,53.3,55.5,58,65.6,69.47,75.07,82.3,93.1 --out ../out/wip/t1-before`
  (run at the base commit in a worktree), then the same command at HEAD to `t1-after`, then `cmp` each pair.
- **Each probe.** `bun scripts/render.ts stills --transition _probe-whip --frames -3,-2,-1,0,1,2 --samples auto`,
  then Read all six:
  - the whip streaks continuously at frames −1 and 0 (no stepped copies);
  - the two pictures abut with no gap or ghost;
  - the frames outside the window are pixel-equal to the plain film's frames there.

  Repeat for zoom (a radial streak), match (B through A's highlights), xfade and dip (ink between, never A and B
  together).
- **Determinism.** Render `--frames 0` twice and in reverse order, then `cmp`.
- **Export.** `bun scripts/render.ts video --transition _probe-whip --samples auto` exits 0. The `.progress` file is
  removed and the histogram is printed.

**Commit:** `Transitions in the engine: two scenes on screen across a cut, whips and zooms blurred over the shutter,
overlays drawn last (M13)`.

---

### Task 2: The sound library: ElevenLabs sound generation, the palette, cache and manifest (creative + infra)

**Time:** about 3 h of agent work, plus about 20 min of generation (Opus: prompt design is creative work).

**Files:**
- Modify: `tools/gitloom_film/elevenlabs.py` (add `sound()`), `tools/tests/test_elevenlabs.py`,
  `tools/pyproject.toml` (add the `film-sfx-lib` script; `matplotlib` for the spectrogram sheets), `.gitignore`
  (add `audio/sfx/lib/` and `audio/sfx/*.wav`)
- Create: `data/sfx_palette.json`, `tools/gitloom_film/sfxlib.py`, `tools/tests/test_sfxlib.py`,
  `audio/sfx/manifest.json` (written by the tool, committed)

**Interfaces:**
```python
# elevenlabs.py
@dataclass
class SoundResult:
    audio: bytes            # raw bytes in output_format (PCM16 LE mono for pcm_*)
    output_format: str
    cost: int
    request_id: str

class ElevenLabs:
    def sound(self, text: str, duration_seconds: float | None = None, prompt_influence: float | None = None,
              loop: bool = False, model_id: str = "eleven_text_to_sound_v2", output_format: str = "pcm_48000",
              seed: int | None = None) -> SoundResult: ...
        # POST /v1/sound-generation?output_format=…, JSON {text, model_id, duration_seconds?, prompt_influence?, loop, seed?}

# sfxlib.py
def load_palette(path: Path = DATA / "sfx_palette.json") -> dict: ...
def request_of(palette: dict, sound_id: str, variant: int) -> dict:      # the exact JSON sent (+ output_format)
def request_key(req: dict) -> str:                                        # sha256 of canonical JSON (sorted keys)
def plan(palette: dict, manifest: dict) -> list[tuple[str, int, dict]]:   # (sound_id, variant, request) still to fetch
def estimate(todo, credits_per_second: float) -> int: ...
def generate(palette: dict, client, lib: Path, manifest_path: Path, budget: int, dry_run: bool = False) -> dict: ...
def to_wav48(raw: bytes, output_format: str) -> np.ndarray:               # PCM16 → float; mp3 via ffmpeg; → 48 kHz
def find_hit(y: np.ndarray, sr: int, align: str) -> float:                # 'onset' | 'peak' | 'end' → seconds in the file
def slice_hits(y: np.ndarray, sr: int, n: int, min_gap: float = 0.08) -> list[np.ndarray]: # isolate n one-shots
def qc(y: np.ndarray, sr: int) -> dict:   # peak_dbfs, lufs, onset_s, dur_s, centroid_hz, silence_ratio, clipped, dc
def pick(variants: list[dict], family: str) -> int:                       # the auto pick, by QC
```

**`data/sfx_palette.json`:**
```json
{ "model_id": "eleven_text_to_sound_v2", "output_formats": ["pcm_48000", "pcm_44100", "mp3_44100_128"],
  "variants": 2, "seed_base": 3100, "seeds_honoured": null,
  "sounds": { "<id>": { "family": "threads", "prompt": "…", "duration": 1.0, "influence": 0.45, "loop": false,
                         "align": "onset", "gain": -12.0, "slice": 0, "pick": null } } }
```
- `slice: n > 0` cuts the take into n one-shots, `<id>_1 … <id>_n`.
- `pick: null` takes the auto pick. The user's C5 choice is written here.
- `seeds_honoured` is the result of the determinism probe, below.

**The palette.** These are starting prompts from spec §5.3. The implementer refines them by critique and keeps the
family and id. The style suffix on every prompt is `", close-mic, dry, no music, no voice"`. The exceptions are the
beds and the risers, which take `", no music, no voice"`.

| id | family | prompt (before the suffix) | dur s | align | gain dB |
|---|---|---|---|---|---|
| `thread_hum` | threads | low taut string tension hum, one fibre under tension, soft sub resonance, steady (loop) | 4.0 | — | −26 |
| `fray_crackle` | threads | fibres fraying, tiny dry crackles of strands tearing apart slowly | 1.5 | onset | −16 |
| `thread_snap` | threads | a taut thread snapping, sharp tight crack then a quick whip recoil | 1.0 | onset | −8 |
| `fibre_whoosh` | threads | soft airy whoosh of loose fibres drifting through air, breathy | 1.5 | onset | −20 |
| `reform_swell` | threads | soft reversed shimmer swelling into a silky tightening, two threads twisting together | 2.0 | end | −16 |
| `float_shimmer` | floats | faint glassy digital shimmer, tiny crystalline ticks, cold, sparse (loop) | 3.0 | — | −28 |
| `flap` | floats | split-flap display flips, small plastic flap clicks with gaps between them | 3.0 | onset | −18 (slice 6) |
| `cosine_ping` | floats | soft sonar-like glass ping, short, clean, cold | 0.8 | onset | −16 |
| `fatal_thunk` | floats | a dull deadpan muted wooden thunk | 0.6 | onset | −12 |
| `commit_thock` | commits | a small solid glass bead seating into place, a rich satisfying thock | 0.6 | onset | −12 |
| `glass_clink` | commits | tiny glass beads touching, one delicate high clink | 0.5 | onset | −20 |
| `key_soft` | typing | soft low-profile mechanical keystrokes, isolated single presses with gaps, quiet room | 4.0 | onset | −24 (slice 8) |
| `key_enter` | typing | one soft mechanical Enter key press, a slightly heavier thock | 0.5 | onset | −18 |
| `shuttle_clack` | loom | a wooden loom shuttle striking home, a single crisp wooden clack | 0.5 | onset | −14 |
| `weave_swish` | loom | a weft thread pulled quickly through warp threads, soft cloth friction swish | 0.8 | onset | −22 |
| `pen_strike` | diff | one fast decisive felt-pen strikethrough across paper | 0.7 | onset | −14 |
| `insert_pop` | diff | tiny soft round pops, small bubbles of air, with gaps | 2.0 | onset | −22 (slice 4) |
| `stitch_pull` | cite | a fine thread pulled taut through cloth, a quick silky zip | 0.8 | onset | −18 |
| `gutter_slide` | cite | a small panel sliding smoothly, a soft glide ending in a tiny click | 0.6 | end | −20 |
| `rope_creak` | braid | a three-strand rope twisting and pulling taut, a low fibrous creak | 1.5 | onset | −16 |
| `visited_tick` | merkle | very short clean precise high electronic ticks with gaps | 2.0 | onset | −26 (slice 8) |
| `fold_click` | merkle | a paper-thin panel folding shut, a small precise click | 0.4 | onset | −20 |
| `edge_zip` | graph | a fine thread zipping taut through the air, a quick rising zip | 0.6 | onset | −18 |
| `heal_shimmer` | graph | a soft warm shimmer resolving upward, an airy chime-like texture, no melody | 1.5 | onset | −20 |
| `room_tone` | honest | quiet intimate room tone, a near-silent late-night studio, very soft air, no hum, no clicks (loop) | 8.0 | — | −40 |
| `odometer_roll` | proof | mechanical odometer drums rolling, a fast ratcheting roll of numbered wheels | 1.0 | end | −16 |
| `connected_chime` | connect | a subtle soft confirmation chime, one warm glassy two-note tone, very short, understated | 1.0 | onset | −18 |
| `card_flip` | connect | a stiff card flipping over, a quick soft flap of card stock | 0.4 | onset | −20 |
| `riser` | weave | a slow dark silky cinematic riser building tension, no drums, no melody | 3.0 | end | −18 |
| `sub_impact` | weave | a deep soft sub impact, a warm low boom with a short tail, restrained | 2.5 | onset | −8 |
| `type_slam` | type | a heavy solid object landing on felt, a soft deep thud with a tight transient | 0.5 | onset | −14 |
| `stamp` | type | a rubber stamp pressed firmly onto paper, a dry thump | 0.5 | onset | −14 |
| `whoosh_whip` | transitions | a fast whip-pan whoosh, a short tight air swish | 0.6 | peak | −16 |
| `whoosh_zoom` | transitions | a deep rushing zoom-through whoosh, air pushing past, building then cutting off | 0.9 | peak | −16 |

That is 34 sounds × 2 variants, about 116 s of audio. Spec §7.1 names `tools/sfx.py`; the library half lives in
`sfxlib.py` and the bus in `sfx.py` (Task 9).

**Behaviour:**
- **The cache is content-addressed.**
  - A variant's file is `audio/sfx/lib/<id>/<request_key[:12]>.wav` (48 kHz / 24-bit mono), next to the raw API
    bytes as `….raw`.
  - `audio/sfx/manifest.json` maps `<id>/<variant>` to `{ "key", "request" (no secret), "seed",
    "output_format", "cost", "request_id", "sha256" (of the wav), "qc", "hit_s", "ts" }`.
  - `plan()` skips any request whose key is in the manifest **and** whose wav exists with the recorded sha256. A
    palette edit to one sound re-fetches only that sound.
  - Paths resolve from the repo root (`paths.py`), never from the working directory.
- **Budget.**
  - `estimate` uses 40 credits/s until the first real call. After that it uses the measured
    `cost/duration_seconds`.
  - `gen` refuses to start if the estimate exceeds `--budget`. It stops before any call that would cross the budget
    (counting what this run has spent), and prints spent/left.
- **Output format.** Try `output_formats` in order. A 4xx saying the format isn't allowed moves to the next; any
  other error fails. Decode to 48 kHz float with `to_wav48`.
- **Seeds and the determinism probe** (once: `film-sfx-lib probe`):
  1. Request `glass_clink` twice with the same seed, `duration_seconds = 0.5`.
  2. If the API rejects `seed` (4xx naming it), record `seeds_honoured: false` and never send a seed again.
  3. Otherwise compare the two PCM payloads: identical means `true`, different means `false`.
  4. Every variant's seed is `seed_base + 100·index(id) + variant`, recorded in the manifest whether or not it is
     honoured, so a reproducible API reproduces it.
- **Post-processing per variant:**
  - Trim leading silence to 5 ms before the hit for `onset` sounds.
  - A 2 ms fade-in and a 20 ms fade-out.
  - Remove DC.
  - `slice > 0` splits the take with `slice_hits` (onset detection, the n strongest separated hits, each trimmed the
    same way). Each slice is a sound of its own in the manifest (`key_soft_3`), inheriting the gain.
  - `hit_s` is where the cue time lands: 0.005 for trimmed onsets, the peak's time for `peak`, the end for `end`.
    Loops get no trim and an equal-power 50 ms seam crossfade.
- **QC and the auto pick.**
  - Reject a variant that is clipped, more than 60% silent, peaks under −40 dBFS, or (for one-shots) has no onset in
    its first 300 ms. Of the rest, prefer the sharper transient (`onset`) or the smoother envelope (beds and
    risers).
  - `pick` is the palette's `pick` if set, else the auto pick.
- **Critique.** `film-sfx-lib sheet` writes `out/review/sfx/<family>.png`: per sound and variant, a log-frequency
  spectrogram, the waveform with `hit_s` marked, and the QC numbers.

**Tests (pytest, a fake transport as in `test_elevenlabs.py`; no network):**
```python
def test_sound_posts_the_request_and_logs_cost(tmp_path):
    calls, log = [], tmp_path / "credits.log"
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "20", "request-id": "s1"}, b"\x01\x00" * 480)], calls), log)
    r = c.sound("a snap", duration_seconds=1.0, prompt_influence=0.4, seed=7)
    method, url, headers, body = calls[0]
    assert url == "https://api.elevenlabs.io/v1/sound-generation?output_format=pcm_48000"
    assert json.loads(body) == {"text": "a snap", "model_id": "eleven_text_to_sound_v2", "duration_seconds": 1.0,
                                "prompt_influence": 0.4, "loop": False, "seed": 7}
    assert (r.cost, r.request_id, r.output_format) == (20, "s1", "pcm_48000")
    assert json.loads(log.read_text())["path"] == "/v1/sound-generation"

def test_sound_error_never_leaks_the_key():
    c = ElevenLabs(KEY, fake([Response(422, {}, f"bad {KEY}".encode())], []))
    with pytest.raises(ElevenLabsError) as e:
        c.sound("x")
    assert KEY not in str(e.value)

def test_a_cached_request_is_never_paid_for_twice(tmp_path):          # Review Focus 1
    pal = palette_with("glass_clink", variants=2)
    client = CountingClient()                                           # returns 0.5 s of PCM and counts calls
    generate(pal, client, tmp_path / "lib", tmp_path / "manifest.json", budget=8000)
    assert client.calls == 2
    generate(pal, client, tmp_path / "lib", tmp_path / "manifest.json", budget=8000)
    assert client.calls == 2                                            # nothing new
    pal["sounds"]["glass_clink"]["prompt"] += ", brighter"
    generate(pal, client, tmp_path / "lib", tmp_path / "manifest.json", budget=8000)
    assert client.calls == 4                                            # only the edited sound

def test_a_corrupted_wav_is_refetched(tmp_path): ...                  # sha256 mismatch → back in plan()
def test_budget_refuses_and_stops(tmp_path): ...                      # estimate > budget → no call; mid-run stop before crossing
def test_the_manifest_holds_no_secret(tmp_path): ...                  # KEY absent from manifest.json bytes
def test_format_fallback_on_a_refused_format(tmp_path): ...           # 403 "output_format" → pcm_44100, resampled to 48k
def test_find_hit_and_trim_put_the_transient_at_5_ms(): ...           # synthetic click at 0.3 s → hit_s == 0.005 ± 1 sample
def test_slice_hits_isolates_n_clicks(): ...                          # 8 clicks in noise → 8 slices, each onset at 5 ms
def test_qc_rejects_clipped_and_silent(): ...
```

**Run:**
1. `cd tools && uv run pytest -q`, green.
2. `uv run film-sfx-lib probe`.
3. `uv run film-sfx-lib plan` prints the todo list and the estimate.
4. `uv run film-sfx-lib gen --budget 8000`, run in the background. It takes about 2 min per 20 calls; poll its log.
5. `uv run film-sfx-lib sheet`.

**Creative acceptance** (the Part B template, adapted to sound; the agent can't hear, spec §5.6):
- Read every family sheet PNG. Check that:
  - one-shots have one clean transient at the trim, no double hits and no tails of music;
  - beds are steady, with no clicks at the loop seam;
  - risers peak at their end;
  - nothing is clipped.
- Rewrite a prompt and regenerate (the cache re-fetches only it) for any sound whose sheet shows the wrong shape.
  Keep the spend inside the budget.
- **The report** lists each sound with its pick, its QC line and one line on what the spectrogram shows.
- Flag `shuttle_clack` and `thread_snap` for the user's ear at C5 (spec §5.3 fallback: real recordings).

**Commit:** first the code and tests, then `data/sfx_palette.json` and `audio/sfx/manifest.json` after generation.
Message: `The sound library: ElevenLabs sound generation, cached by request, with a manifest of seeds and picks`.

---

### Task 3: The voice processing chain (spec §5.1)

**Time:** about 2 h (Sonnet or Opus).

**Files:**
- Create: `tools/gitloom_film/vochain.py`, `tools/tests/test_vochain.py`
- Modify: `tools/pyproject.toml` (`film-vo-chain`), `.gitignore` (`audio/vo/vo-chain.wav`)

**Interfaces:**
```python
CHAIN = {  # the spec's chain; values are starting points the objective checks below confirm
    "hpf": {"f": 80.0, "order": 4},                       # Butterworth high-pass
    "cut": {"f": 300.0, "q": 1.0, "gain_db": -2.5},       # gentle bell cut (RBJ peaking)
    "deess": {"lo": 5000.0, "hi": 9000.0, "thresh_db": -28.0, "max_red_db": 6.0, "attack_ms": 1.0, "release_ms": 60.0},
    "comp": {"ratio": 2.0, "thresh_db": -20.0, "attack_ms": 10.0, "release_ms": 120.0, "knee_db": 6.0},
    "presence": {"f": 3500.0, "gain_db": 1.5},            # high shelf (RBJ)
    "air": {"f": 11000.0, "gain_db": 2.0},                # high shelf (RBJ)
    "sat": {"drive": 1.2, "mix": 0.25},                   # tanh soft-sat, blended
    "plate": {"rt60": 0.45, "predelay_ms": 8.0, "lo": 300.0, "hi": 9000.0, "wet_db": -20.0, "seed": 51},
}
def biquad(kind: str, f: float, sr: int, q: float = 0.707, gain_db: float = 0.0) -> tuple[np.ndarray, np.ndarray]: ...
def deess(y, sr, lo, hi, thresh_db, max_red_db, attack_ms, release_ms) -> np.ndarray: ...  # split-band: only the band is reduced
def compress(y, sr, ratio, thresh_db, attack_ms, release_ms, knee_db) -> np.ndarray: ...   # feed-forward, NO look-ahead
def plate_ir(sr, rt60, predelay_ms, lo, hi, seed) -> np.ndarray: ...  # seeded decaying filtered noise, unit energy
def saturate(y, drive, mix) -> np.ndarray: ...
def chain(y: np.ndarray, sr: int, cfg: dict = CHAIN) -> np.ndarray: ... # hpf → cut → de-ess → comp → presence/air → sat → + plate send; makeup to the input's integrated loudness
def report(raw: np.ndarray, out: np.ndarray, sr: int, vo: dict) -> dict: ...  # objective checks, below
```

**Behaviour:**
- Every stage is causal and zero-latency (IIR biquads, a feed-forward compressor, and a convolution aligned at sample
  0), so the processed voice stays sample-aligned to `data/vo.json`.
- The output is mono 48 kHz / 24-bit `audio/vo/vo-chain.wav`, the same length as `audio/vo/vo.wav`.
- `film-sync` keeps reading the raw `vo.wav`.
- **The report** goes to `out/review/c5/vo-chain.json`, per line. Per line it gives:
  - integrated loudness in and out;
  - true peak;
  - **sibilance ratio** (5–9 kHz energy over 1–4 kHz energy) in and out;
  - the crest factor in and out;
  - the noise floor in the gaps between lines (it must not rise more than 3 dB);
  - any clipped samples.

**Tests (pytest, synthetic, 48 kHz):**
```python
def test_the_chain_keeps_every_onset_on_its_sample():
    y = tone_bursts(starts=[0.5, 1.25, 2.0])                        # 220 Hz bursts with sharp starts
    out = chain(y, SR)
    for s in [0.5, 1.25, 2.0]:
        assert abs(first_above(out, s) - first_above(y, s)) <= 1  # samples

def test_hpf_removes_rumble_and_keeps_the_voice():
    assert band_db(chain(sine(40), SR)) - band_db(sine(40)) <= -12
    assert abs(band_db(chain(sine(1000), SR), 900, 1100) - band_db(sine(1000), 900, 1100)) <= 3

def test_the_de_esser_tames_sibilance_only():
    y = sine(250) * 0.3 + bursts(noise_band(5000, 9000), 0.4)       # voiced tone + /s/ bursts
    out = deess(y, SR, **CHAIN["deess"])
    assert sib_ratio(out) <= sib_ratio(y) - 4                       # dB
    assert abs(band_db(out, 200, 300) - band_db(y, 200, 300)) <= 0.5

def test_2_to_1_compression_halves_level_above_threshold(): ...    # steady tone 10 dB over → ~5 dB over (±1)
def test_the_plate_adds_a_short_tail_and_stays_low(): ...           # impulse → energy 50–400 ms after ≤ −18 dB rel. dry, > −60 dB
def test_saturation_never_clips_and_is_light(): ...                 # |out| ≤ 1; THD of a −6 dBFS sine < 3%
def test_chain_is_deterministic_and_keeps_loudness(): ...           # twice → identical; integrated loudness within 1 dB of input
```

**Run:**
1. `cd tools && uv run pytest -q`.
2. `uv run film-vo-chain`, then Read `out/review/c5/vo-chain.json`.
3. The acceptance:
   - every line's sibilance ratio drops 2–6 dB;
   - no line clips;
   - the gap floor rises ≤ 3 dB;
   - the onset check over all 32 lines' first words (`report` checks each `vo.json` line start ±1 sample) is green.

**Commit:** `The voice chain: high-pass, a cut at 300 Hz, de-essing, 2:1, presence and air, a touch of tape and a short
plate, all without moving a word`.

---
## Part B: the 14 transitions (Tasks 4–7, after Task 1; two at a time)

**Every transition task follows this template** (Plan 2's creative template, for cuts):
- **Files:**
  - the task's transition files `app/src/transitions/<from>-<to>.ts` and its test
    `app/src/transitions/group-<x>.test.ts`;
  - the scene files it **owns** (below), only for what the cut needs: a composition matched to the other side, a
    tail or head of engine-built content with the `handles` it declares, or an anchor read from a track.

  Touch nothing else. Anything needed on a scene you don't own goes to the controller in your report.
- **Ownership** (disjoint across groups; boundary scenes belong to exactly one group):

  | group | transitions | scene files it may edit |
  |---|---|---|
  | A (Task 4) | thread-ex, ex-her, her-repo, repo-loom | `thread*`, `ex*`, `her*`, `repo*`; `blender/shots/b01_thread.py` (track only), `data/track/b01_thread.json` |
  | B (Task 5) | loom-diff, diff-cite, cite-braid, braid-merkle | `loom*`, `diff*`, `cite*`, `braid*` |
  | C (Task 6) | merkle-graph, graph-honest, honest-proof | `merkle*`, `graph*`, `honest*` |
  | D (Task 7) | proof-connect, connect-anywhere, anywhere-weave | `proof*`, `connect*`, `anywhere*`, `weave*` |

- **Pairing:** A ∥ B, then C ∥ D. Group A's Blender track run is the only Cycles job; nothing else renders during
  it.
- **Times:** from the data only.
  - The cut is the scene boundary.
  - A match position comes from a track (`Track.at`) or from the scene's time module at the frame `F − 1` or `F`.
  - `pre` and `post` obey the Global Constraints. Group tests call `transitionEntries` on the real `vo.json` and its
    words.
- **Motion language** (Plan 2 v2): whips are 60–120 ms of directional blur at the cut, zoom-throughs push through an
  object, and match cuts run along the thread. There is no stock glitch, no flash frame, no light leak and no
  cross-dissolve except where the table says `xfade`. Bone never blooms in a transition.
- **Acceptance**, per transition:
  1. `bun test src` and `bun run typecheck` are green. `film-facts` passes if a string changed.
  2. **Stills:** `bun scripts/render.ts stills --transition <from>-<to> --frames -3,-2,-1,0,1,2 --samples auto`.
     **Read all six.** Critique against the direction, fix, and re-render.
  3. **The clip:** `caffeinate -i bun scripts/render.ts video --transition <from>-<to> --samples auto`, run in the
     background. Poll `out/transitions/<from>-<to>.mp4.progress`.
  4. **A sheet** of every frame in the window ±3: `bun scripts/render.ts sheet --transition <from>-<to> --n 12`,
     Read.
  5. The scene's own hero still (Plan 2's key moments) is unchanged unless the task edited that moment on purpose,
     and then the report says so.
  6. The report lists each still with one line on what it shows, and the pair's `pre`/`post` against its word
     limit.
- **Commit:** per transition, only its files, with a one-line subject naming the cut. Commit the scene edits with
  their transition.

**The 14 cuts.** These are proposals in film order. Only #1 and #2 are written in the spec; the rest are for the user
to approve at C5. An implementer may change a kind within the motion language if the stills argue for it. The
report must say why, and the word limits still bind.

| # | cut (s) | first B frame F | from → to | kind | pre / post (s) | word limit (post <) | direction |
|---|---|---|---|---|---|---|---|
| 1 | 6.008 | 181 | thread → ex | match (luma) | 0.067 / 0.1 | 0.374 | Spec: the drifting fibres catch the light and match-cut into float numerals on the beat. B shows through A's brightest fibres first; ex seeds its first numerals on the fibres' tracked screen points. |
| 2 | 15.608 | 469 | ex → her | cut | 0 / 0 | — | Spec: a hard cut to black, then one silent beat (her opens on ink before the re-form; the silent beat is a duck in Task 8/9). Verify only that frame F is ink. |
| 3 | 22.808 | 685 | her → repo | whip, camera up `[0, −1]` | 0.1 / 0.1 | 0.567 | The headline, drifting back out of focus, whips down out of frame; repo's tilted terminal lands from above, its tilt continuing the whip's line. |
| 4 | 28.208 | 847 | repo → loom | match along the thread | 0.1 / 0.12 | 0.215 | repo's moss-lit bead string runs out under user.md; on the cut it becomes loom's weft. repo places the string's last span on the screen line of loom's first fell (`data/track/b05_loom.json` `fell_l`/`fell_r` at frame F). |
| 5 | 37.808 | 1135 | loom → diff | whip, camera right `[1, 0]` | 0.1 / 0.1 | 0.130 | loom already snaps between tiers like whips: the last snap carries on through the cut into diff's editor. `post` is tight: "Change" starts 0.163 s after the cut. |
| 6 | 42.608 | 1279 | diff → cite | zoom-through | 0.2 / 0.15 | 0.567 | diff's romantic push-in accelerates into the ember of the old line (centre: the ember's screen point); cite's chat emerges from 1.6×. "diff." (onset 42.254) still sounds until 12 ms before the cut: the push may start after its onset, never before. |
| 7 | 46.808 | 1405 | cite → braid | whip along the thread | 0.1 / 0.15 | 0.567 | The seam thread cite lays whips out along its own direction into braid's void, where the three arms race in. `pre` ≤ 0.1: the settled chain holds only 0.2 s. |
| 8 | 53.408 | 1603 | braid → merkle | whip, camera up `[0, −1]` | 0.1 / 0.15 | 0.567 | The rope pulls toward camera; the whip tilts up into merkle's vault (merkle opens low, looking up). `pre` ≤ 0.1: the card holds only 0.6 s. |
| 9 | 57.008 | 1711 | merkle → graph | zoom-through | 0.15 / 0.2 | 0.567 | merkle lands low beside its file; push into that file and out of graph's file line `Works with [[facts/orgs/acme.md]].` File to file. "fifty." ends 32 ms before the cut. |
| 10 | 61.208 | 1837 | graph → honest | dip to ink | 0.3 / 0 | — | The light drains out of the constellation before the music goes; honest cuts in hard on ink. |
| 11 | 66.008 | 1981 | honest → proof | xfade | 0.25 / 0.25 | 0.567 | The film's one dissolve, in the room tone: "I don't know." holds as proof's dark drums come up through it. |
| 12 | 72.608 | 2179 | proof → connect | whip, camera right `[1, 0]` | 0.12 / 0.12 | 0.567 | The Act IV lift: the last band of light across 91.4% leads into the whip, and the terminal lands. |
| 13 | 79.208 | 2377 | connect → anywhere | whip with the carousel's turn | 0.1 / 0.1 | 0.567 | The carousel whips round to its next face, and the face that lands is anywhere's terminal on the open book, matched in position and scale (anywhere's first frames). `pre` ≤ 0.1 for the cards' read. |
| 14 | 86.408 | 2593 | anywhere → weave | zoom-through | 0.2 / 0.25 | 0.278 | Push through the namespace field into the dark between the tiles; weave's threads arc out of that dark (B15 holds its first frame). |

The word limit is the next onset minus the cut, minus one frame. Group tests assert it from the data, not from this
table.

### Task 4: Group A: thread → ex, ex → her, her → repo, repo → loom

**Time:** about 4 h (Opus), plus one Blender look frame (about 3 min).

**Files:**
- Create: `app/src/transitions/thread-ex.ts`, `ex-her.ts`, `her-repo.ts`, `repo-loom.ts`, `group-a.test.ts`
- Modify (as needed): `app/src/scenes/ex.ts` and `ex-*.ts` (seed numerals on the fibre anchors), `repo.ts` and
  `repo-*.ts` (the string's exit line), `her*.ts` (only if the whip needs a matched exit),
  `blender/shots/b01_thread.py` (`SHOT["track"]` gains `fibre_0 … fibre_11`: empties that follow freed fibres'
  midpoints; empties don't render, so the plates are unchanged), `data/track/b01_thread.json`

**Interfaces:**
- Consumes: Task 1's `TransitionSpec` and `Track` (`new Track(json)`, `.at(name, t)`).
- Produces: four default-exported `TransitionSpec`s, plus `ex`'s
  `fibreSeeds(track: Track, cut: number): { x: number; y: number }[]` (in `ex-cloud.ts`, pure).

**Blender (one Cycles job; nothing else on the GPU):**
- `caffeinate -i /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot b01_thread --mode look --frames 179`
  rewrites the whole shot's track (tracks are sampled over the full window in every mode).
- Then `--scan --shot b01_thread` must report 181/181 lit, with plates untouched (`git status out/` is not tracked;
  `shasum` 5 plates before and after).

**Group tests (`group-a.test.ts`):**
- the four specs validate against the real `vo.json`, words included;
- `ex-her` is `'cut'`;
- `thread-ex` and `repo-loom` are `'match'`;
- every `fibre_*` anchor is visible at frame 180 and inside the title-safe frame;
- `fibreSeeds` returns ≥ 6 points, all within 2 px of the tracked anchors at the cut.

**Direction:** rows 1–4 of the table.

**Key stills:** for each transition, frames −3…2.
- **#1:** frame 0 must read as fibres becoming numerals: the same bright points, a new material.
- **#2:** frame 0 is ink.

**Commits:** one per transition. Example subject: `thread → ex: the freed fibres match-cut into the float numerals`.

### Task 5: Group B: loom → diff, diff → cite, cite → braid, braid → merkle

**Time:** about 4 h (Opus).

**Files:**
- Create: `app/src/transitions/loom-diff.ts`, `diff-cite.ts`, `cite-braid.ts`, `braid-merkle.ts`, `group-b.test.ts`
- Modify (as needed): `app/src/scenes/loom*.ts` (the last snap's direction), `diff*.ts` (the push-in's centre exposed
  from `diff-time.ts`), `cite*.ts` (the seam's direction at its end), `braid*.ts` (only for engine overlays; B08
  holds)

**Group tests:**
- the four specs validate on the real data;
- `loom-diff.post` < "Change" − cut − 1/30 (from `vo.json`);
- `cite-braid.pre` and `braid-merkle.pre` are ≤ 0.1;
- `diff-cite.center` equals `diff-time`'s ember point at frame F − 1 within 1 px (no copied numbers);
- a whip's `dir` is a unit vector.

**Direction:** rows 5–8.

**Key stills:** frames −3…2 each.
- **#6:** frame −1 shows the ember filling the frame, not a blurred editor.
- **#8:** frame 0's streak runs vertical.

### Task 6: Group C: merkle → graph, graph → honest, honest → proof

**Time:** about 3 h (Opus).

**Files:**
- Create: `app/src/transitions/merkle-graph.ts`, `graph-honest.ts`, `honest-proof.ts`, `group-c.test.ts`
- Modify (as needed): `app/src/scenes/merkle*.ts` (the landing file's screen point from `merkle-time.ts`),
  `graph*.ts` (light drain, if the dip alone reads flat), `honest*.ts` (`handles.tail` if "I don't know." should keep
  breathing through the dissolve; engine content only)

**Group tests:**
- the specs validate;
- `graph-honest` is a dip with `post = 0`;
- `honest-proof` is the only `'xfade'` among all transition files: glob them and count;
- `merkle-graph.center` comes from `merkle-time`'s landing at F − 1.

**Direction:** rows 9–11. honest is the film's held breath: the dip and the dissolve must feel slow and quiet next to
the whips around them.

**Key stills:** frames −9, −6, −3, 0, 3, 6 for the dip and the dissolve (they are longer), and −3…2 for #9.

### Task 7: Group D: proof → connect, connect → anywhere, anywhere → weave

**Time:** about 3.5 h (Opus).

**Files:**
- Create: `app/src/transitions/proof-connect.ts`, `connect-anywhere.ts`, `anywhere-weave.ts`, `group-d.test.ts`
- Modify (as needed): `app/src/scenes/proof*.ts` (the last light band leading the whip), `connect*.ts` (the
  carousel's last turn direction from `connect-time.ts`), `anywhere*.ts` (the opening terminal matched to connect's
  landing face; the dark gap the zoom aims at), `weave*.ts` (B15 holds; engine type only)

**Group tests:**
- the specs validate;
- `connect-anywhere.dir` has the sign of `connect-time`'s last `turnAt` velocity;
- `anywhere-weave.post` < "GitLoom." − cut − 1/30;
- `connect-anywhere.pre` ≤ 0.1.

**Direction:** rows 12–14.

**Key stills:** frames −3…2 each. For #13, frame 1's terminal must sit where connect's face landed (±8 px): check it
on the Read stills against frame −1.

---
## Part C: the sound (Tasks 8–9)

### Task 8: The cue sheet, from the data

**Time:** about 4 h (Opus: the creative spotting of the film).

Run it after Tasks 2 and 4–7: it reads the palette ids, and it may move timing into scene time modules that those
tasks were editing.

**Files:**
- Create:
  - `app/src/sfx/cue.ts`, `app/src/sfx/sheet.ts`, `app/src/sfx/transitions.ts`;
  - `app/src/sfx/scenes/{thread,ex,her,repo,loom,diff,cite,braid,merkle,graph,honest,proof,connect,anywhere,weave}.ts`;
  - `app/src/sfx/sheet.test.ts`, `app/scripts/cues.ts`;
  - `data/sfx.json` (generated, committed).
- Modify: scene time modules where a needed time lives only inside a scene class. Move it out as a pure function:
  `thread.ts` → `thread-time.ts`, `her.ts` → `her-time.ts`, `repo.ts` → `repo-time.ts`, `weave.ts` →
  `weave-time.ts`, and the typing schedules of the others. These are **pure moves**: the 15 hero stills stay
  byte-identical (`cmp` before and after).
- Modify: `app/src/engine/panels.ts`, to export the pure reveal rule as `typedCount(l: PanelLine, t: number): number`,
  the exact rule `Panel.revealed` uses (so key cues land on the frames characters appear).

**Interfaces:**
```ts
// cue.ts
export interface Cue { sound: string; t: number; anchor: string; gain?: number; pan?: number; dur?: number } // gain dB added to the palette's; pan −1..1; dur: beds/loops only
export interface Duck { kind: 'duck'; t: number; dur: number; depth: number; fade: number; bus: 'music' | 'all'; anchor: string }
export interface CueCtx { vo: VO; audio: AudioData; scene: SceneSpan; track: (shot: string) => Track; transitions: TransitionEntry[] }
export type SceneCues = (c: CueCtx) => (Cue | Duck)[];
export function word(c: CueCtx, line: string, w: string): { t: number; anchor: string }; // throws `cue: no word "<w>" in <line>` (Review Focus 2)
export function beatsIn(c: CueCtx, a: number, b: number): { t: number; anchor: string }[];   // anchor `beat:<index>`
export function typing(prefix: string, count: (t: number) => number, from: number, to: number, seed: string): Cue[];
  // scans frame times n/30 in [from, to]; one key cue per newly shown character (a frame that shows k new characters
  // spreads them k/30 apart within it); sounds key_soft_1..8 by hash(seed, i); gain jitter ±1.5 dB and pan ±0.15 seeded
// sheet.ts
export interface SfxSheet { fps: 30; generated_by: string; cues: (Cue & { id: string; scene: string; prompt: string; duration: number; gain: number })[]; ducks: (Duck & { id: string; scene: string })[] }
export function buildSheet(vo: VO, audio: AudioData, tracks: Record<string, Track>, palette: Palette, transitions: TransitionEntry[]): SfxSheet;
  // runs every scene module and transitionCues; resolves gain = palette gain + cue gain; sorts by t; ids `<scene>.<nnnn>`;
  // throws on an unknown sound id, a cue outside [0, duration), or a non-finite t
```

**Spotting** (spec §5.3, in each scene's own events; a module may add cues the table misses, never invent times):

| scene | cues (sound @ anchor) |
|---|---|
| thread | `thread_hum` bed from the first beat to the snap; `fray_crackle` @ "forgets"; `thread_snap` @ the snap (`thread-time`); a **duck** `all` −30 dB, 2 frames at the snap (spec: near-silence for two frames); `fibre_whoosh` @ snap + 2 frames, gain −3 |
| ex | `float_shimmer` bed over the cloud; `flap_*` per split-flap flip (`timesOf`); `cosine_ping` @ the `why?` ping; `stamp` × 3 @ the three blood tags' beats; `typing` for `$ git log` + `key_enter`; `fatal_thunk` @ the fatal line's landing |
| ex → her | a **duck** `music` −24 dB from the cut for one beat, 30 ms fades (spec 03: one silent beat) |
| her | `reform_swell` ending @ the join (`her-reform`); `commit_thock` @ the bead's landing on the downbeat after "me."; `whoosh_whip` @ her internal whip; `type_slam` @ "memory", "commit", "blame"; `typing` (gain −6) for the + lines typed with her; `gutter_slide` @ the blame gutter |
| repo | `typing` + `key_enter` for `cd ~/memory && ls`; `insert_pop_*` × 4 @ the chips; `typing` + `key_enter` for `git log --oneline`; `commit_thock` @ each bead landing (one a beat); `glass_clink` @ the beads' bloom; `card_flip` @ the file's swing-in |
| loom | `shuttle_clack` @ each landing of the tracked `shuttle` (its x velocity changes sign; assert within 1 frame of a beat); `weave_swish` mid-flight of each pick; `fray_crackle` @ the incidents fray; `stamp` @ `gc: expire 3 incidents`; `rope_creak` @ the rules pull; `heal_shimmer` @ `reachTime` (skills light) |
| diff | `pen_strike` @ the strike on "I'll"; `pen_strike` (gain −4) @ the confidence cut; `insert_pop_*` @ the rows opening; `typing` for the neovim line; `whoosh_whip` @ the internal whip down; `glass_clink` @ the playhead landing back and forth |
| cite | `typing` for the question; `fold_click` @ the `why?` click; `gutter_slide` @ the citation label opening; `stitch_pull` over the thread's draw; `glass_clink` (gain −6) @ the lines lighting; `gutter_slide` @ the blame gutter |
| braid | `typing` for the query; `edge_zip` × 3 @ each arm's arrival (`braidTimes`); `rope_creak` @ the braid; `commit_thock` @ the card's landing |
| merkle | `visited_tick_*` cascade with the counter (at most one per frame); `fold_click` per folding subtree (at most one per frame, gain −6); `stamp` @ the first `= hash · skipped`; `type_slam` @ the "50" slam; `whoosh_zoom` @ the plunge |
| graph | `edge_zip` @ the link's lift-off and each drawn edge; `glass_clink` @ the trip bead's drop; `heal_shimmer` @ the heal; `typing` + `key_enter` for the vocab command; `insert_pop_1` @ its result |
| honest | `room_tone` bed from the music-out downbeat (the `honest` section start) to the cut; `typing` (gain −8) for the question; nothing else (restraint) |
| proof | `room_tone` continues to the score's slam; `odometer_roll` ending @ each round's landing; `type_slam` @ 91.4's landing; `card_flip` (gain −8) @ the % smirk on "bad" |
| connect | `typing` + `key_enter` (on its downbeat); `connected_chime` @ the ✔ draw's end; `card_flip` + `whoosh_whip` (gain −8) @ each carousel beat |
| anywhere | `typing` for the install line; `insert_pop_*` @ the chips; `whoosh_whip` @ the split; `glass_clink` @ the namespace tile; `visited_tick_*` per doubling (11) |
| weave | `riser` ending @ the lock (`weave-time`, the B15 lock frame); `sub_impact` @ the lock (spec 15); `weave_swish` per arc arrival; `typing` for `gitloom 3f9a1c2` |
| transitions | `whoosh_whip` peak @ the cut of every whip; `whoosh_zoom` peak @ the cut of every zoom; nothing for match, cut, dip or xfade |

**Tests (bun, `sheet.test.ts`):**
```ts
import { describe, expect, test } from 'bun:test';
import { buildSheet } from './sheet';
import { load, shifted } from './testdata';   // the real vo/audio/tracks/palette/transitions, and a copy shifted by +s

describe('cues follow the data (Review Focus 2)', () => {
  test('shifting every time by +0.5 s shifts every cue and duck by exactly +0.5 s', () => {
    const a = buildSheet(...load()), b = buildSheet(...shifted(0.5));   // words, beats, downbeats, sections, scene windows, track f0 + 15
    expect(b.cues.length).toBe(a.cues.length);
    a.cues.forEach((c, i) => { expect(b.cues[i]!.anchor).toBe(c.anchor); expect(b.cues[i]!.t).toBeCloseTo(c.t + 0.5, 9); });
    a.ducks.forEach((d, i) => expect(b.ducks[i]!.t).toBeCloseTo(d.t + 0.5, 9));
  });
  test('a cue whose word is gone fails loudly, naming it', () => {
    const [vo, ...rest] = load();
    const broken = renameWord(vo, 'L01', 'forgets.', 'leaves.');
    expect(() => buildSheet(broken, ...rest)).toThrow(/no word "forgets" in L01/);
  });
});

describe('the sheet', () => {
  test('every cue names a palette sound and lies in the film', () => { /* sound in palette (or a slice id); 0 ≤ t < 93.6 */ });
  test('word cues sit on their onsets; beat cues on the grid', () => { /* anchor word:L07:3 → t === vo word start; beat:n → audio.beats[n] */ });
  test('typing keys land on frame times, one per character shown', () => { /* connect's command: count === its length; each t·30 is an integer within 1e-9, or spread k/30 inside one */ });
  test('the snap duck is two frames at the snap; the silent beat is one beat after ex → her', () => {});
  test('the shuttle clacks within one frame of a beat', () => {});
  test('honest carries only room tone and typing', () => {});
  test('the sheet is deterministic', () => { expect(JSON.stringify(buildSheet(...load()))).toBe(JSON.stringify(buildSheet(...load()))); });
});
```
`app/src/sfx/testdata.ts` (part of this task) builds `load()` from `data/*.json` and `data/sfx_palette.json`, and
`shifted(s)` by adding `s` to every time field (and `round(s·30)` to each track's `f0`).

**Run:**
1. `cd app && bun test src && bun run typecheck`.
2. `bun scripts/cues.ts` writes `data/sfx.json` and prints counts per scene and per sound.
3. Read the counts: the densest scene (typing) should stay under about 12 cues/s.

**Visual check:** `bun scripts/cues.ts --plot` writes `out/review/sfx/cues.png`, a timeline of every cue over the
VO words and beats (one row per scene). Read it: cues sit on their events, nothing lands inside a VO word except
typing and beds, and the honesty beat is nearly empty.

**Commit:** first the pure moves (`<scene>: timing moved to <scene>-time.ts, stills unchanged`), then
`The cue sheet: every sound placed from the film's own words, beats, tracks and scene events`.

### Task 9: The SFX bus and the final mix with stems

**Time:** about 3 h (Opus).

**Files:**
- Create: `tools/gitloom_film/sfx.py`, `tools/tests/test_sfx.py`
- Modify: `tools/gitloom_film/mix.py`, `tools/tests/test_mix.py`, `tools/gitloom_film/automate.py` (duck lanes),
  `tools/tests/test_automate.py`, `tools/pyproject.toml` (`film-sfx`)

**Interfaces:**
```python
# sfx.py
def load_sheet(path: Path = DATA / "sfx.json") -> dict: ...
def render_bus(sheet: dict, manifest: dict, lib: Path, duration: float, sr: int = 48000) -> np.ndarray:  # (n, 2) float32
    # one-shot: its picked file placed so its hit_s lands on round(t·sr); gain dB; constant-power pan;
    # loops (dur set): tiled with 50 ms equal-power seams, 30 ms fades at both ends, cut to dur
def main(argv=None): ...   # film-sfx → audio/sfx/sfx.wav (48 kHz / 24-bit stereo)
# automate.py
def duck_lanes(ducks: list[dict], sr: int, n: int, bus: str) -> np.ndarray:   # per-sample linear gain from the sheet's ducks for 'music' or 'all'
# mix.py
def mix_stems(vo: Path, music: Path, sfx: Path, out_dir: Path, sections: list[dict] | None = None,
              ducks: list[dict] | None = None) -> dict:
    # music: arc (lanes) × duck_lanes('music') → sidechain-ducked by the voice (the existing premix settings, 6–9 dB)
    # sfx: sidechain-ducked by the voice, ratio 2, ~3 dB ("effects up front": light)
    # 'all' ducks apply to music and sfx; never to the voice
    # sum → static gain to −14 LUFS → limiter at −2 dBFS (latency=1) → mix.wav
    # stems vo.wav / music.wav / sfx.wav = each bus × the same static gain, pre-limiter, 48 kHz / 24-bit stereo
    # returns {"I", "TP", "LRA", "duck_db", "stem_residual_db"}
def duck_depth(music_bus: np.ndarray, ducked: np.ndarray, vo: np.ndarray, sr: int) -> float: ... # median dB the music drops while the voice speaks
```
- **CLI:** `film-mix` now reads `audio/vo/vo-chain.wav` (it fails, naming `film-vo-chain`, if that is missing),
  the chosen score and `audio/sfx/sfx.wav` (`--no-sfx` gives Plan 1's mix). It writes
  `audio/mix/{mix,vo,music,sfx}.wav` and prints the summary.

**Tests (pytest, synthetic):**
```python
def test_a_one_shot_lands_its_hit_on_the_sample(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})   # hit_s = 0.005
    y = render_bus({"cues": [{"sound": "click", "t": 1.0, "gain": 0, "pan": 0}], "ducks": []}, manifest, lib, 2.0)
    assert np.argmax(np.abs(y[:, 0])) == 48000

def test_pan_is_constant_power(): ...                  # pan ±1 → one channel; pan 0 → both at −3 dB; L²+R² const
def test_loops_tile_to_dur_without_clicks(): ...       # max |Δy| at the seams ≤ 2× the median |Δy|
def test_unknown_sound_fails(): ...

def test_hot_sfx_transients_keep_the_master_in_spec(tmp_path):     # Review Focus 3
    vo, mu = synth(tmp_path)                                         # as test_mix.synth
    sfx = tmp_path / "sfx.wav"; write_wav(sfx, clicks_every(0.5, peak=1.0, seconds=10))
    m = mix_stems(vo, mu, sfx, tmp_path / "mix")
    assert m["I"] == pytest.approx(-14.0, abs=0.5) and m["TP"] <= -1.0

def test_stems_sum_to_the_premaster_mix(tmp_path):
    m = mix_stems(*synth3(tmp_path), tmp_path / "mix")
    assert m["stem_residual_db"] <= -30                              # (vo+music+sfx) − mix, where the limiter is idle

def test_music_ducks_six_to_nine_db_under_the_voice(tmp_path):
    assert 6.0 <= mix_stems(*synth3(tmp_path), tmp_path / "mix")["duck_db"] <= 9.0

def test_the_arc_survives_with_sfx(tmp_path): ...       # honest still 12 dB under the tour (±1), as test_mastering_keeps_the_drawn_arc
def test_a_music_duck_silences_only_the_music(): ...    # duck music −30 dB for 2 frames → music RMS there ≤ −28 dB rel., voice untouched
def test_the_voice_stays_on_its_sample(tmp_path): ...   # as the existing test, through mix_stems
```

**Run:**
1. `cd tools && uv run pytest -q`.
2. `uv run film-sfx`.
3. `uv run film-mix`. It must print −14.0 ±0.5 LUFS, TP ≤ −1.0, duck 6–9 dB and a stem residual ≤ −30 dB.
4. `uv run film-sync` is still OK (the voice and the edit are untouched).

**Objective listening proxies** (Read them; the user is the ear):
- `out/review/c5/mix.png`: per-scene RMS of each stem over time, with the cuts and the VO words marked.
- `out/review/c5/mix.json`: per scene, the SFX-to-VO ratio while she speaks. Flag a scene where SFX is within 6 dB of
  the voice during a word.

**Commit:** `The final mix: her processed voice, the score's arc ducked under her, the effects up front, mastered to
−14 LUFS with stems`.

---
## Part D: the film, its deliverables and C5 (Tasks 10–11)

### Task 10: The full 1080p render and the deliverables

**Time:** about 1.5 h of agent work, plus about 2–4 h of unattended rendering (estimated from Plan 2's clips; the
first segment's rate gives the real ETA).

**Files:**
- Create: `tools/gitloom_film/deliver.py`, `tools/tests/test_deliver.py`
- Modify: `tools/pyproject.toml` (`film-deliver`)

**Interfaces:**
```python
def segments(scenes: list[dict], total_frames: int, n: int, margin: float = 1.0, fps: int = 30) -> list[tuple[int, int]]:
    # n contiguous [f0, f1) ranges covering 0..total_frames; each split moved to the midpoint frame of the scene that
    # holds it, so it lies ≥ margin s from every cut (transitions are ≤ 0.5 s a side)
def render_cmds(segs, scale: int = 1) -> list[list[str]]:
    # ["caffeinate", "-i", "bun", "scripts/render.ts", "video", "--from", f"{f0/30}", "--to", f"{f1/30}",
    #  "--samples", "auto", "--noaudio", "--scale", str(scale), "--out", f"../out/film/seg-{k}.mp4"]
def encode_args(kind: str, video: Path, audio: Path, out: Path) -> list[str]:
    # kind 'rough'    → out/rough.mp4: -c:v copy + AAC 320k 48 kHz (the C5 artefact, spec §9)
    # kind 'web1080'  → out/film/gitloom-launch-1080p30.mp4: libx264 -crf 16 -preset slow, BT.709 tags, AAC 320k, +faststart
    # kind 'ig16x9'   → out/instagram/gitloom-launch-16x9.mp4: libx264 -preset slow -crf 17 -maxrate 12M -bufsize 24M
    #                   -profile:v high -pix_fmt yuv420p, BT.709 tags, AAC 256k 48 kHz, +faststart (out/instagram/build.sh)
    # kind 'ig4x5'    → out/instagram/gitloom-launch-4x5.mp4: as ig16x9 with
    #                   -vf "scale=1080:-2,pad=1080:1350:(ow-iw)/2:(oh-ih)/2:color=0x110d10,setsar=1"
    # never -itsoffset, never -ss on the audio; -map 0:v -map 1:a; -shortest is NOT used (lengths are checked instead)
def check(path: Path, kind: str, expect_frames: int = 2808, expect_seconds: float = 93.6) -> list[str]:  # problems: frames != 2808, fps != 30, size, duration ≠ 93.6 ± 1/30,
                                                # stream start_time ≠ 0, missing BT.709 tags, audio ≠ 48 kHz stereo,
                                                # loudness of the decoded audio outside −14 ± 0.5 / TP > −1.0
def main(argv=None): ...  # film-deliver segments | render [--segments 4] [--scale 1] | assemble | check
```

**Behaviour:**
- **`render`.** Runs the segment commands one after another in `app/`. A segment whose `seg-k.mp4` exists with the
  right frame count is skipped, so the render resumes. Each segment writes render.ts's `<out>.progress`.
- **Running it.** The agent launches `film-deliver render` **in the background** and polls
  `out/film/seg-*.mp4.progress` in short calls, never blocking more than about 4 min. It reports the ETA and the
  progress paths to the controller. No Blender runs meanwhile.
- **`assemble`:**
  1. concat the segments (`-f concat -c copy`) to `out/film/video.mp4`;
  2. encode the four outputs from it and `audio/mix/mix.wav`;
  3. copy the stems to `out/film/stems/{mix,vo,music,sfx}.wav`;
  4. run `check` on each output.
- **`check`** also places a 1-frame test: the frame of `thread_snap`'s cue (from `data/sfx.json`) is the snap frame
  of B01. It compares the audio's peak near the snap cue to the cue time (±1 frame).

**Tests (pytest):**
```python
def test_segments_cover_the_film_exactly_and_avoid_cuts():           # real vo.json
    vo = json.loads((DATA / "vo.json").read_text())
    segs = segments(vo["scenes"], 2808, 4)
    assert segs[0][0] == 0 and segs[-1][1] == 2808
    assert all(a[1] == b[0] for a, b in zip(segs, segs[1:]))
    cuts = [s["end"] for s in vo["scenes"][:-1]]
    assert all(min(abs(f / 30 - c) for c in cuts) >= 1.0 for _, f in segs[:-1])

def test_encodes_never_offset_the_audio():                           # Review Focus 5
    for kind in ["rough", "web1080", "ig16x9", "ig4x5"]:
        a = encode_args(kind, Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
        assert "-itsoffset" not in a and "-shortest" not in a and a.count("-ss") == 0

def test_check_reports_a_short_audio_and_a_late_start(tmp_path):
    v = tiny_film(tmp_path, frames=60, audio_seconds=1.9, audio_delay=0.1)   # ffmpeg lavfi testsrc + sine
    probs = check(v, "rough", expect_frames=60, expect_seconds=2.0)
    assert any("duration" in p for p in probs) and any("start" in p for p in probs)

def test_ig4x5_is_1080x1350_on_ink(tmp_path): ...    # encode a tiny clip; probe size; corner pixel ≈ #110d10
```

**Run:**
1. Check the plates: `--scan` must report every shot lit at 1920×1080 (b01 181, b03 34, b05 288, b08 198,
   b15 216). Re-render nothing unless the scan fails, and then one Cycles job at a time.
2. `uv run film-deliver render --segments 4`, in the background.
3. `uv run film-deliver assemble && uv run film-deliver check`, which must print no problems.
4. Visual: `bun scripts/render.ts sheet --from 0 --to 93.6 --cuts` (a still either side of every cut), plus a sheet
   from `out/rough.mp4` at the segment boundaries (`ffmpeg -ss` at the frames either side). Read both: no seams, no
   red frames, and the transitions as approved.

**Commit:** the code and tests only (the outputs are under `out/`):
`film-deliver: the film rendered in resumable segments, assembled with the final mix, encoded for the web and
Instagram`.

### Task 11: Checkpoint C5 (stop and ask the user)

**Time:** about 45 min, then the user's review.

1. **Build `out/review/c5/index.html`** (local, self-contained, relative links). It holds:
   - `out/rough.mp4`, the 1080p film with the final mix (the spec's C5 artefact);
   - the two Instagram files;
   - **the 14 transitions** as short looping clips (`out/transitions/*.mp4`), each with its kind and a line on its
     intent, marked "spec" (#1, #2) or "proposal";
   - **the SFX palette**: every sound with its variants as audio players, the current pick marked, and its
     spectrogram. The user notes a different pick by id. `shuttle_clack` and `thread_snap` are flagged (the spec
     allows real recordings);
   - **the stems** (vo, music, sfx, mix) as players;
   - the loudness line, the duck depth and the stem residual;
   - `out/review/c5/mix.png` and `cues.png`.
2. Open it for the user.
3. **Ask three questions:**
   1. Do the transitions work, and which should change?
   2. Do the effects sit right: too loud, too busy, wrong sound? Say the sound id. And do the snap and the shuttle
      need real recordings?
   3. Is the mix balance right (her, the score, the effects)?
4. **Apply the notes as fix rounds.**
   - A pick change is a palette edit plus `film-sfx` and `film-mix`. No new credits are spent unless a prompt
     changes.
   - A transition change re-renders its clip, then the affected segment only (`seg-k.mp4`), then `assemble`.
   - A level change edits the palette gain or the cue's.
5. Record each ruling in the Plan 3 ledger, `.superpowers/sdd/2026-10-04-plan-3-transitions-sound/progress.md`.

**Do not start Plan 4 until the user approves C5.** Plan 3 is done when they do.

---
## What Plan 3 leaves ready for Plan 4 (the 4K finals; not planned here)

- **Transitions are resolution-independent.** Taps scale with `pxScale` (`tapCount`), and all transforms are in
  logical px, so `--scale 2` needs no transition change. Task 1's tests pin the 4K tap count.
- **The film renders in resumable segments** with `film-deliver render --scale 2`. Plan 4 adds the ProRes 422 HQ
  master and the 4K H.264 (spec §10) as new `encode_args` kinds.
- **The audio is final:**
  - `audio/mix/{mix,vo,music,sfx}.wav` at 48 kHz / 24-bit are the §10 stems;
  - `data/sfx.json`, `data/sfx_palette.json` and `audio/sfx/manifest.json` are committed, so the bus re-renders
    without credits while the library cache exists;
  - Plan 4 should archive `audio/sfx/lib/` and the takes (R9).
- **Still open for Plan 4** (from Plan 2's ledger; untouched here):
  - the E6 must-fixes: a never-drawn Panel renders NaN (connect works around it), the glass bokeh speckle under DoF,
    and bloom staircasing;
  - `e6-partial.patch`;
  - loom's window re-rendered at 64 spp (it is at 32);
  - 1440p plates (B01/B03/B05/B08) and native 4K B15;
  - the SRT captions.
- **Data the finals depend on is locked:** `vo.json`, `audio.json`, the 14 transition files, and the tracks
  (b01's new `fibre_*` anchors included).

## Task list and order

| task | what | depends on | parallel with | time |
|---|---|---|---|---|
| 1 | engine transitions and overlays (M13) | — | 2, 3 | ~4 h |
| 2 | sound library (ElevenLabs, cache, manifest) | — | 1, 3 | ~3 h + ~20 min generation |
| 3 | voice chain | — | 1, 2 | ~2 h |
| 4 | transitions A: thread-ex, ex-her, her-repo, repo-loom | 1 | 5 | ~4 h |
| 5 | transitions B: loom-diff, diff-cite, cite-braid, braid-merkle | 1 | 4 | ~4 h |
| 6 | transitions C: merkle-graph, graph-honest, honest-proof | 1 | 7 | ~3 h |
| 7 | transitions D: proof-connect, connect-anywhere, anywhere-weave | 1 | 6 | ~3.5 h |
| 8 | cue sheet from the data | 2, 4–7 | — | ~4 h |
| 9 | SFX bus and final mix with stems | 3, 8 | — | ~3 h |
| 10 | full 1080p render and deliverables | 4–7, 9 | — | ~1.5 h + 2–4 h render |
| 11 | checkpoint C5 | 10 | — | ~45 min + review |
