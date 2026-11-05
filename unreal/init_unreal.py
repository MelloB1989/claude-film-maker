"""Runs at editor start (Unreal executes every init_unreal.py on its Python path): starts claude-film-maker's bridge.
`film-ue install` copies this file and the fmbridge package into the project's Content/Python."""
import unreal

try:
    import fmbridge
    unreal.log("fmbridge: " + fmbridge.start())
except Exception as e:  # never block the editor from starting
    unreal.log_error(f"fmbridge failed to start: {e}")
