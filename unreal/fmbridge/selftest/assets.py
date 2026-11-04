"""WP2 assets, materials and Fab on a real editor. It writes its own source files on the box (an OBJ box the size of
a chair, a glTF cube, three PNG maps of a texture set), then: imports them (Interchange, no dialog), reads them back
(assets.describe, the registry catalog, assets.find "chair 90 cm tall"), sets mesh build settings (Nanite, LODs,
collision), textures by role, re-imports a changed file; builds all 12 library masters and checks each compiles and
that every texture matches its sampler; PBR from the set, presets, a graph material, instances that converge;
assigns a material to a mesh slot; renames, moves, duplicates, tags, follows references, fixes a redirector,
audits, removes; takes thumbnails; and checks Fab's state (the library only when signed in; fab.add needs a signed
URL and is not run). Takes ~3 min (12 master compiles on a cold DDC, 2 stills). Needs: GPU (stills, shader
statistics); Fab sign-in optional.
"""
from __future__ import annotations

import base64
import json
import os
import struct

REQUIRES = ["gpu"]
AREAS = ["assets", "mat", "fab"]
NEEDS_LEVEL = True
TIMEOUT = 900


def _obj_box(path: str, x: float, y: float, z: float) -> str:
    """A closed box x*y*z (cm), base at z=0, as OBJ."""
    v = [(-x / 2, -y / 2, 0), (x / 2, -y / 2, 0), (x / 2, y / 2, 0), (-x / 2, y / 2, 0),
         (-x / 2, -y / 2, z), (x / 2, -y / 2, z), (x / 2, y / 2, z), (-x / 2, y / 2, z)]
    faces = [(1, 2, 3, 4), (5, 8, 7, 6), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 8, 4), (4, 8, 5, 1)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("o ST_Chair\n" + "".join(f"v {a:.3f} {b:.3f} {c:.3f}\n" for a, b, c in v)
                 + "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n"
                 + "".join(f"f {a}/1 {b}/2 {c}/3 {d}/4\n" for a, b, c, d in faces))
    return path


def _gltf_cube(path: str, size_m: float = 0.3) -> str:
    """A cube as a self-contained glTF 2.0 (metres, Y up, as glTF is)."""
    h = size_m / 2
    pos = [(-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h), (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)]
    idx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
    vb = b"".join(struct.pack("<3f", *p) for p in pos)
    ib = b"".join(struct.pack("<H", i) for i in idx)
    buf = vb + ib
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "name": "ST_Cube"}],
           "meshes": [{"name": "ST_Cube", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "buffers": [{"byteLength": len(buf),
                        "uri": "data:application/octet-stream;base64," + base64.b64encode(buf).decode()}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(vb), "target": 34962},
                           {"buffer": 0, "byteOffset": len(vb), "byteLength": len(ib), "target": 34963}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                          "min": [-h, -h, -h], "max": [h, h, h]},
                         {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"}]}
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return path


def run(t):
    from fmbridge.ops import _assetlib as AL
    from fmbridge.ops import _matlib as LIB

    p, S = t.prefix, t.scratch
    src = t.path("src")
    os.makedirs(src, exist_ok=True)
    obj = _obj_box(os.path.join(src, "st_chair.obj"), 50, 48, 90)
    gltf = _gltf_cube(os.path.join(src, "st_cube.gltf"))
    maps = [AL.write_png(os.path.join(src, n), rgb, size=16) for n, rgb in (
        ("T_ST_Rock_BaseColor.png", (180, 110, 60)), ("T_ST_Rock_Normal.png", (128, 128, 255)),
        ("T_ST_Rock_ORM.png", (255, 160, 0)))]

    # --- import, describe, catalog, find ------------------------------------------------------------------------
    got = t.op("assets.import", files=[obj], dest=f"{S}/Props", detail=True, collision="box")
    meshes = [a for r in got["imported"] for a in r["assets"]]
    t.ok("OBJ import made a static mesh", bool(meshes), detail=meshes)
    chair = next((m for m in meshes if t.op("assets.describe", path=m, refs=False)["class"] == "StaticMesh"), None)
    if chair is None:
        t.skip("the OBJ import made no StaticMesh: nothing else can run (see the log)")
    d = t.op("assets.describe", path=chair)
    t.metric("obj_size_cm", d["size_cm"], "cm")
    t.check("the OBJ chair is 50x48x90 cm (OBJ units read as cm)", d["size_cm"], [50, 48, 90], tol=0.6)
    t.ok("a box has 12 triangles", d["triangles"][0] == 12, detail=d["triangles"])
    again = t.op("assets.import", files=[obj], dest=f"{S}/Props", replace=False, detail=True)
    t.check("re-import with replace=false keeps it", again["changed"], False)
    g = t.op("assets.import", files=[gltf], dest=f"{S}/Gltf", detail=True)
    cube = next((a for r in g["imported"] for a in r["assets"]
                 if t.op("assets.describe", path=a, refs=False)["class"] == "StaticMesh"), None)
    if cube:
        t.check("glTF metres became cm (0.3 m cube)", t.op("assets.describe", path=cube, refs=False)["size_cm"],
                [30, 30, 30], tol=0.6)
    t.raises("a missing file says push it", "assets.import", code="not_found", files=["/nope/x.fbx"], dest=S)

    cat = t.op("assets.catalog", folder=S, cls="StaticMesh", refresh=True)
    t.ok("the catalog lists the chair without loading", any(e["path"] == chair and e.get("size_cm")
                                                             for e in cat["entries"]), detail=cat["entries"][:3])
    hits = t.op("assets.find", query="chair 90 cm tall", folder=S, refresh=True)["hits"]
    t.check("assets.find 'chair 90 cm tall' finds it first", hits[0]["path"] if hits else None, chair)
    t.check("and says no scaling is needed", hits[0]["scale"] if hits else None, 1.0, tol=0.02)

    # --- mesh settings, re-import ------------------------------------------------------------------------------------
    m = t.op("assets.mesh", path=chair, nanite=True, lods=3, collision="convex", convex_hulls=2)
    t.check("Nanite on, 3 LODs", [m["nanite"], m["lods"]], [True, 3])
    t.idempotent("assets.mesh converges", "assets.mesh", path=chair, nanite=True, lods=3)
    _obj_box(obj, 60, 48, 90)
    t.op("assets.reimport", path=chair)
    t.check("re-import picked up the wider source", t.op("assets.describe", path=chair, refs=False)["size_cm"][0],
            60, tol=0.6)

    # --- textures by role ----------------------------------------------------------------------------------------
    tx = t.op("assets.import_textures", files=maps, dest=f"{S}/Tex")
    roles = {os.path.basename(x["file"]): x["role"] for x in tx["textures"]}
    t.check("texture roles from names", roles, {"T_ST_Rock_BaseColor.png": "base_color",
                                                "T_ST_Rock_Normal.png": "normal", "T_ST_Rock_ORM.png": "orm"})
    nd = t.op("assets.describe", path=f"{S}/Tex/T_ST_Rock_Normal", refs=False)
    t.check("the normal map is linear TC_NORMALMAP", [nd["srgb"], nd["compression"]], [False, "TC_NORMALMAP"])
    t.idempotent("assets.texture converges", "assets.texture", path=f"{S}/Tex/T_ST_Rock_ORM", role="orm")

    # --- materials -----------------------------------------------------------------------------------------------
    for name in sorted(LIB.MASTERS):
        r = t.op("mat.master", name=name)
        t.ok(f"master {name} compiles", r.get("stats", {}).get("num_samplers", 0) != -1, detail=r.get("stats"))
    t.idempotent("mat.master converges", "mat.master", name="opaque")
    pbr = t.op("mat.pbr", path=f"{S}/Mats/MI_ST_Rock", maps={"base_color": f"{S}/Tex/T_ST_Rock_BaseColor",
                                                            "normal": f"{S}/Tex/T_ST_Rock_Normal",
                                                            "orm": f"{S}/Tex/T_ST_Rock_ORM"})
    t.check("mat.pbr picks the ORM master", pbr["master"], "opaque_orm")
    ck = t.op("mat.check", path=pbr["path"])
    t.ok("the PBR material passes mat.check", ck["pass"], detail=ck["issues"])
    for preset in ("chrome", "glass_clear", "emissive_panel", "velvet", "leaf"):
        r = t.op("mat.preset", path=f"{S}/Mats/MI_ST_{preset}", name=preset)
        t.ok(f"preset {preset} passes mat.check", t.op("mat.check", path=r["path"])["pass"])
    t.idempotent("mat.instance converges", "mat.instance", path=f"{S}/Mats/MI_ST_Red", master="opaque",
                 params={"Tint": [0.6, 0.05, 0.04], "Roughness": 0.35})
    desc = t.op("mat.describe", path=f"{S}/Mats/MI_ST_Red")
    t.check("parameters read back", desc["params"]["Roughness"]["value"], 0.35, tol=1e-4)
    t.raises("a misspelt parameter names the right one", "mat.instance", code="bad_args",
             path=f"{S}/Mats/MI_ST_Red", master="opaque", params={"Rougness": 0.3})
    spec = {"blend": "opaque", "shading": "default_lit",
            "nodes": {"c": {"type": "Vector", "name": "Col", "default": [0.1, 0.4, 0.8, 1]},
                      "f": {"type": "Fresnel", "exponent": 3.0},
                      "rim": {"type": "Lerp", "in": {"A": "c.RGB", "B": [1, 1, 1], "Alpha": "f"}}},
            "outputs": {"BaseColor": "rim", "Roughness": 0.4}}
    gr = t.op("mat.graph", path=f"{S}/Mats/M_ST_Rim", spec=spec)
    t.ok("a graph material compiles", gr["stats"].get("num_samplers", 0) != -1, detail=gr["stats"])
    t.idempotent("mat.graph converges", "mat.graph", path=f"{S}/Mats/M_ST_Rim", spec=spec)
    t.raises("a bad graph pin is named", "mat.graph", code="bad_args", path=f"{S}/Mats/M_ST_Bad",
             spec={"nodes": {"a": {"type": "Multiply", "in": {"C": 1}}}, "outputs": {"BaseColor": "a"}})
    a = t.op("mat.assign", mesh=chair, material=pbr["path"], slot=0)
    t.ok("material on the mesh's slot 0", a["material"] == pbr["path"])

    # --- a still of it, lit, and thumbnails ----------------------------------------------------------------------
    th = yield from t.op("assets.thumbnail", path=chair, out_dir=t.path("thumbs"), views=4, size_px=384,
                         loc=[0, 0, 0])
    for v in th["views"]:
        t.artifact(v["path"])
    if th.get("sheet"):
        t.artifact(th["sheet"])
    t.check("4 thumbnails", len(th["views"]), 4)
    try:
        img = t.op("qa.image", path=th["views"][0]["path"])
        t.metric("thumbnail_mean_luma", img.get("metrics", img).get("mean_luma", img.get("mean")))
        t.ok("the thumbnail is not black", (img.get("metrics", img).get("mean_luma") or 1) > 0.02, detail=img)
    except Exception as e:  # qa.image's shape is WP10's: only a note if it differs
        t.note(f"qa.image on the thumbnail: {e}")

    # --- managing ------------------------------------------------------------------------------------------------
    dup = t.op("assets.duplicate", src=chair, dst=f"{S}/Props/SM_ST_Chair2")
    t.ok("duplicate", dup == f"{S}/Props/SM_ST_Chair2")
    r = t.op("assets.rename", src=dup, dst=f"{S}/Moved/SM_ST_Chair2")
    t.ok("rename moves it", r["changed"])
    t.idempotent("assets.rename converges", "assets.rename", src=dup, dst=f"{S}/Moved/SM_ST_Chair2")
    t.op("assets.tag", path=chair, set={"category": "furniture", "selftest": "assets"})
    t.check("find by tag", [h["path"] for h in t.op("assets.find", folder=S, tags={"category": "furniture"},
                                                    refresh=True)["hits"]], [chair])
    refs = t.op("assets.refs", path=pbr["path"])
    t.ok("the chair uses the PBR material", chair in refs["referencers"], detail=refs)
    t.raises("removing a used material is refused", "assets.remove", code="conflict", paths=[pbr["path"]])
    # a redirector: move the material while the chair uses it, then fix
    mv = t.op("assets.rename", src=pbr["path"], dst=f"{S}/Mats2/MI_ST_Rock", fix_redirectors=False)
    t.ok("moved a used material", mv["changed"])
    fx = t.op("assets.fix_redirectors", folder=S)
    t.metric("redirectors_fixed", fx["fixed"])
    t.check("no redirector left", fx["left"], [])
    au = t.op("assets.audit", folder=S)
    t.metric("audit", au["metrics"])
    t.ok("the audit finds no broken material", au["metrics"]["broken"] == 0, detail=au["issues"][:5])
    rm = t.op("assets.remove", paths=[f"{S}/Moved/SM_ST_Chair2"])
    t.check("remove", rm["removed"], [f"{S}/Moved/SM_ST_Chair2"])
    t.idempotent("assets.remove of nothing is fine", "assets.remove", paths=[f"{S}/Moved/SM_ST_Chair2"])
    t.op("assets.folder", path=f"{S}/Empty")
    t.op("assets.save", folder=S)
    listed = t.op("assets.list", path=S, cls="StaticMesh")
    t.ok("assets.list sees the chair", ["StaticMesh", chair] in [list(x) for x in listed], detail=listed[:5])
    mvd = t.op("assets.move", paths=[f"{S}/Gltf/{cube.rsplit('/', 1)[-1]}"] if cube else [], folder=f"{S}/Moved")
    t.ok("assets.move", (not cube) or bool(mvd["moved"]), detail=mvd)
    t.ok("assets.props reads a texture's settings", "srgb" in t.op("assets.props", path=f"{S}/Tex/T_ST_Rock_ORM",
                                                                    names=["srgb"]))
    t.idempotent("assets.set_props converges", "assets.set_props", path=f"{S}/Tex/T_ST_Rock_ORM",
                 props={"max_texture_size": 512})
    t.ok("assets.delete", t.op("assets.delete", path=f"{S}/Fab/Planks/MI_planks_x") is False)
    t.ok("mat.masters lists 12", len(t.op("mat.masters")) == len(LIB.MASTERS))
    t.ok("mat.presets", "chrome" in t.op("mat.presets"))
    t.note("assets.save_all (saves every dirty package of the editor) and fab.add (needs a signed URL from "
           "fab_shim.py) are not run here")

    # --- Fab -------------------------------------------------------------------------------------------------------
    st = t.op("fab.status")
    t.metric("fab", {k: st[k] for k in ("plugin", "signed_in", "saved_sign_ins", "pack_installer")})
    fdir = os.path.join(src, "fab_planks")
    os.makedirs(fdir, exist_ok=True)
    for n, rgb in (("Planks_BaseColor.png", (150, 100, 60)), ("Planks_Normal.png", (128, 128, 255)),
                   ("Planks_Roughness.png", (200, 200, 200))):
        AL.write_png(os.path.join(fdir, n), rgb, size=16)
    fi = t.op("fab.import", path=fdir, dest=f"{S}/Fab/Planks")
    t.ok("fab.import of loose textures makes a material", bool(fi["material"]), detail=fi)
    if st["plugin"] and (st["signed_in"] or st["saved_sign_ins"]):
        lg = yield from t.op("fab.login", timeout_s=30.0)
        t.ok("fab.login with the saved sign-in", lg["signed_in"], detail=lg)
        if lg["signed_in"]:
            from fmbridge.errors import OpError
            try:
                lib = t.op("fab.library", limit=5)
                t.metric("fab_library_items", lib["count"])
                t.ok("the Fab library answers", isinstance(lib["items"], list))
            except OpError as e:  # the endpoint is private: a failure is a finding, not the end of the test
                t.ok("the Fab library answers", False, detail=f"{e.code}: {e}")
    else:
        t.note("Fab is not signed in and has no saved sign-in: fab.login/fab.library not exercised ("
               + st["next"] + ")")
    t.note("fab.add needs a signed URL from fab_shim.py (Playwright) and is not run here")
    return {"chair": chair, "masters": sorted(LIB.MASTERS)}
