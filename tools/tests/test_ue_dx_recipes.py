"""B35: every recipe in docs/unreal/RECIPES.md runs on the fake engine with the expected outcome, and the file lists
the recipes recipes_gen.py has (regenerate: cd tools && python tests/recipes_gen.py)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import recipes_gen  # noqa: E402

EXPECT_FAIL = {"A typo, caught before anything is sent": 2, "A missing actor": 1}


def test_every_recipe_runs():
    bad = []
    for (title, _, _, _), outs in recipes_gen.run_all():
        for argv, rc, doc, err in outs:
            want = EXPECT_FAIL.get(title, 0)
            if rc != want or doc is None:
                bad.append((title, argv, rc, err[-300:]))
    assert not bad, bad


def test_recipes_md_is_current():
    text = recipes_gen.OUT.read_text()
    titles = re.findall(r"^## \d+\. (.+)$", text, re.M)
    assert titles == [r[0] for r in recipes_gen.RECIPES], "regenerate: cd tools && python tests/recipes_gen.py"
