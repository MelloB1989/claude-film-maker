"""Proof-of-concept checks for running Unreal on a Linux box with no desktop (docs/linux/workflow.md, section 8), run
from the operator's side against a provisioned box (`film-ue provision`). Each check prints what it measured and
writes it to OUT/pocN.json; nothing here names a film: shots, cameras and references come in as arguments.

    film-ue --box linux poc 1                                 GPU, Vulkan, the engine's version from a commandlet
    film-ue --box linux poc 2                                 bridge installed, editor up offscreen, multi-tick job,
                                                              shader compile time, memory
    film-ue --box linux poc 3 --level /Game/Maps/Main --loc 0,-300,170 --look-at 0,0,150
                              [--sequence /Game/Seq/SEQ --frames 240,260 --camera CamLabel]
                                                              stills with no display (look.still, seq.stills)
    film-ue --box linux poc 4 --sequence /Game/Seq/SEQ --level /Game/Maps/Main --range 236:260 \\
                              [--width 1920 --height 1080 --temporal 8 --cvars '{"r.X": 0}'] \\
                              [--ref /mnt/win/.../MovieRenders/<shot>]   MRQ in the editor and in its own process;
                                                              frames compared with a reference render
    film-ue --box linux poc 5 --wav voice.wav --face-mesh /Game/.../Face_Mesh   audio to face (MetaHuman Animator)
    film-ue --box linux poc 6 [--preset NAME]                 MetaHuman cloud rig + textures: run, or ask to sign in?
    film-ue --box linux poc 7 --minutes 120 [poc 3/4 args]    soak: stills and short renders; memory over time

Common: --out DIR (default ./poc-out). Remote scratch goes to <project>/Saved/PoC on the box.
"""
from __future__ import annotations

import argparse
import json
import shlex
import tempfile
import time
from pathlib import Path

from . import client, workstation as ws

ENV = "set -a; . /etc/default/ue-editor; set +a"  # UE_ROOT, UE_PROJECT


def ok(res: dict):
    if not res.get("ok"):
        raise RuntimeError((res.get("stdout", "") + res.get("error", ""))[-2000:])
    return res.get("result")


def vec(s: str) -> list:
    return [float(x) for x in s.split(",")]


def scratch(*parts: str) -> str:
    return ws.project("Saved", "PoC", *parts)


def memory() -> dict:
    """The editor's resident memory and the GPU's used memory, read on the box."""
    out = ws.sh("echo rss_kb=$(ps -C UnrealEditor -o rss= | awk '{s+=$1} END {print s+0}'); "
                "echo vram_mb=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); "
                "echo scw=$(pgrep -c ShaderCompileWorker || true)", 60)
    kv = dict(line.split("=", 1) for line in out.split() if "=" in line)
    return {"rss_gb": round(int(kv.get("rss_kb") or 0) / 2**20, 2), "vram_gb": round(int(kv.get("vram_mb") or 0) / 1024, 2),
            "shader_workers": int(kv.get("scw") or 0)}


def log_grep(pattern: str, n: int = 20) -> list:
    log = ws.project("Saved", "Logs", "*.log")
    return ws.sh(f"grep -hiE {shlex.quote(pattern)} {log} 2>/dev/null | tail -n {n} || true", 60).splitlines()


# ------------------------------------------------------------------------------------------------- the checks

def poc1(a) -> dict:
    """The GPU, Vulkan and the engine: a commandlet (no rendering) prints the engine's version."""
    from . import linuxbox
    r = {"box": linuxbox.check()}
    code = "import unreal; print('FM_VERSION=' + unreal.SystemLibrary.get_engine_version())"
    t0 = time.time()
    out = ws.sh(f'{ENV}; "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd" "$UE_PROJECT" -run=pythonscript '
                f'-script={shlex.quote(code)} -unattended -nullrhi -nosplash -stdout 2>&1 | grep -E "FM_VERSION=|Error" | head -20',
                1800)
    r["commandlet_s"] = round(time.time() - t0)
    r["engine"] = next((line.split("=", 1)[1] for line in out.splitlines() if line.startswith("FM_VERSION=")), None)
    r["errors"] = [line for line in out.splitlines() if "Error" in line][:10]
    r["vulkan"] = ws.sh("vulkaninfo --summary 2>&1 | grep -E 'apiVersion|driverVersion|deviceName|deviceType' | head -8", 120)
    r["pass"] = bool(r["engine"]) and "none" not in r["box"].get("vulkan", "none")
    return r


TICKS = """def _job():
    import time
    t, n = time.time(), 0
    for _ in range(100):
        yield
        n += 1
    yield 0.5
    return {"ticks": n, "s": round(time.time() - t, 2)}
result = _job()
"""


def poc2(a) -> dict:
    """The editor offscreen under systemd, the bridge installed and answering, a multi-tick job, shader compile time."""
    from .cli import install
    r = {}
    t0 = time.time()
    r["install"] = install()  # on Linux: files over SSM, editor (re)started by systemd, waits for /health
    r["bridge_up_s"] = round(time.time() - t0)
    r["health"] = client.health()
    r["ticks"] = ok(client.exec_code(TICKS, 300))
    t1 = time.time()
    while memory()["shader_workers"] and time.time() - t1 < a.shader_wait * 60:
        time.sleep(30)
    r["shaders_settled_s"] = round(time.time() - t0)
    r["memory"] = memory()
    r["rhi"] = log_grep(r"Vulkan|RHI.*(Using|Selected)|GPU", 12)
    r["errors"] = log_grep(r"Error:|Fatal|Assertion", 15)
    r["screen"] = _screen_answer()
    r["pass"] = r["ticks"].get("ticks") == 100 and r["health"].get("platform", "").startswith("linux")
    return r


def _screen_answer() -> str:
    try:
        client.request("GET", "/screen", timeout=30)
        return "200 (a desktop?)"
    except SystemExit as e:
        return str(e)[:200]


def poc3(a, tag: str = "") -> dict:
    """Stills with no display: look.still through a fresh camera, and seq.stills through a sequence's camera."""
    out = Path(a.out) / f"poc3{tag}"
    r = {}
    if a.level:
        ok(client.exec_code(f"import unreal\nunreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level({a.level!r})\nresult = True", 600))
    cam = "PoC_Cam"
    ok(client.op("look.camera", label=cam, loc=vec(a.loc), look_at=vec(a.look_at), focal=35.0))
    t0 = time.time()
    remote = scratch("stills", f"look{tag}.png")
    try:
        r["look_still"] = ok(client.op("look.still", camera_label=cam, path=remote, width=1920, height=1080, timeout=120))
        r["look_still_s"] = round(time.time() - t0, 1)
    except (RuntimeError, SystemExit) as e:
        r["look_still_error"] = str(e)[-600:]
    if a.sequence and a.camera:
        frames = [int(f) for f in a.frames.split(",")]
        t0 = time.time()
        try:
            r["seq_stills"] = ok(client.op("seq.stills", path=a.sequence, frames=frames, camera=a.camera,
                                           out_dir=scratch("stills", f"seq{tag}"), timeout=900))
            r["seq_stills_s"] = round(time.time() - t0, 1)
        except (RuntimeError, SystemExit) as e:
            r["seq_stills_error"] = str(e)[-600:]
        ok(client.op("seq.close"))
    ws.pull_dir(scratch("stills"), str(out))
    r["files"] = {p.name: _stats(p) for p in sorted(out.rglob("*.png"))}
    r["pass"] = bool(r["files"]) and all(f["mean"] > 2 for f in r["files"].values())
    return r


def _stats(p: Path) -> dict:
    import numpy as np
    from PIL import Image
    im = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    return {"size": [im.shape[1], im.shape[0]], "mean": round(float(im.mean()), 1), "std": round(float(im.std()), 1)}


def ssim(x, y, win: int = 8) -> float:
    """Mean SSIM of two RGB frames on their luma, over win x win box windows (no SciPy needed)."""
    import numpy as np

    def luma(a):
        return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114

    def box(a):  # mean over every win x win window, by integral image
        c = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        return (c[win:, win:] - c[:-win, win:] - c[win:, :-win] + c[:-win, :-win]) / (win * win)
    a, b = luma(x).astype(np.float64), luma(y).astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = box(a), box(b)
    va, vb, cov = box(a * a) - ma * ma, box(b * b) - mb * mb, box(a * b) - ma * mb
    return float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))).mean())


def compare(new: Path, ref: Path, crops: dict | None = None) -> dict:
    """Frame by frame (matching names): SSIM, PSNR, mean absolute difference and the mean colour shift (new - ref,
    per channel, 0-255); as a baseline, the SSIM between adjacent reference frames (what motion alone costs); a
    side-by-side of the worst frame."""
    import numpy as np
    from PIL import Image

    def load(p):
        return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    rows = []
    for f in sorted(new.glob("*.png")):
        g = ref / f.name
        if not g.exists():
            continue
        x, y = load(f), load(g)
        if x.shape != y.shape:
            rows.append({"frame": f.stem, "error": f"size {x.shape[:2]} vs {y.shape[:2]}"})
            continue
        mse = float(((x - y) ** 2).mean())
        row = {"frame": f.stem, "ssim": round(ssim(x, y), 4),
               "psnr": round(10 * np.log10(255 ** 2 / mse), 2) if mse else 99.0,
               "mad": round(float(np.abs(x - y).mean()), 2),
               "shift_rgb": [round(float(v), 2) for v in (x - y).reshape(-1, 3).mean(0)]}
        for name, (cx, cy, cw, ch) in (crops or {}).items():  # a skin patch, the eyes, the hair, a shirt: x, y, w, h
            d = x[cy:cy + ch, cx:cx + cw] - y[cy:cy + ch, cx:cx + cw]
            row[f"crop_{name}"] = [round(float(v), 2) for v in d.reshape(-1, 3).mean(0)]
        rows.append(row)
    good = [r for r in rows if "ssim" in r]
    if not good:
        return {"frames": rows, "matched": 0}
    refs = sorted(ref.glob("*.png"))
    adjacent = [round(ssim(load(a_), load(b_)), 4) for a_, b_ in zip(refs, refs[1:])][:8]
    worst = min(good, key=lambda r: r["ssim"])
    a_, b_ = Image.open(new / f"{worst['frame']}.png").convert("RGB"), Image.open(ref / f"{worst['frame']}.png").convert("RGB")
    side = Image.new("RGB", (a_.width * 2, a_.height))
    side.paste(a_, (0, 0))
    side.paste(b_, (a_.width, 0))
    side.save(new.parent / f"{new.name}_vs_ref_{worst['frame']}.jpg", quality=90)
    n = len(good)
    picks = sorted({good[0]["frame"], good[n // 2]["frame"], worst["frame"]})
    _sheet(new, ref, picks, crops or {}, new.parent / f"{new.name}_vs_ref_sheet.jpg")
    crop_means = {k: [round(sum(r[k][i] for r in good) / n, 2) for i in range(3)] for k in good[0] if k.startswith("crop_")}
    return {"matched": n, "sheet": str(new.parent / f"{new.name}_vs_ref_sheet.jpg"), **crop_means, "ssim_min": worst["ssim"], "ssim_mean": round(sum(r["ssim"] for r in good) / n, 4),
            "psnr_min": min(r["psnr"] for r in good), "psnr_mean": round(sum(r["psnr"] for r in good) / n, 2),
            "mad_max": max(r["mad"] for r in good),
            "shift_rgb_mean": [round(sum(r["shift_rgb"][i] for r in good) / n, 2) for i in range(3)],
            "ref_adjacent_ssim": adjacent, "worst": worst["frame"], "frames": rows}


def _sheet(new: Path, ref: Path, frames: list, crops: dict, out: Path) -> None:
    """A contact sheet: per frame, Linux on the left and Windows on the right, at half size, crops outlined."""
    from PIL import Image, ImageDraw
    tiles = []
    for fr in frames:
        pair = []
        for src in (new, ref):
            im = Image.open(src / f"{fr}.png").convert("RGB")
            d = ImageDraw.Draw(im)
            for name, (cx, cy, cw, ch) in crops.items():
                d.rectangle([cx, cy, cx + cw, cy + ch], outline=(255, 0, 255), width=3)
                d.text((cx + 4, cy + 4), name, fill=(255, 0, 255))
            d.text((12, 12), f"{'Linux' if src == new else 'Windows'} {fr}", fill=(255, 255, 0))
            pair.append(im.resize((im.width // 2, im.height // 2)))
        tiles.append(pair)
    w, h = tiles[0][0].size
    sheet = Image.new("RGB", (w * 2, h * len(tiles)))
    for i, (l_, r_) in enumerate(tiles):
        sheet.paste(l_, (0, i * h))
        sheet.paste(r_, (w, i * h))
    sheet.save(out, quality=88)


def _render(a, executor: str, name: str) -> dict:
    start, end = (int(x) for x in a.range.split(":"))
    remote = scratch("renders", name)
    ok(client.exec_code(f"import shutil\nshutil.rmtree({remote!r}, ignore_errors=True)\nresult = True"))
    ok(client.op("seq.close"))
    t0 = time.time()
    ok(client.op("render.mrq", sequence=a.sequence, level=a.level, out_dir=remote, width=a.width, height=a.height,
                 start=start, end=end, temporal=a.temporal, spatial=1, warmup=32, name=name,
                 cvars=json.loads(a.cvars) if a.cvars else None, executor=executor, path_tracer=a.path_tracer,
                 save_dirty=a.save_dirty))
    peak = {"rss_gb": 0.0, "vram_gb": 0.0}
    p = {}
    while time.time() - t0 < a.render_timeout * 60:
        time.sleep(15)
        p = ok(client.op("render.progress", out_dir=remote, expected=end - start))
        m = memory()
        peak = {k: max(peak[k], m[k]) for k in peak}
        if p["done"]:
            break
        if not p["rendering"] and not p["frames"]:  # the queue gave up before a frame: say so, do not sit out the timeout
            raise RuntimeError(f"{executor}: the render stopped with no frames after {round(time.time() - t0)} s")
    dt = time.time() - t0
    files = ws.sh(f"ls {shlex.quote(remote)}", 60).split()
    child = log_grep(r"command line|NewProcess|MoviePipelineNewProcess|Launching", 10) if executor == "process" else []
    return {"child_command_line": child, "executor": executor, "frames": p.get("frames"), "expected": end - start, "s": round(dt),
            "s_per_frame": round(dt / max(1, p.get("frames") or 1), 1), "wav": [f for f in files if f.endswith(".wav")],
            "peak": peak, "dir": remote}


def poc4(a, tag: str = "") -> dict:
    """MRQ with no display: in the editor (PIE), then in its own -game -RenderOffscreen process; compared with a
    reference render (same frames, same settings) when --ref names one on the box."""
    out = Path(a.out) / f"poc4{tag}"
    r = {}
    for executor in a.executors.split(",") if not tag else ("pie",):
        name = f"{executor}{tag}"
        try:
            r[executor] = _render(a, executor, name)
            ws.pull_dir(r[executor]["dir"], str(out / name))
        except (RuntimeError, SystemExit) as e:
            r[executor] = {"error": str(e)[-800:]}
    if a.ref:
        _fetch_ref(a, out / "ref")
        for executor in ("pie", "process"):
            if (out / executor).exists():
                r[f"{executor}_vs_ref"] = compare(out / executor, out / "ref", json.loads(a.crops) if a.crops else None)
    r["errors"] = log_grep(r"Error:|Fatal|Assertion|MovieRenderPipeline.*(fail|error)", 15)
    pie = r.get("pie", {})
    r["pass"] = bool(pie.get("frames")) and pie.get("frames") >= pie.get("expected", 1)
    return r


def _fetch_ref(a, dest: Path) -> None:
    """The reference frames for --range: from an s3:// prefix (only those frames, synced here) or a folder on the box."""
    import subprocess
    start, end = (int(x) for x in a.range.split(":"))
    if a.ref.startswith("s3://"):
        inc = [x for f in range(start, end) for x in ("--include", f"{f:04d}.png")]
        subprocess.run(["aws", "s3", "sync", "--only-show-errors", a.ref.rstrip("/") + "/", str(dest), "--exclude", "*",
                        *inc, "--region", ws.conf()["region"]], check=True)
    else:
        ws.pull_dir(a.ref, str(dest))


def poc5(a) -> dict:
    """Audio to face on Linux (MetaHuman Animator's audio solver; a MetaHumanPerformance asset)."""
    with tempfile.TemporaryDirectory() as d:
        Path(d, Path(a.wav).name).write_bytes(Path(a.wav).read_bytes())
        ws.push_dir(d, scratch("audio"))
    t0 = time.time()
    r = {}
    try:
        r["result"] = ok(client.op("speech.to_face", wav=ws.rjoin(scratch("audio"), Path(a.wav).name), name="PoC",
                                   face_mesh=a.face_mesh, folder="/Game/PoC/Speech", timeout=1800))
    except (RuntimeError, SystemExit) as e:
        r["error"] = str(e)[-1200:]
    r["s"] = round(time.time() - t0)
    r["log"] = log_grep(r"MetaHuman|Performance|NNE|audio", 15)
    r["pass"] = bool(r.get("result", {}).get("frames"))
    return r


def poc6(a) -> dict:
    """MetaHuman cloud services: does the auto-rig / texture synthesis run headless, or fail asking for a sign-in?"""
    r = {}
    preset = a.preset or ok(client.op("mh.presets"))[0]
    dest = "/Game/PoC/MH_PoC"
    r["preset"] = preset
    ok(client.op("mh.from_preset", preset=preset, dest=dest, overwrite=True))
    for name in ("mh.rig", "mh.textures"):
        t0 = time.time()
        try:
            r[name] = {"result": ok(client.op(name, character=dest, timeout=1800)), "s": round(time.time() - t0)}
        except (RuntimeError, SystemExit) as e:
            r[name] = {"error": str(e)[-1200:], "s": round(time.time() - t0)}
    r["log"] = log_grep(r"login|log in|sign.?in|auth|account|EOS|cloud|AutoRig|TextureSynthesis", 25)
    r["pass"] = all("error" not in r[n] for n in ("mh.rig", "mh.textures"))
    return r


def poc7(a) -> dict:
    """A soak: stills every few minutes and a short render every so often; the editor's memory over time."""
    t0, series, events = time.time(), [], []
    last_still = last_render = 0.0
    n = 0
    while time.time() - t0 < a.minutes * 60:
        now = time.time()
        if now - last_still >= a.still_every * 60 and a.loc:
            n += 1
            try:
                poc3(a, tag=f"_soak{n}")
                events.append({"t_min": round((now - t0) / 60, 1), "still": "ok"})
            except Exception as e:  # keep soaking: the point is what happens over time
                events.append({"t_min": round((now - t0) / 60, 1), "still": str(e)[-300:]})
            last_still = now
        if now - last_render >= a.render_every * 60 and a.sequence and a.range:
            try:
                poc4(a, tag=f"_soak{n}")
                events.append({"t_min": round((now - t0) / 60, 1), "render": "ok"})
            except Exception as e:
                events.append({"t_min": round((now - t0) / 60, 1), "render": str(e)[-300:]})
            last_render = now
        try:
            series.append({"t_min": round((time.time() - t0) / 60, 1), **memory(), "bridge": client.health().get("ok")})
        except Exception as e:
            series.append({"t_min": round((time.time() - t0) / 60, 1), "error": str(e)[-200:]})
        time.sleep(60)
    rss = [s["rss_gb"] for s in series if "rss_gb" in s]
    half = len(rss) // 2
    growth = round((sum(rss[half:]) / max(1, len(rss) - half)) - (sum(rss[:half]) / max(1, half)), 2) if rss else None
    return {"series": series, "events": events, "rss_growth_gb_2nd_half_vs_1st": growth,
            "pass": all(s.get("bridge") for s in series) and (growth is not None and growth < 2.0)}


CHECKS = {"1": poc1, "2": poc2, "3": poc3, "4": poc4, "5": poc5, "6": poc6, "7": poc7}


def main(argv: list) -> None:
    ap = argparse.ArgumentParser(prog="film-ue poc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", help="1-7, or a list: 1,2,3")
    ap.add_argument("--out", default="poc-out")
    ap.add_argument("--shader-wait", type=float, default=120, help="poc 2: minutes to wait for shader compiles")
    ap.add_argument("--level", default="")
    ap.add_argument("--loc", default="", help="poc 3: camera location x,y,z (cm)")
    ap.add_argument("--look-at", default="0,0,150")
    ap.add_argument("--sequence", default="")
    ap.add_argument("--camera", default="", help="poc 3: a camera actor's label for seq.stills")
    ap.add_argument("--frames", default="", help="poc 3: frames for seq.stills, comma-separated")
    ap.add_argument("--range", default="", help="poc 4: start:end (end exclusive), sequence frames")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--temporal", type=int, default=8)
    ap.add_argument("--cvars", default="", help='poc 4: JSON, e.g. \'{"r.HairStrands.SkyLighting": 0}\'')
    ap.add_argument("--crops", default="", help='poc 4: JSON {"skin": [x, y, w, h], "eyes": [...], ...} in pixels')
    ap.add_argument("--save-dirty", action="store_true", help="poc 4: save unsaved packages before a process render")
    ap.add_argument("--path-tracer", action="store_true", help="poc 4: the path tracer instead of the deferred pass")
    ap.add_argument("--executors", default="pie,process", help="poc 4: pie, process or both")
    ap.add_argument("--ref", default="", help="poc 4: reference frames (same names): s3://prefix or a folder on the box")
    ap.add_argument("--render-timeout", type=float, default=120, help="poc 4: minutes")
    ap.add_argument("--wav", default="")
    ap.add_argument("--face-mesh", default="")
    ap.add_argument("--preset", default="")
    ap.add_argument("--minutes", type=float, default=120)
    ap.add_argument("--still-every", type=float, default=5)
    ap.add_argument("--render-every", type=float, default=30)
    a = ap.parse_args(argv)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for w in a.which.split(","):
        t0 = time.time()
        try:
            r = CHECKS[w](a)
        except Exception as e:  # a check that cannot even run is a result too
            r = {"pass": False, "error": f"{type(e).__name__}: {str(e)[-1500:]}"}
        r["wall_s"] = round(time.time() - t0)
        Path(a.out, f"poc{w}.json").write_text(json.dumps(r, indent=1, default=str))
        print(f"poc {w}: {'PASS' if r.get('pass') else 'FAIL'} ({r['wall_s']} s) -> {a.out}/poc{w}.json", flush=True)
