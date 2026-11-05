"""Load unreal/fmbridge/qa as a standalone package (it imports nothing from fmbridge or unreal), so its tests need
neither the editor nor a fake `unreal` module."""
import importlib.util
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parents[2] / "unreal" / "fmbridge" / "qa"


def load():
    if "fmqa" in sys.modules:
        return sys.modules["fmqa"]
    spec = importlib.util.spec_from_file_location("fmqa", QA_DIR / "__init__.py", submodule_search_locations=[str(QA_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fmqa"] = mod
    spec.loader.exec_module(mod)
    return mod
