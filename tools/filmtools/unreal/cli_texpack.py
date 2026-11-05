"""film-ue texpack: get a texture set ready BEFORE pushing it to the box (WP2). Reads a folder (or files) of PBR
maps, tells what each one is by its name (the bridge's own rules: unreal/fmbridge/ops/_assetlib.py), and writes a
clean set: base colour and normal copied (an OpenGL normal map's green flipped to DirectX when asked), gloss turned
into roughness, and separate AO / roughness / metallic maps packed into ONE ORM texture (R AO, G roughness,
B metallic: what the library's opaque_orm master and Unreal's own content expect: one sampler instead of three).

    film-ue texpack /path/to/rock_4k --out /tmp/rock_set [--flip-green] [--size 2048] [--json]

Then push the out folder and run `mat.pbr --folder <box folder>`. Needs numpy and pillow (pip install pillow).
"""
from __future__ import annotations

import json
import os
import sys

NAMES = ("texpack",)
DEFAULTS = {"ao": 255, "roughness": 128, "metallic": 0}  # a missing channel: AO 1, roughness 0.5, metallic 0


def register(sub) -> None:
    p = sub.add_parser("texpack", help="pack a PBR texture set (separate AO/roughness/metallic -> ORM, gloss -> "
                                       "roughness, OpenGL normals) before pushing it to the box")
    p.add_argument("src", nargs="+", help="a folder of maps, or the map files")
    p.add_argument("--out", required=True, help="where the clean set is written")
    p.add_argument("--flip-green", action="store_true", help="flip OpenGL (_gl) normal maps to DirectX")
    p.add_argument("--size", type=int, default=0, help="resize every map to this square size (0 = keep)")
    p.add_argument("--json", action="store_true")


def _lib():
    from .assets_kinds import _pure
    lib = _pure("_assetlib.py")
    if lib is None:
        raise SystemExit("texpack needs the repo's unreal/fmbridge/ops/_assetlib.py (run it from a full checkout)")
    return lib


def _files(src: list) -> list:
    out = []
    for s in src:
        if os.path.isdir(s):
            out += [os.path.join(s, f) for f in sorted(os.listdir(s))]
        else:
            out.append(s)
    return out


def pack(src: list, out: str, *, flip_green: bool = False, size: int = 0) -> dict:
    """Write the clean set(s) into `out`; returns {"sets": {name: {"files": {role: path}, "packed": bool, "notes"}},
    "ignored": [files]}."""
    import numpy as np
    from PIL import Image
    lib = _lib()
    files = _files(src)
    sets = lib.texture_set(files)
    ignored = sets.pop("_unknown", [])
    os.makedirs(out, exist_ok=True)
    res = {"sets": {}, "ignored": ignored}

    def load(path, mode):
        im = Image.open(path)
        if im.mode in ("I;16", "I;16B", "I"):  # 16-bit greyscale: to 8-bit
            im = Image.fromarray((np.asarray(im, dtype=np.float64) / 257.0).clip(0, 255).astype(np.uint8))
        im = im.convert(mode)
        if size:
            im = im.resize((size, size), Image.LANCZOS)
        return im

    for name, roles in sorted(sets.items()):
        base = name if name.lower().startswith("t_") else f"T_{name}"
        base = "".join(c if c.isalnum() or c == "_" else "_" for c in base)
        made, notes = {}, []
        if "base_color" in roles:
            p = os.path.join(out, f"{base}_BaseColor.png")
            load(roles["base_color"], "RGBA" if Image.open(roles["base_color"]).mode in ("RGBA", "LA") else
                 "RGB").save(p)
            made["base_color"] = p
        if "normal" in roles:
            im = load(roles["normal"], "RGB")
            if flip_green and lib.texture_role(roles["normal"])["flip_green"]:
                a = np.asarray(im).copy()
                a[..., 1] = 255 - a[..., 1]
                im = Image.fromarray(a)
                notes.append("normal: OpenGL green flipped to DirectX")
            p = os.path.join(out, f"{base}_Normal.png")
            im.save(p)
            made["normal"] = p
        for role, suffix in (("emissive", "Emissive"), ("opacity", "Opacity"), ("height", "Height"),
                             ("translucency", "Translucency")):
            if role in roles:
                p = os.path.join(out, f"{base}_{suffix}.png")
                load(roles[role], "RGB" if role in ("emissive", "translucency") else "L").save(p)
                made[role] = p
        rough = roles.get("roughness")
        gloss = roles.get("gloss") if not rough else None
        if "orm" in roles and not any(k in roles for k in ("ao", "roughness", "metallic", "gloss")):
            pack_ = lib.texture_role(roles["orm"])["packing"] or ["ao", "roughness", "metallic"]
            im = load(roles["orm"], "RGB")
            if pack_ != ["ao", "roughness", "metallic"]:  # reorder RMA/MRA... into ORM
                ch = dict(zip(pack_, im.split()))
                im = Image.merge("RGB", (ch["ao"], ch["roughness"], ch["metallic"]))
                notes.append(f"packed {''.join(c[0].upper() for c in pack_)} reordered to ORM")
            p = os.path.join(out, f"{base}_ORM.png")
            im.save(p)
            made["orm"] = p
        elif any(k in roles for k in ("ao", "roughness", "metallic", "gloss")):
            chans, shape = {}, None
            for role in ("ao", "roughness", "metallic"):
                f = roles.get(role) or (gloss if role == "roughness" else None)
                if f:
                    a = np.asarray(load(f, "L"))
                    if role == "roughness" and gloss:
                        a = 255 - a
                        notes.append("gloss inverted into roughness")
                    chans[role] = a
                    shape = shape or a.shape
            for role in ("ao", "roughness", "metallic"):
                if role in chans and chans[role].shape != shape:
                    chans[role] = np.asarray(Image.fromarray(chans[role]).resize((shape[1], shape[0]),
                                                                                  Image.LANCZOS))
                if role not in chans:
                    chans[role] = np.full(shape, DEFAULTS[role], dtype=np.uint8)
                    notes.append(f"no {role} map: {DEFAULTS[role]} in its channel")
            p = os.path.join(out, f"{base}_ORM.png")
            Image.fromarray(np.dstack([chans["ao"], chans["roughness"], chans["metallic"]]).astype(np.uint8)).save(p)
            made["orm"] = p
        res["sets"][base] = {"files": made, "packed": "orm" in made, "notes": notes, "from": roles}
    return res


def dispatch(a) -> bool:
    if a.cmd not in NAMES:
        return False
    try:
        r = pack(a.src, a.out, flip_green=a.flip_green, size=a.size)
    except ImportError as e:
        print(f"texpack needs numpy and pillow: {e} (pip install pillow)", file=sys.stderr)
        raise SystemExit(2)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        for name, s in r["sets"].items():
            print(f"{name}: " + ", ".join(f"{k} {os.path.basename(v)}" for k, v in s["files"].items()))
            for n in s["notes"]:
                print(f"  {n}")
        if r["ignored"]:
            print("not a map by its name (rename it, e.g. _BaseColor): " + ", ".join(map(os.path.basename,
                                                                                           r["ignored"])))
        print(f"next: push {a.out} to the box, then film-ue mat pbr --path /Game/<Folder>/MI_<Name> "
              f"--folder <box folder>")
    raise SystemExit(0)
