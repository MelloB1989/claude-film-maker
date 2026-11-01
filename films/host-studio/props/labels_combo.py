"""labels_combo — the six label props at real scale on a light-oak surface (preview only).

    blender -b --factory-startup -P films/host-studio/props/labels_combo.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run_combo()
