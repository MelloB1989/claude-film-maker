"""Off-box test of chin_probe.menton on a synthetic midline profile (plain python3)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chin_probe import menton  # noqa: E402

# (forward, z) of the face's midline relative to the head bone, top -> down: brow, nose tip, upper/lower lip,
# sulcus, pogonion, the chin's underside (menton at z -6.0, 1.5 cm behind the pogonion), the submental line rising
# back to the throat, an Adam's apple, the neck front down to the seam
PROFILE = [(9.0, 9.0), (10.0, 6.0), (13.0, 4.0), (10.5, 3.0), (11.0, 1.5), (10.8, 0.0), (10.0, -1.5),
           (10.6, -3.0), (10.8, -4.0), (10.4, -5.0), (9.3, -5.8), (8.5, -6.0), (7.0, -5.8), (5.5, -5.6),
           (5.0, -7.0), (5.6, -9.0), (5.0, -11.0), (4.8, -14.0)]


def body(lateral_axis):
    pts = []
    for f, z in PROFILE:
        for l in (-0.5, 0.0, 0.5):
            pts.append((f, l, z) if lateral_axis == "y" else (l, -f, z))
    pts += [(-3.0, 0.0, 0.0), (0.0, 8.0, 0.0), (0.0, -8.0, 0.0)]   # skull back, ears (off the midline band)
    return pts


def test_finds_the_menton_not_the_neck():
    for ax, lat in (("y", (0.0, 1.0, 0.0)), ("x", (-1.0, 0.0, 0.0))):
        head = (100.0, 50.0, 150.0)
        P = [(head[0] + p[0], head[1] + p[1], head[2] + p[2]) for p in body(ax)]
        r = menton(P, head, lat)
        assert r["chin_below_head_cm"] == 6.0, (ax, r)
        assert r["pogonion_below_head_cm"] == 4.0, (ax, r)
        assert r["pogonion_fwd_cm"] == 10.8, (ax, r)


if __name__ == "__main__":
    test_finds_the_menton_not_the_neck()
    print("ok")
