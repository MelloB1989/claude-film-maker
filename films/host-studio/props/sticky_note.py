"""sticky_note — yellow sticky note, 7.6 x 7.6 cm, upright facing +X, curled bottom; the front is M_Label_Sticky (origin at its centre).

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/sticky_note.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("sticky_note")
