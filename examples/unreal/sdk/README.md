# SDK examples: Unreal from Python, end to end

Five scripts that build on each other, through `filmtools.unreal.sdk` (the typed ops: `ue.<area>.<verb>(...)`):
empty level and a set (1), light and exposure checked (2), a MetaHuman (3), a camera framed by shot grammar and
checked (4), a 2-second render (5). Each prints every step's result and its checks (PASS/FAIL), exits 1 on a
failure, and is safe to re-run. `--json` prints only the final result. Everything lives under `/Game/_SDK`.

```bash
cd tools
uv run python ../examples/unreal/sdk/ex01_level.py --box demo
uv run python ../examples/unreal/sdk/ex02_lit_set.py --box demo --out /srv/film/sdk
uv run python ../examples/unreal/sdk/ex03_character.py --box demo          # 10-20 min, needs the Epic sign-in
uv run python ../examples/unreal/sdk/ex04_camera.py --box demo             # --subject SDK_Box without example 3
uv run python ../examples/unreal/sdk/ex05_render.py --box demo
film-ue --box demo pull /srv/film/sdk/ex04.png /tmp/ex04.png                # and LOOK at it
```

Each script's docstring says what it prints when it works. The same steps as specs: `examples/unreal/demo/`.
Tested here without a box: `tools/tests/test_ue_dx_examples.py` checks every `ue.<area>.<verb>(...)` call in these
files against the op schema (op exists, argument names right, required ones given) and runs 1, 2 and 4 against the
fake engine.
