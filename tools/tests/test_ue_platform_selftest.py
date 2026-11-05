"""WP1's selftest (unreal/fmbridge/selftest/platform.py): its docstring says what it needs. Its dry run on the fake
is in test_ue_selftest_dryrun.py (B45), with every other area's."""
from __future__ import annotations


def test_the_selftest_says_how_long_and_what_it_needs():
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "unreal" / "fmbridge" / "selftest" / "platform.py").read_text()
    doc = ast.get_docstring(ast.parse(src))
    assert "Takes ~" in doc and "Needs:" in doc
