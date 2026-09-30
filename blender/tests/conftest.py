# The bpy-free parts of blender/lib run under the tools project's Python:
#   uv run --project tools pytest blender/tests
# Put blender/ on the path so the tests import `lib` the way render.py does inside Blender.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
