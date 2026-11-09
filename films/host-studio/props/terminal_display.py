"""terminal_display — slim 'ticker' desk display, 24 x 7 x 6 cm; the screen is M_Label_Terminal, 21 x 4.5 cm, behind a glass pane.

Built by _labels.py, which holds all six label props.

    blender -b --factory-startup -P films/host-studio/props/terminal_display.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _labels  # noqa: E402

_labels.run("terminal_display")
