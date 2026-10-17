from pathlib import Path

from filmtools.amv2 import package as pk


def proj():
    seq = [f"/d/blender/rift/{i:04d}.png" for i in range(3)]
    return {"items": {
        "1": {"name": "a", "kind": {"type": "Footage", "path": "/d/src240/clip_A.mp4"}},
        "2": {"name": "b", "kind": {"type": "Footage", "path": seq[0], "sequence": seq}},
        "3": {"name": "c", "kind": {"type": "Footage", "path": "/x/out/mix.wav"}},
        "4": {"name": "m", "kind": {"type": "Comp"}, "font": "Anton-Regular"}}}


def test_destinations_and_relative_rewrite():
    p = proj()
    plan = pk.plan_media(p, Path("/d"))
    assert plan["/d/src240/clip_A.mp4"] == Path("media/src240/clip_A.mp4")
    assert plan["/d/blender/rift/0001.png"] == Path("media/blender/rift/0001.png")
    assert plan["/x/out/mix.wav"] == Path("audio/mix.wav")
    q = pk.rewrite_project(p, plan, "effectcraft")
    assert q["items"]["1"]["kind"]["path"] == "../media/src240/clip_A.mp4"
    assert q["items"]["2"]["kind"]["sequence"][2] == "../media/blender/rift/0002.png"
    assert pk.leftover_absolute(q) == []
    assert pk.fonts_used(q) == {"Anton-Regular"}


def test_leftover_absolute_flags_paths():
    assert pk.leftover_absolute({"a": ["/home/x/y.png"]}) == ["/home/x/y.png"]
