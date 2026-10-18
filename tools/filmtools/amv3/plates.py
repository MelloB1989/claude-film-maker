"""Timeless v3: shot plates for the Blender stage (runs on the render VM: ffmpeg + numpy + opencv, python 3.10).

    python tools/filmtools/amv3/plates.py [--edl films/timeless/amv3/edl.json] [--data $AMV3_DATA] [--only S08,P1]
                                          [--jobs 12] [--sheets-copy out/plates_sheets]

For every shot of edl.json and the triptych panels P1-P3 writes `<data>/plates/<id>/f_NNNNN.jpg` (q 95, 1920x1080,
NNNNN = absolute comp frame) and `<data>/plates/<id>/plate.json`, plus a contact sheet `<data>/plates/_sheets/<id>.jpg`.

Frames: shots [a-16, b+16), panels [f, 819+16), clamped to 0..899. Source = `$AMV2_DATA/src240/clip_<clip>.mp4` (RIFE
240 fps, same timeline as the 60 fps clip: 240 fps frame 4k = clip frame k). Comp frame -> source time:
  shots   v2's remap (tools/filmtools/amv2/remap.py: speed profiles, exact ends, source_cut landing on its frame); in the
          handles the boundary speed continues; clamped to the clip (first/last real frame held).
  panels  v2's triptych: s0 at the panel's hit f, linear to s1 at f + (819 - f + 9), same speed beyond.
The nearest 240 fps frame is taken (no blending). Around every scene cut of the clip (the tagged source_cut and any
other cut ffmpeg finds) the RIFE in-betweens straddle two scenes, so frames there snap to the last real frame of the old
scene / the first real frame of the new one: the clip's own cuts stay clean.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from filmtools.amv2.remap import Remap  # noqa: E402

W, H = 1920, 1080
SRC_FPS, R240 = 60.0, 240
CUT_MIN = 0.12            # ffmpeg scene score that counts as a cut (v2 ecbuild)
PANEL_TAIL = 9            # v2 triptych: the panel plays s0 -> s1 over [f, 819 + 9)
PEAK = 3.0                # a cut's score vs its neighbours'
BLACK = 6.0               # mean luma below this = a black frame


def amv2_data():
    return Path(os.environ.get("AMV2_DATA", "/home/nikhil/code/film-making/work/timeless_v2"))


def probe_n240(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return int(r.stdout.strip().split(",")[0])


def scene_cuts(clip_file):
    """[(t, score)] of the 60 fps clip's own scene cuts (t = first frame of the new scene). A cut is an isolated peak of
    the ffmpeg scene score: >= CUT_MIN and >= PEAK x every other score within +-3 frames (fast motion gives runs of
    high scores, a cut gives one spike)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(clip_file), "-vf",
                        "select='gte(scene,0)',metadata=print:key=lavfi.scene_score", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    t = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    s = [float(x) for x in re.findall(r"scene_score=([\d.]+)", r.stderr)]
    out = []
    for i, (a, b) in enumerate(zip(t, s)):
        nb = s[max(0, i - 3):i] + s[i + 1:i + 4]
        if b >= CUT_MIN and all(b >= PEAK * x for x in nb):
            out.append((a, b))
    return out


def items(E):
    out = []
    hd, dur = E["handle"], E["dur"]
    for sh in E["shots"]:
        out.append(dict(id=sh["id"], kind="shot", clip=sh["clip"], file=sh["file"], a=sh["a"], b=sh["b"],
                        lo=max(0, sh["a"] - hd), hi=min(dur, sh["b"] + hd), src=sh["src"], speed=sh["speed"],
                        fx=sh.get("fx", [])))
    tri = E["triptych"]
    for p in tri["panels"]:
        out.append(dict(id=p["id"], kind="panel", clip=p["clip"], file=p["file"], a=p["f"],
                        b=tri["shatter"] + PANEL_TAIL, lo=p["f"], hi=min(dur, tri["f1"] + hd), src=list(p["src"]),
                        speed="const", fx=[]))
    return out


def source_times(it, cuts):
    """{comp frame: source time (unclamped)} and the tagged cut (F, tc) or None."""
    n = it["b"] - it["a"]
    cut = None
    if it["kind"] == "shot":
        for tag in it["fx"]:
            m = re.fullmatch(r"source_cut@(\d+)", tag)
            if m:
                F = int(m.group(1))
                lo, hi = sorted(it["src"])
                inside = [c for c in cuts if lo < c[0] < hi]
                if not inside:
                    raise SystemExit(f"{it['id']}: no source cut in {it['clip']} {lo}..{hi}")
                tc = max(inside, key=lambda c: c[1])[0]
                cut = (F - it["a"], tc)
        rm = Remap(it["src"], n, it["speed"], cut)
        T = {f: rm(f - it["a"]) for f in range(it["lo"], it["hi"])}
    else:
        s0, s1 = it["src"]
        T = {f: s0 + (s1 - s0) * (f - it["a"]) / n for f in range(it["lo"], it["hi"])}
    return T, cut


def pick_frames(T, n240, cuts, a, b):
    """comp frame -> (src240 index, held?). The clip is split into scenes at its cuts (real 240 fps frames 4k only:
    the RIFE in-betweens of a cut straddle two scenes). Inside [a, b) a frame snaps to the nearest real frame of the
    scene its time falls in; in the handles the time is clamped to the scene of the shot's first/last frame (the
    handle holds instead of jumping into another scene), and to the clip."""
    top = 4 * ((n240 - 1) // 4)                      # last 240 fps frame that is a real clip frame
    ks = sorted({int(round(t * SRC_FPS)) for t, _ in cuts if 0 < int(round(t * SRC_FPS)) * 4 <= top})
    starts = [0] + [4 * k for k in ks]
    scenes = [(lo, (starts[i + 1] - 4) if i + 1 < len(starts) else top) for i, lo in enumerate(starts)]

    def scene_of(x):
        x = min(max(x, 0.0), top)
        for lo, hi in scenes:
            if x < hi + 2 or (lo, hi) == scenes[-1]:   # in-betweens: the nearer side of the cut
                return lo, hi
        return scenes[-1]

    sa = scene_of(T[a] * R240) if a in T else None
    sb = scene_of(T[b - 1] * R240) if (b - 1) in T else None
    out = {}
    for f, t in T.items():
        x = t * R240
        sc = (sa if f < a else sb if f >= b else scene_of(x)) or scene_of(x)
        lo, hi = sc
        held = x < lo - 0.5 or x > hi + 0.5
        out[f] = (int(round(min(max(x, lo), hi))), held)
    return out


def decode(path, need):
    """{src240 index: BGR frame} for the indices in `need` (one sequential decode of the range)."""
    hi = max(need)
    # decode from the start (clips are <= ~1100 frames at 240 fps): exact frame numbering, no seek ambiguity
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", str(hi + 1), "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-"]
    start = 0
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    sz = W * H * 3
    got, j = {}, start
    while j <= hi:
        buf = p.stdout.read(sz)
        if len(buf) < sz:
            break
        if j in need:
            got[j] = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        j += 1
    p.stdout.close()
    p.wait()
    return got, start


def label(img, text, y, scale=0.5, col=(255, 255, 255)):
    cv2.putText(img, text, (4, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (4, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 1, cv2.LINE_AA)


def sheet(it, frames, picks, path, cols=10, tw=240):
    th = tw * H // W
    fs = sorted(frames)
    rows = (len(fs) + cols - 1) // cols
    S = np.zeros((rows * th + 30, cols * tw, 3), np.uint8)
    label(S, f"{it['id']} {it['clip']} [{it['a']},{it['b']}) plates {fs[0]}..{fs[-1]}  green=in shot  grey=handle  "
             f"red=held  orange=source cut", 20, 0.55)
    for n, f in enumerate(fs):
        t = cv2.resize(frames[f], (tw, th), interpolation=cv2.INTER_AREA)
        j, held = picks[f]
        col = (0, 200, 0) if it["a"] <= f < it["b"] else (128, 128, 128)
        if held:
            col = (0, 0, 255)
        if f == it.get("cut_f"):
            col = (0, 140, 255)
        cv2.rectangle(t, (0, 0), (tw - 1, th - 1), col, 3)
        label(t, f"f{f} s{j}", 16)
        r, c = divmod(n, cols)
        S[30 + r * th:30 + (r + 1) * th, c * tw:(c + 1) * tw] = t
    cv2.imwrite(str(path), S, [cv2.IMWRITE_JPEG_QUALITY, 85])


def run_item(args):
    it, data, cuts_by_clip, sheets_copy = args
    src = amv2_data() / "src240" / f"clip_{it['clip']}.mp4"
    n240 = probe_n240(src)
    cuts = cuts_by_clip[it["clip"]]
    T, cut = source_times(it, cuts)
    picks = pick_frames(T, n240, cuts, it["a"], it["b"])
    if cut is not None:
        # the tagged cut: frames before F show the old scene, F onwards the new (the cut is the 60 fps frame k = tc*60)
        F = it["a"] + cut[0]
        k = int(round(cut[1] * SRC_FPS))
        fwd = it["src"][1] > it["src"][0]
        for f, (j, h) in picks.items():
            if (f < F) == fwd:
                picks[f] = (min(j, 4 * (k - 1)), h)
            else:
                picks[f] = (max(j, 4 * k), h)
        it["cut_f"] = F
    need = {j for j, _ in picks.values()}
    got, start = decode(src, need)
    miss = sorted(need - set(got))
    if miss:
        raise RuntimeError(f"{it['id']}: decode missed src240 frames {miss[:10]} (n240={n240})")
    d = data / "plates" / it["id"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    frames = {}
    for f, (j, _) in sorted(picks.items()):
        cv2.imwrite(str(d / f"f_{f:05d}.jpg"), got[j], [cv2.IMWRITE_JPEG_QUALITY, 95])
        frames[f] = got[j]
    # verify: counts, black frames, duplicate runs that are not deliberate holds
    issues = []
    files = sorted(d.glob("f_*.jpg"))
    if len(files) != it["hi"] - it["lo"]:
        issues.append(f"count {len(files)} != {it['hi'] - it['lo']}")
    fs = sorted(frames)
    luma = {f: float(cv2.cvtColor(frames[f], cv2.COLOR_BGR2GRAY).mean()) for f in fs}
    blacks = [f for f in fs if luma[f] < BLACK]
    if blacks:
        issues.append(f"black frames {blacks}")
    dup = []
    for f0, f1 in zip(fs, fs[1:]):
        same_idx = picks[f0][0] == picks[f1][0]
        if same_idx and not (picks[f0][1] or picks[f1][1]):
            dup.append(f1)
        elif not same_idx:
            diff = float(np.abs(frames[f0].astype(np.int16) - frames[f1].astype(np.int16)).mean())
            if diff < 0.3:
                dup.append(f1)
    if dup:
        issues.append(f"duplicate (non-hold) frames {dup}")
    meta = dict(id=it["id"], kind=it["kind"], clip=it["clip"], src240=str(src), n240=n240, a=it["a"], b=it["b"],
                lo=it["lo"], hi=it["hi"], src=it["src"], speed=it["speed"],
                source_cut=dict(f=it["a"] + cut[0], t=cut[1]) if cut else None,
                clip_cuts=[[round(t, 4), round(s, 3)] for t, s in cuts], issues=issues,
                frames={str(f): dict(t=round(T[f], 5), src240=picks[f][0], held=picks[f][1],
                                     luma=round(luma[f], 1)) for f in fs})
    (d / "plate.json").write_text(json.dumps(meta, indent=1))
    sd = data / "plates" / "_sheets"
    sd.mkdir(parents=True, exist_ok=True)
    sheet(it, frames, picks, sd / f"{it['id']}.jpg")
    if sheets_copy:
        Path(sheets_copy).mkdir(parents=True, exist_ok=True)
        shutil.copy(sd / f"{it['id']}.jpg", Path(sheets_copy) / f"{it['id']}.jpg")
    return it["id"], len(files), issues, [picks[f][0] for f in fs]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--edl", default=str(ROOT / "films/timeless/amv3/edl.json"))
    ap.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--sheets-copy", default="")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    data = Path(a.data)
    its = items(E)
    if a.only:
        keep = set(a.only.split(","))
        its = [i for i in its if i["id"] in keep]
    clips = sorted({(i["clip"], i["file"]) for i in its})
    with Pool(a.jobs) as pool:
        cl = pool.map(scene_cuts, [c[1] for c in clips])
    cuts_by_clip = {c[0]: v for c, v in zip(clips, cl)}
    for c, v in cuts_by_clip.items():
        if v:
            print(f"[plates] clip {c}: scene cuts {v}", flush=True)
    with Pool(a.jobs) as pool:
        res = pool.map(run_item, [(i, data, cuts_by_clip, a.sheets_copy) for i in its], chunksize=1)
    bad = 0
    for iid, n, issues, idx in res:
        print(f"[plates] {iid}: {n} frames, src240 {idx[0]}..{idx[-1]}" + (f"  ISSUES: {issues}" if issues else ""),
              flush=True)
        bad += bool(issues)
    summary = dict(ids=[r[0] for r in res], counts={r[0]: r[1] for r in res}, issues={r[0]: r[2] for r in res if r[2]})
    (data / "plates" / "_summary.json").write_text(json.dumps(summary, indent=1))
    print(f"[plates] {len(res)} ids, {bad} with issues", flush=True)


if __name__ == "__main__":
    main()
