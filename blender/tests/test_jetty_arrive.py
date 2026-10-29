"""The Rain Ferry's arrival at the jetty's end (films/rain-ferry/blender/rf/jetty_arrive.py): its pure halves."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "films" / "rain-ferry" / "blender"))

from rf import jetty_arrive as ja  # noqa: E402


def test_speech_moves_the_mouth_through_the_line_and_shuts_it_outside():
    say = ja.speech("ame no hi wa, watasanai yo.", 0.9, 2.89, seed=4)
    assert say(0.5) == {} and say(3.2) == {}
    opened = [max(say(0.9 + k / 48).values(), default=0.0) for k in range(int(1.99 * 48))]
    assert max(opened) > 0.4
    # it opens and closes, a mora at a time, not one held shape
    assert sum(1 for a, b in zip(opened, opened[1:]) if (a - 0.45) * (b - 0.45) < 0) >= 6
