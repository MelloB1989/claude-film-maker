"""Build the reel's cut in Unreal from shots.py: the master sequence /Game/Reel/SEQ_Reel, a Reel_<shot> cine camera
per shot (full-frame 16:9 back, the shot's lens and stop) keyed along its move (motion.py: eased, arcs round their
subject, handles), its focus keyed (the plan's pulls, else on the subject), the camera cuts on the plan's frames, and
the presenters on their reel marks, shown from the first shot that has them (the stool goes when they come).

It touches only what is the reel's: the sequence (made if missing, never deleted, so the light timeline and the
performances keyed into it by other scripts stay) and the Reel_ cameras (respawned on every run). The level itself
is not saved: the cameras are rebuilt on every run, and the sequence's bindings are pointed at the actors of today's
level first (studio.py respawns everything but the host).

    cd tools && uv run python ../films/host-studio/reel/build.py              # build (or rebuild) the cut
    cd tools && uv run python ../films/host-studio/reel/build.py --previs 12  # and a still every 12 frames, + sheet
    cd tools && uv run python ../films/host-studio/reel/build.py --sheet      # only remake previs/cut/contact.jpg
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from filmtools.unreal import client, workstation as ws


def _j(*parts: str) -> str:
    """A path on the box in its own style (Linux or Windows)."""
    from filmtools.unreal.boxpaths import BoxPaths
    return BoxPaths.current().join(*parts)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import motion as M  # noqa: E402
from shots import FPS, FULL_FRAME, MARK_HER, MARK_HIM, SHOTS  # noqa: E402

SEQ = "/Game/Reel/SEQ_Reel"
START, END = SHOTS[0].start - M.HANDLE, SHOTS[-1].end + M.HANDLE
HIM, HER = ["Host"], ["Presenter", "HerEarL", "HerEarR", "HerWatch"]  # her hoops and watch ride her bones
EMPTY_ROOM = ["Stool"]  # studio.py: for the empty-room shots, hidden when the presenters are in frame
FOCUS = "FocusSettings.ManualFocusDistance"
OUT = HERE / "previs" / "cut"
REMOTE = _j(ws.project("Saved", "Previs", "reel_cut"))


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def run(code: str):
    return ok(client.exec_code(code))


def sequence() -> None:
    """SEQ_Reel at 24 fps over the film and its handles, made if missing; an existing one keeps all its tracks."""
    ok(client.op("seq.new", path=SEQ, start=START, end=END, fps=FPS))


def rebind(labels: list) -> dict:
    """Point the sequence's bindings named like these actors at the level's actors of that label (after studio.py or
    this script respawned them), so their tracks (the reel's and other scripts') stay with them."""
    return ok(client.op("seq.rebind", path=SEQ, labels=labels))


def snapshot(labels: list) -> dict:
    """The level state of the actors the sequence moves or hides: Sequencer leaves them as the sequence had them when
    it is closed (Host on his reel mark, the stool hidden), so build() puts them back with restore()."""
    return run(f"""
from fmbridge.ops.level import actor
out = {{}}
for lab in {labels!r}:
    try:
        a = actor(lab)
    except ValueError:
        continue
    p, r = a.get_actor_location(), a.get_actor_rotation()
    out[lab] = [[p.x, p.y, p.z], [r.pitch, r.yaw, r.roll], a.is_temporarily_hidden_in_editor(), a.is_hidden_ed()]
result = out
""")


def restore(state: dict) -> None:
    """Close the sequence and put the actors back as snapshot() found them (attached ones only their visibility)."""
    ok(client.op("seq.close"))
    run(f"""
import unreal
from fmbridge.ops.level import actor
for lab, (loc, rot, temp, hid) in {state!r}.items():
    a = actor(lab)
    if a.get_attach_parent_actor() is None:
        a.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                          False, False)
    a.set_is_temporarily_hidden_in_editor(temp)
result = len({state!r})
""")


def pose(label: str) -> dict:
    """An actor's rotation and scale in the level (the marks keep the facing studio.py gave them)."""
    return run(f"""
from fmbridge.ops.level import actor
a = actor({label!r})
r, s = a.get_actor_rotation(), a.get_actor_scale3d()
result = {{"pitch": r.pitch, "yaw": r.yaw, "roll": r.roll, "scale": [s.x, s.y, s.z]}}
""")


def exists(labels: list) -> list:
    """Which of these labels are actors in the open level."""
    have = {a[0] for a in ok(client.op("level.actors"))}
    return [lab for lab in labels if lab in have]


# Exposure compensation per shot (stops, relative to the light timeline's exposure; bias() makes it absolute): S01 looks into the sheers
# from inside the olive's crown, 1.5 stops under the DAY room so the window holds (measured on viewport stills).
EXPOSURE = {"V03": -3.0, "V04": 2.5, "V05": 2.0, "N01": -1.0, "S12": 1.0}  # V03: contre-jour into the sun-lit sheers, three stops under so the window holds detail and the leaves go to silhouette; exposure alone could not (MRQ at -4.5 still clipped 34% at f360), so light.py cuts the sun over V03's frames (V03_SUN) and the room keeps -3; V04: two and a half stops up so the unlit letters read against the slats at dusk (MRQ at +1: f560 mean 33, slats 16; at +4: mean 105, slats 89, but it reads as day); V05: two stops up so the slat wall and the dark sign, the payoff's centre, are not a black void (MRQ at +1: f610 mean 43, 17% crushed), with light.py's cool slat spill keeping it blue against S12's warm night; N01: night must read dark, the LED lines carry it; S12: the night wide, a stop up so the room reads (MRQ luma 14 at 0)


def bias(s) -> float | None:
    """The camera's auto_exposure_bias for a shot with an EXPOSURE entry. A camera's post-process override replaces
    FM_Post's keyed bias, it does not add to it (N01's -1.0 rendered near-black in MRQ), so the override is absolute:
    light.py's exposure at the shot's middle frame plus the shot's compensation."""
    if s.id not in EXPOSURE:
        return None
    import light
    post = next(t for t in light.tracks() if t.label == "FM_Post")
    return round(post.curve.at(s.start + s.frames / 2) + EXPOSURE[s.id], 3)

# A binding that drives more than its own camera: after the level is rebuilt, rebinding (replace_binding_with_actors)
# added the new camera to old bindings instead of replacing it, so one binding moved two cameras (S05's keys moved
# Reel_S11 too: S11 looked at the wall behind) and removing the extra actor does not stick. Such bindings are dropped
# (their tracks go with them) and cameras() keys the shots afresh.
CLEAN = r"""
import unreal
seq = unreal.load_asset(SEQ)
unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
gone = []
for b in list(seq.get_bindings()):
    labs = [o.get_actor_label() for o in seq.locate_bound_objects(b, world) if hasattr(o, "get_actor_label")]
    name = str(b.get_display_name())
    if any(l.startswith("Reel_") for l in labs) and (labs != [name] or not name.startswith("Reel_")):
        for c in b.get_child_possessables():
            c.remove()
        b.remove()
        gone.append([name, labs])
unreal.EditorAssetLibrary.save_asset(SEQ)
result = gone
"""

EXPOSE = r"""
import unreal
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
acts = {a.get_actor_label(): a for a in EAS.get_all_level_actors()}
for lab, bias in BIAS.items():
    c = acts[lab].get_cine_camera_component()
    pp = c.get_editor_property("post_process_settings")
    pp.set_editor_property("override_auto_exposure_bias", bias is not None)
    pp.set_editor_property("auto_exposure_bias", bias or 0.0)
    c.set_editor_property("post_process_settings", pp)
result = BIAS
"""


def cameras() -> None:
    """A Reel_ cine camera per shot, placed at its first frame, then its move and focus keyed."""
    for s in SHOTS:
        loc, at = s.keys[0][1], s.keys[0][2]
        ok(client.op("look.camera", label=f"Reel_{s.id}", loc=loc, look_at=at, focal=float(s.lens),
                     aperture=float(s.stop), filmback=list(FULL_FRAME), pilot=False))
    rebind([f"Reel_{s.id}" for s in SHOTS])
    dropped = run(f"SEQ = {SEQ!r}\n" + CLEAN)
    if dropped:
        print("dropped bindings that drove more than their camera:", dropped)
    run(f"BIAS = {({f'Reel_{s.id}': bias(s) for s in SHOTS})!r}\n" + EXPOSE)
    for s in SHOTS:
        lab, sm = f"Reel_{s.id}", M.samples(s)
        keys, last = [], None
        for f, loc, pitch, yaw, _ in sm:
            while last is not None and yaw - last > 180:  # unwrapped: Sequencer interpolates the numbers, so a move
                yaw -= 360                                 # across +-180 deg would swing the long way round and
            while last is not None and yaw - last < -180:  # face the wall behind (S05's orbit, S11)
                yaw += 360
            keys.append([s.start + f, loc, {"pitch": pitch, "yaw": yaw, "roll": 0.0}])
            last = yaw
        ok(client.op("seq.key_transform", path=SEQ, label=lab, keys=keys))
        ok(client.op("seq.key_float", path=SEQ, label=lab, component="CameraComponent", prop=FOCUS,
                     keys=[[s.start + f, d] for f, *_, d in sm]))
        print(s.id, f"{s.lens:g}mm T{s.stop:g}", len(keys), "keys", flush=True)
    cut()


def cut() -> None:
    """The camera cuts on the plan's frames, made afresh and checked. Part of cameras(): CLEAN may drop a camera's
    binding and keying makes a new one, so cut sections made before would point at a binding that is gone (box, day 1
    r3: cameras() run on its own left the cut track on dead binding GUIDs)."""
    ok(client.op("seq.camera_cuts", path=SEQ, cuts=M.cuts()))
    got = ok(client.op("seq.cuts", path=SEQ))
    want = [[c, f, (M.cuts() + [[None, END]])[k + 1][1]] for k, (c, f) in enumerate(M.cuts())]
    # the ranges must match; the camera names too, once seq.cuts gives labels (it gave a Guid's repr on 2026-11-01)
    if [g[1:3] for g in got] != [w[1:] for w in want] or any(g[0].startswith("Reel_") and g[0] != w[0]
                                                              for g, w in zip(got, want)):
        raise SystemExit(f"the cut in SEQ_Reel is not the plan's: {got}")
    print("cut:", len(got), "shots,", got[0][1], "to", got[-1][2])


def marks() -> None:
    """The presenters on their reel marks for the whole sequence, and who is visible when."""
    for lab, mark in (("Host", MARK_HIM), ("Presenter", MARK_HER)):
        p = pose(lab)
        if any(abs(v - 1) > 1e-3 for v in p["scale"]):
            raise SystemExit(f"{lab} is scaled {p['scale']}: seq.key_transform keys scale 1")
        rot = {k: p[k] for k in ("pitch", "yaw", "roll")}
        ok(client.op("seq.key_transform", path=SEQ, label=lab, keys=[[START, list(mark), rot]]))
    have = exists(HIM + HER + EMPTY_ROOM)
    for who, lab in (("him", "Host"), ("her", "Presenter")):  # with what rides on them (her hoops and watch)
        if lab in have:
            ok(client.op("seq.key_visible", path=SEQ, label=lab, keys=[[f, who in cast] for f, cast in M.cast_at()],
                         attached=True))
    for lab in EMPTY_ROOM:
        if lab in have:
            ok(client.op("seq.key_visible", path=SEQ, label=lab, keys=[[f, not cast] for f, cast in M.cast_at()]))
    missing = sorted(set(HIM + HER + EMPTY_ROOM) - set(have))
    if missing:
        print("not in the level (no visibility keys):", ", ".join(missing))


LOD0 = """
import unreal
done = {}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab not in LABELS:
        continue
    r = done.setdefault(lab, {})
    def put(key, c, f):
        if c.get_name().startswith("TRASH_"):  # a blueprint re-instance (op -> trey swap) left the actor stale ones
            r[f"{key} {c.get_name()}"] = "ERR stale TRASH_ component: save and reopen the level, then pin again"
            return
        try:
            f(c)
            r[f"{key} {c.get_name()}"] = "ok"
        except Exception as e:
            r[f"{key} {c.get_name()}"] = f"ERR {type(e).__name__}: {e}"[:160]
    for c in a.get_components_by_class(unreal.LODSyncComponent) if hasattr(unreal, "LODSyncComponent") else []:
        put("lodsync.forced_lod", c, lambda c: c.set_editor_property("forced_lod", SYNC))
    for c in a.get_components_by_class(unreal.GroomComponent):
        put("groom.set_forced_lod", c, lambda c: c.set_forced_lod(SYNC))
        put("groom.lod_forced_index", c, lambda c: c.set_editor_property("lod_forced_index", SYNC))
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        put("skel.forced_lod_model", c, lambda c: c.set_editor_property("forced_lod_model", SKEL))  # 0 auto, N = LOD N-1
    a.modify()
result = done
"""


def lod0(on: bool = True) -> dict:
    """Note 3 (round 3): her hair shortened at the shoulders at the end of S17's crane out (v2 45 s cut 0:39-0:40,
    master f1416-1440): the groom dropped to a coarser LOD as she got smaller in frame. MRQ's game overrides pin
    meshes to LOD 0, not grooms, so the presenters' LODSync, grooms and skeletal meshes are pinned to LOD 0 on the
    placed actors (saved with the level, which the render saves before PIE). Says what took, per component."""
    # Round 5: the core op groom.lock does all of it and reads it back: LODSync forced_lod, every visible groom
    # added to LODSync's components_to_sync (a re-dress can rename the hair out of it), use_cards off, the
    # skeletal meshes, and the hair cvars (r.HairStrands.LODMode 0 + AutoLOD.Bias 1: Auto LOD thinned her hair on
    # S18's wide even at LOD 0; docs/unreal/research/hair-lod.md). It refuses on TRASH_ components.
    # off (the before of the proof): release (LODSync -1, skeletal 0, the engine's cvars).
    from filmtools.unreal import client
    r = client.op("groom.lock", labels=HIM[:1] + HER[:1], lod=0, release=not on)
    if not r.get("ok"):
        raise SystemExit(f"groom.lock failed: {r.get('error') or r}")
    res = r["result"]
    if on and not res.get("pass"):
        raise SystemExit("groom.lock did not verify:\n  " + "\n  ".join(res["check"]["problems"]))
    return res


def build() -> None:
    if not exists(["Host"]):
        raise SystemExit("no Host in the level: `film-ue op level.open path=/Game/Studio/Studio` first")
    sequence()
    rebind(HIM + HER + EMPTY_ROOM)
    cameras()
    marks()
    print("lod0:", lod0())


def previs(every: int, width: int, only: set | None = None) -> None:
    """Viewport stills across the cut, each through its own shot's camera: every `every` frames of each shot from its
    first, and its last frame, into previs/cut/<shot>_<frame>.png."""
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SHOTS:
        if only and s.id not in only:
            continue
        frames = sorted(set(range(s.start, s.end, every)) | {s.end - 1})
        remote = _j(REMOTE, s.id)
        # each shot's own camera: every frame here is inside its cut (seq.cuts checked it in build())
        got = ok(client.op("seq.stills", path=SEQ, frames=frames, camera=f"Reel_{s.id}", out_dir=remote,
                           width=width, height=width * 9 // 16))
        for f, g in zip(frames, got):
            client.pull(g[-1] if isinstance(g, list) else g, str(OUT / f"{s.id}_{f:04d}.png"))
        print(s.id, len(frames), "stills", flush=True)


def sheet(w: int = 400) -> Path:
    """previs/cut/contact.jpg: a row per shot, its first, middle and last stills, captioned with the shot, its frames,
    lens and light."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(str(HERE.parents[2] / "fonts" / "src" / "Geist[wght].ttf"), 15)
    h, cap, pad, cols = w * 9 // 16, 24, 6, 3
    rows = []
    for s in SHOTS:
        st = sorted(OUT.glob(f"{s.id}_*.png"))
        if st:
            rows.append((s, [st[0], st[len(st) // 2], st[-1]]))
    img = Image.new("RGB", (cols * (w + pad) + pad, len(rows) * (h + cap + pad) + pad), (16, 16, 17))
    d = ImageDraw.Draw(img)
    for r, (s, ps) in enumerate(rows):
        y = pad + r * (h + cap + pad)
        for c, p in enumerate(ps):
            x = pad + c * (w + pad)
            img.paste(Image.open(p).convert("RGB").resize((w, h), Image.LANCZOS), (x, y))
            d.text((x + 4, y + 3), f"f{int(p.stem.split('_')[1])}", fill=(240, 236, 228), font=font)
        d.text((pad + 2, y + h + 4), f"{s.id}  {s.title}  ·  f{s.start}-{s.end - 1}  ·  {s.lens:g}mm T{s.stop:g}  ·  "
               f"{s.light}  ·  {s.move}"[:150], fill=(225, 220, 210), font=font)
    out = OUT / "contact.jpg"
    img.save(out, quality=88)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--previs", type=int, default=0, help="also a still every N frames of the cut (0: none)")
    ap.add_argument("--width", type=int, default=640, help="previs still width (16:9)")
    ap.add_argument("--sheet", action="store_true", help="only remake the contact sheet from previs/cut (no bridge)")
    ap.add_argument("--only", default="", help="previs only these shots (S03,S04)")
    ap.add_argument("--no-build", action="store_true", help="previs the sequence as it is, without rebuilding")
    ap.add_argument("--lod0", choices=("on", "off"), help="only pin the presenters' hair and bodies to LOD 0 (note 3), "
                    "or put them back on automatic LODs (off: the before of the proof)")
    ap.add_argument("--cameras", action="store_true", help="only the Reel_ cameras: respawn, rebind, key, and the cut "
                    "made afresh (after a body or a shots.py change); run r3/probe_cam.py --check after it")
    a = ap.parse_args()
    if a.cameras:
        cameras()
        return
    if a.lod0:
        print("lod0:", lod0(a.lod0 == "on"))
        return
    if not a.sheet:
        state = snapshot(HIM + HER + EMPTY_ROOM)
        try:
            if not a.no_build:
                build()
            if a.previs:
                previs(a.previs, a.width, set(a.only.split(",")) if a.only else None)
        finally:
            restore(state)
    if a.sheet or a.previs:
        print(sheet())


if __name__ == "__main__":
    main()
