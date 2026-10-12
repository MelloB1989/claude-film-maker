# CampX Digital Evaluation × Medha AI: launch film brief

Repo: `~/code/claude-film-maker`, branch `campx-launch`. Film folder: `films/campx-launch/`.
Read `README.md`, `docs/CONVENTIONS.md`, `docs/KIT.md` and (for Blender) `docs/PIPELINE-BLENDER.md` first. The
engine and kits were built for the GitLoom film (branch `gitloom-film`, a finished premium launch film); reuse its ideas freely.

Deadline: the final master by 2026-10-14 03:30 UTC. Every task has a hard time box, so ship on time over perfect.

## The film
- 90 s, landscape 1920×1080, 30 fps. Hero launch film for college principals, deans, controllers of examination and faculty.
- Tone: Apple keynote meets an academic institution. Calm, confident, precise. No hype words. Premium means restraint,
  slow camera, generous negative space, perfect type and sound.
- Message: CampX's new evaluation service ingests scanned answer scripts, transcribes the handwriting, and Medha AI
  **suggests** marks point by point against the answer key. **Faculty stay in control**: accept, adjust or override;
  doubtful answers are flagged for review.
- Real material only: real scanned answer sheets (`assets/sheets/`) and real UI screenshots (`assets/ui/`, landing
  within about 1 h, described in `assets/ui/INDEX.md`). Showing them as-is is approved.
- Never invent numbers or claims (no "10x faster", no accuracy %). Text on screen comes from the VO below or from
  the real UI.

## Look
- Theme `campx` (in film.json): ink background, warm-white paper/fg, magenta `accent`, coral `accent2`, deep indigo in
  the bg/surface tints. Use roles, never hexes.
- Brand gradient as light (glows, rims, sweeps): indigo → magenta → coral. Paper stays warm white.
- Type: the engine's display face for statements; a serif italic for one or two emotional words (e.g. *future*).
- Motion: slow dollies, parallax, rack focus, light sweeps, match cuts on paper. Whips and zooms only at act changes.
  Nothing that looks like a template.

## Timeline (scene ids are the contract between everyone)
| scene id | film time | len | what | owner |
|---|---|---|---|---|
| `open` | 0:00–0:09 | 9.0 s | Blender plate A: a cathedral of answer scripts in the dark; one page rises into the light | blender-A |
| `stakes` | 0:09–0:15 | 6.0 s | macro handwriting (real page), type: "a student's *future*." | lead |
| `title` | 0:15–0:21 | 6.0 s | "CampX Digital Evaluation" + "Powered by Medha AI" reveal | lead |
| `ingest3d` | 0:21–0:29 | 8.0 s | Blender plate B: booklets pass a scan gate, the cover dissolves (identity removed), pages fan into a grid | blender-B |
| `ingestui` | 0:29–0:35 | 6.0 s | real admin ingestion UI in a floating frame, callouts: Split · Anonymised · Tamper-checked | product |
| `read3d` | 0:35–0:42 | 7.0 s | Blender plate C1: a scan line reads a real page; typeset lines lift off the paper | blender-C1 |
| `readui` | 0:42–0:49 | 7.0 s | real page ↔ transcription, answer regions mapped to questions | product |
| `mark3d` | 0:49–0:55 | 6.0 s | Blender plate C2: transcribed answer threads to answer-key points that light up | blender-C2 |
| `markui` | 0:55–1:02 | 7.0 s | real key-point breakdown UI, suggested mark | product |
| `control` | 1:02–1:18 | 16.0 s | the real evaluator UI hero: script + Medha's suggestions side by side; accept / adjust / override; a "flagged for review" chip | product |
| `outcome` | 1:18–1:25 | 7.0 s | "Faster results. Consistent marking. Complete control." | lead |
| `end` | 1:25–1:30 | 5.0 s | the CampX logo (`assets/brand/campx-logo.svg`), "Medha AI · Evaluate smarter. Decide faster.", `campx.in` | lead |

## Voiceover (Indian English, female, warm and assured)
Placed by the audio pipeline into the windows above (`data/vo.json` is the truth once it lands).
1. open: "Every semester, thousands of answer scripts. Millions of handwritten pages."
2. stakes: "And behind every page, a student's future."
3. title: "Introducing CampX Digital Evaluation. Powered by Medha AI."
4. ingest3d + ingestui: "Upload one ZIP of scanned scripts. CampX splits every booklet, reads its cover, removes the student's identity, and checks each script for tampering, before an evaluator ever sees it."
5. read3d + readui: "Then Medha reads. Every line of handwriting is transcribed, corrected, and mapped to the right question, even when an answer runs across pages."
6. mark3d + markui: "Each answer is checked against your answer key, point by point. Medha suggests a mark, and shows exactly why."
7. control: "But the final word belongs to your faculty. Evaluators see the script and Medha's suggestions side by side. Accept, adjust, or override, in seconds. Anything uncertain is flagged for a closer look."
8. outcome: "Faster results. Consistent marking. Complete control."
9. end: "CampX. Evaluate smarter. Decide faster."

## Ownership (one writer per file; no one else edits it)
- lead: `film.json`, `film.ts`, `scenes/` except `scenes/product/`, `data/timeline.json`, `data/look/`.
- product: `scenes/product/**`.
- blender-X: `blender/shots/<x>.py` only (`open.py`, `ingest3d.py`, `read3d.py`, `mark3d.py`).
- manager (me): `assets/`, `data/script.json`, the audio pipeline (`audio/`, `data/vo.json`, `data/audio.json`), final renders.
Do not git commit or push; the manager reviews and commits. Do not touch secrets or paid APIs (ElevenLabs).

## Assets
- `assets/sheets/giet_<booklet>_pNN.jpg`: 150 dpi pages (1167×1754). `hires_<booklet>_pNN.jpg`: 300 dpi
  (hires_38189_p01..p04 are booklet 38189's pages 2–5, which are dense and beautiful: a row-reduction answer with matrices).
- `assets/brand/campx-logo.svg` (dark wordmark) and `campx-logo-white.svg` (white wordmark for a dark background).
- `assets/ui/`: real UI captures with `INDEX.md`.

## Rendering hosts
- Engine stills and previews: `cd app && bun scripts/render.ts stills --film campx-launch --t ... --allow-software`
  (no GPU in agent containers; software WebGL is fine for drafts).
- Blender: render `look` and `preview` locally on CPU (`--allow-cpu` if asked). The finals run on the manager's
  16-vCPU CPU VM at 1920×1080, so design for **≤ 8 s per frame there at ≤ 48 samples**.

## Engine changes
Improving the engine or kits (`app/src/**`, `blender/lib/**`, `tools/**`) is allowed when a scene needs it. Keep changes
additive and generic: no film names in the engine, and don't change the defaults other films rely on. `cd app && bun test src && bun run typecheck`
must pass. List every engine file you changed in your report.

## Blender frame windows (film frames, half-open, 30 fps)
open [0, 270) · ingest3d [630, 870) · read3d [1050, 1260) · mark3d [1470, 1650). Use explicit `"frames"` in `SHOT`
until `data/timeline.json` exists.
