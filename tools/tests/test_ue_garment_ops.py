"""qa.clip / qa.garment_look / body.hide_under's pure part against the fake engine: components draw `fake_depth`
layers, so each part is captured alone as the ops do on the box."""
import json
import os

import pytest

from fakeunreal import run_op

from test_ue_qa_ops import cine


def region(x0, y0, x1, y1, z, holes=()):
    """A fake_depth function: z inside the (u, v) box, minus the holes [(box, z)] drawn instead."""
    def fn(u, v):
        for (a, b, c, d), hz in holes:
            if a <= u < c and b <= v < d:
                return hz
        return z if x0 <= u < x1 and y0 <= v < y1 else None
    return fn


@pytest.fixture
def host(ue, fmb, monkeypatch):
    a = ue.spawn("SkeletalMeshActor", "Host", location=ue.Vector(0, 0, 90), extent=(25, 25, 90))
    for c in a._components:  # the fake actor's own mesh component: not a part of him
        c.set_visibility(False)
    body = a.add_component(ue.SkeletalMeshComponent, "Body")
    tee = a.add_component(ue.SkeletalMeshComponent, "SkeletalMesh")
    body._props["fake_depth"] = region(0.3, 0.3, 0.7, 0.9, 101.0)
    tee._props["fake_depth"] = region(0.3, 0.3, 0.7, 0.9, 100.0)
    cine(ue, "CamA", [300, 0, 120], [0, 0, 120])
    import fmbridge.ops.garment as G

    def scrub(seq, f, settle):
        yield

    monkeypatch.setattr(G, "_scrub", scrub)
    monkeypatch.setattr(G, "cut_camera", lambda seq, f: "CamA")
    monkeypatch.setattr(G, "_frames_of", lambda seq, shots, n, extra: {"S1": [10, 20]})
    return a


def test_qa_clip_clean_then_poke(host, tmp_path):
    out = str(tmp_path / "clip")
    r = run_op("qa.clip", label="Host", sequence="/Game/S", width_px=64, out_dir=out, stills=False, layer_masks=True)
    from fmbridge.qa import image
    m = image.read(os.path.join(out, "S1_0010_tee.png"))
    assert m.size == (64, 36) and 0 < sum(1 for v in m.data if v) < 64 * 36
    assert r["pass"] and r["metrics"]["worst"]["Body>tee"]["fraction"] == 0.0
    assert os.path.isfile(os.path.join(out, "S1_0010_depth.bin")) and os.path.isfile(os.path.join(out, "clip.json"))
    body = next(c for c in host._components if c.get_name() == "Body")
    body._props["fake_depth"] = region(0.3, 0.3, 0.7, 0.9, 101.0, holes=[((0.45, 0.5, 0.55, 0.6), 99.0)])
    r2 = run_op("qa.clip", label="Host", sequence="/Game/S", width_px=64, ref_dir=out, stills=False)
    assert not r2["pass"] and {i["code"] for i in r2["issues"]} == {"clip.pair"}
    f = r2["metrics"]["shots"]["S1"][10]
    assert f["Body>tee"]["px"] > 0 and f["silhouette"]["pct"] == 0.0
    assert "garment.fit" in r2["issues"][0]["fix"] or "hide" in r2["issues"][0]["fix"]


def test_roles_picks_the_default_garment_as_tee(host):
    import fmbridge.ops.garment as G
    assert sorted(G.roles(host)) == ["Body", "tee"]
    with pytest.raises(Exception):
        G.roles(host, {"tee": "Nope"})
    import unreal
    host.add_component(unreal.SkeletalMeshComponent, "Tee")  # the refit, dressed beside the default garment
    r = G.roles(host)
    assert r["tee"].get_name() == "Tee" and "SkeletalMesh" in r


def test_depth_file_roundtrip(fmb, tmp_path):
    import fmbridge.ops.garment as G
    p = str(tmp_path / "d.bin")
    G.write_depth(p, 2, 1, 30.0, {"Body": [1.0, 2.0], "tee": [3.0, 1e7]})
    w, h, fov, L = G.read_depth(p)
    assert (w, h, fov) == (2, 1, 30.0) and L["Body"] == [1.0, 2.0] and L["tee"][1] == pytest.approx(1e7)


def test_covered_shrinks_from_the_border(fmb):
    import fmbridge.ops.garment as G
    # a strip of 6 quads (12 triangles) over verts 0..13 (two rows of 7): all covered but the last column
    tris = []
    for k in range(6):
        a, b, c, d = k, k + 1, k + 7, k + 8
        tris += [(a, b, c), (b, d, c)]
    hit = [True] * 14
    hit[6] = hit[13] = False
    assert len(G.covered(14, tris, hit, rings=0)) == 10
    assert len(G.covered(14, tris, hit, rings=1)) == 8
    assert G.covered(14, tris, [False] * 14, rings=0) == []


def _grid(n):
    """An n x n vertex grid's triangles (vertex r * n + c)."""
    tris = []
    for r in range(n - 1):
        for c in range(n - 1):
            a = r * n + c
            tris += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    return tris


def test_fill_holes_covers_small_islands_only(fmb):
    import fmbridge.ops.garment as G
    n = 7
    tris = _grid(n)
    hit = [True] * (n * n)
    for v in (0, 1, 7, 8):          # the open skin: a corner of 4
        hit[v] = False
    hit[3 * n + 3] = False          # a 1-vertex miss in the middle of the covered patch
    hit[5 * n + 5] = False          # another, refused by ok
    out, filled, islands = G.fill_holes(n * n, tris, hit, max_verts=2, ok=lambda comp: 5 * n + 5 not in comp)
    assert islands == [4, 1, 1] and filled == [1]
    assert out[3 * n + 3] and not out[5 * n + 5] and not any(out[v] for v in (0, 1, 7, 8))
    out, filled, _ = G.fill_holes(n * n, tris, hit, max_verts=0)
    assert filled == [] and out == hit
    hidden = G.covered(n * n, tris, G.fill_holes(n * n, tris, hit, 2)[0], rings=1)
    assert len(hidden) > len(G.covered(n * n, tris, hit, rings=1))


def test_hide_under_refuses_the_face(host):
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="Body only"):
        run_op("body.hide_under", label="Host", garment="SkeletalMesh", body="Face")


def test_ops_registered_with_docs(fmb):
    r = run_op("list", prefix="qa.clip", full=True)
    text = json.dumps(r)
    assert "neck_px" in text
    for name in ("qa.garment_look", "garment.export", "body.hide_under"):
        assert name in json.dumps(run_op("list", prefix=name.split(".")[0]))
