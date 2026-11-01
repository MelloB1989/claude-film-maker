"""desk_calendar — wire-o flip desk calendar on a black easel; the front page is M_Label_Calendar, 10 x 12 cm.

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/desk_calendar.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("desk_calendar")
