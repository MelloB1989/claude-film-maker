"""WP2's spec kinds: `material` (an instance of a library master or any material, a named preset, or a whole graph)
and `asset` (a file imported to a path, with its mesh settings, texture role and tags). Materials apply after assets
(order 12 vs 10), so a material names the mesh slots it goes on (`assign`).
`film-ue apply` converges them through mat.* and assets.*; the second plan is empty once they match.

    kind: material
    version: 1
    name: rock
    path: /Game/Set/Mats/MI_Rock
    master: opaque_orm                    # or parent: /Game/..., or preset: chrome, or graph: {nodes, outputs}
    params: {Tint: [1, 1, 1], BaseColorMap: /Game/Set/Tex/T_Rock_BaseColor, Roughness: 1.0}
    assign: [{mesh: /Game/Set/Props/SM_Chair, slot: 0}]   # mesh asset slots that wear it (after assets apply)
    ---
    kind: asset
    version: 1
    name: chair
    file: /data/props/chair.fbx           # on the box
    dest: /Game/Set/Props
    asset: SM_Chair                       # the asset's name in dest (default: the file's stem)
    import: {collision: convex, kind: static}
    mesh: {nanite: true, lods: 3}
    tags: {category: furniture}

Planning is pure (no unreal, no I/O but reading the library's master/preset tables from the repo).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_lib_cache: dict = {}


def _pure(rel: str):
    """An engine-free bridge module (unreal/fmbridge/ops/_x.py) when this checkout has unreal/, else None."""
    if rel in _lib_cache:
        return _lib_cache[rel]
    p = _REPO / "unreal" / "fmbridge" / "ops" / rel
    mod = None
    if p.exists():
        spec = importlib.util.spec_from_file_location(f"_wp2_{p.stem}", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    _lib_cache[rel] = mod
    return mod


def master_path(name: str) -> str:
    """The library master's package path (unreal/fmbridge/ops/_matlib.py master_path)."""
    return "/Game/FM/Lib/M_Lib_" + "".join(p.capitalize() for p in name.split("_"))


def fingerprint(graph: dict) -> str:
    """unreal/fmbridge/ops/_matgraph.py fingerprint: what a built graph material carries as metadata."""
    s = json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def _pkg(p) -> str:
    p = str(p or "")
    last = p.rsplit("/", 1)[-1]
    return p[: len(p) - len(last)] + last.split(".", 1)[0] if "." in last else p


def _same(have, want, tol: float = 1e-4) -> bool:
    if isinstance(want, bool) or isinstance(have, bool):
        return bool(have) == bool(want)
    if isinstance(want, (int, float)):
        return isinstance(have, (int, float)) and abs(float(have) - float(want)) <= tol
    if isinstance(want, (list, tuple)):
        w = list(want) + [1.0] * (4 - len(want)) if len(want) in (3,) else list(want)
        h = list(have or [])
        if len(h) == 4 and len(w) == 3:
            w = w + [1.0]
        return len(h) == len(w) and all(_same(a, b, tol) for a, b in zip(h, w))
    if isinstance(want, str) and want.startswith("/"):
        return _pkg(have) == _pkg(want)
    return have == want


# ----------------------------------------------------------------------------------------------------- material

def plan_material(spec: dict, state: dict | None) -> list:
    """Steps for one material document. state: mat.describe (None/{"missing": True} when it does not exist)."""
    path = spec["path"]
    modes = [k for k in ("master", "parent", "preset", "graph") if spec.get(k)]
    if len(modes) != 1:
        raise ValueError(f"material {spec.get('name')}: give exactly one of master, parent, preset, graph "
                         f"(got {modes or 'none'})")
    mode = modes[0]
    params = dict(spec.get("params") or {})
    missing = not state or state.get("missing")
    if mode == "graph":
        if missing or state.get("fingerprint") != fingerprint(spec["graph"]):
            return [{"op": "mat.graph", "args": {"path": path, "spec": spec["graph"]},
                     "why": "missing" if missing else "the graph changed"}]
        return []
    if mode == "preset":
        lib = _pure("_matlib.py")
        if lib is not None and spec["preset"] in lib.PRESETS:
            m, vals = lib.PRESETS[spec["preset"]]
            want_parent, want = master_path(m), {**vals, **params}
        else:  # no table here: check only what the spec names
            want_parent, want = None, params
        args = {"path": path, "name": spec["preset"], "params": params}
        if missing:
            return [{"op": "mat.preset", "args": args, "why": "missing"}]
        why = _diff(state, want_parent, want)
        return [{"op": "mat.preset", "args": args, "why": why}] if why else []
    want_parent = master_path(spec["master"]) if mode == "master" else _pkg(spec["parent"])
    args = {"path": path, mode: spec[mode], "params": params}
    if missing:
        return [{"op": "mat.instance", "args": args, "why": "missing"}]
    why = _diff(state, want_parent, params)
    return [{"op": "mat.instance", "args": args, "why": why}] if why else []


def _diff(state: dict, want_parent: str | None, want: dict) -> str:
    chain = state.get("chain") or []
    if want_parent and (len(chain) < 2 or _pkg(chain[1]) != want_parent):
        return f"parent {chain[1] if len(chain) > 1 else None} -> {want_parent}"
    have = state.get("params") or {}
    for k, v in want.items():
        h = (have.get(k) or {}).get("value")
        if not _same(h, v):
            return f"{k} {h} -> {v}"
    return ""


def _assign_steps(spec: dict, state: dict | None) -> list:
    steps = []
    slots_of = (state or {}).get("_slots", {})
    for a in spec.get("assign") or []:
        mesh, slot = a["mesh"], a.get("slot", 0)
        slots = slots_of.get(mesh) or []
        cur = next((s for s in slots if (s["index"] == slot if isinstance(slot, int) else s["name"] == slot)), {})
        if _pkg(cur.get("material")) != _pkg(spec["path"]):
            steps.append({"op": "mat.assign", "args": {"mesh": mesh, "material": spec["path"], "slot": slot},
                          "why": f"{mesh} slot {slot}: {cur.get('material')} -> {spec['path']}"})
    return steps


def plan_material_and_slots(spec: dict, state: dict | None) -> list:
    return plan_material(spec, state) + _assign_steps(spec, state)


def describe_material(ue, spec: dict) -> dict:
    try:
        st = ue.mat.describe(path=spec["path"])
    except Exception as e:
        if "not_found" in str(getattr(e, "code", "")) or "no material" in str(e):
            st = {"missing": True}
        else:
            raise
    slots = {}
    for a in spec.get("assign") or []:
        try:
            slots[a["mesh"]] = ue.assets.describe(path=a["mesh"], refs=False).get("materials", [])
        except Exception:
            slots[a["mesh"]] = []
    st["_slots"] = slots
    return st


# -------------------------------------------------------------------------------------------------------- asset

_IMAGES = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".psd", ".exr", ".hdr", ".dds")


def asset_path(spec: dict) -> str:
    """Where the import lands. Images are named as assets.import_textures names them (T_ + the stem, made a valid
    name); other files by `asset`, else the stem."""
    stem, ext = os.path.splitext(os.path.basename(spec["file"].replace("\\", "/")))
    if ext.lower() in _IMAGES:
        lib = _pure("_assetlib.py")
        name = lib.safe_name(stem) if lib is not None else stem
        name = name if name.startswith("T_") else "T_" + name
    else:
        name = spec.get("asset") or stem
    return f"{spec['dest'].rstrip('/')}/{name}"


def plan_asset(spec: dict, state: dict | None) -> list:
    """Steps for one asset document. state: assets.describe of the expected path (None/{"missing": True})."""
    path = asset_path(spec)
    imp = dict(spec.get("import") or {})
    steps = []
    missing = not state or state.get("missing")
    src_changed = (not missing and state.get("source") and
                   os.path.basename(str(state["source"]).replace("\\", "/")).lower()
                   != os.path.basename(spec["file"].replace("\\", "/")).lower())
    if missing or src_changed or spec.get("reimport"):
        args = {"files": [spec["file"]], "dest": spec["dest"], "replace": True, **imp}
        if spec.get("asset"):
            args["name"] = spec["asset"]
        steps.append({"op": "assets.import", "args": args,
                      "why": "missing" if missing else "the source file changed" if src_changed else "reimport"})
        state = {}
    mesh = dict(spec.get("mesh") or {})
    if mesh:
        h = state or {}
        need = (not h or ("nanite" in mesh and bool(h.get("nanite")) != bool(mesh["nanite"]))
                or ("lods" in mesh and h.get("lods") != mesh["lods"])
                or ("collision" in mesh and (mesh["collision"] == "none") != (not (h.get("collision") or {}).get(
                    "simple"))))
        if need:
            steps.append({"op": "assets.mesh", "args": {"path": path, **mesh}, "why": "mesh settings differ"})
    if spec.get("texture_role"):
        h = state or {}
        steps += [] if h and h.get("_role_ok") else [{"op": "assets.texture", "args": {
            "path": path, "role": spec["texture_role"]}, "why": "texture settings for its role"}]
    tags = {str(k): str(v) for k, v in (spec.get("tags") or {}).items()}
    if tags and any((state or {}).get("tags", {}).get(k) != v for k, v in tags.items()):
        steps.append({"op": "assets.tag", "args": {"path": path, "set": tags}, "why": "tags differ"})
    return steps


def describe_asset(ue, spec: dict) -> dict:
    try:
        st = ue.assets.describe(path=asset_path(spec), refs=False)
    except Exception as e:
        if "not_found" in str(getattr(e, "code", "")) or "no asset" in str(e):
            return {"missing": True}
        raise
    role = spec.get("texture_role")
    if role and st.get("class", "").startswith("Texture"):
        lib = _pure("_assetlib.py")
        if lib is not None and role in lib.ROLES:
            _, srgb, comp, _ = lib.ROLES[role]
            st["_role_ok"] = st.get("srgb") == srgb and str(st.get("compression", "")).upper().endswith(comp)
    return st


SPEC_KINDS = [
    {"name": "material", "plan": plan_material_and_slots, "describe": describe_material, "order": 12,
     "doc": "A material: an instance of a library master (mat.masters) or of any material with parameters, a named "
            "preset (mat.presets), or a node graph (mat.graph); and the mesh slots that wear it."},
    {"name": "asset", "plan": plan_asset, "describe": describe_asset, "order": 10,
     "doc": "A file on the box imported to a content path, with its mesh settings, texture role and tags."},
]
