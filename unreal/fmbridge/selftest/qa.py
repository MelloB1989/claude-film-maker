"""WP10's selftest: Claude's eyes work in the real editor. Takes ~2 min on the L4 (most of it scene-capture warm-up
and the sequence review). Needs: GPU (a real RHI; offscreen is fine). No Epic sign-in, no project assets: the scene
is engine basic shapes. A MetaHuman part runs only when one is found under /Game/MetaHumans.

It proves:
- view.still renders a viewport-free PNG through a cine camera, an ad-hoc camera and a sequence's cut; it is not flat,
  it matches a viewport still of the same camera (SSIM, mean colour), and which render-target format (RGBA8 or
  RGBA8_SRGB) matches the viewport's gamma (metric `capture_gamma`; the default must be the closer one);
- view.camera's projection agrees with the picture: the pillar's projected box holds the pillar's colour;
- view.turntable, view.stills, view.sheet, view.overlay write their images;
- qa.image measures exposure (a lit scene is not "flat"; a black still is); qa.compare gives SSIM 1 for a still and
  itself and flags a different camera;
- qa.framing: the pillar is in the wide camera and out of the turned-away one;
- qa.floating finds a cube 20 cm above the floor (gap within 1 cm) and none for a resting one;
- qa.overlaps finds two interpenetrating cubes;
- qa.penetration finds a sphere ("skin") poking through a cube ("cloth"), from 4 views, and nothing when the cloth is
  bigger;
- qa.snapshot / qa.diff see a move; qa.review writes review.json + review.png for a camera and for a sequence;
- errors are actionable (unknown camera: not_found with candidates).
"""
from __future__ import annotations

import os

REQUIRES = ["gpu"]
AREAS = ["qa", "view"]
TIMEOUT = 600

SHAPES = "/Engine/BasicShapes"


def run(t):
    P = t.prefix
    out = t.path("qa")
    os.makedirs(out, exist_ok=True)

    # --- a little set: floor, pillar (the subject), props, light, two cameras --------------------------------------
    t.op("level.spawn", label=P + "Floor", shape="cube", loc=[0, 0, -5], size=[2000, 2000, 10])
    t.op("level.spawn", label=P + "Pillar", shape="cylinder", loc=[0, 0, 90], size=[50, 50, 180])
    t.op("level.spawn", label=P + "Resting", shape="cube", loc=[150, -150, 25], size=[50, 50, 50])
    t.op("level.spawn", label=P + "Floating", shape="cube", loc=[150, 150, 45], size=[50, 50, 50])  # bottom at 20
    t.op("level.spawn", label=P + "SunkA", shape="cube", loc=[-150, 150, 40], size=[80, 80, 80])
    t.op("level.spawn", label=P + "SunkB", shape="cube", loc=[-110, 150, 40], size=[80, 80, 80])
    t.op("level.spawn", label=P + "Sun", cls="DirectionalLight", loc=[0, 0, 500], rot_={"pitch": -50, "yaw": 30})
    t.op("level.spawn", label=P + "Sky", cls="SkyLight", loc=[0, 0, 300])
    t.op("look.camera", label=P + "Wide", loc=[600, 0, 150], look_at=[0, 0, 90], focal=35.0, aperture=8.0, pilot=False)
    t.op("look.camera", label=P + "Away", loc=[600, 0, 150], look_at=[1200, 0, 150], focal=35.0, pilot=False)
    yield 1.0

    # --- view.still ----------------------------------------------------------------------------------------------
    cap = yield from t.op("view.still", out=f"{out}/wide_capture.png", camera=P + "Wide", width_px=960, height_px=540,
                          guides=["thirds", "safe"])
    t.ok("view.still capture wrote a PNG", os.path.isfile(cap["path"]), detail=str(cap)[:300])
    t.check("view.still size", [cap["width"], cap["height"]], [960, 540])
    t.artifact(cap["path"])
    t.artifact(cap.get("guides_path", ""))
    img = t.op("qa.image", image=cap["path"])
    t.ok("capture is not flat", img["metrics"]["exposure"]["verdict"] != "flat", detail=str(img["metrics"]["exposure"]))
    t.metric("capture_exposure_stops", img["metrics"]["exposure"]["stops"], "stops")

    vp = None
    try:
        vp = yield from t.op("view.still", out=f"{out}/wide_viewport.png", camera=P + "Wide", width_px=960,
                             height_px=540, mode="viewport")
    except Exception as e:  # the viewport screenshot needs a viewport; offscreen it may not have one
        t.note(f"viewport still unavailable here: {e}")
    if vp and os.path.isfile(vp["path"]):
        best, scores = None, {}
        for fmt in ("RTF_RGBA8", "RTF_RGBA8_SRGB"):
            c = yield from t.op("view.still", out=f"{out}/wide_{fmt}.png", camera=P + "Wide", width_px=960,
                                height_px=540, rt_format=fmt)
            cmp_ = t.op("qa.compare", image=c["path"], reference=vp["path"], min_ssim=0.5)
            scores[fmt] = {"ssim": cmp_["metrics"]["ssim"], "mean_shift": cmp_["metrics"]["mean_shift"]}
            err = max(abs(v) for v in cmp_["metrics"]["mean_shift"])
            if best is None or err < best[1]:
                best = (fmt, err)
        t.metric("capture_gamma", {"closest": best[0], "scores": scores})
        t.check("the default capture format (RTF_RGBA8) matches the viewport's gamma best", best[0], "RTF_RGBA8")
        t.ok("capture and viewport show the same picture (SSIM > 0.6)", scores["RTF_RGBA8"]["ssim"] > 0.6,
             detail=str(scores))

    adhoc = yield from t.op("view.still", out=f"{out}/adhoc.png", loc=[300, 300, 250], look_at=[0, 0, 90],
                            width_px=320, height_px=180, warmup=2)
    t.ok("ad-hoc camera still", os.path.isfile(adhoc["path"]))
    t.raises("unknown camera is not_found with candidates", "view.still", code="not_found", out=f"{out}/x.png",
             camera=P + "Wid")

    # --- projection agrees with the picture ---------------------------------------------------------------------
    pr = t.op("view.camera", camera=P + "Wide", width_px=960, height_px=540, actors=[P + "Pillar"],
              points={"pillar_mid": [0, 0, 90]})
    t.ok("pillar centre projects near the frame centre", abs(pr["points"]["pillar_mid"]["u"] - 0.5) < 0.02,
         detail=str(pr["points"]))
    box = pr["actors"][P + "Pillar"]["box"]
    from ..qa import image as qimg, metrics as qmet
    full = qimg.read(cap["path"])
    inner = [box[0] + 0.3 * (box[2] - box[0]), box[1] + 0.3 * (box[3] - box[1]),
             box[2] - 0.3 * (box[2] - box[0]), box[3] - 0.3 * (box[3] - box[1])]
    pil = qmet.color(qimg.crop_frac(full, inner))
    t.metric("pillar_color_in_box", pil["mean_rgb"])
    t.ok("the projected box lands on the pillar (not the sky): a lit grey surface", pil["saturation"] < 0.35,
         detail=str(pil))

    # --- framing -------------------------------------------------------------------------------------------------
    fr = yield from t.op("qa.framing", subjects=[P + "Pillar"], camera=P + "Wide", still_out=f"{out}/framing.png")
    t.check("pillar framed in Wide passes", fr["pass"], True)
    t.artifact(fr.get("still", ""))
    away = yield from t.op("qa.framing", subjects=[P + "Pillar"], camera=P + "Away")
    t.check("pillar out of Away's frame", [i["code"] for i in away["issues"]][:1], ["framing.out_of_frame"])

    # --- turntable, sheet, overlay ------------------------------------------------------------------------------
    tt = yield from t.op("view.turntable", target=P + "Pillar", out_dir=f"{out}/turntable", views=4, width_px=256,
                         height_px=256, isolate=True)
    t.check("turntable views", len([v for v in tt["views"] if os.path.isfile(v["path"])]), 4)
    t.ok("turntable sheet", bool(tt["sheet"]) and os.path.isfile(tt["sheet"]))
    t.artifact(tt["sheet"])
    sh = t.op("view.sheet", images=[cap["path"], adhoc["path"]], out=f"{out}/sheet.png", labels=["wide", "adhoc"])
    t.ok("view.sheet", os.path.isfile(sh["path"]))
    ov = t.op("view.overlay", image=cap["path"], out=f"{out}/overlay.png", guides=["thirds", "safe", "aspect:2.39"],
              boxes=[{"box": box, "label": "pillar", "color": "ok"}], caption="selftest")
    t.ok("view.overlay", os.path.isfile(ov["path"]))
    t.artifact(ov["path"])

    # --- compare -------------------------------------------------------------------------------------------------
    same = t.op("qa.compare", image=cap["path"], reference=cap["path"])
    t.check("a still against itself: SSIM 1", same["metrics"]["ssim"], 1.0, tol=1e-6)
    diff = t.op("qa.compare", image=adhoc["path"], reference=cap["path"], out_diff=f"{out}/diff.png")
    t.ok("a different camera is flagged", not diff["pass"] or diff["issues"], detail=str(diff["metrics"]["ssim"]))

    # --- meshes ---------------------------------------------------------------------------------------------------
    fl = t.op("qa.floating", labels=[P + "Resting", P + "Floating", P + "Pillar"])
    gaps = fl["metrics"]["gaps"]
    t.check("floating cube gap ~20 cm", gaps.get(P + "Floating"), 20.0, tol=1.0)
    t.check("resting cube gap ~0", gaps.get(P + "Resting"), 0.0, tol=1.0)
    t.ok("qa.floating flags the floating cube", any(i.get("subject") == P + "Floating" for i in fl["issues"]))
    ovl = t.op("qa.overlaps", labels=[P + "SunkA", P + "SunkB", P + "Resting"])
    t.check("qa.overlaps finds the sunk pair", [sorted(p[:2]) for p in ovl["metrics"]["pairs"]],
            [sorted([P + "SunkA", P + "SunkB"])])

    t.op("level.spawn", label=P + "Skin", shape="sphere", loc=[0, -400, 100], size=[100, 100, 100])
    t.op("level.spawn", label=P + "Cloth", shape="cube", loc=[0, -400, 100], size=[90, 90, 90])
    pen = yield from t.op("qa.penetration", label=P + "Skin", body=[P + "Skin"], garments=[P + "Cloth"], views=4,
                          size_px=128, out_dir=f"{out}/penetration")
    t.ok("a sphere through a cube is penetration", any(i["code"] == "mesh.penetration" for i in pen["issues"]),
         detail=str(pen["metrics"])[:400])
    t.metric("penetration_worst_fraction", pen["metrics"]["worst_fraction"])
    t.op("level.move", label=P + "Cloth", size=[130, 130, 130])
    clean = yield from t.op("qa.penetration", label=P + "Skin", body=[P + "Skin"], garments=[P + "Cloth"], views=4,
                            size_px=128)
    t.ok("a bigger cube covers it: no penetration", not any(i["code"] == "mesh.penetration" for i in clean["issues"]),
         detail=str(clean["metrics"])[:400])
    t.check("the capture rig is gone", len(t.op("level.actors", contains="FMQA_Capture")), 0)

    yield from _metahuman(t, out)

    # --- continuity ------------------------------------------------------------------------------------------------
    snap = t.op("qa.snapshot", out=f"{out}/before.json")
    t.ok("snapshot has the pillar", P + "Pillar" in snap["actors"])
    t.op("level.move", label=P + "Resting", loc=[180, -150, 25])
    d = t.op("qa.diff", before=f"{out}/before.json")
    t.check("qa.diff sees the move", sorted(d["metrics"]["changed"]), [P + "Resting"])

    # --- reviews ---------------------------------------------------------------------------------------------------
    rv = yield from t.op("qa.review", camera=P + "Wide", out_dir=f"{out}/review_cam", subjects=[P + "Pillar"],
                         ignore=[P + "Floor"], width_px=640, height_px=360)
    t.ok("qa.review (camera) wrote review.json and review.png", os.path.isfile(rv["report"]) and os.path.isfile(rv["image"]))
    t.ok("the review found the floating cube", any(i.get("subject") == P + "Floating" for i in rv["issues"]))
    t.artifact(rv["image"])

    seq = f"{t.scratch}/{P}Seq"
    try:
        t.op("seq.new", path=seq, start=0, end=48, fps=24, replace=True)
        t.op("seq.camera_cuts", path=seq, cuts=[[P + "Wide", 0], [P + "Away", 24]])
    except Exception as e:
        t.note(f"no sequence for the sequence review: {e}")
        return {"out": out}
    st = yield from t.op("view.stills", sequence=seq, out_dir=f"{out}/stills", per_shot=2, width_px=320, height_px=180)
    t.check("view.stills: 2 per cut", len(st["frames"]), 4)
    t.check("view.stills follows the cut", [f["camera"] for f in st["frames"]], [P + "Wide"] * 2 + [P + "Away"] * 2)
    t.artifact(st["sheet"])
    sq = yield from t.op("qa.review", sequence=seq, out_dir=f"{out}/review_seq", per_shot=1, subjects=[P + "Pillar"],
                         ignore=[P + "Floor"], width_px=480, height_px=270)
    t.check("sequence review: one panel per cut", len(sq["metrics"]["frames"]), 2)
    t.ok("the Away cut is flagged out of frame", any(i["code"] == "framing.out_of_frame" and i.get("frame") == 24
                                                    for i in sq["issues"]))
    t.artifact(sq["image"])
    return {"out": out, "review": sq["report"]}


def _metahuman(t, out):
    """With a MetaHuman Blueprint in the project: spawn it, list its parts, check its garments from 4 views and
    frame it. Skipped (a note) without one."""
    import unreal
    eal = unreal.EditorAssetLibrary
    if not eal.does_directory_exist("/Game/MetaHumans"):
        t.note("no /Game/MetaHumans: MetaHuman penetration/framing part skipped")
        return
    bps = [p for p in eal.list_assets("/Game/MetaHumans", True, False) if p.rsplit("/", 1)[-1].split(".")[0].startswith("BP_")]
    if not bps:
        t.note("no BP_* under /Game/MetaHumans: MetaHuman part skipped")
        return
    label = t.prefix + "MH"
    t.op("level.spawn", label=label, asset=bps[0].split(".")[0], loc=[0, 400, 0])
    yield 2.0
    parts = t.op("qa.parts", label=label)
    t.note(f"MetaHuman {bps[0]} parts: {[c['name'] for c in parts['components']]}")
    pen = yield from t.op("qa.penetration", label=label, views=4, size_px=256, out_dir=f"{out}/mh_penetration")
    t.metric("mh_penetration_worst_fraction", pen["metrics"]["worst_fraction"])
    t.note(f"MetaHuman penetration issues: {[i['message'] for i in pen['issues']][:5]}")
    t.op("look.camera", label=t.prefix + "MHCam", loc=[250, 400, 150], look_at=[0, 400, 150], focal=50.0, pilot=False)
    fr = yield from t.op("qa.framing", subjects=[label], camera=t.prefix + "MHCam", still_out=f"{out}/mh_framing.png")
    t.ok("MetaHuman framing reads bones (a shot size)", "size" in fr["metrics"]["subjects"][label],
         detail=str(fr["metrics"]["subjects"][label])[:400])
    t.artifact(fr.get("still", ""))
