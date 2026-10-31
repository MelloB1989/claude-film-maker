"""The host's first line as a finished shot, on the Unreal workstation through the bridge: the voice solved to a face
in a mood, two cameras (a slow push-in and a punch-in cut on the pauses), face and body made one skeleton (so the
chest never pokes through the shirt), the eyes locked on the lens, a Movie Render Queue render, and the frames
brought back and cut into an mp4 with the voice.

    cd tools && uv run python ../films/host-studio/shot.py [--solve] [--cams] [--sync] [--gaze] [--render] [--all]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from filmtools.unreal import client, workstation as ws

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "host-studio"
PROJECT = r"C:\UEProjects\HostStudio"
SEQ, LEVEL = "/Game/Studio/SEQ_Line2", "/Game/Studio/Studio"
FACE_MESH = "/Game/Host/Unpacked/Host/Face/SKM_Host_Trey_FaceMesh"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
ANIM = "/Game/Speech/Anim"
WAV = rf"{PROJECT}\Saved\Import\line1.wav"
SUPER35 = (23.76, 13.365)
# the edit: cut on the voice's pauses (silences at 1.4, 5.6, 8.7, 10.6 s; 24 fps)
CUTS = [["HostCam", 0], ["HostCamB", 144], ["HostCam", 216]]


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def solve(mood: str = "CONFIDENCE", intensity: float = 1.0) -> dict:
    return ok(client.op("speech.to_face", wav=WAV, name="line1_conf", face_mesh=FACE_MESH, mood=mood, intensity=intensity))


def cams() -> dict:
    ok(client.op("seq.close"))
    eyes = [0.0, 9.0, 174.0]  # the host's eyes in its own frame (it stands at the origin turned -90)
    ok(client.op("look.camera", label="HostCamB", loc=[229, 6, 169.3], look_at=[0, 0, 166], focal=58.0, aperture=2.0,
                 filmback=list(SUPER35), pilot=False))
    for cam in ("HostCam", "HostCamB"):
        ok(client.op("look.focus_track", camera_label=cam, target="Host", offset=eyes))
    keys = ok(client.op("seq.key_transform", path=SEQ, label="HostCam",
                        keys=[[0, [243, 9, 169.3], [0, 0, 157]], [300, [219, 3, 169.3], [0, 0, 157]]]))
    cuts = ok(client.op("seq.camera_cuts", path=SEQ, cuts=CUTS))
    return {"keys": keys, "cuts": cuts}


def sync() -> dict:
    """One skeleton for face and body. The face rig turns the head from the speech on the face alone, so its neck and
    chest drift from the body (and through the shirt): ride the face on the body with its head control still on, give
    the body the head motion that makes, then bake the whole shared skeleton back on the face with head control off."""
    ok(client.op("seq.set_anim", path=SEQ, component="Body", anim=IDLE))
    ok(client.op("seq.set_anim", path=SEQ, component="Face", anim=f"{ANIM}/AS_line1_conf"))
    ok(client.op("anim.bake_follow", sequence=SEQ, actor_label="Host", anim=f"{ANIM}/AS_line1_conf",
                 out=f"{ANIM}/AS_line1_body", head_control=True, timeout=1800))
    ok(client.op("anim.head_to_body", sequence=SEQ, actor_label="Host", body_anim=IDLE, out=f"{ANIM}/AS_line1_bodyidle",
                 timeout=1800))
    return ok(client.op("anim.bake_follow", sequence=SEQ, actor_label="Host", anim=f"{ANIM}/AS_line1_conf",
                        out=f"{ANIM}/AS_line1_body", timeout=1800))


def gaze() -> dict:
    return ok(client.op("anim.gaze_lock", sequence=SEQ, actor_label="Host", anim=f"{ANIM}/AS_line1_body",
                        out=f"{ANIM}/AS_line1_gaze", camera="HostCam", timeout=1800))


def render(name: str = "line1_v2", temporal: int = 8, fetch_only: bool = False) -> Path:
    remote = rf"{PROJECT}\Saved\MovieRenders\{name}"
    if fetch_only:
        return encode(name, remote)
    ok(client.op("seq.close"))
    ok(client.op("assets.save_all"))
    ok(client.op("render.mrq", sequence=SEQ, level=LEVEL, out_dir=remote, temporal=temporal, name=name))
    t0 = time.time()
    while True:
        p = ok(client.op("render.progress", out_dir=remote))
        print(f"\r{p['frames']} frames, {time.time() - t0:.0f}s", end="", flush=True)
        if p["done"]:
            break
        time.sleep(15)
    print()
    return encode(name, remote)


def encode(name: str, remote: str) -> Path:
    """Bring a render's frames back (through S3) and cut them with its audio into out/host-studio/<name>.mp4."""
    local = OUT / "renders" / name
    print(ws.pull_dir(remote, str(local)), "files back")
    mp4 = OUT / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "24", "-i", str(local / "%04d.png"),
                    "-i", str(local / "MasterSubmixDefault.wav"), "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(mp4)],
                   check=True)
    return mp4


def main() -> None:
    ap = argparse.ArgumentParser()
    for f in ("solve", "cams", "sync", "gaze", "render", "all"):
        ap.add_argument(f"--{f}", action="store_true")
    ap.add_argument("--name", default="line1_v2")
    ap.add_argument("--temporal", type=int, default=8)
    ap.add_argument("--fetch", action="store_true", help="only bring back and encode a finished render")
    a = ap.parse_args()
    if a.solve or a.all:
        print("solve:", json.dumps(solve()))
    if a.cams or a.all:
        print("cams:", json.dumps(cams()))
    if a.sync or a.all:
        print("sync:", json.dumps(sync()))
    if a.gaze or a.all:
        g = gaze()
        print("gaze:", json.dumps({k: g[k] for k in ("anim", "frames", "passes")}))
    if a.render or a.all or a.fetch:
        print("render:", render(a.name, a.temporal, fetch_only=a.fetch))


if __name__ == "__main__":
    main()
