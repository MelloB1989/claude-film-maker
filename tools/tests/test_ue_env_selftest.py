"""WP5's selftest (unreal/fmbridge/selftest/env.py) on the fake engine: it runs to the end, covers every env/light
op, and every check the fake can judge passes (the picture-dependent ones are judged tomorrow on the GPU box)."""
from __future__ import annotations

import json

from fakeunreal import run_op

# checks only a real renderer can judge (the fake's captures are a flat grey we choose)
RENDER = {"one stop more exposure brightens the image", "env.check fails an underexposed card with a fix",
          "noir_bw has no colour cast"}


def test_env_selftest_on_the_fake(ue, fmb, tmp_path, monkeypatch):
    from fmbridge.envlib import photometry as ph
    lum = 0.18 * 800 / 3.141592653589793

    class Px:
        def __init__(self, v):
            self.r = self.g = self.b = v

    def read(world, rt, normalize=True):
        return [Px(0.46 if normalize else lum)] * 64
    ue.RenderingLibrary.read_render_target_raw = staticmethod(read)

    def still(**kw):
        """A fake still."""
        yield
        path = kw.get("out") or kw.get("path")
        from fmbridge.envlib import stats
        stats.write_png(path, 16, 9, [(0.46, 0.46, 0.46)] * 144)  # a real (flat grey) PNG: the harness baselines stills
        return {"path": path, "width": 960, "height": 540}
    monkeypatch.setitem(fmb._OPS, "view.still", still)
    rep = run_op("selftest.run", area="env", out_dir=str(tmp_path))
    assert rep["status"] == "done", json.dumps(rep.get("errors"), indent=1)[:3000]
    bad = [c for c in rep["checks"] if not c["ok"] and c["name"] not in RENDER]
    assert not bad, json.dumps(bad, indent=1)[:3000]
    missed = [o for o in rep["ops_missed"] if o.startswith(("env.", "light."))]
    assert missed == [], missed
    assert abs(rep["extra"]["meter_offset_stops"]) < 0.01, rep["metrics"]["meter_offset_stops"]
    assert ue.dialogs == []
