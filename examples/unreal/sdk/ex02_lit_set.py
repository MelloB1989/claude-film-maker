"""2. Light the set from example 1 and check the exposure with numbers: a key and a fill (rect lights aimed at the
box), haze, a camera, a still through it with no viewport (view.still, WP10), and qa.image on that still: the mean
must sit within a few stops of mid-grey and nothing may clip badly.

    cd tools && uv run python ../examples/unreal/sdk/ex02_lit_set.py [--box NAME] [--out /srv/film/sdk]
Expected: look.light x2, look.fog, cam.add, view.still {"path": ".../ex02.png", ...}, qa.image {"pass": true, ...}.
Then pull and LOOK: film-ue pull /srv/film/sdk/ex02.png /tmp/ex02.png"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import Log, run  # noqa: E402

TARGET = [0, 0, 60]


def main(ue, args, log: Log) -> dict:
    log.step("key", ue.look.light(label="SDK_Key", kind="rect", loc=[300, 200, 250], look_at=TARGET, intensity=20,
                                  temperature=5200, width=120, height=120))
    log.step("fill", ue.look.light(label="SDK_Fill", kind="rect", loc=[300, -250, 150], look_at=TARGET, intensity=6,
                                   shadows=False, width=200, height=200))
    log.step("haze", ue.look.fog(density=0.01))
    log.step("camera", ue.cam.add(label="SDK_Cam", loc=[450, 0, 140], look_at=TARGET, focal_mm=35))
    still = log.step("still", ue.view.still(out=f"{args.out}/ex02.png", camera="SDK_Cam", width_px=1280, height_px=720))
    path = (still or {}).get("path", f"{args.out}/ex02.png")
    img = log.step("qa.image", ue.qa.image(image=path))
    log.check("exposure and clipping pass", bool(img.get("pass")), "; ".join(i.get("message", "") for i in img.get("issues", []))[:300])
    return {"still": path, "image": {k: img.get(k) for k in ("pass", "metrics")}}


if __name__ == "__main__":
    run(main, __doc__)
