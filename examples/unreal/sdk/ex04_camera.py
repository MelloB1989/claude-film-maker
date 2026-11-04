"""4. Frame a subject by shot grammar and check the framing with numbers: cam.frame solves the camera for "an MCU of
the subject from the left 3/4 at eye level, 50 mm" from its real skeleton (or bounds), then qa.framing measures
headroom, cut-offs and size in that camera, and view.still takes the picture. The subject is the MetaHuman from
example 3, or with --subject any actor (SDK_Box from example 1).

    cd tools && uv run python ../examples/unreal/sdk/ex04_camera.py [--box NAME] [--subject SDK_Host] [--size MCU]
Expected: cam.frame {"camera": "SDK_CamMCU", "loc": [...], "focal_mm": 50, ...} -> qa.framing {"pass": true, ...}
-> view.still {"path": ".../ex04.png"}; PASS. Pull and LOOK: film-ue pull /srv/film/sdk/ex04.png /tmp/ex04.png"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import Log, run  # noqa: E402


def main(ue, args, log: Log) -> dict:
    subject, size = getattr(args, "subject", "SDK_Host"), getattr(args, "size", "MCU")
    cam = f"SDK_Cam{size}"
    log.step("cam.add", ue.cam.add(label=cam, loc=[400, 0, 150], look_at=[0, 0, 120]))
    solved = log.step("cam.frame", ue.cam.frame(camera=cam, subjects=[subject], size=size, angle=30.0, side="left",
                                                height="eye", focal_mm=50.0))
    fr = log.step("qa.framing", ue.qa.framing(subjects=[subject], camera=cam))
    log.check(f"{size} of {subject} frames cleanly", bool(fr.get("pass")),
              "; ".join(i.get("message", "") for i in fr.get("issues", []))[:300])
    still = log.step("view.still", ue.view.still(out=f"{args.out}/ex04.png", camera=cam))
    return {"camera": cam, "solved": solved, "framing": {k: fr.get(k) for k in ("pass", "metrics")},
            "still": (still or {}).get("path")}


if __name__ == "__main__":
    run(main, __doc__, [("--subject", {"default": "SDK_Host", "help": "an actor label to frame"}),
                        ("--size", {"default": "MCU", "help": "ECU CU MCU MS MWS WS EWS (film-ue cam presets)"})])
