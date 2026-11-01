"""nameplate — walnut desk nameplate, 12 x 4.2 x 3.4 cm; the engraved name is the M_Label_Name decal on the front.

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/nameplate.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("nameplate")
