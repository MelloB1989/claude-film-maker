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

from filmtools.unreal import client

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
REMOTE = r"C:\UEProjects\HostStudio\Saved\Previs\reel_cut"


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


def cameras() -> None:
    """A Reel_ cine camera per shot, placed at its first frame, then its move and focus keyed."""
    for s in SHOTS:
        loc, at = s.keys[0][1], s.keys[0][2]
        ok(client.op("look.camera", label=f"Reel_{s.id}", loc=loc, look_at=at, focal=float(s.lens),
                     aperture=float(s.stop), filmback=list(FULL_FRAME), pilot=False))
    rebind([f"Reel_{s.id}" for s in SHOTS])
    for s in SHOTS:
        lab, sm = f"Reel_{s.id}", M.samples(s)
        keys = [[s.start + f, loc, {"pitch": pitch, "yaw": yaw, "roll": 0.0}] for f, loc, pitch, yaw, _ in sm]
        ok(client.op("seq.key_transform", path=SEQ, label=lab, keys=keys))
        ok(client.op("seq.key_float", path=SEQ, label=lab, component="CameraComponent", prop=FOCUS,
                     keys=[[s.start + f, d] for f, *_, d in sm]))
        print(s.id, f"{s.lens:g}mm T{s.stop:g}", len(keys), "keys", flush=True)


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


def build() -> None:
    if not exists(["Host"]):
        raise SystemExit("no Host in the level: `film-ue op level.open path=/Game/Studio/Studio` first")
    sequence()
    rebind(HIM + HER + EMPTY_ROOM)
    cameras()
    marks()
    ok(client.op("seq.camera_cuts", path=SEQ, cuts=M.cuts()))
    got = ok(client.op("seq.cuts", path=SEQ))
    want = [[c, f, (M.cuts() + [[None, END]])[k + 1][1]] for k, (c, f) in enumerate(M.cuts())]
    # the ranges must match; the camera names too, once seq.cuts gives labels (it gave a Guid's repr on 2026-11-01)
    if [g[1:3] for g in got] != [w[1:] for w in want] or any(g[0].startswith("Reel_") and g[0] != w[0]
                                                              for g, w in zip(got, want)):
        raise SystemExit(f"the cut in SEQ_Reel is not the plan's: {got}")
    print("cut:", len(got), "shots,", got[0][1], "to", got[-1][2])


def previs(every: int, width: int, only: set | None = None) -> None:
    """Viewport stills across the cut, each through its own shot's camera: every `every` frames of each shot from its
    first, and its last frame, into previs/cut/<shot>_<frame>.png."""
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SHOTS:
        if only and s.id not in only:
            continue
        frames = sorted(set(range(s.start, s.end, every)) | {s.end - 1})
        remote = rf"{REMOTE}\{s.id}"
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
    a = ap.parse_args()
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
