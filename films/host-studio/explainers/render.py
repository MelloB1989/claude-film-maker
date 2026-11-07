"""Render an explainer's presenter shots on a box, as agent-11's composite reads them: one folder per shot,
shot<NN>_<CAM>/<frame>.png with the SEQUENCE frame number, ±6 handle frames, an h264 preview per shot, all synced to
s3 private/renders/r6/explain/<film>/ (KMS). The performance is one continuous sequence; each shot is rendered
through its own camera alone (the cut track set to that camera for the whole range while it renders, the edit put
back after), pre-rolled from frame 0 so hair and cloth arrive as in one continuous take.

    uv run python ../films/host-studio/explainers/render.py --box boxb --instance i-0123 --who her \
        --edl ../films/host-studio/explainers/edl/netflix.json --film netflix [--preset preview|final] [--shots 1,2]

Run set.py --check, groom.lock and the leaders check before it. Face rule: every frame here has a presenter in it:
box and s3 private/ only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import set as S  # noqa: E402

OUT = "/srv/ue/explainer/renders"
S3 = f"{S.BUCKET}/private/renders/r6/explain"
# round 5's film cvars (groom.lock's render_cvars, SSS full res); r.HairStrands.SkyLighting 0 as studio.py sets it
CVARS = {"r.SSS.Quality": 1, "r.SSS.HalfRes": 0, "r.HairStrands.LODMode": 0, "r.HairStrands.AutoLOD.Bias": 1.0,
         "r.HairStrands.UseCardsInsteadOfStrands": 0, "r.HairStrands.SkyLighting": 0,
         # r6b (the CU f1300 rectangular tile blocks: textures still streaming in): every used texture fully resident,
         # a pool big enough for the set at full mips (L40S 46 GB), and warm-up frames before the first kept frame
         "r.Streaming.FullyLoadUsedTextures": 1, "r.Streaming.PoolSize": 12000}
PRESETS = {
    "preview": {"preset": "preview", "spatial": 1, "temporal": 2, "width": 1920, "height": 1080, "warmup_render": 16},
    "final": {"preset": "final", "spatial": 4, "temporal": 8, "width": 1920, "height": 1080, "aa_method": "none",
              "warmup_render": 24},
}


def spec(who: str, film: str, n: int, cam: str, f0: int, f1: int, preset: str) -> dict:
    out = f"{OUT}/{film}/{preset}/shot{n:02d}_{cam}"
    return {"kind": "render", "version": 1, "name": f"exp_{film}_{preset}_shot{n:02d}_{cam}", "sequence": S.SEQ[who],
            "level": S.LEVELS[who], "out_dir": out, "frames": [f0, f1], "chunking": "none", "preroll": "cut",
            "warmup_engine": 22, "shutter_timing": "open", "overwrite": False, "zero_pad": 4, "cvars": CVARS,
            **{k: v for k, v in PRESETS[preset].items()}}


def post(film: str, preset: str, shots: list, audio: str = "") -> None:
    """On the box: an h264 preview per shot (24 fps; with `audio`, an s3 key or box path of the film's mix, its slice
    from the shot's first frame muxed in, for judging lips), then sync to s3 (KMS)."""
    base = f"{OUT}/{film}/{preset}"
    dirs = [f"shot{n:02d}_{cam}" for n, cam, _, _ in shots]
    code = f"""import subprocess, os, glob
base, res, audio = {base!r}, {{}}, {audio!r}
if audio.startswith("s3://"):
    local = f"{{base}}/_mix.wav"
    subprocess.run(["aws", "s3", "cp", "--only-show-errors", audio, local])
    audio = local
for d in {dirs!r}:
    pngs = sorted(glob.glob(f"{{base}}/{{d}}/[0-9]*.png")) or sorted(glob.glob(f"{{base}}/{{d}}/[0-9]*.jpeg"))
    if not pngs:
        res[d] = "no frames"; continue
    ext = os.path.splitext(pngs[0])[1]  # the preview preset writes jpeg, the finals png
    first = int(os.path.basename(pngs[0]).split(".")[0])
    a = ["-ss", f"{{first / 24:.4f}}", "-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k",
         "-shortest"] if audio else []
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-start_number", str(first),
                        "-i", f"{{base}}/{{d}}/%04d{{ext}}", *a, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                        f"{{base}}/{{d}}.mp4"], capture_output=True, text=True)
    res[d] = [len(pngs), first, r.returncode, r.stderr[-200:]]
r = subprocess.run(["aws", "s3", "sync", base, {f"{S3}/{film}/{preset}/"!r}, "--sse", "aws:kms", "--only-show-errors"],
                   capture_output=True, text=True)
res["s3"] = [r.returncode, r.stderr[-300:]]
result = res"""
    print(json.dumps(S.ex(code), indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--box", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--who", required=True, choices=["her", "him"])
    ap.add_argument("--edl", required=True)
    ap.add_argument("--film", required=True)
    ap.add_argument("--preset", default="preview", choices=sorted(PRESETS))
    ap.add_argument("--shots", help="only these shot numbers (comma list)")
    ap.add_argument("--dry", action="store_true", help="print the plan and the specs, touch nothing")
    ap.add_argument("--post-only", action="store_true", help="only encode the previews and sync (frames on disk)")
    ap.add_argument("--audio", default="", help="the film's mix (s3 key or box path) muxed into each preview")
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text())
    plan = S.render_plan(edl)
    if a.shots:
        keep = {int(x) for x in a.shots.split(",")}
        plan = [p for p in plan if p[0] in keep]
    if a.dry:
        for n, cam, f0, f1 in plan:
            print(json.dumps(spec(a.who, a.film, n, cam, f0, f1, a.preset)))
        return 0
    os.environ["FILM_UE_BOX"] = a.box
    from filmtools.unreal import client
    S.client = client
    S.guard(a.box, a.instance)
    if a.post_only:
        post(a.film, a.preset, plan, a.audio)
        return 0
    seq, failed = S.SEQ[a.who], []
    box_json = HERE / "numbers" / a.film / "box.json"
    box = json.loads(box_json.read_text()) if box_json.exists() else {}
    jobs = box.setdefault("jobs", [])
    try:
        for cam in dict.fromkeys(p[1] for p in plan):  # one cut change per camera, its shots in order
            S.op("seq.camera_cuts", path=seq, cuts=[[cam, 0]])
            for n, c, f0, f1 in [p for p in plan if p[1] == cam]:
                # garment.leaders_ok (agent-09's hard row): every garment led by Body, read right before EVERY job
                # + agent-06's pre-render guard: no Test_*/FMQA_* or second presenter, her face lit in this camera
                S.op("mh.leader", label=S.ACTOR[a.who])
                g = S.guard_scene(a.who, c, (f0 + f1) // 2)
                lead = {"pass": g["ok"], "why": g["why"]}
                jobs.append({"job": f"{a.preset}/shot{n:02d}_{c}", "frames": [f0, f1], "box": a.instance,
                             "at": time.strftime("%Y-%m-%d %H:%M:%S"), "garment.leaders_ok": g["leaders_ok"],
                             "strays": g["strays"], "face_luma": g.get("face_luma"), "guard_ok": int(bool(g["ok"])),
                             # shot.streaming_settled: the spec warms streaming (CVARS + warm-up frames); the job's first
                             # frame goes to the orchestrator's 1:1 eye (no tile blocks), who sets the value
                             "streaming_warmed": 1, "first_frame": f"{a.preset}/shot{n:02d}_{c}/{f0:04d}.png",
                             "shot.streaming_settled": None})
                box["garment.leaders_ok"] = min(j["garment.leaders_ok"] for j in jobs)
                box_json.parent.mkdir(parents=True, exist_ok=True)
                box_json.write_text(json.dumps(box, indent=1) + "\n")
                if not lead.get("pass"):
                    print(f"shot{n:02d} {c}: GUARD FAIL ({lead.get('why')}): not rendered")
                    failed.append(n)
                    continue
                t = time.time()
                rep = S.ok(client.op("render.job", timeout=4 * 3600, spec=spec(a.who, a.film, n, c, f0, f1, a.preset)))
                print(f"shot{n:02d} {c} [{f0},{f1}) {rep.get('status')} {rep.get('frames')} frames "
                      f"{time.time() - t:.0f} s")
                if rep.get("status") != "ok":
                    failed.append(n)
    finally:  # the edit back, whatever happened
        S.op("seq.camera_cuts", path=seq, cuts=S.edl_cuts(edl))
        S.op("assets.save", paths=[seq])
    post(a.film, a.preset, plan, a.audio)
    print("FAILED shots:", failed if failed else "none")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
