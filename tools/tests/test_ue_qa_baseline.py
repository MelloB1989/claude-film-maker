"""B43 visual baselines: the pure store/compare, the qa.baseline_* ops on the fake, film-qa baseline pull/push."""
import json
import os
import shutil
from pathlib import Path

import pytest

from _qa_load import load

load()
from fmqa import baseline, draw, image  # noqa: E402

from test_ue_qa import noisy  # noqa: E402


def still(path, seed=1, mark=False, dark=False):
    img = noisy(96, 54, seed)
    if mark:
        draw.fill(img, 60, 0, 96, 27, (255, 255, 255))
    if dark:
        img = image.Image(img.w, img.h, 3, bytearray(v // 3 for v in img.data))
    return image.write(img, str(path))


def test_save_compare_check_list_remove(tmp_path):
    root = str(tmp_path / "bl")
    a = still(tmp_path / "a.png")
    r = baseline.check(root, "selftest/look", "key", a)
    assert r["status"] == "created" and os.path.isfile(r["baseline"])
    again = baseline.check(root, "selftest/look", "key", a)
    assert again["status"] == "match" and again["ssim"] == pytest.approx(1.0) and again["issues"] == []
    moved = baseline.check(root, "selftest/look", "key", still(tmp_path / "b.png", mark=True),
                           diff_out=str(tmp_path / "d.png"))
    assert moved["status"] in ("differs", "different") and moved["issues"][0]["code"].startswith("baseline.")
    assert os.path.isfile(moved["diff"]) and moved["changed"]
    other = baseline.compare(root, "selftest/look", "key", still(tmp_path / "c.png", seed=7))
    assert other["status"] == "different" and other["issues"][0]["severity"] == "fail"
    dark = baseline.compare(root, "selftest/look", "key", still(tmp_path / "e.png", dark=True), min_ssim=0.0)
    assert dark["status"] == "match" and dark["stops_shift"] < -1 and dark["issues"][0]["code"] == "baseline.exposure"
    # save keeps an existing baseline unless overwrite
    kept = baseline.save(root, "selftest/look", "key", str(tmp_path / "b.png"))
    assert kept["changed"] is False
    upd = baseline.check(root, "selftest/look", "key", str(tmp_path / "b.png"), mode="update")
    assert upd["status"] == "updated"
    assert baseline.compare(root, "selftest/look", "key", str(tmp_path / "b.png"))["status"] == "match"
    assert baseline.get(root, "selftest/look", "key")["created"] <= baseline.get(root, "selftest/look", "key")["updated"]
    baseline.save(root, "film/s010", "00048", a, meta={"camera": "CamA"}, thresholds={"min_ssim": 0.5})
    ls = baseline.list_(root)
    assert [(b["suite"], b["name"]) for b in ls] == [("film/s010", "00048"), ("selftest/look", "key")]
    assert baseline.list_(root, "film")[0]["rel"] == "film/s010/00048.png"
    assert baseline.get(root, "film/s010", "00048")["thresholds"] == {"min_ssim": 0.5}
    assert baseline.remove(root, "film/s010", "00048") and not baseline.remove(root, "film/s010", "00048")
    nb = baseline.check(root, "x", "y", a, mode="compare")
    assert nb["status"] == "no_baseline" and nb["issues"][0]["severity"] == "info"
    assert baseline.check(root, "x", "y", a, mode="off")["status"] == "off"
    with pytest.raises(ValueError):
        baseline.check(root, "x", "y", a, mode="bogus")
    with pytest.raises(ValueError):
        baseline.safe("///")
    assert baseline.paths(root, "a//b", "n:1")[0].endswith(os.path.join("a", "b", "n_1.png"))
    with pytest.raises(ValueError):  # no climbing out of the root
        baseline.paths(root, "a/../b", "n")


def test_size_mismatch_is_a_fail(tmp_path):
    root = str(tmp_path / "bl")
    baseline.save(root, "s", "n", still(tmp_path / "a.png"))
    sq = image.write(image.solid(40, 40, (9, 9, 9)), str(tmp_path / "sq.png"))
    r = baseline.compare(root, "s", "n", sq)
    assert r["status"] == "different" and r["issues"][0]["code"] == "baseline.shape"


def test_baseline_ops(ue, fmb, tmp_path, monkeypatch):
    from fakeunreal import run_op
    monkeypatch.setenv("FMBRIDGE_BASELINES", str(tmp_path / "box_bl"))
    a = still(tmp_path / "a.png")
    s = run_op("qa.baseline_save", suite="film/s010", name="00048", image=a, meta={"camera": "CamA"})
    assert s["changed"] and os.path.isfile(s["png"])
    assert run_op("qa.baseline_save", suite="film/s010", name="00048", image=a)["changed"] is False
    c = run_op("qa.baseline_compare", suite="film/s010", name="00048", image=still(tmp_path / "b.png", mark=True),
               diff_out=str(tmp_path / "d.png"))
    assert c["pass"] in (True, False) and c["metrics"]["status"] in ("differs", "different")
    chk = run_op("qa.baseline_check", suite="film/s010", name="00050", image=a)
    assert chk["metrics"]["status"] == "created" and chk["pass"]
    ls = run_op("qa.baseline_list")
    assert ls["root"] == str(tmp_path / "box_bl") and len(ls["baselines"]) == 2
    assert run_op("qa.baseline_remove", suite="film/s010", name="00050")["changed"] is True
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("qa.baseline_compare", suite="s", name="n", image=str(tmp_path / "missing.png"))
    with pytest.raises(OpError) as e:
        run_op("qa.baseline_check", suite="s", name="n", image=a, mode="nope")
    assert e.value.code == "bad_args"
    monkeypatch.delenv("FMBRIDGE_BASELINES")
    import fmbridge.ops.qa as q
    assert q.baseline_root().replace("\\", "/").endswith("Saved/fmbridge/baselines")


class FakeClient:
    """client.op/pull/push against a folder standing in for the box."""

    def __init__(self, box_root):
        self.root = str(box_root)

    def op(self, name, **args):
        assert name == "qa.baseline_list"
        return {"ok": True, "result": {"root": self.root, "baselines": baseline.list_(self.root, args.get("suite", ""))}}

    def pull(self, remote, local):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(remote, local)
        return local

    def push(self, local, remote):
        Path(remote).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, remote)
        return {"ok": True}


def test_film_qa_baseline_pull_push_check(tmp_path, capsys):
    from filmtools.unreal import qa_local
    box = tmp_path / "box"
    a = still(tmp_path / "00048.png")
    baseline.save(str(box), "film/s010", "00048", a)
    baseline.save(str(box), "selftest/look", "key", a)
    fc = FakeClient(box)
    r = qa_local.baseline_pull(str(tmp_path / "local"), "film", client=fc)
    assert r["pulled"] == ["film/s010/00048.png"] and (tmp_path / "local/film/s010/00048.json").is_file()
    # accept a new look locally, push it back
    b = still(tmp_path / "new" / "00048.png", mark=True)
    res = qa_local.baseline_check(str(tmp_path / "local"), "film/s010", [b], diff_dir=str(tmp_path / "diffs"))
    assert res["metrics"]["stills"][0]["status"] in ("differs", "different")
    qa_local.baseline_check(str(tmp_path / "local"), "film/s010", [b], mode="update")
    p = qa_local.baseline_push(str(tmp_path / "local"), client=fc)
    assert p["pushed"] == ["film/s010/00048.png"]
    assert baseline.compare(str(box), "film/s010", "00048", b)["status"] == "match"
    qa_local.main(["baseline", "list", str(tmp_path / "local")])
    assert json.loads(capsys.readouterr().out)["baselines"][0]["name"] == "00048"
