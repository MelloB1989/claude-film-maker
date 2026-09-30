# GitLoom launch film: *I Don't Forget. I Commit.* (design spec)

- **Date:** 2026-09-30
- **Status:** design approved in conversation (sections 1–5), awaiting review of this written spec
- **Repo:** `~/Developer/code/gitloom-film`

## 0. Summary

A ~90-second, 16:9 launch film for GitLoom, mastered at 3840×2160 and 30 fps.

- **How it's made:** rendered from code. The base is a fork of the MIT-licensed
  [PDoom-Video](https://github.com/mexicat/PDoom-Video) engine: three.js and GLSL, deterministic, with adaptive
  motion blur and a filmic finishing pass. Hero 3D shots are rendered in Blender Cycles.
- **Who speaks:** GitLoom's memory is the narrator, an alluring and witty femme fatale. She is voiced by the ElevenLabs
  library voice *Jean* on Eleven v4, and talks to the developer about their agent's memory the way one talks about an ex.
- **The motif:** one luminous thread (a bone core with a blood-red `−` strand and a moss-green `+` strand) runs through
  every scene and ends by weaving the 3D GitLoom mark.
- **The type:** every spoken word appears as kinetic type built into the scene, synced per word.
- **The edit:** every cut lands on the beat of a score composed to the edit (ElevenLabs Music v2.5).
- **Accuracy:** every command, snippet and number on screen is verbatim from GitLoom's public docs and site (§11).

## 1. Decisions (from brainstorming)

| # | Decision | Choice |
|---|---|---|
| D1 | Placement | ~90 s launch film, 16:9: landing page, YouTube, X, LinkedIn |
| D2 | Tone | Flirty and witty; git words double as relationship words; never explicit |
| D3 | Soundtrack | Instrumental score plus voiceover; an A/B version where the ending is sung |
| D4 | Voice | ElevenLabs library voice "Jean – Alluring and Playful Femme Fatale" (`eVItLK1UvXctxuaRV2Oq`) on `eleven_v4`, pace tightened (§5.1) |
| D5 | Build | Fork of the PDoom-Video engine, plus Blender Cycles for the hero 3D shots |
| D6 | Benchmark | Include LongMemEval 44% → 91.4%, labelled exactly as the site does (oracle split, 456/499). The founder's earlier launch-copy decision (commit `eb855d0`) and the 91.4% provenance gap were flagged; the user chose to include it |
| D7 | Logo | Rebuild the woven mark as clean 3D geometry traced from `web/public/mark.png` (no vector source exists) |
| D8 | Format | 3840×2160 at 30 fps. Engine at native 4K; Blender plates at 2560×1440, upscaled; the logo finale at native 4K |
| D9 | Repo | `~/Developer/code/gitloom-film`, its own git repo |
| D10 | Scope | The 16:9 film plus the deliverables in §10. The vertical cut and the interactive web version are follow-ups |

## 2. Audience, goals, acceptance criteria

**Audience:** developers and technical founders building AI agents, the gitloom.cloud audience.

**Goals:**
1. Viewers remember the line *"I don't forget. I commit."*
2. They understand what GitLoom is (git-backed memory for agents) and why it's different: provenance, diffs, and
   honesty (it abstains rather than guessing).
3. They go to gitloom.cloud and start free.

**Acceptance criteria:**
- Duration 85–95 s; 16:9; 3840×2160; 30 fps; H.264 (BT.709-tagged) plus a ProRes 422 HQ master.
- **Word sync:** each voiceover word becomes visible (or starts its highlight) within ±1 frame (33 ms) of its spoken
  onset. The one allowed exception is showing a line early, dimmed, up to 0.4 s ahead; highlighting never runs ahead
  of the voice.
- **Cut sync:** every hard cut lands on a beat of the score, within ±1 frame. Act changes land on downbeats.
- **Loudness:** −14 LUFS integrated (±0.5), true peak ≤ −1.0 dBTP.
- **Facts:** every on-screen command, snippet, path, hash and number matches §11. Illustrative values are marked there
  as illustrative, and they match the real response shape.
- **Craft:** zero typos. Display type uses typographic punctuation (’ “ ” … – — × −); typed input keeps typewriter quotes.
- The user approves each checkpoint in §9.

## 3. Concept and story

**Premise:**
- GitLoom's memory is a character: alluring, playful, unflappably precise.
- She talks to the developer about their agent the way a femme fatale talks about an ex: *"It's not you. It's your
  vector store."* Its old memory had commitment issues; she doesn't.
- Git words double as relationship words throughout: commit, history, blame, diff, "change your mind".

**The contrast is the joke.** Her voice flirts while the picture stays exacting: paths, line ranges, hashes, and real
commands. The sultry side lives in the voice and the slow camera; the wit lives in the snapping type and the deadpan
monospace footnotes.

**The thread (the motif, playing the role PDoom's spark plays).** One luminous thread, with a bone core, a blood-red
`−` strand and a moss-green `+` strand. Through the film it:
- **snaps**, when the agent forgets;
- re-forms and pierces the first **commit bead**;
- strings commits like beads;
- **weaves** the four memory tiers on a loom;
- **stitches** a citation to an exact line, as a needle;
- **braids** the three retrieval arms into one rope;
- **hangs slack** when there is nothing to find;
- finally **weaves the 3D GitLoom mark**.

**The diff (the typographic device).** Anything replaced goes blood-red with a `−` gutter and a strikethrough; its
replacement arrives in moss-green with a `+`. The film states the site's hero headline in motion:
`− your agent forgets / + every memory has a commit / + every fact has a blame`.

**Acts:**

| Act | Name | Window | Beats |
|---|---|---|---|
| I | The Ex | 0:00–0:15 | forgetting; the vector store's commitment issues |
| II | Her | 0:15–0:28 | "I'm just a git repo. You already know how to read me." |
| III | The Tour | 0:28–1:15 | tiers, diff, cite, braid, Merkle, graph and vocabulary, the honesty beat (music out), the proof |
| IV | Everywhere | 1:15–1:25 | Claude Code in one command, MCP and SDKs, binary or cloud, free plan |
| V | The Weave | 1:25–1:33 | every thread becomes the 3D mark; *"GitLoom. I don't forget. I commit."* |

**Guardrails:**
- Flirty, never explicit. No hearts, lips or bedroom imagery.
- None of the reference's banned clichés: no glowing brains, no purple/cyan neon, no Matrix rain, no particle nebulae, no
  stock "AI" imagery, nothing that looks AI-generated.
- No reuse of the site's brain glTF (it's CC-BY-4.0).
- No logos or UIs of third parties. "Claude Code", "OpenAI" and the language names appear only as words and real
  commands. The Claude Code step is a plain terminal, not an imitation of its interface.
- No competitor is named.

## 4. Script v1 and scene treatments

Times are approximate. They get locked to the real voice takes and the beat grid (§8.2). If the cut runs long, lines
are trimmed rather than rushed; trim candidates are marked ✂.

**Voiceover lines** (the text sent to TTS; ellipses shape pauses inside a line, and the edit sets the gaps between lines):

| id | scene | text |
|---|---|---|
| L01 | 01 | Your agent forgets. |
| L02 | 01 | Every conversation... back to zero. |
| L03 | 02 | It's not you... it's your vector store. |
| L04 | 02 | It overwrites what it knew... and never tells you why. |
| L05 | 02 | Commitment issues. |
| L06 | 03 | Not me. |
| L07 | 03 | Every memory... a commit. |
| L08 | 03 | Every fact... a blame. |
| L09 | 04 | I'm just a git repo. |
| L10 | 04 | You already know how to read me. |
| L11 | 05 | Facts I keep. |
| L12 | 05 | Incidents... I let go. |
| L13 | 05 | Rules I never break. |
| L14 | 05 | Skills, only when you need them. ✂ |
| L15 | 06 | Change your mind? |
| L16 | 06 | I'll change mine. |
| L17 | 06 | We'll always have the diff. |
| L18 | 07 | Ask me why I believe something... I'll show you the line. |
| L18b | 07 | Go ahead. Blame me. *(optional tag; only if time allows)* |
| L19 | 08 | Your words. What you meant. How you'd ask... braided into one answer. |
| L20 | 09 | Fifty things changed? I only look at fifty. |
| L21 | 10 | I connect the dots... and I learn your language. ✂ |
| L22 | 11 | And when I don't know... |
| L23 | 11 | ...I say so. |
| L24 | 12 | Forty-four... to ninety-one point four. |
| L25 | 12 | Not bad... for a memory. |
| L26 | 13 | One command... and I'm in Claude Code. |
| L27 | 13 | Or any agent, in any language. ✂ |
| L28 | 14 | On your machine... or in my cloud. |
| L29 | 14 | One memory for every user you have. ✂ |
| L30 | 15 | GitLoom. |
| L31 | 15 | I don't forget. |
| L32 | 15 | I commit. |

That's about 169 words. At Jean's tightened pace it's roughly 75 s of speech, plus about 15 s of music-only moments.

**Scene index:**

| # | id | act | ≈ window | build |
|---|---|---|---|---|
| 01 | `thread` | I | 0:00–0:06 | Blender B01 + engine type |
| 02 | `ex` | I | 0:06–0:15 | engine |
| 03 | `her` | II | 0:15–0:22 | Blender B03 + engine type |
| 04 | `repo` | II | 0:22–0:28 | engine |
| 05 | `loom` | III | 0:28–0:35 | Blender B05 + engine labels (tracked) |
| 06 | `diff` | III | 0:35–0:41 | engine |
| 07 | `cite` | III | 0:41–0:47 | engine |
| 08 | `braid` | III | 0:47–0:54 | Blender B08 + engine labels and card (tracked) |
| 09 | `merkle` | III | 0:54–0:59 | engine 3D |
| 10 | `graph` | III | 0:59–1:04 | engine |
| 11 | `honest` | III | 1:04–1:09 | engine (music out) |
| 12 | `proof` | III | 1:09–1:15 | engine (music back) |
| 13 | `connect` | IV | 1:15–1:20 | engine |
| 14 | `anywhere` | IV | 1:20–1:25 | engine |
| 15 | `weave` | V | 1:25–1:33 | Blender B15 (native 4K) + engine type |

### 01 `thread`: Your agent forgets

- **Picture:**
  - Black, then half a second of silence and a low sub drone.
  - A macro shot (85 mm feel, shallow depth of field): a single bone-white thread spans the frame on a shallow diagonal,
    taut and rim-lit from the upper left. Its three twisted plies and a fine fuzz of fibres catch the light.
  - It vibrates slightly in time with a heartbeat pulse in the sub.
- **L01 "Your agent forgets."**
  - Type: Bricolage, bone at 70%, lower-left third. As *forgets* is spoken, its tracking loosens and the letters drift
    apart.
  - On *forgets*, the thread begins to **fray** at the centre as fibres lift.
- **L02 "Every conversation... back to zero."**
  - Type: *back to zero* sits right of centre.
  - On *zero* the thread **snaps**. Sound cuts to near-silence for two frames, then the recoil plays at 0.4× speed and
    freed fibres drift.
- **Out:** the drifting fibres catch the light, and on the next beat they match-cut into monospace float numerals
  (scene 02).
- **Covers:** session amnesia ("An agent forgets everything when its session ends").

### 02 `ex`: It's not you, it's your vector store

- **Picture:**
  - "The ex": about 6,000 monospace float numerals (`0.2143`, `−0.0931`, `0.7715`, …) at 25–60% bone, arranged as a
    jittered lattice in a loose spheroid (precise, not a nebula). The camera orbits slowly.
- **L03**
  - Type: Bricolage, large, left: *It's not you.* then *it's your vector store*, with *vector store* set in mono (the
    machine voice).
  - Bottom label: `vectors.bin · 1536 dims · 0 commits`.
- **L04**
  - A sentence card, `Maya lives in Berlin.`, flies in and dissolves into floats, letters becoming numerals.
  - `Maya moved to Lisbon in March 2026.` flies in; that region's numerals **flip like a split-flap board** to new
    values, and Berlin is gone without a trace. A ghost query, `berlin?`, returns nothing.
  - On *why*, a ping `why?` returns only a tooltip, `cosine 0.8127`: a score, not a reason.
  - Red diff tags stamp in on beats: `− no history`, `− no provenance`, `− one flat bag`.
- **L05 "Commitment issues."**
  - The cloud collapses, all numerals falling to one line, and resolves into a deadpan terminal:
    `$ git log` → `fatal: your current branch 'main' does not have any commits yet` (bone-dim, with *commits* in blood).
- **Covers:** the three pains: "You can't diff an embedding" / "Provenance dies at chunk time" / "Everything is one
  flat bag".

### 03 `her`: Not me

- **Picture:**
  - A hard cut to black on the downbeat, then one silent beat.
  - **B03 (Blender):** the two frayed ends are drawn back together from off-frame. As they meet, a blood strand and
    a moss strand twist around the bone core: the diff thread is born.
- **L06 "Not me."** The kick and bass enter on *me*.
  - The thread pierces a **commit bead**, a glassy sphere with `3f9a1c2` engraved, and the bead slides along it.
- **L07 and L08**
  - The site's hero headline plays as a live diff: `− your agent forgets` (small, struck through, blood), then
    `+ every memory has a commit` typed in sync (*commit* in moss), then `+ every fact has a blame` (*blame* in moss).
  - On *blame*, a blame gutter slides in at left: `3f9a1c2 (you 2026-07-26)`.
- **Covers:** git-backed memory, commit, blame.

### 04 `repo`: I'm just a git repo

- **Picture:** a tilted 2.5D terminal panel with depth of field.
- **L09**
  - `$ cd ~/memory && ls` → `facts/  incidents/  rules/  skills/`
- **L10**
  - `$ git log --oneline` scrolls like beads on the thread:
    - `3f9a1c2 remember: uses neovim`
    - `8b21e04 remember: uses VS Code`
    - `a41c9d0 gc: expire 3 incidents`
    - `105ca74 remember(2026-07-31): 3 memories from session chat-2026-07-31-a`
  - The memory file `facts/people/user.md` then opens, verbatim from §11.4, with line numbers.
  - Footnote in mono: *Nothing about that is a metaphor — you can cd into it.*
- **Covers:** markdown plus YAML frontmatter, plain git, tier directories, provenance in the log.

### 05 `loom`: Facts I keep

- **Picture (B05 Blender):**
  - A low-angle loom: four warp bundles stretch into depth.
  - A shuttle (a bead carrying the diff thread) flies across **on every beat**, weaving a weft row, so the fabric grows
    toward camera.
- **Labels** (engine overlays positioned from Blender-exported 2D track data): `facts/ · long-term`,
  `incidents/ · ttl 30d`, `rules/ · loaded whole`, `skills/ · lazy`.
- **L11** — the facts warp glows steady.
- **L12** — the incidents warp frays and dissolves at its end; a mono stamp reads `gc: expire 3 incidents`.
- **L13** — the rules warp pulls tight.
- **L14** — the skills warp stays dim until the shuttle reaches it, then lights: lazy-loaded.
- **Covers:** the four tiers, TTL expiry as a `gc:` commit, rules loaded whole, lazy skills.

### 06 `diff`: We'll always have the diff

- **Picture:** `facts/people/user.md` in an editor-like panel with line numbers.
- **L15** — the cursor lands on `Uses VS Code.`
- **L16**
  - That line strikes through in blood with a `−` gutter.
  - `+ Uses neovim. Has since 2019.` types in moss.
  - The frontmatter shows `− confidence: 0.6` / `+ confidence: 0.9`.
- **L17**
  - `$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2` → `1 file changed, 2 insertions(+), 2 deletions(-)`
  - A commit-history scrubber slides in beneath. The playhead scrubs back and the old version is intact, then forward
    again.
  - A slow push-in, with the old line still glowing faintly. (The romantic beat.)
- **Covers:** the current-state memory (reconcile rewrites the file), history kept, diff between any two commits,
  confidence.

### 07 `cite`: I'll show you the line

- **Picture:**
  - An agent chat in mono: `what editor do I use?` → streaming answer `neovim.`
- **L18**
  - On *why*, the cursor clicks a small `why?` chip.
  - On *the line*, the thread becomes a needle and stitches from the answer down into the file. Citation label:
    `facts/people/user.md#editor · L11–14 · 3f9a1c2`
  - Lines 11–14 highlight, and the blame gutter shows `3f9a1c2 · 2026-07-26`.
  - The optional L18b ("Go ahead. Blame me.") would play over the blame gutter.
- **Rule:** every citation shown must match the shown file's real line numbers (the `## Editor` heading is line 11 of
  §11.4).
- **Covers:** citations (path, section, line range), commit provenance, memory that can be cross-examined.

### 08 `braid`: Braided into one answer

- **Picture (B08 Blender):**
  - Three threads race in from left, top and right through a dark void, and braid into one three-strand rope that pulls
    taut toward the camera.
  - Small side threads branch off to neighbouring beads: graph expansion.
- **Labels** (tracked, engine): `lexical · your words`, `body · what you meant`, `cues · how you'd ask`, lit in the
  order she names them.
- **The query** above: `what camera did I buy`.
- **On *one answer***, the rope lands on a result card (engine), verbatim fields from §11.6:
  - `facts/camera-gear/sony-a7iii-purchase-42065a87.md`
  - `matched: lexical · cue · body`
  - `mode: raw`
  - `millis: 82`
  - Footnote: *Ranked memories, no model call. Milliseconds.*
- **Covers:** hybrid retrieval (lexical BM25 + cue vectors + body vectors), fusion, graph expansion, calibrated score
  and `matched`, provenance, no model call in raw mode.

### 09 `merkle`: I only look at fifty

- **Picture (engine 3D):**
  - A Merkle tree of 10,000 leaves drawn in hairlines, with small node dots; the camera flies over it.
- **On *changed*** — 50 leaves pulse moss and their ancestor paths light up.
- **On *only look at fifty***
  - Each unchanged subtree folds shut and darkens with the stamp `= hash · skipped`.
  - The camera dives along one lit path.
  - A counter reads `visited 50 of 10,000` (site stat: "50 of 10,000 files visited").
  - Footnote: `index is a pure cache · gitloom rebuild`.
- **Covers:** incremental Merkle indexing; the index as a rebuildable cache.

### 10 `graph`: I connect the dots

- **Picture:**
  - `Works with [[facts/orgs/acme.md]].` (from §11.4): the wikilink lifts off the text as a thread and draws an edge to
    the `acme.md` node.
  - A new memory's `[[facts/trips/lisbon-2026.md]]` points at a file that doesn't exist yet: a dashed blood edge.
  - When the target is written, the edge **heals** to moss.
  - A walk lights up to 3 hops: trip → hotel → city.
- **Then:** `$ gitloom vocab add --term kubernetes --alias k8s` → `k8s → kubernetes  ·  search finds either form`
  (verbatim). A search for `k8s` then highlights a memory that says "kubernetes".
- **Covers:** relationship graph (frontmatter edges and wikilinks, forward references heal, 3-hop walk); custom
  vocabulary.

### 11 `honest`: When I don't know, I say so

- **Sound:** the music drops out completely, leaving room tone.
- **Picture:**
  - A near-black frame. A single question types: `what's my sister's name?`
- **L22**
  - Three thin threads (the arms) extend into the dark, searching.
  - A hairline marks the **evidence floor**. The thread tips hover below it, nothing clears it, and they go slack and
    fall.
  - About 1 s of silence.
- **L23**
  - A response panel (illustrative, real shape): `"memories": []`, `"candidates": 2`, `"filtered_out": 2`.
  - Then large bone type: *I don't know.*
  - Footnote (verbatim): *the engine returns nothing rather than the nearest vector.*
- **Covers:** abstention via the evidence floor; the site's promise of memory "that can't lie about what it knows".

### 12 `proof`: Forty-four to ninety-one point four

- **Sound:** the music slams back in on the downbeat.
- **Picture:**
  - A large Bricolage odometer rolls one round per beat: `44` (v1) → `72` (v3) → `80` (v4) → `83` (v5) → `91.4%` (v7).
    A sparkline climbs with it, and 91.4 lands in moss.
  - A strip of per-category v7 bars flashes: knowledge-update 94.9 · multi-session 87.9 ·
    single-session-assistant 96.4 · preference 100 · single-session-user 97.1 · temporal 85.7.
  - Footnote: `LongMemEval · oracle split · 456/499` and *Every round was diagnosed from the previous round's failures.*
- **L25** — a smirk beat: the `%` settles last.
- **Covers:** quality proof (per D6).

### 13 `connect`: One command and I'm in Claude Code

- **Picture:** a full-frame terminal with the real command (§11.1), typed in sync, then
  `$ claude mcp list` → `gitloom: npx -y @gitloomhq/mcp - ✔ Connected` (the ✔ in moss).
- **L27** — cards flip in, one per beat:
  1. the MCP JSON config
  2. `gitloom install codex --write`, with the host list `claude-code · openclaw · opencode · codex · hermes`
  3. TypeScript: `withMemory(new OpenAI(), { memory }) // ← the only setup`
  4. Python: `gitloom.wrap(OpenAI(), memory)  # ← the only setup`
  5. Go: `client := gitloom.New("") // reads GITLOOM_API_KEY`
  6. Rust: `let client = Client::new(""); // reads GITLOOM_API_KEY`
- **Covers:** Claude Code in one command, any MCP client, `gitloom install` for five hosts, drop-in SDKs in four
  languages.

### 14 `anywhere`: On your machine, or in my cloud

- **Picture:** a split composition.
- **Left (*On your machine*)**
  - `$ curl -fsSL https://gitloom.cloud/install.sh | sh   # current: 0.3.0`
  - Chips: `one static binary · no CGo · arm64 + amd64 · licence verified offline`
- **Right (*or in my cloud*)** — recreated console panels, built from the real layouts in `web/src/app` (no
  screenshots):
  - Playground: a chat with tool chips, `gitloom_retrieve` in moss and `gitloom_remember` in blood.
  - Memory Graph: a force layout settling into tier regions, with green relation lines.
  - Namespaces.
- **L29**
  - The Namespaces list multiplies (`user-0001 … user-2048`), each an isolated repo icon.
  - Label: *one per end user · a storage boundary, not a WHERE clause*.
- **Footnote:** `free plan · no card · storage is free`.
- **Covers:** the self-hosted binary, portability, the offline licence, the cloud console (Playground, Graph,
  Namespaces), namespace isolation, the free plan.

### 15 `weave`: I don't forget. I commit.

- **Picture (B15 Blender, native 4K):**
  - Every thread from the film converges out of the dark in long arcs. Blood and moss weave over and under the bone G to
    form the **GitLoom mark**.
  - The last crossing locks with a soft sub impact on the downbeat.
  - A slow push-in, with raking light across the fibres; a slight rotation settles to the front view.
- **L30** — the mark completes.
- **L31 and L32**
  - The wordmark types in mono beside the mark, as a git log entry: `gitloom 3f9a1c2`.
  - Below it: `gitloom.cloud` and `start free — no card`.
- **Out:** hold 2–3 s on the music tail. The final frame is clean and poster-worthy.
- **Sung-hook A/B:** the alternate score sings *"I don't forget… I commit"* here (§5.2).
- **Covers:** brand, CTA.

**Covered on screen only (not in the voiceover):** YAML frontmatter, TTL garbage collection, the navigable tree, the
index as a rebuildable cache, plugin hooks and `<private>` tags (a card in 13 if time allows), conversations (the
Playground), the offline CLI licence, the free plan.

## 5. Sound

### 5.1 Voiceover

- **Engine:** `POST /v1/text-to-speech/eVItLK1UvXctxuaRV2Oq/with-timestamps`, `model_id: eleven_v4`.
  - `output_format: pcm_48000` (48 kHz lossless; verified allowed on the Starter plan, while `pcm_44100` and
    `mp3_44100_192` are refused).
  - One request per line (§4). Takes are saved with their seed and settings.
- **Takes:** 2–3 alternates for the key lines: L05, L06, L17, L23, L25, L30–L32.
- **Pace:** Jean runs slow (audition: 192 characters in 19.7 s), so tighten by about 10–12%.
  1. First try `voice_settings.speed` at 1.10–1.20 (accepted by v4; effect to be measured on full lines).
  2. Then a formant-preserving time-stretch (Rubber Band R3, formant mode), up to 12%.
  3. Never pitch-shift.
- **Timing:** character-level timestamps from the API give word times. Each line is placed on the timeline by the edit
  (§8.2), which writes `data/vo.json` with absolute word times.
- **Processing:** high-pass at 80 Hz; a gentle cut around 300 Hz; presence and air shelves; a de-esser; 2:1
  compression; a very short plate reverb at low mix; light saturation for warmth.

### 5.2 Score

- **Engine:** `POST /v1/music` with a `composition_plan`, `model_id: music_v2_5`. Output as 48 kHz PCM if allowed,
  otherwise the best allowed format.
- **Style (positive):** nocturnal, sensual, minimal electronic; warm sub bass; a soft round kick; crisp brushed hats;
  breathy analog pads; a plucked motif like a taut thread being pulled (muted harp / koto-like); tape saturation;
  intimate and expensive-sounding; about 100 BPM; minor key.
- **Negative styles:** EDM drops, trap hi-hat rolls, cheesy synth brass, vocals (except in the sung variant).
- **Sections:** durations come from the voice timing, rounded to whole bars.

  | section | covers | intent |
  |---|---|---|
  | cold open | 01 | drone, heartbeat pulse, one plucked note, no drums |
  | the ex | 02 | filtered pulse, tension, glassy ticks |
  | her | 03–04 | kick and bass land on L06 "Not me"; a sparse, confident groove |
  | the tour | 05–10 | full groove, sensual bassline, the thread motif, a variation every 8 bars |
  | honest | 11 | everything out; one soft pad breath at most |
  | proof and everywhere | 12–14 | slams back in on a downbeat; fuller, confident lift |
  | weave | 15 | resolve: one big hit on the mark's lock, reverb tail, the pluck alone to end |

- **Variants:** 2–3 generated with different seeds; the user picks one by ear.
- **Sung-hook variant:** the weave section carries the lines `I don't forget` / `I commit` with a breathy, intimate
  female vocal style. It's A/B'd against the spoken ending at the rough-cut checkpoint.
- **Beat grid:** librosa analysis of the chosen variant gives tempo, beats, downbeats (bar-phase estimate verified
  against the plan's section starts), onsets, and envelopes (rms, low, mid, high). It's written to `data/audio.json`
  in the engine's format.
- **Section drift:** if the model doesn't hold the section durations exactly, **the music is the truth**: scene
  windows are refitted to the analysed sections. Fallbacks, in order: regenerate or inpaint the drifting section, or
  cut on a downbeat.

### 5.3 Sound effects

- **Engine:** ElevenLabs sound generation, `duration_seconds` fitted to the cue.
- **Cue sheet:** `data/sfx.json` (id, scene, time or anchor, prompt, duration, gain).
- **Cues:**
  - **Threads:** tension hum, fray crackle, snap, fibre whoosh, re-form swell.
  - **Floats:** digital shimmer, split-flap flips, cosine ping, a dull "fatal" thunk.
  - **Commits:** a glassy commit "thock".
  - **Typing:** soft mechanical keys (one per typed character, humanised), enter.
  - **Loom:** shuttle clack on the beat, weave swish.
  - **Diff:** pen strikethrough, soft insertion pops.
  - **Cite:** needle stitch, gutter slide.
  - **Braid:** rope creak.
  - **Merkle:** a visited-tick cascade, fold clicks.
  - **Graph:** edge zips, a heal shimmer.
  - **Honest:** room tone.
  - **Proof:** odometer roll.
  - **Connect:** a subtle "Connected" chime.
  - **Weave:** risers and a deep sub impact.
- **Fallback:** if the generated **loom shuttle** or **thread snap** sounds artificial, the user supplies real
  recordings.

### 5.4 Mix and master

- The music ducks 6–9 dB under the voice (sidechain), with the music as the bed and effects up front.
- Two-pass EBU R128 loudness normalisation to −14 LUFS / −1 dBTP, at 48 kHz / 24-bit.
- Stems: `vo.wav`, `music.wav`, `sfx.wav`, plus `mix.wav`.

### 5.5 Credit budget

About 39.4k ElevenLabs credits remain this cycle. Estimated spend is 15–20k:

| Item | Credits |
|---|---|
| Voice takes | ≈1k |
| Music, 3 variants plus sung variant plus retries | ≈8–10k |
| Sound effects, about 40 | ≈4–8k |

Every call logs its `character-cost` header to `audio/credits.log`.

### 5.6 Limitation

The agent building this can't hear audio. Quality is checked objectively (timings, loudness, clipping, sibilance-band
energy, silence gaps), and **the user is the ear** at every listening checkpoint.

## 6. Visual system

**Palette** (from `web/src/styles/tokens.css`, the source of truth):

| role | hex | rule |
|---|---|---|
| ink (bg) | `#110d10`, `#161114` | page and void |
| panel | `#1e181c`, `#282027` | 2.5D panels |
| rule | `#2b2229`, `#3e323b` | hairlines |
| bone | `#ede7ea` / `#a99fa5` / `#6f6469` | type; never blooms |
| blood | `#c22b45` (bright `#dc4a63`, dim `#8e1f35`) | accent, `−`, key numerals, CTA; **never a surface fill** |
| moss | `#4aad63` (dim `#1c3324`) | `+` and gain only; **never decoration** |

**Glow:** only blood and moss may exceed about 0.85 linear and bloom. Bone type stays crisp.

**Type:**
- **Bricolage Grotesque** is her voice, for display and kinetic type. Its axes are opsz 12–96, wdth 75–100 and
  wght 200–800. It's used through static instances made with fontTools (opsz 96 × wdth {75, 87.5, 100} ×
  wght {300, 500, 600, 800}), so opentype.js can kern them. Width and weight follow her delivery: stretched on held
  vowels, condensed on punchlines.
- **JetBrains Mono** is the machine: paths, hashes, commands, JSON, footnotes, labels.
- **Geist** is UI chrome inside the recreated console.
- **Craft rules:**
  - Every proportional line is kerned (the font's kerning, glyph by glyph).
  - Display text uses typographic punctuation; mono typed input keeps typewriter quotes.
  - No outlined or haloed type. No glyphs from outside the three families; missing symbols are drawn.
  - Title-safe margin of at least 96 logical px (1080p layout units).

**Layout:** Swiss-grid discipline, asymmetric compositions, generous black, and small mono annotations beside big
display type.

**Motion:**
- Hard cuts on beats; act changes on downbeats.
- Type snaps on strong easing (outExpo, inOutCubic, springs), with holds between snaps.
- 3D cameras are the opposite: slow, luxurious push-ins, slides and rack focus. The sultriness is in the camera, the
  wit in the type.
- No floaty screensaver motion.

**Finishing pass (engine, applied to every shot, including Blender plates):**
- Film grain, rendered per 4K pixel.
- Halation on blood and moss; bloom with a high threshold.
- Subtle chromatic aberration toward the edges and a subtle vignette.
- True motion blur: the engine's adaptive sub-frame sampling for engine scenes, and native Cycles motion blur for
  plates, both with a 180° shutter (0.5 of the frame at 30 fps).

**The mark (D7):**
- Traced from `web/public/mark.png` at high zoom into Bézier paths:
  - the bone "G" arc and stem;
  - the blood crossbar and vertical;
  - the moss loop.
- Built as flat ribbon bands (extruded, depth about 0.15 of the band width, softly rounded edges) with explicit
  over/under weave offsets.
- Material: satin, matching the soft gradient shading of the PNG.
- **Acceptance:** at the front view, a silhouette overlay against `mark.png` shows no visible deviation. The user
  approves it at the style-frames checkpoint.

## 7. Build architecture

### 7.1 Repo layout

```
gitloom-film/
  app/                    forked engine (TypeScript, three.js, bun + Vite) + GitLoom scenes
    src/engine/           engine core (MIT © 2026 Giacomo Magnanini, adapted)
    src/scenes/           thread ex her repo loom diff cite braid merkle graph honest proof connect anywhere weave (+ helpers)
    src/timeline.ts       scene windows anchored to VO lines, snapped to the beat grid
    scripts/render.ts     stills / sheet / video / perf (headless Chrome → ffmpeg)
    public/fonts/         static instances of Bricolage Grotesque, JetBrains Mono, Geist (OFL)
    public/plates/        proxies of Blender plates for live preview (JPEG); finals read from out/plates
  blender/
    lib/                  thread materials, twisted-ply + fuzz generator, weave generator, mark geometry, timing import
    shots/                b01_thread.py b03_reform.py b05_loom.py b08_braid.py b15_weave.py
  tools/                  Python (uv): el.py (ElevenLabs client), vo.py, pace.py, assemble_vo.py, music.py,
                          analyze.py (librosa), sfx.py, mix.py, factcheck.py
  data/                   script.json, vo.json, audio.json, sfx.json, edit.json, track/<shot>.json
  audio/                  vo/ music/ sfx/ mix/ credits.log
  docs/                   specs/ TREATMENT.md ENGINE.md CREDITS.md
  out/                    renders, plates, stills (gitignored)
```

### 7.2 Engine fork changes

- **fps and shutter:** default fps 30, shutter 0.5; adaptive sampling unchanged.
- **Palette:** `palette.ts` and the GLSL constants swap to GitLoom's tokens (`C_INK`, `C_BONE`, `C_BLOOD`, `C_MOSS`, …).
- **Fonts:** `type.ts` switches its families to Bricolage (width and weight grid), JetBrains Mono and Geist.
- **VO timing:** `lyrics.ts` becomes `vo.ts`, same API (`lines`, `get(q)`, `words`, `wordProgress`,
  `lineCharProgress`) reading `data/vo.json`.
- **HUD:** `hud.ts` loses the P(doom) instrument and captions. Crop marks stay available and off by default.
- **New: `plates.ts`.** Loads Blender frame sequences as textures by frame index. Finals use half-float EXR (linear),
  with a half-res JPEG proxy in preview. It's deterministic; the sub-frame index maps to the nearest plate frame, since
  Cycles already motion-blurs the plates.
- **New: `track.ts`.** Loads Blender-exported per-frame 2D anchor positions in logical px, so engine labels and cards
  sit exactly on 3D objects.
- **render.ts:** audio input is `audio/mix/mix.wav`; the default output is 3840×2160 at 30 fps, with an optional
  ProRes 422 HQ encode.

### 7.3 Blender pipeline

- **Invocation:** Blender 5.2.2 LTS, headless (`blender -b -P shots/<shot>.py -- <args>`).
- **Render settings:** Cycles on the Metal GPU (M5, 10 cores), OpenImageDenoise, motion blur with a 0.5 shutter,
  depth of field. 2560×1440 for B01, B03, B05 and B08; 3840×2160 for B15.
- **Timing:** each shot script imports `data/vo.json` and `data/audio.json` and keys events at `frame = round(t × 30)`,
  so thread snaps, shuttle passes and the mark's lock land on the same frames as words and beats.
- **Outputs:**
  - `out/plates/<shot>/####.exr` (half float, linear, beauty with alpha where the engine composites behind)
  - `data/track/<shot>.json` (2D anchors via `world_to_camera_view`)
  - `app/public/plates/<shot>/` proxies
- **Measured cost** (probe, 60 twisted threads with DoF): about 10 s/frame at 1080p and 128 samples; about 33 s/frame
  at 4K and 64 samples, after a one-time Metal kernel compile of about 2 min.
- **Budget:** final Blender renders of 8–12 h, overnight and split into segments. Look-dev and previews use EEVEE or
  low-sample Cycles at 720p.

### 7.4 Data flow

```
script (§4) ─► tools/vo.py ─► audio/vo/takes/*.wav (+ timestamps) ─► tools/pace.py ─► selects
selects + data/edit.json (line placement, gaps) ─► tools/assemble_vo.py ─► audio/vo/vo.wav + data/vo.json (absolute word times)
data/vo.json (act lengths → whole bars) ─► tools/music.py (composition plan) ─► audio/music/variant-*.wav
chosen variant ─► tools/analyze.py ─► data/audio.json ─► re-place lines on beats (≤150 ms nudges), cuts on downbeats
data/vo.json + data/audio.json ─► app timeline + Blender shot scripts ─► plates + track data
data/sfx.json ─► tools/sfx.py ─► audio/sfx/*.wav ─► tools/mix.py ─► audio/mix/{mix,vo,music,sfx}.wav
app + plates + mix ─► scripts/render.ts ─► out/gitloom-launch-4k30.mp4 (+ ProRes master)
```

### 7.5 Secrets

The ElevenLabs key is read at runtime from `~/11labs`. It is never printed, logged, committed or copied into the repo.
`.gitignore` covers `out/`, raw takes, `node_modules/` and `.env*`.

## 8. Production process

### 8.1 Order of work

1. Repo setup, engine fork and re-skin, fonts, a smoke-test scene.
2. Voiceover takes and pacing, then assembly into `data/vo.json`.
3. Score composition plan, variants, the user's pick, beat analysis, then lock the edit.
4. **Animatic:** the full 90 s with voice and music, a timed card per scene, and cuts on beats.
5. Style frames: one finished still per scene. Engine scenes 01–04 first, to set the look, then the rest. Blender
   look-dev in parallel: the thread, the loom and the mark.
6. Full build: engine scenes, with subagents building in parallel against the locked style once the style frames are
   approved; Blender shot animation and previews.
7. Sound effects and the mix.
8. Rough cut at 1080p (draft motion blur, Blender previews).
9. Finals: Blender plates overnight, then the engine 4K pass, the encode and the deliverables.

### 8.2 Timing lock procedure

1. Lines are placed with target gaps: 0.35–0.6 s within a scene, and 0.8–1.5 s at act breaks and before the honesty
   beat.
2. Act lengths are rounded to whole bars at about 100 BPM and set as the composition plan's section durations.
3. The chosen music is analysed. Each line's first stressed word is nudged by up to 150 ms onto the nearest beat, and
   scene cuts snap to the beat or downbeat nearest their planned time.
4. If the total runs outside 85–95 s, trim ✂ lines, re-take, or adjust the gaps, then repeat from step 2.

### 8.3 User checkpoints

| # | checkpoint | what the user does |
|---|---|---|
| C1 | voice takes | listen, pick alternates, final wording tweaks |
| C2 | score variants | listen, pick one |
| C3 | animatic | watch; lock pacing |
| C4 | style frames | review one still per scene plus the mark; lock the look |
| C5 | rough cut (1080p) | watch; notes; sung-hook A/B |
| C6 | final | approve the 4K master and deliverables |

### 8.4 Quality gates (run by the agent)

- Every scene is checked from rendered stills and contact sheets, which the agent looks at.
- **Sync report:** for every word, on-screen onset versus spoken onset, and for every cut, its time versus the nearest
  beat. It fails at more than 1 frame.
- **`tools/factcheck.py`:** every on-screen string in the scenes' text tables is matched against §11 and the source
  files it cites. Unknown strings must be marked illustrative.
- Loudness and true peak are measured on the final mix.
- A render-log scan finds no scene errors and no console errors.

## 9. Checkpoint artefacts

- **C1:** a local audition page listing the takes per line.
- **C2:** the variants as WAVs plus a page.
- **C3:** `out/animatic.mp4` at 1080p.
- **C4:** `out/style/` 4K stills plus a contact sheet.
- **C5:** `out/rough.mp4` at 1080p30.
- **C6:** §10.

## 10. Deliverables

- `gitloom-launch-4k30.mp4`: H.264, CRF about 14–16, BT.709-tagged, AAC 320k
- `gitloom-launch-4k30-prores.mov`: ProRes 422 HQ master with 48 kHz / 24-bit PCM audio
- `gitloom-launch-1080p30.mp4`: web
- `stems/`: `mix.wav`, `vo.wav`, `music.wav`, `sfx.wav` (48 kHz / 24-bit)
- `stills/`: one 4K PNG hero frame per scene
- `gitloom-launch.srt`: captions exported from `data/vo.json` (a cheap extra)
- The repo: re-generate any audio, re-render any scene

## 11. Facts sheet: allowed on-screen strings and numbers

Everything shown on screen must come from this list, verbatim, or be marked illustrative. Sources are paths in
`~/Developer/code/gitloom`.

**11.1 Claude Code** (`docs/content/claude-code.md:25-29, 38-44`)
```bash
claude mcp add gitloom --scope user \
  -e GITLOOM_API_KEY=gl_live_... \
  -- npx -y @gitloomhq/mcp
```
```
claude mcp list
gitloom: npx -y @gitloomhq/mcp - ✔ Connected
```

**11.2 MCP config** (`docs/content/mcp.md:55-65`)
```json
{
  "mcpServers": {
    "gitloom": {
      "command": "npx",
      "args": ["-y", "@gitloomhq/mcp"],
      "env": { "GITLOOM_API_KEY": "gl_live_..." }
    }
  }
}
```
- `gitloom install codex --write`
- Supported hosts: `claude-code`, `openclaw`, `opencode`, `codex`, `hermes` (`docs/content/mcp.md:78-91`)

**11.3 SDKs** (`docs/typescript.md`, `docs/python.md`, `docs/go.md`, `docs/rust.md`, `docs/sdks.md`)
- TypeScript: `npm install @gitloomhq/sdk` · `const openai = withMemory(new OpenAI(), { memory }) // ← the only setup`
- Python: `pip install gitloom-sdk` · `openai = gitloom.wrap(OpenAI(), memory)  # ← the only setup`
- Go: `go get github.com/GitLoomHQ/gitloom-go/gitloom` · `client := gitloom.New("") // reads GITLOOM_API_KEY`
- Rust: `cargo add gitloom` · `let client = Client::new(""); // reads GITLOOM_API_KEY`
- Rust doc comment: `// Ranked memories, no model call. Milliseconds.` (`docs/rust.md:55`)

**11.4 The memory file** (`web/src/sections/FinalCta.tsx:9-26`). Line numbers as shown in the film:
```
 1 ---
 2 tier: facts
 3 tags: [user, prefs]
 4 confidence: 0.9
 5 updated: 2026-07-26
 6 ---
 7
 8 Dark mode preferred.
 9 Ships on Fridays without ceremony.
10
11 ## Editor
12
13 Uses neovim. Has since 2019.
14
15 ## Timezone
16
17 IST. Prefers async review to calls.
18 Works with [[facts/orgs/acme.md]].
```
The citation is `facts/people/user.md#editor · L11–14`.

**11.5 The diff** (`web/src/sections/HowItWorks.tsx:38-49`)
```
# facts/people/user.md
  tier: facts
- confidence: 0.6
+ confidence: 0.9

- Uses VS Code.
+ Uses neovim. Has since 2019.
$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2
1 file changed, 2 insertions(+), 2 deletions(-)
```

**11.6 A retrieval response** (`docs/content/quickstart.md:190-248`), fields used:
- `"query": "what camera did I buy"`
- `"mode": "raw"`
- `"path": "facts/camera-gear/sony-a7iii-purchase-42065a87.md"`
- `"matched": ["lexical","cue","body"]`
- `"provenance": {"commit": "105ca74b…", "message": "remember(2026-07-31): 3 memories from session chat-2026-07-31-a"}`
- `"millis": 82`

**11.7 CLI** (`docs/content/cli.md`)
- `curl -fsSL https://gitloom.cloud/install.sh | sh   # current: 0.3.0`
- `gitloom license activate gll_...`
- `echo "Maya moved to Lisbon in March 2026." | gitloom write -p facts/people/maya.md --tags person -m "maya moved"`
- `gitloom search "where does maya live"`
- Vocabulary (`web/src/sections/Integration.tsx:23-24`): `gitloom vocab add --term kubernetes --alias k8s` →
  `k8s → kubernetes  ·  search finds either form`
- Not to be shown as real: `gitloom log --blame` (no such flag), and `gitloom diff A..B -- path` (the real syntax is
  `diff PATH FROM TO`).

**11.8 Numbers**
- LongMemEval by round (`web/src/data/benchmarks.ts:15-18, 53-65`): v1 44 → v3 72 → v4 80 → v5 83 → v7 **91.4%**,
  `456/499`, "oracle split".
- v7 by category: knowledge-update 94.9 · multi-session 87.9 · single-session-assistant 96.4 ·
  single-session-preference 100 · single-session-user 97.1 · temporal-reasoning 85.7.
- Incremental indexing: "50 of 10,000 files visited" (`web/src/sections/Internals.tsx:15`).
- Latency in words: "milliseconds" (the quickstart response shows `millis: 82`).
- **Not to be shown:** "15 ms" for hosted retrieval; "10,000 shards / 100M memories" as a deployed fact.

**11.9 Quoted lines** (verbatim, for footnotes)
- "Nothing about that is a metaphor — you can cd into it." (`Idea.tsx:46`)
- "the engine returns nothing rather than the nearest vector." (`LiveSearch.tsx:64`)
- "Every round was diagnosed from the previous round's failures." (`Benchmarks.tsx:146`)
- "a storage boundary, not a WHERE clause" (shortened from `docs/content/concepts.md:28-29`)
- Pricing: Free is ₹0 with no card; "Storage is free." (`docs/content/pricing.md`, `web/src/sections/Pricing.tsx`)

**11.10 Illustrative values** (the real shape, invented values; allowed)
- `vectors.bin · 1536 dims · 0 commits`, the float numerals, `cosine 0.8127`
- the commit hashes in `git log` beyond `3f9a1c2`, `8b21e04` and `105ca74`, and every `git log` message except
  `105ca74`'s (the messages are the kind a `gitloom write -m` produces)
- `gc: expire 3 incidents`; the blame date `2026-07-26` (matches the file's `updated`)
- the honesty response counts (`"candidates": 2`, `"filtered_out": 2`)
- `user-0001 … user-2048` namespaces; `lisbon-2026.md` / hotel / city graph nodes
- the Merkle tree's node count

## 12. Risks and mitigations

| # | risk | mitigation |
|---|---|---|
| R1 | the agent can't hear audio | objective checks (§5.6), plus user listening at C1, C2, C3, C5 and C6 |
| R2 | the music doesn't hold its section durations | music is the truth: refit windows; regenerate or inpaint a section; cut on downbeats |
| R3 | v4 takes vary in pace and emphasis | several takes per key line; time-stretch; pick at C1 |
| R4 | Blender render time on an M5 with 16 GB | 1440p plates, EEVEE previews, overnight segmented finals, Blender and engine renders never run at once |
| R5 | memory of the engine's 4K render (~5 GB Chrome + ~4 GB ffmpeg) | render in segments and concat losslessly; shorter x264 lookahead |
| R6 | the mark rebuilt from a 256 px PNG isn't faithful | high-zoom trace plus silhouette overlay check; approved at C4 |
| R7 | the benchmark's provenance | D6 recorded; label exactly as the site does; nothing beyond §11.8 |
| R8 | ElevenLabs credits | ~15–20k budget against ~39.4k available; per-call cost log |
| R9 | the library voice could be withdrawn by its owner | generate and archive all final takes early (Jean is already in the account's library) |
| R10 | commercial-use terms for ElevenLabs output on Starter | verify the voice-library and Music commercial terms before C6 |
| R11 | the engine fork's code volume | keep the engine's scene API; build 01–04 first to validate before parallelising |

## 13. Out of scope and follow-ups

- The 30 s vertical (9:16) social cut.
- An interactive web version of the film for gitloom.cloud: the engine runs live in the browser, so viewers could pause
  on any scene and copy the real commands.
- Localisation.
- Fixing the landing page's benchmark provenance text (flagged in brainstorming; a separate task in the gitloom repo).

## 14. Credits and licences

- **Engine:** adapted from PDoom-Video, © 2026 Giacomo Magnanini, MIT licence (kept in `docs/CREDITS.md` and the
  engine file headers).
- **Voice:** ElevenLabs voice library, "Jean – Alluring and Playful Femme Fatale". **Music and sound effects:**
  ElevenLabs (terms per R10).
- **Fonts:** Bricolage Grotesque, JetBrains Mono and Geist, all under the SIL Open Font License.
- **Brand assets:** GitLoom (`web/public/mark.png`, `tokens.css`).
