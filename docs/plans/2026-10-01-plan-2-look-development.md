# GitLoom launch film, Plan 2: look development → look test → style frames (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (the user chose it) to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the premium motion toolkit (engine and Blender), then prove the look on three hero moments (C4a), then
bring all 15 scenes to finished style frames (C4). Everything plays against the locked voice, score and timing from
Plan 1.

**Architecture:**
- **Engine additions** (`app/src/engine/`), each a small module with one job:
  - a 3D stage with studio lighting and depth of field;
  - extruded kinetic 3D type;
  - 2.5D UI panels;
  - the thread in 3D;
  - beat-locked motion helpers;
  - a Blender plate/track loader.
- **Blender** (`blender/`): a shared library plus a render CLI, driven by the same timing files.
- **Scenes** (`app/src/scenes/<id>.ts`): each replaces its animatic card as soon as the module exists (`edit.ts`'s
  `moduleFor`).

**Tech stack:** as Plan 1, plus three.js PBR (`MeshPhysicalMaterial`, `PMREMGenerator` + `RoomEnvironment`,
`EXRLoader`) and Blender 5.2.2 LTS (Cycles on Metal, AgX, headless `bpy`).

**Spec:** `docs/specs/2026-09-30-gitloom-launch-film-design.md` (§3 concept, §4 scene treatments, §6 visual system, §7
build, §11 facts). **Ledger of Plan 1 rulings:** `docs/ledgers/2026-09-30-plan-1-ledger.md`, and the onset
calibration in `docs/ledgers/2026-09-30-plan-1-final-fix-report.md`. The rulings that bind this plan are copied below.

**How the tasks are specified:**
- Infrastructure tasks give exact interfaces, behaviour and tests.
- Creative tasks give art direction, technical requirements and visual acceptance criteria.

The look is found by rendering stills and looking at them, so creative implementers are the most capable model
(Opus), per the user's direction. Every creative task ends with rendered stills that the implementer inspects with
the Read tool, and the controller reviews them too.

This is **Plan 2 of 4**:
- Plan 1 (done): voice, score, mix, timing, animatic.
- Plan 2 (this one): look.
- Plan 3: full animation, sound effects, final mix.
- Plan 4: finals and deliverables.

## Global Constraints

**Carried over from Plan 1:**
- **Repo:** `~/Developer/code/gitloom-film`.
- **Palette** (the only colours):
  - ink `#110d10`, ink2 `#161114`, panel `#1e181c`, panel2 `#282027`
  - rule `#2b2229`, ruleStrong `#3e323b`
  - bone `#ede7ea`, boneDim `#a99fa5`, boneFaint `#6f6469`
  - blood `#c22b45`, bloodBright `#dc4a63`, bloodDim `#8e1f35`
  - moss `#4aad63`, mossDim `#1c3324`
- **Colour roles:** blood is the accent, `−`, key numerals and the CTA, never a large surface fill. Moss means `+` and
  gain only. **Only blood and moss may glow; bone never blooms.**
- **Fonts:** Bricolage Grotesque (display; her voice), JetBrains Mono (the machine), Geist (UI chrome). These are the
  static instances in `app/public/fonts/`. Every proportional line is kerned (`layout()`/`glyphX()`). Display text uses
  typographic punctuation. No outlined or haloed type.
- **Timing:** 30 fps. Scenes are pure functions of `f.t`: no `Math.random`, `Date` or `performance.now()` for visuals;
  seeded noise only (`hash`, `mulberry32`). Per-frame flicker uses `frameIdx(t)`.
- **Data:** `data/vo.json` (words with measured onsets), `data/audio.json` (beats/downbeats/sections at 100 BPM,
  envelopes from the music as heard) and `audio/mix/mix.wav` are **locked**. Only Task 1 changes them.
- **Facts:** every on-screen command, snippet, path, hash and number is verbatim from spec §11, or listed there as
  illustrative. Task 9 enforces this.
- **Secrets:** the key in `~/11labs` is never printed, logged or committed. This plan makes **no** ElevenLabs calls.
- **Commits:** end with a blank line and then `Co-Authored by MelloB's coding agent <build@mellob.in>`. Stage by
  explicit path; never `git add -A`; never `git clean`. Renders live in `out/` (gitignored).

**New in Plan 2:**
- **Review resolution:** style frames at 1920×1080. The engine renders at `--scale 1` for review and at `--scale 2` for
  4K later. Blender look-dev renders at 960×540, and style frames at 1920×1080.
- **Blender:** `/Applications/Blender.app/Contents/MacOS/Blender`, run headless (`-b -P script.py -- args`). Cycles on
  the Metal GPU with the AgX view transform, 30 fps, motion blur with shutter 0.5, OpenImageDenoise. Plates are
  written as linear half-float EXR (and PNG proxies for preview).
- **Performance:** each engine scene must preview at ≤ 120 ms/frame at 1080p on this M5 (`render.ts perf`).
  Precompute in `init()`.
- **Legibility:** at 1080p, body lines are ≥ 28 px and mono labels ≥ 16 px. Everything sits inside the title-safe
  area (≥ 96 px from the edges), except full-bleed imagery.

## Motion language v2: "crazy, sexy, kick-ass, premium" (the user's direction)

The spec's treatments (§4) are the *what*; this section is the *how it moves*. Every scene applies all of it.

1. **Every downbeat is an event:** a cut, a type slam, a camera snap, a light sweep, or a thread hit. Off-beats carry
   micro-motion (a slow push, parallax drift, a breathing glow). Nothing sits still for more than a beat.
2. **Hero words are 3D.** The words that carry a line are extruded Bricolage glyphs:
   - depth 0.16 em, bevel 0.012 em, satin bone;
   - accents get an emissive blood or moss edge (the "diff glow");
   - they **slam** in from depth on their spoken onset, with spring overshoot (settling in about 250 ms) and real
     motion blur;
   - the rest of the line is flat, crisp Bricolage.
3. **The camera always moves.** Each scene has at least one deliberate move: a push-in, an orbit, a crane, or a
   rack-focus. Scene changes use **whips** (60–120 ms of directional blur at the cut), **zoom-throughs**, or **match
   cuts along the thread**.
4. **Speed ramps:** peak moments go to slow motion (the snap at 0.25×, the mark's lock at 0.5×) and snap back to real
   time on a beat.
5. **Light is choreography.** Studio key plus a hard rim on a dark environment. **Specular sweeps** cross glossy type
   on hits. The blood and moss strands carry a soft emissive core that halates.
6. **Depth:** shallow depth of field on 3D shots, foreground elements drifting out of focus for parallax, and rack
   focus to guide the eye.
7. **Premium restraint:** palette and type discipline, bone never blooms, and precise hairlines. There is no
   lens-flare soup, no random particle confetti, no stock glitch, no neon or cyber look, and no bouncy cartoon
   easing. Springs are fast and tight: frequency 4–6 Hz, damping 0.5–0.7.
8. **Sultry vs witty:** the camera carries the sultriness (slow, luxurious, close); the type and cuts carry the wit
   (snaps on the beat, deadpan mono footnotes).

## Review Focus

These are the failure modes most likely to bite, each pinned by a test in its owning task.

1. **Bone blooming:** a full-intensity bone surface must contribute less than 1% bloom, while blood and moss at an
   HDR value of 3.0 must glow. Tested in Task 2.
2. **Non-determinism:** rendering the same `t` twice, in any order, gives byte-identical frames. Adaptive motion blur
   depends on it. Tested in Task 3's stage test and every scene's stills step.
3. **Glyph holes:** extruded "o", "a", "e" and "g" have real counters, not filled blobs. Tested in Task 4.
4. **Plate frame mapping:** plate frame *n* is shown exactly at film frame *n* of its shot, with no half-frame drift,
   and overlays sit on their tracked anchors within 2 px. Tested in Task 8.
5. **Facts drift:** a scene string that isn't in `data/facts.json` fails the gate. Tested in Task 9.

## File map

```
app/src/engine/
  look.ts            post "look" presets (bloom/halation tuned so bone never blooms)                       (Task 2)
  stage.ts           3D stage: scene, camera rig, PMREM env, depth texture, render into `out`              (Task 3)
  dof.ts             depth-of-field pass (CoC gather, half-res)                                              (Task 3)
  type3d.ts          extruded kinetic 3D type from font outlines, kerned                                     (Task 4)
  panels.ts          2.5D UI panels (terminal, editor, JSON, chat, console) + syntax highlighter            (Task 5)
  thread3d.ts        the thread motif in 3D (plies, sheen, glow core, draw-on, fray)                        (Task 6)
  motion.ts          beat-locked helpers (slam, springs, whips, speed ramps, word reveal times)             (Task 7)
  plates.ts track.ts Blender plate sequences + tracked 2D anchors                                           (Task 8)
  *.test.ts          bun tests for each of the above
app/src/scenes/<id>.ts (+ <id>-*.ts helpers)   the 15 scenes                                               (Tasks 10–25)
blender/lib/         setup.py materials.py thread.py lights.py timing.py export.py                          (Task 8)
blender/render.py    CLI: look | preview | final, per shot                                                  (Task 8)
blender/shots/       b01_thread.py b03_reform.py b05_loom.py b08_braid.py b15_weave.py                      (Tasks 11–12, 15, 18, 25)
blender/mark/        trace + parametric mark geometry                                                       (Task 12)
tools/gitloom_film/onsets.py   fricative-aware onsets                                                       (Task 1)
tools/gitloom_film/factcheck.py + data/facts.json                                                           (Task 9)
out/style/<id>/      style frames and motion clips (gitignored)
```

---
## Part A: foundations (Tasks 1–9)

### Task 1: Onsets for fricatives and plosives, and the chain re-run

This carries a Plan 1 ruling forward.
- **The gap:** words that open with /s/, /tʃ/, /k/, /t/ or aspirated plosives light at the start of *voicing*,
  30–155 ms after their consonant becomes audible. Examples are "Skills," (155 ms), "tells", "keep.", "Change" and
  "to".
- **Spec:** §2 wants the reveal within one frame of the *spoken* onset.

**Files:**
- Modify `tools/gitloom_film/onsets.py`, `tools/gitloom_film/sync.py`, `tools/gitloom_film/music.py`,
  `tools/gitloom_film/beats.py`, `data/sync_waivers.json`
- Modify the tests: `tools/tests/test_onsets.py`, `test_sync.py`, `test_music.py`, `test_beats.py`

Then re-run the data chain.

**Measured on the real takes by the Plan 1 re-review.** Against the first audible frame (≥ −30 dB), the consonant
openings light **late**:

| word | lateness |
|---|---|
| "Commitment" | +65 ms |
| "Facts" | +40 ms |
| "Skills," | +155 ms |
| "Change" | +100 ms |
| "Fifty" | +80 ms |

The takes contain **no pre-word inhalations**, only breathy word tails. "Skills," has a −47 dB stop closure between
its /s/ and its /k/ release.

**Rule:** after finding the voiced run (the current logic), walk **back** from its start while the 5 ms RMS stays at or
above −35 dB relative to the take's peak.
- Allow gaps below that level of at most 15 ms.
- Additionally, bridge **one** stop-closure gap of up to 90 ms when the segment before it holds at least 20 ms at
  −25 dB or louder (a real fricative, as in "Skills").
- Stop at the search window's start.
- The onset is the start of that contiguous run. A low-level breath separated from the word is excluded; a fricative,
  burst or aspiration running into the vowel is included.

**Sync gate hardening** (from the Plan 1 re-review):
- **An unwaivable any-sound check.** `film-sync` adds a check on **line-initial** words: the frame that first lights
  the word must be no more than 40 ms after the first audible frame (≥ −30 dB) in that word's window.
- **Act cuts off the beat grid.** They are a separate problem that a waiver can't clear, because waivers exempt "not
  on a downbeat" only.
- **Waiver reasons.** Update `data/sync_waivers.json`'s reasons to match the current cut offsets. Drop "C3-approved"
  where a cut moved after C3.
- **A missing `audio/vo/vo.wav`** gives a clear message, not a raw `LibsndfileError`.
- **Fix `test_sync.py`'s waived-line assertion.** It currently asserts a non-empty string.

**Music meta guard** (latent, from the Plan 1 re-review):
- `merge_plan` keeps the pick's section timing as `chosen_meta` (backfill it now from the current `meta`).
- `film-beats` prefers `chosen_meta` over `meta`, so a future `film-music` run can't move the chosen score's sections.

**Tests to add** (synthetic, 48 kHz):
- **Fricative:** 120 ms of band-limited 4–8 kHz noise at −12 dB flowing straight into a 150 Hz voiced tone. The onset
  is at the noise start ±5 ms.
- **Plosive:** a 5 ms click, 20 ms of aspiration noise, then the tone. The onset is at the click ±5 ms.
- **Breath:** 150 ms of broadband noise at −24 dB, then 40 ms of silence, then the tone. The onset is at the tone
  start ±5 ms (the breath is excluded).
- **Stop closure ("Skills"):** 100 ms of /s/-like noise at −15 dB, a 60 ms closure at −47 dB, a 10 ms burst, 20 ms of
  aspiration, then the tone. The onset is at the /s/ start ±5 ms.
- **Sync, any-sound:** a vo.json whose line-initial word starts 60 ms after an audible fricative head fails the new
  check, and one starting 20 ms after passes.
- **Sync, off-grid:** a waived act cut moved off the beat grid still fails ("act cut not on a beat").
- **Music meta:** after `merge_plan` with a new plan, `chosen_meta` is unchanged, and `film-beats`' section starts come
  from `chosen_meta`.
- **Existing tests:** all still pass.

**Chain:**
```bash
cd tools && uv run film-pace && uv run film-edit && uv run film-snap && uv run film-beats && uv run film-mix && uv run film-sync
```
`film-sync` must pass: only the three waived act cuts, with the any-sound check green.
- **Report:** the new sync error for the 11 words the Plan 1 fix wave named, and for the five words in the table above.
- **Commit** the code, `data/vo.json`, `data/audio.json`, `data/music_plan.json` and `data/sync_waivers.json`, with the
  message: `Onsets count the consonant: fricatives and bursts that run into the vowel start the word`.

---

### Task 2: The look: bone never blooms, and 2D layers blend as designed

**Files:**
- Create: `app/src/engine/look.ts`, `app/src/engine/look.test.ts`
- Modify: `app/src/engine/post.ts` (`DEFAULT_POST`), `app/src/engine/gl.ts` (the Compositor / Layer2D blending)

**Problems (from Plan 1):**
1. **Bloom:** with threshold 0.85 and knee 0.5, *bone* blooms the most (prefilter weights: bone 0.146, blood 0.033,
   moss 0.006). That's the opposite of the rule.
2. **Canvas alpha:** Canvas2D layers are decoded to linear and then alpha-blended in linear light, so designed low
   opacities come out much brighter. 28% bone over ink displays at about 52% grey instead of about 26%.

**Requirements:**
- **`look.ts`** exports:
  - `bloomWeight(lum: number, threshold: number, knee: number): number`, a pure-TS mirror of the exact prefilter curve
    used in `post.ts`. Read the shader and mirror it exactly.
  - `LOOK: PostOverrides`, the film-wide defaults.
- **Tune `DEFAULT_POST`** so that:
  - `bloomWeight(luma(LIN.bone), …) === 0`;
  - an emissive blood or moss value at 3.0× linear gets weight ≥ 0.5;
  - bloom 0.6 and halation (blood-tinted, already) 0.35 look good;
  - CA ≈ 0.6 px at the edge, grain ≈ 0.045 and vignette ≈ 0.28.

  Set the final values by rendering the Plan 1 cards and a test frame with an HDR blood glyph. Record them in a
  comment.
- **2D layers composite in sRGB (display) space,** the way design tools and browsers blend, so an alpha of 0.28 looks
  like 28%.
  - Implement this in the Compositor as the default for `Layer2D` uploads. For example, blend `toSRGB(dst)` and
    `src_srgb` by alpha, then convert back to linear. If destination read-back needs a ping-pong target, add one.
  - Keep a `'linear'` mode for HDR glows that should add in light.

**Tests (bun, `look.test.ts`):**
- `bloomWeight` is 0 for bone at the default settings;
- blood and moss at 3.0 get ≥ 0.5;
- the function is monotonic in `lum`;
- **blend math:** a pure `blendSRGB(dst, src, a)` gives `toLinear(0.28 * srgb(bone))` over an ink of about 0 (±1
  level).

**Visual acceptance:**
- Re-render the four Plan 1 card stills: `bun scripts/render.ts stills --t 1.64,16.69,59.19,90.68 --out ../out/wip/look`.
- Read them: the dim words are now visibly dimmer (designed 28%), the watermark numeral is faint, and no bone glows.

**Commit:** `The film's look: bone never blooms, and 2D layers blend at their designed opacity`.

---

### Task 3: The stage: 3D scenes with studio light, camera rig and depth of field

**Files:**
- Create: `app/src/engine/stage.ts`, `app/src/engine/dof.ts`, `app/src/engine/stage.test.ts`, and a dev harness
  `app/src/scenes/_stagetest.ts`
- Modify: `app/src/main.ts` and `app/scripts/render.ts` (the `--module` harness)

**Interfaces:**
```ts
// stage.ts
export interface StageOpts { fov?: number; near?: number; far?: number; envIntensity?: number; background?: [number, number, number] }
export class Stage {
  scene: THREE.Scene; camera: THREE.PerspectiveCamera;
  constructor(renderer: THREE.WebGLRenderer, opts?: StageOpts);           // PMREM(RoomEnvironment) env, dark by default
  render(out: THREE.WebGLRenderTarget, opts?: { dof?: DofParams | null; clear?: boolean }): void; // color+depth → DoF → out
  dispose(): void;
}
export interface CamKey { t: number; pos: [number, number, number]; target: [number, number, number]; fov?: number; roll?: number; ease?: (x: number) => number }
export class CameraRig { constructor(keys: CamKey[]); apply(cam: THREE.PerspectiveCamera, t: number): void; }
// dof.ts
export interface DofParams { focus: number; fstop: number; maxBlurPx?: number }
export function cocPx(depth: number, p: DofParams, fovDeg: number, imageHeightPx: number): number; // thin-lens, pure
export class DofPass { render(renderer, color: THREE.Texture, depth: THREE.DepthTexture, cam: THREE.PerspectiveCamera, p: DofParams, out): void }
```

**Behaviour:**
- `Stage.render` draws `scene` with `camera` into an internal HDR target that has a `DepthTexture`, then runs the DoF
  pass into `out`. Without `dof`, it copies straight through.
- The environment is a dim studio (`RoomEnvironment` via `PMREMGenerator.fromScene`), with `environmentIntensity`
  about 0.4 by default, so glossy surfaces get sweeps and black stays black.
- DoF is a half-resolution gather over a Poisson disc, weighted by circle of confusion, with near/far separation to
  avoid halo bleed. Keep it at 2 passes or fewer.
- **Harness:** `render.ts stills --module <name> --t …` loads `scenes/<name>.ts` as the only timeline entry over
  [0, duration], via `?module=<name>` in `main.ts`. `_stagetest.ts` is a lit scene with three satin spheres at 2, 4
  and 8 m, focused at 4 m, f/1.4.

**Tests (bun):**
- `cocPx` is 0 at the focus distance and grows with |1/focus − 1/depth|;
- it's clamped at `maxBlurPx`;
- `CameraRig.apply` gives exact key values at key times and eases between them.

**Visual acceptance:**
- `bun scripts/render.ts stills --module _stagetest --t 1 --out ../out/wip/stage`.
- Read it: the middle sphere is sharp, the near and far ones are soft with no halo fringe, the highlights are glossy
  (with the rim of the room environment), and the background is ink.
- Render the same `t` twice and check the files are byte-identical (determinism).

**Commit:** `The stage: 3D scenes with studio light, a camera rig and depth of field`.

---

### Task 4: Kinetic 3D type

**Files:** Create `app/src/engine/type3d.ts`, `app/src/engine/type3d.test.ts`, `app/src/scenes/_typetest.ts` (harness)

**Interfaces:**
```ts
export interface Type3DOpts { family: string; size: number; depth?: number; bevel?: number; curveSegments?: number; tracking?: number }
// size = world units per em; depth/bevel in em (defaults 0.16 / 0.012)
export interface Glyph3D { ch: string; mesh: THREE.Mesh; x: number; w: number; word: number }
export class Type3D {
  group: THREE.Group; glyphs: Glyph3D[]; width: number;
  constructor(text: string, opts: Type3DOpts, material: THREE.Material | ((g: { ch: string; i: number; word: number }) => THREE.Material));
  dispose(): void;
}
export function glyphShapes(family: string, ch: string): THREE.Shape[];   // unit em, y up, holes resolved
export const Mat: { satinBone(): THREE.MeshPhysicalMaterial; accent(c: 'blood' | 'moss', emissive?: number): THREE.MeshPhysicalMaterial };
```

**Behaviour:**
- Outlines come from `ot(family)` (opentype.js commands): M/L/Q/C/Z go to a `THREE.ShapePath`, then `toShapes`, with
  hole orientation handled.
- Geometry is `ExtrudeGeometry` with a bevel, cached per (family, ch, depth, bevel).
- Glyph x positions are the **kerned** `layout()` positions scaled to world units, so 3D words keep the same kerning
  as 2D ones.
- **Materials:**
  - satin bone: `MeshPhysicalMaterial`, colour `LIN.bone`, roughness ≈ 0.38, clearcoat 0.25, sheen 0.3;
  - accents: a satin surface plus an emissive rim through a fresnel `onBeforeCompile`, or an emissive-only bevel
    material, so the edge glows blood or moss.

**Tests (bun):**
- `glyphShapes('Bricolage-1000-600', 'o')` → 1 shape with 1 hole;
- `'i'` → 2 shapes;
- the `Type3D("commit")` width matches `layout()`'s width × scale within 1%;
- each glyph's x matches `layout().glyphs[i].x` × scale.

**Visual acceptance:**
- `_typetest.ts` shows "every memory has a commit" in 3D, lit by the Stage, with "commit" as a moss accent.
- `stills --module _typetest --t 1`, then Read it:
  - the counters of o/e/a are open;
  - the bevels catch the light;
  - the kerning matches a 2D line drawn under it;
  - the moss edge glows and the bone doesn't.

**Commit:** `Kinetic 3D type: kerned, extruded Bricolage with satin and glowing accents`.

---

### Task 5: 2.5D UI panels and a syntax highlighter

**Files:** Create `app/src/engine/panels.ts`, `app/src/engine/panels.test.ts`, `app/src/scenes/_paneltest.ts` (harness)

**Interfaces:**
```ts
export type Lang = 'bash' | 'ts' | 'python' | 'go' | 'rust' | 'json' | 'yaml' | 'md' | 'plain';
export type TokenClass = 'kw' | 'id' | 'str' | 'num' | 'com' | 'punc' | 'prompt' | 'ok';
export function tokenize(line: string, lang: Lang): { text: string; cls: TokenClass }[];
export interface PanelLine { text: string; kind?: 'cmd' | 'out' | 'add' | 'del' | 'ctx' | 'com'; at?: number; cps?: number }
export interface PanelSpec { kind: 'terminal' | 'editor' | 'json' | 'chat' | 'card'; title?: string; w: number; h: number; lang?: Lang; gutter?: 'numbers' | 'diff' | 'none'; lines: PanelLine[]; firstLine?: number }
export class Panel {
  mesh: THREE.Mesh;                       // a plane in world units (w/h px ÷ 1000), rounded corners via alpha
  constructor(spec: PanelSpec, pxScale?: number);
  draw(t: number): void;                  // repaint: lines typed in by `at`/`cps`, cursor blink on frameIdx
  revealed(t: number): number[];          // chars shown per line at t (pure)
  dispose(): void;
}
```

**Style (the brand):**
- **Surface and edges:** panel `#1e181c` with a 1 px `#3e323b` edge; a title bar with three muted dots; 16 px radius.
- **Code fonts:** JetBrains Mono 400; bold 500 for `kw`.
- **Colours, monochrome with hierarchy:** `id` bone 0.88, `kw` bone 1.0, `str` boneDim, `num` bone 0.95, `com`
  boneFaint in italic, `punc` boneFaint.
- **Semantic colours:** `prompt` (`$`) bloodBright; `ok` (✔, drawn as a path) moss.
- **Diff gutters:** `add` lines have a moss `+` and a 6% moss wash; `del` lines have a blood `−`, a 6% blood wash and
  a strikethrough.
- **Canvas density:** 2× the canvas resolution for 4K.

**Tests (bun):**
- `tokenize("const memory = new Gitloom()  // reads GITLOOM_API_KEY", 'ts')` → `const` and `new` are `kw`, and the
  `//…` tail is `com`;
- a bash line starting `$ ` gets a `prompt` token;
- `revealed(t)` counts characters per line by `at`/`cps`, is monotonic in t, and is capped at the line length.

**Visual acceptance:** `_paneltest.ts` shows the §11.1 Claude Code command typing into a terminal and the §11.5 diff in
an editor, both tilted in 3D on the Stage.
- Read `stills --module _paneltest --t 2`:
  - the text is crisp at 1080p;
  - the diff colours are semantic;
  - the corners are rounded and free of aliasing;
  - nothing from outside the palette appears.
- Every snippet shown must pass Task 9's facts check.

**Commit:** `2.5D UI panels and a restrained syntax highlighter`.

---

### Task 6: The thread in 3D

**Files:** Create `app/src/engine/thread3d.ts`, `app/src/engine/thread3d.test.ts`, `app/src/scenes/_threadtest.ts` (harness)

**Interfaces:**
```ts
export interface ThreadOpts { radius: number; plies?: 1 | 2 | 3; twist?: number; colors?: ('bone' | 'blood' | 'moss')[]; glow?: number; radialSegments?: number; tubularSegments?: number }
export class Thread {
  mesh: THREE.Mesh;
  constructor(points: THREE.Vector3[], opts: ThreadOpts);   // CatmullRom through points
  setPoints(points: THREE.Vector3[]): void;
  setDraw(p0: number, p1: number): void;                     // visible arc-length fraction window (draw-on / retract)
  setFray(at: number, amount: number): void;                 // plies separate and fibres lift around `at` (0..1)
  length(): number;
  dispose(): void;
}
```

**Look:**
- Plies are twisted bands carried in the shader, as v + u·twist bands with per-ply colour.
- The fibre surface has anisotropic-ish sheen and a fresnel rim.
- Blood and moss plies carry an emissive core scaled by `glow`, so they halate. Bone never glows.
- The look must match the Blender thread (Task 8/11) closely enough to intercut. Plan 3 compares them side by side,
  and Task 11 sets the reference.

**Tests (bun):**
- `length()` is within 1% of the CatmullRom arc length;
- `setDraw(0, 0.5)` shows half the arc length (via the shader uniform range);
- `setPoints` keeps a stable ply phase for the same points.

**Visual acceptance:** `_threadtest.ts` shows a 3-ply bone/blood/moss thread on a gentle S-curve, lit by the Stage with
DoF, drawing on from 0 to 1 over 2 s.
- Read stills at 0.5 s and 2 s: the plies are readable, blood and moss glow softly, and the bone stays matte-satin.

**Commit:** `The thread in 3D: twisted plies, sheen and a glowing diff core`.

---

### Task 7: Beat-locked motion helpers

**Files:** Create `app/src/engine/motion.ts`, `app/src/engine/motion.test.ts`

**Interfaces** (compose the existing `util.ts` helpers; don't duplicate `ease`, `springStep`, `prog` or `pulse`):
```ts
export function spring(t: number, freq?: number, damping?: number): number;          // 0 at t≤0 → 1, tight overshoot
export function slam(t: number, hit: number, o?: { lead?: number; freq?: number; damping?: number }): number; // 0 before hit−lead
export function remap(tLocal: number, keys: [t: number, speed: number][]): number;  // speed-ramp time remap (∫speed)
export function whip(t: number, cut: number, dur?: number): { k: number; blurPx: number }; // around a cut
export function wordTimes(vo: VO, scene: string): { w: Word; at: number }[];      // spoken onsets for a scene
export function onBeat(f: Frame, halfLife?: number): number;                        // decaying pulse on each beat
export function onDownbeat(f: Frame, halfLife?: number): number;
```

**Tests (bun):**
- `spring(0) = 0`; `spring(2) ≈ 1` (±0.001); the peak overshoot is ≤ 12% at damping 0.6;
- `slam` is 0 before `hit − lead`;
- `remap` is monotonic and continuous: the speed-1 identity segment maps 1:1, and a 0.25 segment advances at a quarter;
- `wordTimes` returns the scene's words in order, with `at == word.start`.

**Commit:** `Beat-locked motion helpers: slams, springs, ramps, whips`.

---

### Task 8: The Blender pipeline, plates and tracks

**Files:**
- Create:
  - `blender/lib/{__init__,setup,timing,materials,thread,lights,export}.py`
  - `blender/render.py`
  - `blender/shots/_cube.py` (a test shot)
  - `blender/tests/test_timing.py` (pure Python, run with `uv run --project tools pytest blender/tests`)
  - `app/src/engine/plates.ts`, `app/src/engine/track.ts`, `app/src/engine/plates.test.ts`, `app/src/scenes/_platetest.ts`
- Modify: `app/vite.config.ts` (serve `out/plates`), `app/src/engine/scene.ts` and `engine.ts` (an optional async
  `prepare(t)`), `app/src/main.ts` (await `prepare` before `still`/`stream` frames)

**Blender side:**
- **`setup.new_scene(res, fps=30, engine='CYCLES', samples, denoise=True, motion_blur=0.5, view='AgX')`:** selects the
  Metal GPU and turns off the unused default objects.
- **`timing` (bpy-free):**
  - `load()` reads `data/vo.json` and `data/audio.json`;
  - `frame(t) = round(t * 30)`;
  - `scene_frames(scene_id) -> (f0, f1)`;
  - `word(line_id, i).start`, `beats_in(f0, f1)`, `downbeats_in(f0, f1)`.
- **`materials.fiber(color, sheen, emissive=0)`** and **`materials.satin(color)`**: palette colours converted to
  linear.
- **`thread.ply_thread(points, radius, plies=3, twist, fuzz=True)`:** twisted plies as curve objects with a bevel, plus
  fibre fuzz through Geometry Nodes or hair curves. **`lights.studio(key, rim, fill, world)`.**
- **`export`:**
  - EXR half-float RGBA to `out/plates/<shot>/####.exr`, plus 8-bit PNG proxies at half resolution in
    `app/public/plates/<shot>/proxy/####.png` (gitignored);
  - `track(names, cam, f0, f1)` writes `data/track/<shot>.json` as
    `{ "fps": 30, "f0": …, "anchors": { name: [[x, y, visible], …] } }` in 1920×1080 logical px, via
    `world_to_camera_view`.
- **CLI:** `blender -b -P blender/render.py -- --shot <name> --mode look|preview|final [--frames a-b] [--res WxH]`.

  | mode | resolution | samples | frames | output |
  |---|---|---|---|---|
  | look | 960×540 | 32 | the chosen frames | PNG |
  | preview | 960×540 | 16 (or EEVEE) | all frames | proxies |
  | final | 2560×1440 (or `--res`) | 128 | all frames | EXR |

  `render.py` imports `blender/shots/<shot>.py`, which defines `SHOT = {"scene": "<id>", "frames": "scene"}` and
  `build(ctx)`.

**Engine side:**
- **`Plate`:**
  - `new Plate(shot, f0)`
  - `async prepare(t)` loads frame `round(t * 30) - f0`: the EXR (via `EXRLoader`, half float) in export, and the PNG
    proxy in preview. It keeps an LRU of ≤ 8 textures.
  - `texture(t)` returns the prepared frame, or the nearest loaded one in preview.
- **`Track`:** `await Track.load(shot)`, then `at(name, t) -> { x, y, visible }` in logical px, linearly interpolated.
- **`Scene.prepare?(t): Promise<void>`:** the engine awaits it for every active scene before `still()` and before each
  streamed frame. The player calls it best-effort.

**Tests:**
- **Python:** `frame(1.0) == 30`; `scene_frames` equals `vo.json`'s scene windows × 30, rounded; `downbeats_in` is
  correct.
- **Bun:** a plate's frame index for `t` (rounding at half frames), LRU eviction order, and `Track.at` interpolation.

**Integration (Review Focus 4):**
- `_cube.py` renders 20 look frames of a lit cube with an empty on its top-right corner.
- `_platetest.ts` shows the plate and draws a 6 px blood dot at `track.at('corner', t)`.
- Read two stills: the dot sits on the corner within 2 px, and plate frame *n* matches film frame *n* (burn the frame
  number into the Blender render with a text object to prove it).

**Commit:** `The Blender pipeline: shared library, render CLI, plates and tracks the engine composites`.

---

### Task 9: The facts gate

**Files:** Create `data/facts.json`, `tools/gitloom_film/factcheck.py`, `tools/tests/test_factcheck.py`; add
`film-facts` to `tools/pyproject.toml`.

**`data/facts.json`:** `{ "verbatim": [ {text, source} ], "copy": [ {text, source} ], "illustrative": [ {text} ] }`.
- **verbatim:** every snippet, path, hash, number and quote in spec §11.1–11.9, with its source file:line.
- **copy:** every on-screen label written into spec §4's scene treatments (for example `− no history`,
  `vectors.bin · 1536 dims · 0 commits`, `visited 50 of 10,000`, `index is a pure cache · gitloom rebuild`).
- **illustrative:** §11.10.

**Scenes declare their strings** in `app/src/scenes/<id>.strings.json` (a string array). Scene code **imports** that
JSON for its text, so no string is duplicated.

**`film-facts`:** loads every `*.strings.json`. A string passes if it:
1. equals a `verbatim` or `copy` entry, or is a substring of one;
2. is illustrative;
3. is her voiceover text (any `vo.json` line text or word, as displayed); or
4. is a scene/act label from `data/script.json`.

Anything else is printed with its file, and the exit code is 1.

**Tests:**
- a known snippet passes;
- a substring of a verbatim snippet passes;
- a made-up `gitloom log --blame` fails (spec §11.7 names it as not-real);
- a VO word passes;
- the exit code is 1 on any failure.

**Commit:** `The facts gate: every on-screen string is verbatim, approved copy, illustrative or her words`.

---
## Part B: the look test (Tasks 10–12, then C4a)

Three hero moments prove the look before it's scaled to fifteen scenes.

**Every creative task follows this template:**
- **Files:** its scene module (`app/src/scenes/<id>.ts`, plus `<id>-*.ts` helpers and `<id>.strings.json`) and, where
  named, its Blender shot. Touch nothing else. Engine changes are requests to the controller in your report.
- **Times:** all times come from the data. Use `wordTimes(ctx.vo, '<id>')`, `ctx.vo.get('…')`, and the beats and
  downbeats in the window. Never hard-code seconds.
- **Acceptance:**
  1. `bun test src` and `bun run typecheck` are green.
  2. `film-facts` passes.
  3. `render.ts perf --only <id>` is ≤ 120 ms/frame at 1080p preview.
  4. Stills at the task's key moments go to `out/style/<id>/`. The implementer **Reads every still**, fixes what
     breaks the Global Constraints or the direction, and re-renders.
  5. A motion clip of the scene window, 1080p with adaptive motion blur:
     `render.ts video --only <id> --from <start> --to <end> --samples auto --out ../out/style/<id>/<id>.mp4`.
  6. The report lists each key-moment still with one line on what it shows.
- **Commit:** only the task's files, with a one-line subject naming the scene.

### Task 10: `her`: the headline slam (engine), the look test's typographic hero

**Window:** scene `her`. **Lines:** L06 "Not me.", L07 "Every memory… a commit.", L08 "Every fact… a blame."

**Uses:** Stage, Type3D, Thread, motion helpers, Panel (for the blame gutter's mono strip), `look.ts`.

**Direction** (spec §4 scene 03, in motion language v2):
- **Cut in, black.** A single diff thread whips in from frame left: a bone core with blood and moss plies, the moss
  and blood cores glowing. It pulls taut across the frame in 3D. The camera rides along it in a slow push with
  shallow DoF.
- **On "Not".** The thread snaps taut with a specular sweep running along it.
- **The downbeat after "me."** The score opens here, and the camera **whips** onto a glass commit bead threading onto
  the thread. The bead is a physical satin-glass sphere with `3f9a1c2` engraved, catching the rim light.
- **L07.** The site's headline lives in 3D space: `− your agent forgets` sits small and struck through in blood, then
  `+ every memory has a commit` types in sync with her.
  - **"memory"** and **"commit"** are extruded Type3D words that **slam** in from depth on their onsets. "commit" is
    satin bone with a moss diff-glow edge.
  - The `+` gutter is moss.
  - "has a" appear flat and quiet.
- **L08.** `+ every fact has a blame` stacks under it, with the same treatment and **"blame"** in moss. On "blame" a
  blame gutter slides in at left: mono `3f9a1c2 (you 2026-07-26)`.
- **Camera through L07–L08.** A slow orbit of about 12° around the 3D type, holding focus on the hero word as each
  lands (rack focus).
- **The exit.** The whole headline drifts back and out of focus.

**Key moments for stills:**
1. the whip onto the bead (downbeat + 0.15 s);
2. "commit" onset + 0.3 s;
3. "blame" onset + 0.3 s.

**The bar to beat:** frame 2 should look like the hero frame of a premium launch film, with type you want to touch.

### Task 11: `thread`: the macro snap (Blender B01 plus the engine overlay)

**Window:** scene `thread`, 0 → the `ex` cut. **Lines:** L01 "Your agent forgets.", L02 "Every conversation… back to
zero."

**Blender** (`blender/shots/b01_thread.py`, using `blender/lib`):
- **The macro.** One bone thread (3 plies with fibre fuzz) spans the frame on a shallow diagonal.
  - Lens: 85 mm equivalent, f/1.8.
  - Lighting: a dark world, a warm-neutral key from upper left, and a hard rim that sculpts the plies.
  - Background: pure ink, with no set.
- **The pulse.** The thread vibrates subtly on the **beats** (`timing.beats_in`), like a plucked string: a heartbeat.
- **"forgets".** The fuzz lifts and the plies loosen at the centre: the fray.
- **"zero".** The **snap.** The thread breaks at the fray and the two ends recoil.
  - This runs as a **speed ramp**: 0.25× for about 1.0 s of film time, then back to 1× on the next beat.
  - The thread's own freed fibres drift and tumble through the key light, a few hundred hair strands. These are not
    generic particles.
- **Output.** Look frames at the key moments first (960×540). Then a `preview` of the whole window to the PNG proxies,
  plus `track` anchors for the two break ends.

**Engine** (`app/src/scenes/thread.ts`): composite the plate, then set the type.
- **L01.** Lower-left third, in flat Bricolage. On "forgets" its tracking loosens and the letters drift apart as she
  says it.
- **L02.** "back to" sits flat, right of centre. **"zero."** is Type3D bone that **cracks and splits in two** at the
  snap frame, riding the recoil: the word snaps with the thread.

**Key moments:**
1. the taut thread, 1.0 s;
2. "forgets" onset + 0.3 s;
3. the snap frame + 0.25 s (slow motion).

### Task 12: `weave`: the woven mark (Blender B15 plus the engine overlay)

**Window:** scene `weave`, to the end. **Lines:** L30 "GitLoom.", L31 "I don't forget.", L32 "I commit."

**The mark** (`blender/mark/`):
1. **Trace the mark** from `~/Developer/code/gitloom/web/public/gitloom.png`, cropping the mark region (about 420 px
   wide), with `mark.png` as a second reference.
2. **Build parametric ribbon paths:**
   - a bone "G" arc and stem;
   - a blood crossbar and vertical;
   - a moss horizontal and loop.

   The ribbons are flat extruded bands with softly rounded edges, with real **over/under** offsets where they cross,
   as in the PNG.
3. **Validate:** an orthographic front render of the silhouette against the thresholded `mark.png` silhouette must
   reach **IoU ≥ 0.90**. A script prints the IoU.
4. **Materials:** satin bone, satin blood and satin moss. Blood and moss get a faint emissive core so they halate in
   the engine's post.

**Animation** (`blender/shots/b15_weave.py`):
- The film's threads (bone, blood and moss) converge out of the dark in long arcs and **weave** over and under into the
  mark.
- The last crossing **locks** on the scene's first downbeat, with a 0.5× speed ramp around the lock.
- Then: a slow push-in, a raking light sweep across the satin, and a slight rotation settling to the front view.

**Engine** (`app/src/scenes/weave.ts`):
- composite the plate;
- **L30:** the mark completes, with no type;
- **L31:** flat Bricolage "I don't forget." beside the mark;
- **L32:** "I commit." with **"commit"** as a Type3D moss-edged slam, a callback to the headline;
- **the wordmark:** mono `gitloom 3f9a1c2` types in as a git log entry, the site's nav wordmark;
- **below it:** `gitloom.cloud` and `start free — no card`;
- **the hold:** the final frame is clean and poster-worthy.

**Key moments:**
1. mid-weave (L30 onset);
2. the lock + 0.3 s;
3. the final frame (the end − 0.5 s).

### Checkpoint C4a: the look test (stop and ask the user)

1. Build `out/style/looktest.html`, a local page with the nine stills and the three clips.
2. Open it for the user.
3. Ask one question: does this look premium and kick-ass enough, and what should change?
4. Apply their notes to Tasks 10–12 as fix rounds.
5. Rule on whether B03 (the Blender re-form for `her`, Task 25) is needed, or whether the engine thread in Task 10 is
   enough.

**Do not start Part C until the user approves the look.**

---
## Part C: style frames for the other twelve scenes (Tasks 13–25, then C4)

Each scene follows the creative-task template from Part B and applies the look the user approved at C4a.
- **Parallelism:** at most **two** scene tasks run in parallel, and they touch disjoint files. Each commits only its
  own files; if git reports `index.lock`, wait 2 s and retry.
- **Blender:** shots render one at a time.
- **Times:** always from the data.

### Task 13: `ex`, the ex (engine)
- **The float cloud.** About 6,000 mono numerals (`0.2143`, `−0.0931`, …) as instanced glyph quads in a jittered
  spherical **lattice**: orderly, not a nebula. The camera orbits slowly with DoF, so the near numerals are soft.
- **L03.** "It's not you…" in flat Bricolage; "vector store" in mono; and the label `vectors.bin · 1536 dims · 0 commits`.
- **L04.** The card `Maya lives in Berlin.` flies into the cloud, its letters **morphing into numerals**. Then
  `Maya moved to Lisbon in March 2026.` arrives, and that region **split-flaps** to new values, the flips landing on
  the beats.
  - A ghost `berlin?` query returns nothing.
  - On "why", a `why?` ping returns only the tooltip `cosine 0.8127`.
  - The blood tags `− no history`, `− no provenance` and `− one flat bag` **stamp** on successive beats.
- **L05, "Commitment issues."** The whole cloud **collapses**, every numeral falling into one line, and resolves into
  a terminal: `$ git log` → `fatal: your current branch 'main' does not have any commits yet`, with "commits" in blood.
  The beat is deadpan.
- **Key moments:** the cloud with "vector store"; the overwrite flip; the fatal line.

### Task 14: `repo` (engine)
- **L09.** A tilted 3D terminal Panel types `cd ~/memory && ls` in sync with her. `facts/  incidents/  rules/  skills/`
  pops out as four chips.
- **L10.** `git log --oneline` scrolls as **glass beads on a thread** (Thread plus instanced beads, each labelled with
  its hash and message from spec §4). The camera tracks along the string.
- **Then.** The editor Panel of `facts/people/user.md` (§11.4, with line numbers) swings in, over the footnote
  *Nothing about that is a metaphor — you can cd into it.*
- **Key moments:** the `ls` chips; the bead string; the file.

### Task 15: `loom` (Blender B05 plus engine labels)
- **The loom** (Blender):
  - a low angle on four warp bundles stretching into depth;
  - a shuttle carrying the diff thread flies across **on every beat**, weaving a weft row, and the fabric grows toward
    camera;
  - an **incidents** section frays and dissolves, a **rules** warp pulls tight, and a **skills** warp stays dim until
    the shuttle reaches it, then lights.
- **Labels:** the engine sets them on the tracked anchors: `facts/ · long-term`, `incidents/ · ttl 30d`,
  `rules/ · loaded whole`, `skills/ · lazy`. The stamp `gc: expire 3 incidents` lands on "let go".
- **L11–L14:** flat type, with each tier's word lighting as she says it.
- **Key moments:** "Facts I keep"; the incidents fray; the skills warp lighting.

### Task 16: `diff` (engine)
- **The editor Panel in close 3D.** The cursor lands on `Uses VS Code.`, which strikes through in blood with a `−`.
  `+ Uses neovim. Has since 2019.` types in moss, and `confidence: 0.6` becomes `0.9`.
- **Then.** `gitloom diff facts/people/user.md 8b21e04 3f9a1c2` → `1 file changed, 2 insertions(+), 2 deletions(-)`.
- **The commit-history scrubber** slides in underneath. Its playhead scrubs **back**, and the old version returns
  (time travel, with a speed ramp), then forward again.
- **L17, "We'll always have the diff."** A slow, romantic push-in, the old line still glowing faintly in blood.
- **Key moments:** the strike; the scrub back; the push-in.

### Task 17: `cite` (engine)
- **The chat Panel.** `what editor do I use?` gets the answer `neovim.`, and a `why?` chip is clicked on "why".
- **The stitch.** On "the line", the **thread becomes a needle** (Thread plus a needle mesh) and stitches from the
  answer down into the editor Panel. Lines 11–14 highlight.
- **Labels:** the citation `facts/people/user.md#editor · L11–14 · 3f9a1c2` and the blame gutter `3f9a1c2 · 2026-07-26`.
- **Key moments:** the question; the needle mid-stitch; the highlighted lines.

### Task 18: `braid` (Blender B08 plus engine labels and card)
- **The braid** (Blender): three threads race in from left, top and right and **braid** into one rope that pulls taut
  toward camera. Side threads branch off to neighbouring beads.
- **Labels:** the engine sets them on the tracked anchors, lit in the order she names them: `lexical · your words`,
  `body · what you meant`, `cues · how you'd ask`.
- **The result card.** The rope lands on an engine Panel card holding the §11.6 fields verbatim, with the footnote
  *Ranked memories, no model call. Milliseconds.*
- **Key moments:** the threads apart; the braid; the card.

### Task 19: `merkle` (engine 3D)
- **The tree.** A vast hairline Merkle tree of 10,000 leaves (instanced lines and points), seen from a crane.
- **"changed".** 50 leaves pulse moss, and their ancestor paths light up.
- **"only look at fifty".** Every unchanged subtree **folds shut** and darkens with an `= hash · skipped` stamp. The
  camera **dives** along one lit path.
- **Labels:** the counter `visited 50 of 10,000` and the footnote `index is a pure cache · gitloom rebuild`.
- **Key moments:** the whole tree; the 50 lit; the dive.

### Task 20: `graph` (engine)
- **The wikilink.** `Works with [[facts/orgs/acme.md]].`: the link **lifts off as a thread** and draws an edge to the
  `acme.md` node.
- **The heal.** A dashed blood edge to `[[facts/trips/lisbon-2026.md]]` dangles, then **heals** to moss when its target
  appears.
- **The walk.** Three hops light up: trip → hotel → city.
- **The vocabulary.** `$ gitloom vocab add --term kubernetes --alias k8s` → `k8s → kubernetes  ·  search finds either form`,
  and a `k8s` search highlights a memory that says "kubernetes".
- **Key moments:** the edge draw; the heal; the vocab result.

### Task 21: `honest` (engine)
- **Restraint** is this scene's premium.
- **The question.** Near-black; `what's my sister's name?` types out.
- **L22.** Three thin threads reach into the dark, searching. A hairline marks the evidence floor, and the thread tips
  hover **under** it.
- **The silence.** In slow motion the threads go slack and fall.
- **L23.** A small response Panel: `"memories": []`, `"candidates": 2`, `"filtered_out": 2`. Then quiet, centred, flat
  bone type, *I don't know.*, with the verbatim footnote.
- **Key moments:** the searching threads; them falling; "I don't know."

### Task 22: `proof` (engine)
- **The slam.** It lands on the score's slam.
- **The odometer.** A huge Bricolage odometer of Type3D digit **drums** rolls one round per beat:
  44 → 72 → 80 → 83 → **91.4%**, with round labels and a climbing sparkline.
- **The landing.** 91.4 lands in moss with a light sweep. The per-category bars flash, and the footnotes read
  `LongMemEval · oracle split · 456/499` and *Every round was diagnosed from the previous round's failures.*
- **L25.** The `%` settles last with a tiny smirk-bounce.
- **Key moments:** mid-roll; 91.4 landing; the bars.

### Task 23: `connect` (engine)
- **The command.** A full-frame 3D terminal Panel types the §11.1 command in sync with her.
- **The check.** `claude mcp list` → `gitloom: npx -y @gitloomhq/mcp - ✔ Connected`, with the ✔ drawn as a moss path.
- **L27.** Cards flip in a 3D carousel, **one per beat**: the MCP JSON, `gitloom install codex --write` with its hosts,
  then the TypeScript, Python, Go and Rust snippets (§11.2–11.3).
- **Key moments:** the command; ✔ Connected; the carousel mid-flip.

### Task 24: `anywhere` (engine)
- **A split composition.**
- **The left side.** The install one-liner and the chips
  `one static binary · no CGo · arm64 + amd64 · licence verified offline`.
- **The right side.** Recreated console panels:
  - a Playground chat with the `gitloom_retrieve` (moss) and `gitloom_remember` (blood) chips;
  - the Memory Graph force layout **settling** into tier regions;
  - Namespaces multiplying `user-0001 … user-2048`, with the label
    *one per end user · a storage boundary, not a WHERE clause*.
- **The footnote:** `free plan · no card · storage is free`.
- **Key moments:** the split; the graph settling; the namespaces multiplying.

### Task 25: `her` re-form (Blender B03). Conditional: the C4a ruling decides
- Build it only if C4a rules that the engine thread can't carry the re-form macro.
- **The shot:** the two frayed ends drawn back together, with blood and moss plies twisting around the bone core,
  composited into `her`'s opening beat.
- **Key moment:** the ends meeting.

### Task 26: The contact sheet and style reel, then checkpoint C4
1. Render one hero still per scene (15), at the key moment each task's report named, into `out/style/sheet/`.
2. Build a 5×3 contact sheet PNG.
3. Concatenate the fifteen motion clips in film order into `out/style/style-reel.mp4`, with the real mix under it,
   placed at each clip's film time.
4. Build `out/style/c4.html` and open it for the user.

**CHECKPOINT C4 (stop and ask):** does this lock the look? Apply the notes as fix rounds. Plan 2 is done when the user
locks the look.

## After Plan 2

Plan 3 (full build) is written after C4. It covers:
- full animation of every scene between its key moments;
- the transitions (whips, zoom-throughs, match cuts along the thread);
- the SFX cue sheet and generation;
- the voiceover processing chain and final mix;
- the sung-hook A/B (inpainting from `chosen_plan`);
- the rough cut (C5).
