"""Off-box test of hand_probe.rest_heights on a synthetic hand profile (plain python3)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hand_probe import rest_heights  # noqa: E402

# (x along the hand from the wrist joint, y toward the palm surface), cm: the back of the hand at y -1.8, the heel
# pad 3.5 cm under the wrist at x 1, the palm 2.5 under, the knuckle pads at x 9 2.5 under, finger pads at x 15 1.5
PALM = [(-1.0, 3.0), (1.0, 3.5), (3.0, 3.2), (5.0, 2.6), (7.0, 2.4), (9.0, 2.5), (12.0, 2.0), (15.0, 1.5), (17.0, 0.8)]
BACK = [(x, -1.8) for x in range(-1, 18)]


def test_heel_flat_and_heel_to_pads():
    r = rest_heights(PALM + BACK, {"hand": (0.0, 0.0), "middle_01": (9.0, 0.6)}, 4.0)
    assert r["heel_flat"] == {"hand": 3.5, "middle_01": 2.9}, r
    assert r["contacts"][0] == [1.0, 3.5]
    # the hull from the heel runs to the knuckle pad at (9, 2.5) (the palm between sits inside it)
    assert r["contacts"][1] == [9.0, 2.5], r
    # tipped down 7 deg onto the knuckle pad: the wrist (behind the heel contact) rises a little, the knuckle drops
    assert r["tilt_deg"] == -7.1 and 3.55 < r["heel_pads"]["hand"] < 3.65, r
    assert abs(r["heel_pads"]["middle_01"] - 1.89) < 0.01, r


if __name__ == "__main__":
    test_heel_flat_and_heel_to_pads()
    print("ok")
