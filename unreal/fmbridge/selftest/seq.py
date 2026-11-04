"""WP8's acceptance test, the Sequencer core on a real editor: a scratch scene (a cube, a skeletal actor, two cine
cameras, a point light), a SEQUENCE SPEC applied over it with every track kind the core writes (transform with
look-at, visibility, skeletal animation, float / colour properties on components, a material parameter, camera cuts,
audio, fade, a parameter collection when one exists, markers), then:

- apply again: changed false, plan empty (idempotent), and describe fed back to apply is a no-op (round trip);
- the engine's own evaluation agrees with the spec: world transforms at key frames (seq.eval, ControlRig) and
  channel values between linear keys (curve evaluation), within 0.01;
- one track changed: only that track is rewritten; prune removes what the spec dropped;
- a 20,000-key bake through seq.write: timed (keys/s), and the editor keeps ticking (multi-tick);
- shots: a master of three shot sequences with pre-roll, seq.shots, seq.chunks (cloth pre-roll back to each shot
  start), seq.preroll; a shot list (one sequence per shot, end to end, handles); seq.conform keeping time; seq.copy of a window, seq.retime ripple, seq.time, seq.validate, seq.check;
- errors an agent can act on: a typo'd actor label (not_found + candidates), a bad spec (bad_args, all problems);
- stills through the cut at four frames (seq.stills), when a GPU renders.

Takes ~1-2 min (most of it the stills). Needs: GPU only for the stills (everything else runs without one); no
assets beyond the engine's (an AnimSequence is looked for under /Game and the MetaHuman plugin; without one the
animation part is noted and skipped). Leaves nothing outside /Game/_Selftest/seq.
"""
from __future__ import annotations

import math
import os
import struct
import time
import wave

AREAS = ["seq"]
NEEDS_LEVEL = True
TIMEOUT = 900

ANIM_ROOTS = ["/Game", "/MetaHumanCharacter/Optional/Animation"]


def _wav(path: str, seconds: float = 2.0, rate: int = 48000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(int(seconds * rate))))
    return path


def _first_anim(t):
    for root in ANIM_ROOTS:
        try:
            found = t.op("assets.list", path=root, cls="AnimSequence", limit=1)
        except Exception:
            continue
        if found:
            return found[0][1]
    return None


def run(t):
    p, S = t.prefix, t.scratch
    seq = f"{S}/{p}SEQ"
    cube, hero, cam_a, cam_b, key = (p + n for n in ("Cube", "Hero", "CamA", "CamB", "Key"))

    # --- the scene ----------------------------------------------------------------------------------------------
    t.op("level.spawn", label=cube, shape="cube", loc=[0, 0, 50])
    t.op("level.spawn", label=hero, cls="SkeletalMeshActor", loc=[0, 200, 0])
    t.op("level.spawn", label=cam_a, cls="CineCameraActor", loc=[-500, 0, 150])
    t.op("level.spawn", label=cam_b, cls="CineCameraActor", loc=[0, -500, 150])
    t.op("level.spawn", label=key, cls="PointLight", loc=[200, 200, 300])
    anim = _first_anim(t)
    sound = None
    try:
        wav = _wav(t.path("tone.wav"))
        r = t.op("audio.import", files=[wav], folder=f"{S}/Audio")
        sound = r["sounds"][0]["path"]
    except Exception as e:  # WP12's op missing or failing: the audio part is noted, not failed
        t.note(f"audio import unavailable ({e}); the audio track is not exercised")

    spec = {
        "kind": "sequence", "version": 1, "name": "selftest", "sequence": seq, "fps": 24, "range": [0, 120],
        "markers": [[24, "a"], [96, "b"]],
        "bindings": {
            cube: {
                "transform": {"keys": [[0, [0, 0, 50], {"yaw": 0}, "linear"], [48, [200, 0, 50], {"yaw": 170}, "linear"],
                                       [96, [200, 200, 50], {"yaw": -170}, "linear"]]},
                "visible": [[0, True], [110, False]],
                "materials": [{"slot": 0, "param": "SelftestGlow", "keys": [[0, 0], [24, 1]]}],
            },
            cam_a: {"transform": {"keys": [{"frame": 0, "loc": [-500, 0, 150], "look_at": cube}]},
                    "props": {"CameraComponent/CurrentFocalLength": [[0, 24, "linear"], [60, 50, "linear"]],
                              "CameraComponent/FocusSettings.ManualFocusDistance": [[0, 500]]}},
            cam_b: {"transform": [[0, [0, -500, 150], [0, 0, 50]]]},
            key: {"props": {"LightComponent0/Intensity": [[0, 1000, "linear"], [100, 5000, "linear"]],
                            "LightComponent0/LightColor": {"type": "color", "srgb": True,
                                                           "keys": [[0, [1.0, 0.8, 0.6]]]}}},
        },
        "camera_cuts": [[cam_a, 0], [cam_b, 60]],
        "fade": {"color": [0, 0, 0], "keys": [[0, 1], [12, 0]]},
    }
    if anim:
        spec["bindings"][hero] = {"anim": {"sections": [{"anim": anim, "start": 0, "end": 120, "blend_in": 6}]}}
    else:
        t.note("no AnimSequence found: skeletal animation not exercised")
    if sound:
        spec["audio"] = {"Tone": [{"sound": sound, "start": 12}]}

    v = t.op("seq.validate", spec=spec)
    t.check("the spec validates", v["problems"], [])
    pl = t.op("seq.plan", spec=spec)
    t.ok("a plan before the first apply has steps", len(pl["steps"]) > 5, detail=pl["steps"][:3])

    t0 = time.time()
    r = yield from t.op("seq.apply", spec=spec)
    t.metric("apply_s", round(time.time() - t0, 3), "s")
    t.check("apply converges", [r["converged"], r["remaining"]], [True, []])
    r2 = yield from t.op("seq.apply", spec=spec)
    t.check("apply again changes nothing", [r2["changed"], len(r2["steps"])], [False, 0])
    t.check("plan after apply is empty", t.op("seq.plan", spec=spec)["steps"], [])

    doc = t.op("seq.describe", path=seq)
    t.check("rate and range", [doc["fps"], doc["range"]], ["24", [0, 120]])
    t.check("markers", doc["markers"], [{"frame": 24, "label": "a"}, {"frame": 96, "label": "b"}])
    t.ok("every binding bound", all(b["bound"] for b in doc["bindings"]), detail=doc["bindings"])
    t.check("nothing unsupported", doc["unsupported"], [])
    kinds = sorted({x["kind"] for x in doc["tracks"]})
    t.note(f"track kinds written: {kinds}")
    back = {"sequence": seq, "fps": doc["fps"], "range": doc["range"], "tracks": doc["tracks"],
            "bindings": doc["bindings"], "markers": doc["markers"]}
    r3 = yield from t.op("seq.apply", spec=back)
    t.check("describe round-trips through apply", [r3["changed"], [s["why"] for s in r3["steps"]]], [False, []])

    # --- what the engine evaluates ------------------------------------------------------------------------------
    ev = t.op("seq.eval", path=seq, frames=[0, 24, 48, 96], labels=[cube],
              tracks=[{"kind": "float", "binding": key, "component": "LightComponent0", "name": "Intensity"},
                      {"kind": "float", "binding": cam_a, "component": "CameraComponent", "name": "CurrentFocalLength"}])
    tr = ev["transforms"][cube]
    t.check("cube at its keys (world, cm)", [x[:3] for x in tr], [[0, 0, 50], [100, 0, 50], [200, 0, 50],
                                                                   [200, 200, 50]], tol=0.01)
    t.check("cube yaw unwrapped through 180 (170 -> 190)", (tr[3][4] - tr[2][4]) % 360, 20, tol=0.01)
    ch = ev["channels"]
    t.check("light intensity on a linear ramp", ch[f"{key}.LightComponent0/float:Intensity"]["value"],
            [1000, 1960, 2920, 4840], tol=0.01)
    t.check("focal length ramp", ch[f"{cam_a}.CameraComponent/float:CurrentFocalLength"]["value"][:2], [24, 34.4],
            tol=0.01)

    # --- one change, prune ----------------------------------------------------------------------------------------
    spec2 = dict(spec, bindings=dict(spec["bindings"]))
    spec2["bindings"][key] = {"props": {"LightComponent0/Intensity": [[0, 1000, "linear"], [100, 3000, "linear"]],
                                        "LightComponent0/LightColor": spec["bindings"][key]["props"][
                                            "LightComponent0/LightColor"]}}
    r4 = yield from t.op("seq.apply", spec=spec2)
    t.check("one changed track, one write", [s["op"] for s in r4["steps"]], ["seq.write"])
    spec3 = dict(spec2, bindings=dict(spec2["bindings"]))
    spec3["bindings"][cube] = {k: v for k, v in spec2["bindings"][cube].items() if k != "visible"}
    r5 = yield from t.op("seq.apply", spec=spec3, prune=True)
    t.check("prune removes the dropped visibility track", [s["op"] for s in r5["steps"]], ["seq.remove_track"])

    # --- a big batched write --------------------------------------------------------------------------------------
    n = 20000
    t.op("seq.add", path=seq, end=n)
    bake = {"kind": "float", "binding": key, "component": "LightComponent0", "name": "AttenuationRadius",
            "sections": [{"range": [None, None], "channels": {"value": {"keys": [[f, 500 + 100 * math.sin(f / 50),
                                                                                  "linear"] for f in range(n)]}}}]}
    t0 = time.time()
    w = yield from t.op("seq.write", path=seq, track=bake)
    dt = time.time() - t0
    t.metric("write_keys_per_s", round(n / max(dt, 1e-6)), "keys/s")
    t.check("20k keys written", w["keys"], n)
    t.ok("20k keys in under 60 s", dt < 60, detail=f"{dt:.1f} s")
    w2 = yield from t.op("seq.write", path=seq, track=bake)
    t.check("the same bake again changes nothing", w2["changed"], False)
    t.op("seq.remove_track", path=seq, kind="float", binding=key, component="LightComponent0",
        name="AttenuationRadius")
    t.op("seq.add", path=seq, end=120)

    # --- shots, chunks, pre-roll --------------------------------------------------------------------------------
    for i in (10, 20, 30):
        t.op("seq.add", path=f"{S}/{p}sh{i:03d}", fps=24, start=0, end=120)
    master = {"sequence": f"{S}/{p}Master", "fps": 24, "range": [0, 300],
              "shots": [{"sequence": f"{S}/{p}sh010", "name": "sh010", "start": 0, "end": 100, "preroll": 8},
                        {"sequence": f"{S}/{p}sh020", "name": "sh020", "start": 100, "end": 200, "offset": 10},
                        {"sequence": f"{S}/{p}sh030", "name": "sh030", "start": 200, "end": 300, "timescale": 0.5}]}
    r = yield from t.op("seq.apply", spec=master)
    t.check("master converges", r["converged"], True)
    r = yield from t.op("seq.apply", spec=master)
    t.check("master idempotent", r["changed"], False)
    shots = t.op("seq.shots", path=master["sequence"])
    t.check("shots read back", [(s["name"], s["start"], s["end"], s["preroll"]) for s in shots],
            [("sh010", 0, 100, 8), ("sh020", 100, 200, 0), ("sh030", 200, 300, 0)])
    c = t.op("seq.chunks", path=master["sequence"], start=150, end=260, max_frames=40)
    t.check("chunks pre-roll to their shot start", [(x["start"], x["eval_from"]) for x in c["chunks"]],
            [(150, 100), (190, 100), (200, 200), (240, 200)])
    t.idempotent("seq.preroll converges", "seq.preroll", path=master["sequence"], frames=12)
    t.check("pre-roll on every shot", [s["preroll"] for s in t.op("seq.shots", path=master["sequence"])], [12, 12, 12])

    # --- a shot list: one sequence per shot, laid end to end (B20) ----------------------------------------------
    edit = {"sequence": f"{S}/{p}Edit", "fps": 24,
            "shots": [{"name": "a", "camera": cam_a, "duration": 48, "handles": 6, "preroll": 12},
                      {"name": "b", "duration": 36, "shot": {"bindings": {cam_b: {}}, "camera_cuts": [[cam_b, 0]]}}]}
    r = yield from t.op("seq.apply", spec=edit)
    t.check("shot list converges", [r["converged"], r["remaining"]], [True, []])
    r = yield from t.op("seq.apply", spec=edit)
    t.check("shot list idempotent", r["changed"], False)
    t.check("shots end to end", [(x["name"], x["start"], x["end"]) for x in t.op("seq.shots", path=edit["sequence"])],
            [("a", 0, 48), ("b", 48, 84)])
    t.check("shot a has its handles", t.op("seq.describe", path=f"{S}/{p}Edit_a", keys=False)["range"], [0, 60])

    # --- conform (B22) ------------------------------------------------------------------------------------------
    r = yield from t.op("seq.conform", path=seq, fps=30, keep="time", out=f"{S}/{p}At30")
    t.check("conform keeps time: range in 30 fps frames", r["range"], [0, 150])
    ev30 = t.op("seq.eval", path=f"{S}/{p}At30", frames=[60], labels=[cube])
    t.check("the cube is where it was at 2 s", ev30["transforms"][cube][0][:3], [tr[2][0], tr[2][1], tr[2][2]], tol=0.01)
    r = yield from t.op("seq.conform", path=seq, fps="29.97", keep="time", out=f"{S}/{p}At2997")
    t.check("29.97 needs 60000 ticks", r["tick_resolution"], 60000)

    # --- copy, retime, time -------------------------------------------------------------------------------------
    r = yield from t.op("seq.copy", src=seq, dst=f"{S}/{p}Cut", start=60, end=120, replace=True)
    t.check("copied window range", r["range"], [0, 60])
    cut = t.op("seq.describe", path=f"{S}/{p}Cut")
    cuts = [x for x in cut["tracks"] if x["kind"] == "camera_cut"][0]["sections"]
    t.check("the copy keeps the second camera", [(s["range"], s["params"]["camera"]) for s in cuts], [([0, 60], cam_b)])
    r = yield from t.op("seq.retime", path=f"{S}/{p}Cut", offset=12, after=30)
    t.check("ripple moves the end", t.op("seq.describe", path=f"{S}/{p}Cut", keys=False)["range"], [0, 72])
    t.check("time conversion", t.op("seq.time", value="00:00:02:12", fps=24)["frame"], 60)
    chk = t.op("seq.check", path=seq)
    t.ok("seq.check passes the main sequence", chk["pass"], detail=chk["issues"][:5])

    # --- errors an agent can act on -------------------------------------------------------------------------------
    t.raises("a typo'd label names candidates", "seq.apply", code="not_found",
             spec={"sequence": seq, "bindings": {cube + "x": {"visible": [[0, True]]}}})
    t.raises("a bad spec lists its problems", "seq.apply", code="bad_args",
             spec={"sequence": seq, "range": [10, 0], "camera_cuts": [[1, 2]]})
    t.raises("a missing sequence is not_found", "seq.check", code="not_found", path=f"{S}/{p}Nope")

    # --- stills through the cut ---------------------------------------------------------------------------------
    try:
        out = t.path("stills_cut")
        res = yield from t.op("seq.stills", path=seq, frames=[0, 40, 70, 110], camera="", out_dir=out,
                              width=640, height=360)
        for f, cam, path in res:
            ok = os.path.isfile(path) and os.path.getsize(path) > 0
            t.ok(f"still at {f} through {cam}", ok, detail=path)
            if ok:
                t.artifact(path)
    except Exception as e:
        t.note(f"stills not taken ({type(e).__name__}: {e}); needs a GPU")
    return {"anim": anim, "sound": sound, "kinds": kinds}
