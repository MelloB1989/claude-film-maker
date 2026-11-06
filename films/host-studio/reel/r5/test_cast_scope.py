"""r5/cast_scope.py: the presenters' visible frames from the shot table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cast_scope as r5scope  # noqa: E402


def test_him_is_out_of_scope_in_her_close_up():
    t = r5scope.table()
    s16 = next(s for s in t["shots"] if s["id"] == "S16")
    assert s16["cast"] == ["her"] and (s16["start"], s16["end"]) == (1200, 1320)
    assert not any(a <= 1294 and 1306 < b for a, b in t["him"])   # his f1294-1306 nod: off screen
    assert any(a <= 1294 and 1306 < b for a, b in t["her"])
