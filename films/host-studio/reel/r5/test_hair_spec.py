"""r5/hair_spec.py's offline part: the head-and-shoulders box from projected bones."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hair_spec import box_from  # noqa: E402


def test_box_from_bones():
    b = box_from(head_v=0.3, chest_v=0.5, head_u=0.5)
    assert b[1] < 0.3 < 0.5 < b[3] and b[0] < 0.5 < b[2]
    assert abs((b[3] - 0.3) - 0.44) < 1e-6  # 2.2 head units below the head
    assert box_from(0.05, 0.4, 0.02) [0] == 0.0 and box_from(0.6, 0.95, 0.5)[3] == 1.0
