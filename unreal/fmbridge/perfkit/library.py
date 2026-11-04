"""The animation library: what an animation is, from its path, and a search that ranks a project's animations for
a plain-words query ("happy face loop", "walk forward loop", "idle body").

`KNOWN` is the MetaHuman Creator's optional template animations as the 5.8 plugin ships them (an inventory taken on
the workstation: films/host-studio/reel/previs/metahuman_animations.json). The MetaHuman plugin's content is not in
the engine source, so anim.find reads the live asset registry; KNOWN is the fallback a client can search offline and
the vocabulary `infer` understands.
"""
from __future__ import annotations

import re

MH = "/MetaHumanCharacter/Optional/Animation"
_T = MH + "/TemplateAnimations"
_L = MH + "/UEFNAnimPreset/Locomotion"
KNOWN = [
    _T + "/Technical_Loops/Idle/mhc_mh001_fmn_b_idle",
    _T + "/Technical_Loops/Idle/mhc_mh001_fmn_f_idle",
    _T + "/Technical_Loops/BodyROM/mhc_body_rom_body",
    _T + "/Technical_Loops/BodyROM/mhc_body_rom_face",
    _T + "/Technical_Loops/FaceROM/mhc_mh001_fmn_b_rom_face",
    _T + "/Technical_Loops/FaceROM/mhc_mh001_fmn_rom_face",
] + [f"{_T}/Expression_Loops/{e}{v}/mhc_mh002_fmn_{bf}_facialloop_{n}_{g}_s00{k}"
     for e, n, rows in (("Anger", "angry", (("A", "f", "f", 1), ("A", "b", "f", 1), ("B", "f", "m", 1), ("B", "b", "m", 1))),
                        ("Fear", "fear", (("A", "f", "f", 1), ("A", "b", "f", 1), ("B", "f", "m", 1), ("B", "b", "m", 1))),
                        ("Happy", "happy", (("A", "f", "f", 1), ("A", "b", "f", 1), ("B", "b", "m", 1))),
                        ("Sad", "sad", (("A", "f", "f", 1), ("A", "b", "f", 1), ("B", "f", "m", 1), ("B", "b", "m", 1))),
                        ("Surprise", "surprise", (("A", "f", "f", 1), ("A", "b", "m", 1), ("B", "f", "m", 1), ("B", "b", "m", 2))))
     for v, bf, g, k in rows] + [
    _T + "/Expression_Loops/HappyB/ue_mh002_fmn_f_facialloop_happy_m_s001",
] + [f"{_T}/Facial_Poses/{e}/mhc_mh002_fmn_f_gpf_{e.lower()}_s001" for e in ("Anger", "Fear", "Happy", "Sad", "Surprise")] + [
    f"{_L}/AS_MH_Neutral_{gait}_{phase}" for gait in ("Walk", "Run") for phase in
    ("Loop_F", "Loop_B", "Loop_LR", "Loop_RL")] + [
    _L + "/AS_MH_Neutral_Walk_Start_F_Rfoot", _L + "/AS_MH_Neutral_Walk_Start_B_Lfoot",
    _L + "/AS_MH_Neutral_Walk_Start_LR_Lfoot", _L + "/AS_MH_Neutral_Walk_Start_RL_Rfoot",
    _L + "/AS_MH_Neutral_Walk_Stop_F_Lfoot", _L + "/AS_MH_Neutral_Walk_Stop_B_Rfoot",
    _L + "/AS_MH_Neutral_Walk_Stop_LR_Lfoot", _L + "/AS_MH_Neutral_Walk_Stop_RL_Rfoot",
    _L + "/AS_MH_Neutral_Run_Start_F_Lfoot", _L + "/AS_MH_Neutral_Run_Start_B_Lfoot",
    _L + "/AS_MH_Neutral_Run_Start_LR_Lfoot", _L + "/AS_MH_Neutral_Run_Start_RL_Rfoot",
    _L + "/AS_MH_Neutral_Run_Stop_F_Lfoot", _L + "/AS_MH_Neutral_Run_Stop_B_Rfoot",
    _L + "/AS_MH_Neutral_Run_Stop_LR_Lfoot", _L + "/AS_MH_Neutral_Run_Stop_RL_Rfoot",
    _L + "/AS_MH_Neutral_Stand_Idle_Loop",
]

EMOTIONS = {"angry": "anger", "anger": "anger", "fear": "fear", "happy": "happy", "sad": "sad", "surprise": "surprise"}
SYNONYMS = {"happy": ["joy", "smile", "smiling", "glad"], "anger": ["angry", "mad", "furious"], "sad": ["sadness", "unhappy"],
            "fear": ["afraid", "scared", "fearful"], "surprise": ["surprised", "shock", "shocked"],
            "idle": ["rest", "standing", "stand", "breathing"], "walk": ["walking", "stroll"],
            "run": ["running", "jog"], "face": ["facial", "expression"], "body": ["full", "fullbody"],
            "loop": ["cycle", "looping"], "forward": ["fwd", "ahead", "f"], "backward": ["back", "b"],
            "start": ["begin", "starting"], "stop": ["end", "stopping"], "pose": ["still", "static"],
            "rom": ["range", "calibration", "test"]}


def words(s: str) -> list:
    """Lower-case words of a path or query: camelCase, snake_case and digits split."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return [w for w in re.split(r"[^a-zA-Z0-9]+", s.lower()) if w]


def infer(path: str) -> dict:
    """What an animation is, from its path: {"kind": face|body|?, "category": idle|expression_loop|facial_pose|
    locomotion|rom|other, "emotion", "gait", "phase" (start|loop|stop), "direction" (forward|backward|left_right|
    right_left), "tags": [...]}. MetaHuman naming: _f_ face, _b_ body; Loop_F/B/LR/RL directions."""
    p = path.split(".")[0]
    name = p.rsplit("/", 1)[-1]
    low = p.lower()
    w = words(name)
    d = {"kind": "?", "category": "other", "emotion": None, "gait": None, "phase": None, "direction": None}
    if "_f_" in name or name.endswith("_rom_face") or "facial_poses" in low:
        d["kind"] = "face"
    if "_b_" in name or "locomotion" in low or name.endswith("_rom_body"):
        d["kind"] = "body"
    if "idle" in w:
        d["category"] = "idle"
    elif "facialloop" in w or "expression_loops" in low:
        d["category"] = "expression_loop"
    elif "gpf" in w or "facial_poses" in low:
        d["category"] = "facial_pose"
    elif "rom" in w:
        d["category"] = "rom"
    if "walk" in w or "run" in w:
        d["category"] = "locomotion"
        d["gait"] = "walk" if "walk" in w else "run"
        d["kind"] = "body"
    for k, v in EMOTIONS.items():
        if k in w:
            d["emotion"] = v
    for ph in ("start", "loop", "stop"):
        if ph in w:
            d["phase"] = ph
    m = re.search(r"_(F|B|LR|RL)(?:_|$)", name)
    if m and d["category"] == "locomotion":
        d["direction"] = {"F": "forward", "B": "backward", "LR": "left_right", "RL": "right_left"}[m.group(1)]
    tags = [x for x in (d["kind"], d["category"], d["emotion"], d["gait"], d["phase"], d["direction"]) if x and x != "?"]
    d["tags"] = tags
    return d


def _expand(q: list) -> set:
    out = set(q)
    for w in q:
        for k, syn in SYNONYMS.items():
            if w == k or w in syn:
                out.add(k)
                out.update(syn)
    return out


def score(path: str, query: str, info: dict | None = None) -> float:
    """How well an animation's path (and inferred tags) matches a plain-words query: each query word found in the
    tags counts 3, in the path's words 2, as a prefix of a path word 1; unmatched words cost 1. 0 = no match."""
    q = words(query)
    if not q:
        return 1.0
    info = info or infer(path)
    pw = words(path.split(".")[0])
    tags = set(info["tags"]) | {t.replace("_", "") for t in info["tags"]}
    s = 0.0
    for w in q:
        alts = _expand([w])
        if alts & tags:
            s += 3
        elif alts & set(pw):
            s += 2
        elif any(x.startswith(w) for x in pw if len(w) >= 3):
            s += 1
        else:
            s -= 1
    return max(0.0, s)


def search(paths: list, query: str = "", kind: str = "", limit: int = 20) -> list:
    """Rank `paths` for `query` (and `kind` face/body): [{"path", "score", **infer(path)}], best first."""
    out = []
    for p in paths:
        info = infer(p)
        if kind and info["kind"] not in (kind, "?"):
            continue
        sc = score(p, query, info)
        if sc > 0:
            out.append({"path": p.split(".")[0], "score": sc, **info})
    out.sort(key=lambda d: (-d["score"], d["path"]))
    return out[:limit]
