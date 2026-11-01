"""polaroid — instant-film print, 8.8 x 10.7 cm, bowed 2 mm; the whole front is M_Label_Polaroid.

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/polaroid.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("polaroid")
