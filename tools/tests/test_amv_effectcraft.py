"""EffectCraft export: the plan -> spec half (no effectcraft-cli needed); the CLI half is tested when the binary exists."""
import json
import subprocess
from pathlib import Path

import pytest

from filmtools.amv import effectcraft as ec
from filmtools.amv import plan as P

FILM = Path(__file__).resolve().parents[2] / "films" / "timeless"
needs_film = pytest.mark.skipif(not (FILM / "amv" / "plan.json").exists(), reason="timeless plan missing")


def interp(keys, f):
    for a, b in zip(keys, keys[1:]):
        if a[0] <= f <= b[0]:
            u = (f - a[0]) / (b[0] - a[0])
            return [x + (y - x) * u for x, y in zip(a[1:], b[1:])]
    return keys[-1][1:]


def test_compress_keeps_curve_and_drops_straight_runs():
    rows = [[f, 2.0 * f, 0.0 if f < 10 else (f - 10) ** 2 * 0.5] for f in range(20)]
    out = ec.compress(rows)
    assert len(out) < len(rows)
    for r in rows:
        assert interp(out, r[0]) == pytest.approx(r[1:], abs=ec.KEY_TOL * 1.01)


def test_array_keys_positions_and_scalars():
    k = ec.array_keys([[0, 0], [1, 1], [2, 2], [3, 5]], 10)
    assert k[0] == [10, [0, 0]] and k[-1] == [13, [3, 5]]
    assert ec.array_keys([1, 1, 1, 1], 5) == [[5, 1], [8, 1]]


@needs_film
def test_spec_for_timeless():
    plan = P.load(FILM)
    spec = ec.build_spec(plan, ec.Options(film_dir=FILM, layers_dir=None, titles_dir=None, outro_dir=None))
    json.dumps(spec)
    assert spec["dur"] == 900 and len(spec["shots"]) == 33
    types = [l["type"] for l in spec["layers"]]
    # build.jsx order, bottom to top
    assert types.index("grade") > types.index("flash") > max(i for i, t in enumerate(types) if t == "shot")
    assert types[-1] == "watermark" and types[-2] == "outro"
    # the drop portal sits right after its shot B, and A comes first
    pi = types.index("portal")
    assert spec["layers"][pi - 1] == {"type": "shot", "shot": 17}
    # per-frame transform keys reproduce the plan to the compression tolerance
    sh = plan.shots[5]
    ks = spec["shots"][5]["transform"]["pos"]
    for f in range(sh.a, sh.end):
        x, y = interp([[k[0]] + k[1] for k in ks], f)
        assert (x, y) == pytest.approx(sh.transform(f)[:2], abs=0.01)
    # eye-dive hole: keys start one frame before hole_f0, offset keys as plan.Shot.hole documents
    eye = next(s for s in spec["shots"] if s["name"] == "T08_eye_dive")
    assert eye["hole"]["shape"][0][0] == plan.shot("T08_eye_dive").raw["hole_f0"] - 1
    assert eye["hole"]["offset"][-1] == [plan.shot("T08_eye_dive").b - 1, 40]


@needs_film
def test_baked_source_requires_frames():
    plan = P.load(FILM)
    spec = ec.build_spec(plan, ec.Options(film_dir=FILM, layers_dir=Path("/nonexistent"), source="baked"))
    if (FILM / "assets" / "clips").exists():      # falls back to the clips
        assert {s["mode"] for s in spec["shots"]} == {"clips"}
    else:
        pytest.skip("clips not available")


@needs_film
def test_emit_only(tmp_path):
    out = tmp_path / "proj"
    assert ec.main(["--film", str(FILM), "--out", str(out), "--emit-only"]) == 0
    jsx = (out / "build.jsx").read_text()
    assert jsx.startswith("var SPEC = ") and "OUT_PROJECT" in jsx


@needs_film
def test_cli_builds_project(tmp_path):
    cli = ec.find_cli()
    if not cli:
        pytest.skip("effectcraft-cli not installed")
    # a 3-shot excerpt keeps this fast: cut the plan down in a temp film folder
    raw = json.loads((FILM / "amv" / "plan.json").read_text())
    raw["shots"] = raw["shots"][:2]
    raw["portals"] = []
    film = tmp_path / "films" / "mini"
    (film / "amv").mkdir(parents=True)
    (film / "amv" / "plan.json").write_text(json.dumps(raw))
    (film / "film.json").write_text(json.dumps({"id": "mini", "amv": {"plan": "amv/plan.json"}}))
    (film / "assets").symlink_to(FILM / "assets")
    (film / "audio").symlink_to(FILM / "audio")
    if not (film / "assets" / "clips").exists():
        pytest.skip("clips not available")
    out = tmp_path / "proj"
    assert ec.main(["--film", str(film), "--out", str(out), "--cli", cli, "--preview", "10", "--scale", "0.2"]) == 0
    assert (out / "mini.ecproj").exists() and (out / "preview" / "f0010.png").exists()
