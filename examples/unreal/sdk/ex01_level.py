"""1. An empty level and a set in it, by spec, through the SDK: a floor, a back wall, a box and a ball, converged
with scene.apply (WP6), then read back with level.describe. Run twice: the second run changes nothing.

    cd tools && uv run python ../examples/unreal/sdk/ex01_level.py [--box NAME]
Expected: level.new (or level.open) -> scene.apply {"changed": true, ...} -> level.describe counts; PASS x3.
Second run: scene.apply {"changed": false}."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import LEVEL, Log, run  # noqa: E402

SET = {"kind": "scene", "version": 1, "name": "sdk-set", "folder": "SDK",
       "actors": [{"label": "SDK_Floor", "shape": "plane", "size": [1000, 1000, 100], "loc": [0, 0, 0]},
                  {"label": "SDK_Wall", "shape": "cube", "size": [20, 1000, 300], "loc": [-300, 0, 150]},
                  {"label": "SDK_Box", "shape": "cube", "size": [60, 60, 60], "loc": [0, -80, 200], "drop": True},
                  {"label": "SDK_Ball", "shape": "sphere", "size": [50, 50, 50], "loc": [0, 80, 200], "drop": True}]}


def main(ue, args, log: Log) -> dict:
    worlds = ue.assets.list(path=LEVEL.rsplit("/", 1)[0], cls="World")      # [[class, package path], ...]
    if any(path == LEVEL for _, path in worlds):
        log.step("level.open", ue.level.open(path=LEVEL))
    else:
        log.step("level.new", ue.level.new(path=LEVEL))
    res = log.step("scene.apply", ue.scene.apply(spec=SET))
    log.check("scene converged", not res.get("remaining"), res.get("remaining"))
    found = log.step("level.find SDK_", ue.level.find(label="SDK_*"))
    labels = sorted(a["label"] for a in found)
    log.check("four actors", labels == ["SDK_Ball", "SDK_Box", "SDK_Floor", "SDK_Wall"], labels)
    log.step("level.save", ue.level.save())
    return {"changed": res.get("changed"), "actors": labels}


if __name__ == "__main__":
    run(main, __doc__)
