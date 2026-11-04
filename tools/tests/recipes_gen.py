"""B35: docs/unreal/RECIPES.md, the common tasks as copy-paste commands WITH their real JSON answers: each recipe is
run here through the generated CLI against the fake engine (the same path as on a box, minus the GPU), and its
--json output is written under the command. Values differ on a box (positions, timings); the shapes do not.

    cd tools && python tests/recipes_gen.py            # rewrite docs/unreal/RECIPES.md
test_ue_dx_recipes.py runs every recipe and fails when one errors or the file is stale."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

OUT = HERE.parents[1] / "docs" / "unreal" / "RECIPES.md"

# (title, why, [argv, ...], check)   argv after `film-ue`; "@spec:path" applies a spec file instead
RECIPES = [
    ("Find the op for a job", "Discover offline: areas, then one area, then one op.",
     [["describe", "level.spawn", "--json"]], "the `params` list: names, types, defaults"),
    ("Start a clean level", "Everything below happens in it.",
     [["level", "new", "--path", "/Game/Recipes/L_Recipes", "--json"]], "`result` is the level path"),
    ("Put basic shapes in the level", "A shape converges on its label: running it again replaces, never duplicates.",
     [["level", "spawn", "--label", "Box", "--shape", "cube", "--loc", "0,0,50", "--json"],
      ["level", "spawn", "--label", "Ball", "--shape", "sphere", "--loc", "150,0,50", "--size", "50,50,50", "--json"]],
     "`result` is the label"),
    ("Find actors", "By label glob, class, tag, folder or distance; with transforms and bounds.",
     [["level", "find", "--label", "B*", "--json"]], "one dict per actor: label, class, loc, rot, scale, bounds"),
    ("Move and aim an actor", "`--look-at` turns it toward a point.",
     [["level", "move", "--label", "Box", "--loc", "0,-100,50", "--look-at", "150,0,50", "--json"]],
     "`result` is the new location"),
    ("Lay out a set from a spec", "One YAML for the whole set; apply converges, a second apply changes nothing.",
     [["@spec:examples/unreal/scene/office.yaml"]], "`converged: true`"),
    ("Rest props on the floor", "Drop actors onto what is under them.",
     [["layout", "drop", "--labels", '["Ball"]', "--json"]], "per actor, how far it moved"),
    ("Check for floating or overlapping props", "Numbers, not a picture.",
     [["qa", "floating", "--json"], ["qa", "overlaps", "--ignore", '["Floor"]', "--json"]],
     "`pass` and `issues` (each with a `fix`)"),
    ("Add a light", "A rect light aimed at a point; converges on its label.",
     [["look", "light", "--label", "Key", "--kind", "rect", "--loc", "300,200,250", "--look-at", "0,0,60",
       "--intensity", "20", "--json"]], "`result` is the label"),
    ("Add a camera", "A cine camera placed and aimed, lens and focus set.",
     [["cam", "add", "--label", "CamA", "--loc", "400,0,150", "--look-at", "0,0,60", "--focal-mm", "35", "--json"]],
     "`changed`, the camera's numbers"),
    ("Where does a point land in the frame?", "Projection without rendering: u right, v down, 0..1.",
     [["cam", "project", "--camera", "CamA", "--points", '{"box": "Box", "origin": [0, 0, 0]}', "--json"]],
     "each point's u, v, depth and whether it is in frame"),
    ("Every camera, as numbers", "", [["cam", "describe", "--json"]], "location, rotation, focal, filmback, fields of view"),
    ("A sequence", "Playback range in frames at its rate; kept if it exists.",
     [["seq", "new", "--path", "/Game/Recipes/SEQ_A", "--end", "96", "--fps", "24", "--json"]],
     "`created`, `start`, `end`, `fps`"),
    ("Cut between cameras", "Each cut runs to the next.",
     [["seq", "camera_cuts", "--path", "/Game/Recipes/SEQ_A", "--cuts", '[["CamA", 0]]', "--json"],
      ["seq", "cuts", "--path", "/Game/Recipes/SEQ_A", "--json"]], "[camera, first frame, end frame] per cut"),
    ("The whole level as JSON", "Counts by class, lights, cameras, sequences.",
     [["level", "describe", "--json"]], ""),
    ("What was done to the level", "The op journal: every change with its arguments.",
     [["journal", "tail", "--n", "3", "--json"]], "the last entries: op, args, ms, result"),
    ("A typo, caught before anything is sent", "Exit code 2: nothing reached the editor.",
     [["level", "move", "--lable", "Box", "--json"]], "`error.candidates` holds the fix"),
    ("A missing actor", "Exit code 1: the op ran and says what to do.",
     [["level", "move", "--label", "Bxo", "--loc", "0,0,0", "--json"]], "`error.code`, `error.hint`"),
    ("A long op as a job", "`--async` returns at once; `film-ue job ID --wait` follows it.",
     [["seq", "new", "--path", "/Game/Recipes/SEQ_B", "--end", "48", "--async", "--json"]], "`job` (an id)"),
    ("Which selftests can run here", "Before running them on a box.",
     [["selftest", "list", "--json"]], "areas with what each needs; the box's capabilities"),
]


def _cli(argv, transport):
    from filmtools.unreal import describe as describe_mod, dxcli, opcli, schema, spec
    from filmtools.unreal.sdk import Unreal
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if argv[0].startswith("@spec:"):
            docs = spec.load(HERE.parents[1] / argv[0].split(":", 1)[1])
            res = spec.apply(docs, Unreal(transport=transport))
            print(json.dumps({"ok": res["ok"], "converged": res.get("converged"), "summary": res["summary"],
                              "items": [{"kind": i["kind"], "name": i["name"], "steps": [s["op"] for s in i["steps"]]}
                                        for i in res["items"]]}))
            rc = 0 if res["ok"] else 1
        elif argv[0] == "describe":
            ix = schema.index(schema.load())
            d = describe_mod.data(ix, argv[1])
            print(json.dumps({k: d[k] for k in ("name", "summary", "params", "returns", "multi_tick", "mutates",
                                                "idempotent")} if isinstance(d, dict) and "params" in d else d))
            rc = 0
        else:
            rc = opcli.run(argv, transport=transport)
    return rc, out.getvalue(), err.getvalue()


def run_all():
    """[(recipe, [(argv, rc, json)])] on a fresh fake engine."""
    from fakeunreal import core
    from test_ue_dx_e2e import FakeBridge
    with tempfile.TemporaryDirectory() as d:
        core.install(str(Path(d) / "project"))
        try:
            fmb = core.load_fmbridge()
            from fmbridge.ops import journal
            journal._state["path"] = str(Path(d) / "journal.jsonl")
            tr = FakeBridge(fmb)
            results = []
            for r in RECIPES:
                outs = []
                for argv in r[2]:
                    rc, out, err = _cli(list(argv), tr)
                    try:
                        doc = json.loads(out) if out.strip() else None
                    except ValueError:
                        doc = {"raw": out[-500:]}
                    outs.append((argv, rc, doc, err))
                results.append((r, outs))
            return results
        finally:
            core.uninstall()


def _short(v, depth=0):
    """Long lists cut to 3 items, long strings to 120 chars: the shape stays readable."""
    if isinstance(v, list):
        return [_short(x, depth + 1) for x in v[:3]] + ([f"... {len(v) - 3} more"] if len(v) > 3 else [])
    if isinstance(v, dict):
        return {k: _short(x, depth + 1) for k, x in v.items()}
    if isinstance(v, str) and len(v) > 120:
        return v[:117] + "..."
    if isinstance(v, float):
        return round(v, 3)
    return v


def render(results) -> str:
    out = ["# RECIPES: the common tasks, with their answers", "",
           "GENERATED by `tools/tests/recipes_gen.py`: each command below was run through the generated CLI against the",
           "fake engine and its `--json` answer is shown under it (lists cut to 3 items). On a box the values differ",
           "(positions, timings, paths); the shapes and the codes do not. Start with [GUIDE.md](GUIDE.md); the tools are",
           "in [dx.md](dx.md).", ""]
    for n, ((title, why, _, check), outs) in enumerate(results, 1):
        out += [f"## {n}. {title}", ""]
        if why:
            out += [why, ""]
        for argv, rc, doc, _ in outs:
            if argv[0].startswith("@spec:"):
                cmd = f"film-ue apply ../{argv[0].split(':', 1)[1]} --json"
            else:
                import shlex
                cmd = "film-ue " + " ".join(shlex.quote(a) for a in argv)
            out += ["```bash", cmd + (f"     # exit {rc}" if rc else ""), "```", "```json",
                    json.dumps(_short(doc), indent=1, default=str)[:2500], "```", ""]
        if check:
            out += [f"Check: {check}.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    OUT.write_text(render(run_all()))
    print(f"wrote {OUT}")
