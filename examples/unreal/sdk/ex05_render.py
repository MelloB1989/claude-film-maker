"""5. Render 2 seconds: a 48-frame sequence at 24 fps cut to the camera from example 4, a Movie Render Queue job
(deferred, 1280x720, a few samples: a preview), followed with render.progress until all 48 frames are on disk.

    cd tools && uv run python ../examples/unreal/sdk/ex05_render.py [--box NAME] [--camera SDK_CamMCU]
Expected: seq.new {"created": true, ...} -> seq.camera_cuts -> level.save -> render.mrq {...} -> progress lines ->
render.progress {"frames": 48, ...}; PASS. Pull a frame and LOOK: film-ue pull /srv/film/sdk/render/0024.png /tmp/f.png
(the file naming is MRQ's: film-ue op render.progress out_dir=/srv/film/sdk/render lists what is there)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import LEVEL, SEQ, Log, run  # noqa: E402

FRAMES = 48


def main(ue, args, log: Log, poll_s: float = 5.0, max_s: float = 1800.0) -> dict:
    cam = getattr(args, "camera", "SDK_CamMCU")
    log.step("seq.new", ue.seq.new(path=SEQ, start=0, end=FRAMES, fps=24))
    log.step("seq.camera_cuts", ue.seq.camera_cuts(path=SEQ, cuts=[[cam, 0]]))
    log.step("level.save", ue.level.save())  # MRQ's separate process loads the level from disk
    out = f"{args.out}/render"
    log.step("render.mrq", ue.render.mrq(sequence=SEQ, level=LEVEL, out_dir=out, width=1280, height=720, temporal=4,
                                         warmup=16))
    end, prog = time.time() + max_s, {}
    while time.time() < end:
        prog = ue.render.progress(out_dir=out, expected=FRAMES)
        print(f"   ... {prog.get('frames', prog)}/{FRAMES}")
        if not prog.get("running", True) or (prog.get("frames") or 0) >= FRAMES:
            break
        time.sleep(poll_s)
    log.step("render.progress", prog)
    log.check(f"{FRAMES} frames on disk", (prog.get("frames") or 0) >= FRAMES, prog)
    return {"out_dir": out, "progress": prog}


if __name__ == "__main__":
    run(main, __doc__, [("--camera", {"default": "SDK_CamMCU", "help": "the camera to cut to (example 4's)"})])
