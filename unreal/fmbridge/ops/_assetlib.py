"""Pure helpers of the assets area (WP2): no `unreal` here, so the client and the unit tests use them as they are.

- paths: package path from any spelling (`/Game/A/B.B`, `StaticMesh'/Game/A/B.B'`), split, join, validate.
- textures: the role of a texture from its file name (base colour, normal, roughness, packed ORM...), the settings
  that role needs (sRGB, compression, the material sampler), a texture set grouped from a folder of files, and a
  cheap look at a PNG's pixels to tell a normal map that is not named as one.
- the catalog query: "a 45 cm chair" -> words and sizes, and the score of a catalog entry against it.
"""
from __future__ import annotations

import os
import re
import struct
import zlib

# ---------------------------------------------------------------------------------------------------------- paths

_PATH_RE = re.compile(r"^/[A-Za-z0-9_]+(/[A-Za-z0-9_\-\.]+)*$")


def package_path(path: str) -> str:
    """`/Game/A/B`, `/Game/A/B.B`, `/Game/A/B.B:Sub`, `StaticMesh'/Game/A/B.B'` -> `/Game/A/B`."""
    p = str(path or "").strip()
    m = re.match(r"^[A-Za-z0-9_]+'(.*)'$", p)
    if m:
        p = m.group(1)
    p = p.split(":", 1)[0]
    last = p.rsplit("/", 1)[-1]
    if "." in last:
        p = p[: len(p) - len(last)] + last.split(".", 1)[0]
    return p.rstrip("/")


def object_path(path: str) -> str:
    """`/Game/A/B` -> `/Game/A/B.B` (what the asset registry and `load_object` want)."""
    p = package_path(path)
    return f"{p}.{p.rsplit('/', 1)[-1]}"


def split(path: str) -> tuple:
    """`/Game/A/B` -> (`/Game/A`, `B`)."""
    p = package_path(path)
    folder, _, name = p.rpartition("/")
    return folder, name


def valid_path(path: str) -> str:
    """An error message if `path` cannot be a content path, else ''."""
    p = package_path(path)
    if not p.startswith("/"):
        return f"{path!r} is not a content path: it starts with a mount point, like /Game/Props/SM_Chair"
    if not _PATH_RE.match(p):
        return f"{path!r} has characters a package name cannot have (letters, digits, _ and - only)"
    if p.count("/") < 2:
        return f"{path!r} names a mount point, not an asset: give /Game/<Folder>/<Name>"
    return ""


def safe_name(name: str) -> str:
    """A file stem made into an asset name: spaces and punctuation to _, never starting with a digit."""
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(name)).strip("_") or "Asset"
    return ("A_" + s) if s[0].isdigit() else s


# ------------------------------------------------------------------------------------------------------- textures

# role -> (tokens that name it, sRGB, compression, material sampler type)
# Data maps (everything but colour) are linear and use TC_MASKS with the Masks sampler: a TC_MASKS map sampled as
# Color or Linear Color does not compile and the engine draws its checker (unreal/README.md).
ROLES = {
    "base_color": (("basecolor", "base_color", "albedo", "diffuse", "diff", "color", "colour", "col", "alb", "bc",
                    "d", "c", "a"), True, "TC_DEFAULT", "SAMPLERTYPE_COLOR"),
    "normal": (("normal", "normals", "nrm", "nor", "norm", "nml", "n", "normalgl", "normal_gl", "normaldx",
                "normal_dx", "nrm_gl", "nrm_dx"), False, "TC_NORMALMAP", "SAMPLERTYPE_NORMAL"),
    "roughness": (("roughness", "rough", "rgh", "r"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "gloss": (("gloss", "glossiness", "smoothness", "g"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "metallic": (("metallic", "metalness", "metal", "met", "mtl", "m"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "ao": (("ao", "ambientocclusion", "ambient_occlusion", "occlusion", "occ", "o"), False, "TC_MASKS",
           "SAMPLERTYPE_MASKS"),
    "orm": (("orm", "arm", "rma", "mra", "rmo", "packed", "mask", "masks", "mk"), False, "TC_MASKS",
            "SAMPLERTYPE_MASKS"),
    "opacity": (("opacity", "alpha", "transparency", "opac", "op"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "height": (("height", "displacement", "disp", "displace", "bump", "h"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "emissive": (("emissive", "emission", "emit", "glow", "e"), True, "TC_DEFAULT", "SAMPLERTYPE_COLOR"),
    "specular": (("specular", "spec", "s"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "translucency": (("translucency", "transmission", "sss", "subsurface", "scattering", "thickness"), True,
                     "TC_DEFAULT", "SAMPLERTYPE_COLOR"),
    "cavity": (("cavity", "cav"), False, "TC_MASKS", "SAMPLERTYPE_MASKS"),
    "fuzz": (("fuzz", "sheen"), True, "TC_DEFAULT", "SAMPLERTYPE_COLOR"),
}
# which channel carries what in a packed map, by the token that names it (R, G, B)
PACKING = {"orm": ("ao", "roughness", "metallic"), "arm": ("ao", "roughness", "metallic"),
           "rma": ("roughness", "metallic", "ao"), "mra": ("metallic", "roughness", "ao"),
           "rmo": ("roughness", "metallic", "ao"), "packed": ("ao", "roughness", "metallic"),
           "mask": ("roughness", "metallic", "ao"), "masks": ("roughness", "metallic", "ao"),
           "mk": ("roughness", "metallic", "ao")}
HDR_EXT = (".exr", ".hdr")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".psd", ".exr", ".hdr", ".dds")
_ONE_LETTER = {t for spec in ROLES.values() for t in spec[0] if len(t) == 1}
_TOKEN_ROLE = {}
for _role, _spec in ROLES.items():
    for _t in _spec[0]:
        _TOKEN_ROLE.setdefault(_t, _role)
_RES = re.compile(r"^(\d+k|\d{3,5}(x\d{3,5})?|lod\d+|udim|\d{4}|v\d+)$")  # 4k, 2048, 1001 (UDIM), LOD0, v2


def _tokens(stem: str) -> list:
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", stem)  # BaseColor -> Base_Color: keep both the joined and split forms
    return [t for t in re.split(r"[\s_\-\.]+", s.lower()) if t]


def texture_role(filename: str) -> dict:
    """What a texture is from its file name: {"role", "srgb", "compression", "sampler", "packing", "flip_green",
    "token", "set"} where `set` is the name with the role (and a resolution like 4K) taken off, so the maps of one
    material share it. role is "" when the name does not say (treat it as colour; `probe_png` can tell a normal
    map). Rules: the LAST token that names a role wins (T_Wood_Normal_4K -> normal); one-letter tokens (_N, _R, _D)
    count only at the end; `_gl`/`opengl` normal maps get flip_green (Unreal is DirectX, Y down); .exr/.hdr is
    HDR colour."""
    base = os.path.basename(str(filename))
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    out = {"role": "", "srgb": True, "compression": "TC_DEFAULT", "sampler": "SAMPLERTYPE_COLOR", "packing": None,
           "flip_green": False, "token": "", "set": stem}
    if ext in HDR_EXT:
        out.update(srgb=False, compression="TC_HDR", role="hdr", sampler="SAMPLERTYPE_COLOR")
    raw = _tokens(stem)
    toks = list(raw)
    while toks and _RES.match(toks[-1]):  # T_Wood_Normal_4K: the resolution is not the role
        toks.pop()
    joined = "".join(toks)
    found = None
    for i in range(len(toks) - 1, -1, -1):
        t = toks[i]
        if i > 1:  # two tokens naming one role: base_color, ambient_occlusion, normal_gl
            pair = toks[i - 1] + "_" + t
            for key in (pair, pair.replace("_", "")):
                if key in _TOKEN_ROLE and key != t:
                    found = (i - 1, 2, key)
                    break
            if found:
                break
        alone = len(toks) == 1 and len(t) > 2  # a file called just Normal.png
        if t in _TOKEN_ROLE and (t not in _ONE_LETTER or i == len(toks) - 1) and (i > 0 or alone):
            found = (i, 1, t)
            break
    if found is None:
        for key in ("basecolor", "ambientocclusion", "normalgl", "normaldx"):
            if joined.endswith(key) and len(joined) > len(key):
                found = (len(toks) - 1, 1, key)
                break
    if found is None:
        return out
    i, n, tok = found
    role = _TOKEN_ROLE[tok]
    _, srgb, comp, sampler = ROLES[role]
    out.update(role=role, srgb=srgb, compression=comp, sampler=sampler, token=tok)
    if role == "orm":
        out["packing"] = list(PACKING.get(tok, PACKING["orm"]))
    if role == "normal" and ("gl" in tok or "gl" in raw or "opengl" in raw):
        out["flip_green"] = True
    rest = toks[:i] + toks[i + n:]
    rest = [t for t in rest if t not in ("gl", "dx", "opengl", "directx") and not _RES.match(t)]
    out["set"] = "_".join(rest) if rest else stem
    return out


def texture_set(files: list) -> dict:
    """Group texture files into sets by their shared name: {set: {role: file}}, plus "_unknown": [files] for names
    that say nothing. A set's key is in lower case (T_Rock_BaseColor.png and T_Rock_Normal.png -> "t_rock")."""
    sets: dict = {}
    unknown = []
    for f in files:
        if os.path.splitext(str(f))[1].lower() not in IMAGE_EXT:
            continue
        r = texture_role(f)
        if not r["role"] or r["role"] == "hdr":
            unknown.append(f)
            continue
        sets.setdefault(r["set"].lower(), {}).setdefault(r["role"], f)
    if unknown:
        sets["_unknown"] = unknown
    return sets


def pbr_inputs(roles: dict) -> dict:
    """From a set's {role: file} to the material channels and where each comes from: {"base_color": (role, "RGB"),
    "roughness": ("orm", "G") or ("roughness", "R"), ...}. Gloss stands in for roughness (inverted: "invert": True).
    """
    out: dict = {}
    if "base_color" in roles:
        out["base_color"] = ("base_color", "RGB")
    if "normal" in roles:
        out["normal"] = ("normal", "RGB")
    if "emissive" in roles:
        out["emissive"] = ("emissive", "RGB")
    if "opacity" in roles:
        out["opacity"] = ("opacity", "R")
    if "orm" in roles:
        pack = texture_role(roles["orm"])["packing"] or list(PACKING["orm"])
        for ch, what in zip("RGB", pack):
            out.setdefault(what, ("orm", ch))
    for what in ("roughness", "metallic", "ao", "specular", "height", "translucency"):
        if what in roles:
            out[what] = (what, "RGB" if what == "translucency" else "R")
    if "roughness" not in out and "gloss" in roles:
        out["roughness"] = ("gloss", "R", "invert")
    return out


def probe_png(path: str, rows: int = 64) -> dict:
    """A cheap look at a PNG's pixels (the first `rows` rows, decoded in pure Python): {"width", "height",
    "channels", "mean": [r, g, b] 0..1, "normal_like": bool}. A tangent-space normal map averages near (0.5, 0.5,
    1.0) with blue never low. {} for anything this cannot read (16-bit, palette, interlaced, not a PNG)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return {}
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return {}
    pos, idat, w = 8, [], 0
    h = depth = ctype = interlace = 0
    while pos + 8 <= len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
        pos += 12 + n
    chans = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if not w or depth != 8 or interlace or chans is None:
        return {}
    stride = w * chans
    want = min(h, rows)
    raw = zlib.decompressobj().decompress(b"".join(idat), want * (stride + 1))
    prev = bytearray(stride)
    sums = [0, 0, 0]
    low_blue = 0
    count = 0
    for r in range(want):
        line = raw[r * (stride + 1):(r + 1) * (stride + 1)]
        if len(line) < stride + 1:
            break
        ft, cur = line[0], bytearray(line[1:])
        for i in range(stride):
            a = cur[i - chans] if i >= chans else 0
            b = prev[i]
            c = prev[i - chans] if i >= chans else 0
            if ft == 1:
                cur[i] = (cur[i] + a) & 255
            elif ft == 2:
                cur[i] = (cur[i] + b) & 255
            elif ft == 3:
                cur[i] = (cur[i] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        for x in range(0, stride, chans * max(1, w // 256)):  # at most ~256 samples a row
            px = cur[x:x + chans]
            rgb = (px[0], px[0], px[0]) if chans < 3 else (px[0], px[1], px[2])
            sums[0] += rgb[0]
            sums[1] += rgb[1]
            sums[2] += rgb[2]
            low_blue += rgb[2] < 110
            count += 1
        prev = cur
    if not count:
        return {}
    mean = [round(s / count / 255.0, 4) for s in sums]
    normal_like = (chans >= 3 and abs(mean[0] - 0.5) < 0.12 and abs(mean[1] - 0.5) < 0.12 and mean[2] > 0.75
                   and low_blue / count < 0.02)
    return {"width": w, "height": h, "channels": chans, "mean": mean, "normal_like": normal_like}


# ------------------------------------------------------------------------------------------------- catalog query

_UNITS_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0, "in": 2.54, "inch": 2.54, "inches": 2.54, '"': 2.54, "ft": 30.48,
             "foot": 30.48, "feet": 30.48, "'": 30.48}
_AXIS_WORDS = {"tall": "z", "high": "z", "height": "z", "wide": "y", "width": "y", "long": "x", "length": "x",
               "deep": "x", "depth": "x", "across": "max", "diameter": "max"}
_STOP = {"a", "an", "the", "of", "about", "around", "roughly", "approx", "approximately", "some", "with", "and",
         "for", "in", "on", "to", "x", "by", "size", "sized", "big", "mesh", "asset", "model", "~", "me", "find",
         "i", "need", "want", "like", "that", "is", "be"}
_SYN = {"sofa": ["couch"], "couch": ["sofa"], "lamp": ["light"], "table": ["desk"], "desk": ["table"],
        "plant": ["pot", "foliage"], "mug": ["cup"], "cup": ["mug"], "rug": ["carpet"], "carpet": ["rug"],
        "shelf": ["bookshelf", "shelves"], "chair": ["stool", "seat"], "stool": ["chair"], "tv": ["television"],
        "bin": ["trash", "can"], "picture": ["frame", "painting"], "painting": ["picture", "frame"]}
_NUM = r"(\d+(?:\.\d+)?)"


def parse_query(q: str) -> dict:
    """'a 45 cm chair', 'table 120x80 cm', 'lamp 1.5m tall', 'mug ~10cm' -> {"words": [...], "sizes_cm": [..],
    "axis": "z"|"x"|"y"|"max"|None, "tolerance": 0.25}. Sizes without a unit are cm. `axis` comes from a word
    (tall/high = z, wide = y, long/deep = x); with several sizes they are matched sorted, axis-free."""
    s = str(q or "").lower().replace("×", "x")
    sizes = []
    for m in re.finditer(_NUM + r"\s*(?:x\s*" + _NUM + r")?\s*(?:x\s*" + _NUM + r")?\s*(mm|cm|m|inches|inch|in|ft|feet|foot|\"|')?(?![a-z])", s):
        unit = _UNITS_CM.get(m.group(4) or "cm", 1.0)
        sizes += [float(g) * unit for g in m.groups()[:3] if g]
    s_words = re.sub(_NUM + r"\s*(mm|cm|m|inches|inch|in|ft|feet|foot|\"|')?(?![a-z])", " ", s)
    words, axis = [], None
    tol = 0.25
    for w in re.findall(r"[a-z][a-z0-9_]*", s_words):
        if w in _AXIS_WORDS:
            axis = _AXIS_WORDS[w]
        elif w in ("exactly", "exact"):
            tol = 0.1
        elif w not in _STOP and w not in _UNITS_CM:
            words.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return {"words": words, "sizes_cm": [round(x, 3) for x in sizes], "axis": axis if len(sizes) == 1 else None,
            "tolerance": tol}


def _entry_words(e: dict) -> set:
    toks = set()
    for f in (e.get("name", ""), e.get("path", "")):
        toks.update(_tokens(re.sub(r"^(SM|SK|MI|M|T|BP|S|A)_", "", str(f).rsplit("/", 1)[-1])))
        toks.update(t.lower() for t in str(f).split("/") if t)
    for t in e.get("tags", []) or []:
        toks.update(_tokens(str(t)))
    return {t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t for t in toks}


def score_entry(e: dict, q: dict) -> dict | None:
    """How well a catalog entry fits a parsed query: None if it does not fit at all, else {"score" 0..1,
    "word_hits", "size_error" (relative, 0 is exact), "scale" (uniform factor that makes it exactly the asked size)}.
    An entry: {"path", "name", "class", "tags", "size_cm": [x, y, z] (bounding box), ...}."""
    words = q.get("words") or []
    have = _entry_words(e)
    hits = 0.0
    for w in words:
        if w in have or any(h.startswith(w) or w.startswith(h) and len(h) > 3 for h in have):
            hits += 1
        elif any(s in have for s in _SYN.get(w, [])):
            hits += 0.6
    if words and hits == 0:
        return None
    wscore = hits / len(words) if words else 1.0
    sizes = q.get("sizes_cm") or []
    size = e.get("size_cm")
    err, scale = None, None
    if sizes:
        if not size or not any(size):
            return None
        dims = [abs(float(v)) for v in size]
        if len(sizes) == 1:
            ax = q.get("axis")
            if ax in ("x", "y", "z"):
                cand = [dims["xyz".index(ax)]]
            elif ax == "max":
                cand = [max(dims)]
            else:  # unspecified: height or the longest side, whichever is closer
                cand = [dims[2], max(dims)]
            want = sizes[0]
            have_d = min(cand, key=lambda d: abs(d - want))
            err = abs(have_d - want) / max(want, 1e-6)
            scale = want / have_d if have_d > 1e-6 else None
        else:
            want = sorted(sizes, reverse=True)
            got = sorted(dims, reverse=True)[:len(want)]
            errs = [abs(g - w) / max(w, 1e-6) for g, w in zip(got, want)]
            err = sum(errs) / len(errs)
            scale = sum(w / g for g, w in zip(got, want) if g > 1e-6) / len(want)
        tol = float(q.get("tolerance", 0.25))
        if err > max(tol * 4, 1.0):
            return None
        sscore = max(0.0, 1.0 - err / (tol * 4))
        score = 0.55 * wscore + 0.45 * sscore if words else sscore
    else:
        score = wscore
    return {"score": round(score, 4), "word_hits": hits, "size_error": None if err is None else round(err, 4),
            "scale": None if scale is None else round(scale, 4)}


def search(entries: list, query: str, limit: int = 10, cls: str = "") -> list:
    """The catalog entries that best fit `query`, best first, each with its fit merged in."""
    q = parse_query(query)
    out = []
    for e in entries:
        if cls and e.get("class") != cls:
            continue
        f = score_entry(e, q)
        if f is not None:
            out.append({**e, **f})
    out.sort(key=lambda x: (-x["score"], x.get("size_error") or 0, x.get("path", "")))
    return out[:limit]
