# The Rain Ferry's own tests, moved here from blender/tests when the film left main (core is on main, each film on
# film/<id>). They run without Blender:
#   python3 -m pytest -q films/rain-ferry/tests
# Put the repo's blender/ on the path, as blender/tests/conftest.py does, so the film's code imports core `lib`.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "blender"))
