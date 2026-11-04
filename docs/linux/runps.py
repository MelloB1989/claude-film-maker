"""Run a PowerShell file on the workstation over SSM and print its output: uv run python runps.py FILE [timeout]."""
import sys
from filmtools.unreal import workstation as w
print(w.ps(open(sys.argv[1]).read(), timeout=int(sys.argv[2]) if len(sys.argv) > 2 else 600))
