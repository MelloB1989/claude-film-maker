"""The review gate (v2): sign a render only when every item the operator would look at is a NUMBER inside its line.

Round 4 shipped with a signed gate and four blockers the operator saw at once (lips before the audio and not
tracking it, a head nod on each blink, an armour-like tee clipping at the neck, the hair shortening at a cut). The
gate had either no number for them, a number it never read (the grooms' own LOD), or a failing number that was
waived. v2's rules:

1. An item is a measured number, a comparison and a line (ITEMS); a `guard` item protects against a new failure
   (a fix overshooting) and need not fail round 4.
   It says where to look (shots, frames), which
   command produces the number, and the round-4 value that the line must fail (`r4`), so a line that would have
   passed round 4 is visible in review.
2. A missing number FAILS ("not measured" is not a pass); so does an error.
3. A waiver needs a written reason and a name, and is REFUSED for an item marked `complaint` (the operator
   complained about it) or for any item whose `area` the round lists in `complaints`: what the operator saw cannot
   be signed away by the people who missed it.

    numbers = {"lips.lead_in_cm": {"value": 0.33, "where": "S13 f977-1001"}, ...}
    rep = gate.judge(numbers, waivers={"garment.silhouette_pct": ("by eye: no balloon", "cc-64d05f6e")})

`film-qa gate NUMBERS.json [--spec SPEC.json] [--waive ITEM=REASON] [--by NAME]` runs it on the operator's side and
exits 1 on REFUSE.

The numbers contract (every track's check writes one file; the gate merges them):

    {"gate": {"<item id>": {"value": <number|bool>, "where": "<shot fN-M>", "error"?: "<why it could not measure>"}}}

Item ids are `<area>.<measure>_<unit>` (ITEMS below). A track adds or retunes its own items in the round's spec
(`{"items": {id: {"line": .., "op": .., "unit": .., "what": .., "how": .., "r4": [value, source], "area": ..}},
"complaints": [areas]}`), and the line must fail its own round-4 value (`film-qa gate --lines` checks it).
Owners (round 5): lips T1 agent-01, head T2 agent-04, garment fit/clip/silhouette T3a agent-02, cloth T3b
agent-08, hair + the gate T4 agent-09.
"""
from __future__ import annotations

import math

from .issues import issue

OPS = {"<=": lambda v, t: v <= t, ">=": lambda v, t: v >= t, "==": lambda v, t: v == t}

# id -> spec. area: the operator's words the item answers (complaints are matched on it). r4: what round 4 measured
# (None: not measured in round 4; the item's round-5 probe gives it), with its source.
ITEMS: dict = {
    # --- T1: lip sync against the audio (the operator: "lips are moving before even his audio starts, and he has no
    # lip sync at all"). Numbers from perfkit / cast_gate lipgap (the lip bone gap on the evaluated face).
    "lips.lead_in_cm": {
        "area": "lips", "track": "T1", "op": "<=", "line": 0.05, "unit": "cm/frame",
        "what": "worst lip-gap motion in the 1.0 s before each line's audio onset (the speaker silent)",
        "where": "every line, the 24 frames before its first word",
        "how": "cast_gate.py lipgap (silence window = onset-24..onset-1); T1 has no cm measure, so it stays T4's",
        "r4": [0.33, "S13 L1 silence f977-1001 (QA_HANDOFF 08:47), waived as a smirk"],
        "why": "clean silences read 0.003-0.009; the mouth opening before L1 read 0.33"},
    "lips.onset_lead_ms": {
        "area": "lips", "track": "T1", "op": "<=", "line": 250, "unit": "ms",
        "what": "how early the mouth first opens before the line's audio onset (worst line)",
        "where": "every line's first word",
        "how": "film-ue lips gate (agent-01, T1)",
        "r4": [600, "S13 L1: mouth wide f1000-1008 vs audio f1020 (orchestrator, ~0.6-0.8 s)"],
        "why": "natural anticipation is 100-300 ms (Chandrasekaran 2009); 600-800 ms is out of sync"},
    "lips.lag_frames": {
        "area": "lips", "track": "T1", "op": "<=", "line": 1, "unit": "frames",
        "what": "max |lag| over lines: cross-correlation of the syllable-band voice envelope vs mouth aperture",
        "where": "every spoken line", "how": "film-ue lips gate (T1)",
        "r4": [17, "agent-01's estimate of round 4's S13 L1 lead"], "why": "a frame of lag is the limit"},
    "lips.track_r": {
        "area": "lips", "track": "T1", "op": ">=", "line": 0.35, "unit": "r",
        "what": "min over lines of the correlation at the best lag (voice envelope vs mouth aperture)",
        "where": "every spoken line", "how": "film-ue lips gate (T1)",
        "r4": [None, "measured in T1's probe on round 4's face; the operator: no lip sync during his lines"],
        "why": "synthetic good sync 0.9+, wrong words < 0.3"},
    "lips.silence_open": {
        "area": "lips", "track": "T1", "op": "<=", "line": 0.10, "unit": "jawOpen",
        "what": "p95 jaw opening above rest outside the voice activity (+-0.25 s)",
        "where": "every silence of each speaker", "how": "film-ue lips gate (T1)",
        "r4": [None, "T1's probe; round 4 opened before L1"], "why": "a closed mouth in silence"},
    "lips.silence_busy": {
        "area": "lips", "track": "T1", "op": "<=", "line": 0.25, "unit": "ratio",
        "what": "mouth speed in silence / mouth speed on lines", "where": "every speaker",
        "how": "film-ue lips gate (T1)", "r4": [None, "T1's probe"], "why": "talking reads ~1.0"},
    "lips.render_lag_frames": {
        "area": "lips", "track": "T1", "op": "<=", "line": 1, "unit": "frames",
        "what": "lag of the RENDERED mouth crop vs the voice", "where": "every spoken line",
        "how": "film-ue lips gate --render (T1)", "r4": [None, "T1's probe on round 4's finals"],
        "why": "the curves can be right and the render still wrong"},
    "lips.render_conclusive": {
        "area": "lips", "track": "T1", "op": "==", "line": 1, "unit": "bool",
        "what": "the render lag beats a 6-frame shifted-audio control", "where": "every spoken line",
        "how": "film-ue lips gate --render (T1)", "r4": [None, "T1's probe"],
        "why": "an inconclusive measure cannot sign"},
    "lips.cues_fresh": {
        "area": "lips", "track": "T1", "op": "==", "line": 1, "unit": "bool",
        "what": "cues.json rebuilt from this round's stems with real word times (words_lost false)",
        "where": "out/host-studio/reel/cues.json",
        "how": "film-ue lips gate (T1): measured word times, stem sha256 match, no words_lost",
        "r4": [0, "cues.json was round 3's copy, words_lost=true"],
        "why": "lip sync and captions key off the word times; estimated times cannot be in sync"},
    # --- T2: her head nods on blinks
    "head.blink_nod_deg": {
        "area": "head", "track": "T2", "op": "<=", "line": 0.6, "unit": "deg",
        "what": "worst blink's head-pitch departure (head bone forward axis elevation, world), window lid start "
                "-0.1 s to lid open +0.12 s, de-trended by the chord between the window edges",
        "where": "every blink of each presenter (her f1080-1559, him from f960)",
        "how": "film-ue op qa.head_stability + film-qa head-gate (agent-04, T2)",
        "r4": [1.61, "her S17 f1380 glance blink, perfkit alone (before the solver's head); also 1.23 f1397, 0.83 f1145"],
        "why": "the operator: 'every time she blinks her head nods a little down'"},
    "head.blink_locked_deg": {
        "area": "head", "track": "T2", "op": "<=", "line": 0.3, "unit": "deg",
        "what": "blink-triggered average of the de-trended head pitch: small nods on EVERY blink that each stay "
                "under the per-blink line",
        "where": "all blinks of each presenter", "how": "film-qa head-gate (T2)",
        "r4": [None, "T2's probe on round 4's face anims"], "why": "the operator saw it on every blink"},
    # --- T3a/T3b: garments
    "garment.neck_px": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 0, "unit": "px",
        "what": "skin pixels poking through his tee's collar band, worst frame",
        "where": "S13, S15, S17, S18 (6 frames each)",
        "how": "r4/clip_pass.py neck_px",
        "r4": [3, "S15 f1082-1128 1-3 px, waived (QA_HANDOFF 09:1x)"],
        "why": "the operator saw it: any pixel is a clip"},
    "garment.silhouette_pct": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 2.0, "unit": "%",
        "what": "tee silhouette change vs the ACCEPTED round-5 fit's own first pass (render-to-render stability)",
        "where": "S15 hold, S17, S18",
        "how": "r4/tee_silhouette.py against the accepted fit's reference pass (not round 4's Host_after: the refit "
               "adds real ease and would read +4..+8% against it)",
        "r4": [2.23, "S15 f1150-1198 +2.1..+2.23%, waived"],
        "why": "a later render must not drift from the fit the orchestrator accepted"},
    "garment.wpo_cm": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 0.2, "unit": "cm",
        "what": "the material inflate push on his tee (FM_Inflate + FM_Neck + FM_Patch): the rigid-shell cause",
        "where": "his tee's materials", "how": "film-ue garment-gate (agent-02, T3a)",
        "r4": [2.66, "0.15 + 0.75 + 1.76 cm (patch3)"], "why": "the operator: 'heavy armor inside'"},
    "garment.armor_index": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 0.5, "unit": "index",
        "what": "qa.garment_look: ease spread vs the uncut body, wall thickness, wpo, silhouette ratio, normal "
                "detail, motion",
        "where": "S15 f1082/1150, S17 f1397", "how": "film-ue garment-gate --look (T3a)",
        "r4": [None, "probe G3 on the r4 state before the refit (agent-02 expects ~0.7)"],
        "why": "the operator: a smooth, thick, rigid shell"},
    "garment.pair_fraction": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 0.001, "unit": "fraction",
        "what": "worst under>over clip fraction over the non-face pairs (Body>tee, Body>Trousers, Trousers>tee)",
        "where": "S13, S15, S17, S18", "how": "film-ue op qa.clip (T3a)",
        "r4": [0.0067, "Trousers>tee at cast_op4"], "why": "~4 px of a garment"},
    "garment.silhouette_ratio": {
        "area": "garment", "track": "T3a", "op": "<=", "line": 1.12, "unit": "ratio", "guard": True,
        "what": "(garment U body) / uncut body px in the garment's rows: the balloon guard for the refit",
        "where": "S15, S17", "how": "qa.garment_look (T3a)",
        "r4": [None, "a guard, not a regression line: round 4 did not balloon (probe G3 gives its value)"],
        "why": "08:19 round 4: the tee BALLOONED once"},
    "garment.cloth_detail": {
        "area": "garment", "track": "T3b", "op": ">=", "line": None, "unit": "",
        "what": "cloth behaviour: fold/shading detail on the tee's chest (T3b's metric)",
        "where": "S13, S15 close shots",
        "how": "T3b's check",
        "r4": [None, "not measured; the operator: a smooth rigid shell"],
        "why": "T3b sets the line"},
    # --- T4: hair
    "hair.cut_reach_pct": {
        "area": "hair", "track": "T4", "op": "<=", "line": 12.0, "unit": "%",
        "what": "|change| of the hair's reach below the head across each cut, same character (qa/hair.py)",
        "where": "every cut both presenters span; S17->S18 f1440 first",
        "how": "film-ue op qa.hair_continuity (editor), or film-qa hair on rendered frames",
        "r4": [None, "probe P3 re-reads round 4's S17->S18 frames; the operator: 'at 01:00 her hair becomes short'"],
        "why": "qa/hair.py THRESHOLDS: an LOD switch to cards shortens long hair far more; sim/turns move 1-3%"},
    "hair.pop_reach_pct": {
        "area": "hair", "track": "T4", "op": "<=", "line": 8.0, "unit": "%",
        "what": "worst frame-to-frame |change| of the hair's reach inside a shot",
        "where": "every presenter shot",
        "how": "qa.hair_continuity / film-qa hair",
        "r4": [None, "round 3's pop at S17 f1416-1440 (probe P3 re-reads it)"],
        "why": "a mid-shot LOD switch"},
    "hair.lock": {
        "area": "hair", "track": "T4", "op": "==", "line": 1, "unit": "bool",
        "what": "groom.lock_check: every live groom of each presenter at the locked LOD, drawn as strands, in "
                "its LODSync's list, no TRASH_ component",
        "where": "the level, read right before the render",
        "how": "film-ue op groom.lock_check labels=[...]",
        "r4": [0, "gate g read LODSync/skeletal pins only, never a groom"],
        "why": "a pin that does not reach the groom does nothing"},
    "hair.render_cvars": {
        "area": "hair", "track": "T4", "op": "==", "line": 1, "unit": "bool",
        "what": "the final render spec carries groom.lock's render_cvars",
        "where": "the render YAML used for the finals",
        "how": "groom.lock's render_cvars vs the spec's cvars (film-qa gate reads both)",
        "r4": [0, "r3/30-final.yaml cvars lack r.HairStrands.LODMode 0 (951adf24 never merged)"],
        "why": "the engine's auto hair LOD overrides the pin in the render"},
}


def items(spec: dict | None = None) -> dict:
    """ITEMS with a round's overrides ({id: {field: value}}; a new id adds an item)."""
    out = {k: dict(v) for k, v in ITEMS.items()}
    for k, v in (spec or {}).get("items", {}).items():
        out[k] = {**out.get(k, {}), **v}
    return out


def _num(v):
    if isinstance(v, dict):
        return v.get("value"), v
    return v, {}


def check(item_id: str, it: dict, raw) -> dict:
    """One item: {"id", "state": PASS|FAIL, "value", "line", "op", "reason"}."""
    v, extra = _num(raw)
    row = {"id": item_id, "value": v, "line": it.get("line"), "op": it.get("op"), "unit": it.get("unit", ""),
           "area": it.get("area"), "where": extra.get("where") or it.get("where")}
    if it.get("line") is None:
        return {**row, "state": "FAIL", "reason": f"no line set yet ({it.get('track')} sets it): an item without a "
                                                    "line cannot pass"}
    if raw is None or v is None:
        return {**row, "state": "FAIL", "reason": f"not measured: run {it.get('how')}"}
    if extra.get("error"):
        return {**row, "state": "FAIL", "reason": f"the check errored: {extra['error']}"}
    if isinstance(v, bool):
        v = int(v)
    if not isinstance(v, (int, float)) or (isinstance(v, float) and math.isnan(v)):
        return {**row, "state": "FAIL", "reason": f"not a number: {v!r}"}
    ok = OPS[it["op"]](v, it["line"])
    return {**row, "value": v, "state": "PASS" if ok else "FAIL",
            "reason": "" if ok else f"{v} {it.get('unit', '')} is not {it['op']} {it['line']}"}


def judge(numbers: dict, waivers: dict | None = None, spec: dict | None = None, only: list | None = None) -> dict:
    """The gate. `numbers`: {item: value | {"value", "where", "error"}}. `waivers`: {item: (reason, by)}.
    `spec`: {"items": overrides, "complaints": [areas or item ids the operator complained about]}. `only`: judge a
    subset (a per-track pre-check; the full gate never passes `only`).
    Returns {"verdict": SIGN|REFUSE, "rows", "issues", "refused_waivers"}."""
    its = items(spec)
    complaints = set((spec or {}).get("complaints", []))
    rows, issues, refused = [], [], []
    for k, it in its.items():
        if only and k not in only:
            continue
        row = check(k, it, numbers.get(k))
        w = (waivers or {}).get(k)
        if w and row["state"] == "FAIL":
            reason, by = (w if isinstance(w, (list, tuple)) else (w, ""))[:2]
            protected = it.get("complaint") or it.get("area") in complaints or k in complaints
            why_not = ("the operator complained about this" if protected else
                       "a waiver needs a written reason" if not str(reason or "").strip() else
                       "a waiver needs who waived it" if not str(by or "").strip() else "")
            if why_not:
                refused.append({"id": k, "reason": reason, "by": by, "refused": why_not})
            else:
                row.update(state="WAIVED", waiver={"reason": reason, "by": by})
        rows.append(row)
        if row["state"] == "FAIL":
            issues.append(issue(f"gate.{k}", "fail", f"{k}: {row['reason']}" +
                                (f" (round 4 read {it['r4'][0]}: {it['r4'][1]})" if it.get("r4") else ""),
                                f"produce/fix it with: {it.get('how')}", where=row.get("where")))
    for r in refused:
        issues.append(issue("gate.waiver_refused", "fail", f"waiver on {r['id']} refused: {r['refused']}",
                            "fix the item; it cannot be waived", subject=r["id"]))
    verdict = "SIGN" if not any(r["state"] == "FAIL" for r in rows) and not refused else "REFUSE"
    return {"verdict": verdict, "rows": rows, "issues": issues, "refused_waivers": refused,
            "complaints": sorted(complaints)}


def lines_fail(round_values: dict | None = None, spec: dict | None = None) -> dict:
    """The gate's own test: does every item's line fail the round-4 value it is meant to catch? {item: True (it
    fails r4, good) | False (the line would have passed round 4: tighten it) | None (no r4 number yet)}."""
    out = {}
    for k, it in items(spec).items():
        v = (round_values or {}).get(k, (it.get("r4") or [None])[0])
        if v is None or it.get("line") is None or it.get("guard"):  # a guard catches a new failure, not round 4's
            out[k] = None
        else:
            out[k] = not OPS[it["op"]](v, it["line"])
    return out
