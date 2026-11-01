"""framed_print — abstract print in a light-oak frame, 21 x 26 x 2 cm, leaning back 8 degrees; the artwork is M_Label_Print, 13 x 18 cm.

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/framed_print.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("framed_print")
