"""3. A MetaHuman from a preset, rigged and built in the cloud, standing in the set: mh.from_preset, mh.rig and
mh.textures as jobs with progress (minutes each: Epic's cloud), mh.build to a Blueprint, level.spawn of it. Each step
is skipped when its result is already there, so a re-run after a failure resumes. Needs the Epic sign-in on the box.

    cd tools && uv run python ../examples/unreal/sdk/ex03_character.py [--box NAME] [--preset Trey]
Expected: mh.presets [...] -> mh.from_preset "/Game/_SDK/MH/SDK_Host" -> mh.rig, mh.textures (jobs) -> mh.build
"/Game/_SDK/MH/.../BP_SDKHost" -> level.spawn "SDK_Host" -> mh.components {Body, Face, ...}; PASS x2."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, Log, run  # noqa: E402

MH = ROOT + "/MH"
CHARACTER = MH + "/SDK_Host"


def main(ue, args, log: Log) -> dict:
    preset = getattr(args, "preset", "Trey")
    presets = log.step("mh.presets", ue.mh.presets())
    log.check(f"preset {preset} exists", not presets or any(preset in str(p) for p in presets), presets[:5])
    have = {cls: [p for c, p in ue.assets.list(path=MH) if c == cls] for cls in ("MetaHumanCharacter", "Blueprint")}
    if not have["MetaHumanCharacter"]:
        log.step("mh.from_preset", ue.mh.from_preset(preset=preset, dest=CHARACTER))
    bp = next((p for p in have["Blueprint"] if p.endswith("BP_SDKHost")), None)
    if not bp:
        for verb in ("rig", "textures"):  # cloud work: start it as a job and wait, printing progress
            job = getattr(ue.mh, verb)(character=CHARACTER, _wait=False)
            log.step(f"mh.{verb}", job.wait(timeout=3600, on_progress=lambda r: print(f"   ... {r.get('progress')} {r.get('message', '')}")))
        bp = log.step("mh.build", ue.mh.build(character=CHARACTER, name="SDKHost", _timeout=1800))
    log.step("level.spawn", ue.level.spawn(label="SDK_Host", asset=bp, loc=[0, 0, 0], rot_={"yaw": 0}))
    comps = log.step("mh.components", ue.mh.components(label="SDK_Host"))
    log.check("a body and a face", {"Body", "Face"} <= set(comps), sorted(comps))
    return {"blueprint": bp, "components": sorted(comps)}


if __name__ == "__main__":
    run(main, __doc__, [("--preset", {"default": "Trey", "help": "a MetaHuman Creator preset (film-ue mh presets)"})])
