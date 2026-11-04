"""WP11 (Claude DX): the op schema, the generated CLI and SDK, error hints. Pure Python: no editor, no box."""
import json
import textwrap

import pytest

from filmtools.unreal import dxcli, errors, opcli, schema
from filmtools.unreal.sdk import Job, OpError, Unreal, gen

OPS = '''
"""Widgets: make and move them."""
from . import op


@op("wid.make", mutates=True, idempotent=True, tags=["fast"])
def make(label: str, *, size: float = 1.0, loc=(0, 0, 0), rot_=None, colors: list | None = None, opts: dict = None,
         kind: str = "box", on: bool = True) -> str:
    """A widget at `loc` (cm). `kind` one of box, ball, cone.

    Args:
        label: the actor label.
        size: edge in cm.

    Example: film-ue wid make --label W1 --size 20
    """
    return label


@op("wid.settle")
def settle(label: str, frames: int = 3):
    """Wait for it to settle (multi-tick)."""
    for _ in range(frames):
        yield
    return 1


def helper():
    pass
'''


@pytest.fixture
def ops_dir(tmp_path):
    d = tmp_path / "unreal" / "fmbridge" / "ops"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("def op(name, **kw):\n    return lambda f: f\n")
    (d / "wid.py").write_text(textwrap.dedent(OPS))
    (d / "broken.py").write_text("def (:\n")
    return d


@pytest.fixture
def ix(ops_dir, tmp_path):
    return schema.index(schema.extract(ops_dir, tmp_path))


# --------------------------------------------------------------------------------------------------------- schema

def test_extract_wire_shape(ops_dir, tmp_path):
    s = schema.extract(ops_dir, tmp_path)
    assert s["version"] == 1 and isinstance(s["ops"], list)
    o = {x["name"]: x for x in s["ops"]}["wid.make"]
    assert set(o) == {"name", "area", "verb", "module", "file", "line", "summary", "doc", "params", "returns",
                      "multi_tick", "mutates", "idempotent", "tags"}
    assert (o["area"], o["verb"], o["module"], o["file"]) == ("wid", "make", "fmbridge.ops.wid", "unreal/fmbridge/ops/wid.py")
    assert o["mutates"] is True and o["idempotent"] is True and o["tags"] == ["fast"]
    assert o["returns"] == "str" and o["multi_tick"] is False
    p = {x["name"]: x for x in o["params"]}
    assert p["label"] == {"name": "label", "kind": "positional", "type": "str", "required": True, "default": None}
    assert p["size"]["kind"] == "keyword" and p["size"]["default"] == 1.0
    assert p["loc"]["default"] == [0, 0, 0] and p["loc"]["type"] is None
    assert {x["name"]: x for x in s["ops"]}["wid.settle"]["multi_tick"] is True
    assert "fmbridge.ops.broken" in s["broken"]
    assert s["areas"]["wid"] == "Widgets: make and move them."


def test_index_derives_cli_facts(ix):
    p = {x["name"]: x for x in ix["ops"]["wid.make"]["params"]}
    assert p["rot_"]["flag"] == "rot" and p["rot_"]["nullable"]
    assert p["loc"]["value"] == "list" and p["colors"]["value"] == "list" and p["opts"]["value"] == "dict"
    assert p["on"]["value"] == "bool" and p["size"]["value"] == "float"
    assert p["label"]["help"] == "the actor label." and p["size"]["help"] == "edge in cm."
    assert p["kind"]["choices"] == ["box", "ball", "cone"]
    assert ix["ops"]["wid.make"]["examples"] == ["film-ue wid make --label W1 --size 20"]


def test_from_list_matches_static_names(ix):
    listing = {"wid.make": "wid.make(label: str, *, size: float = 1.0) -> str: A widget.",
               "list": "list(prefix: str = '', full: bool = False) -> dict: Every op."}
    s = schema.from_list(listing)
    assert [o["name"] for o in s["ops"]] == ["list", "wid.make"]
    o = s["ops"][1]
    assert o["returns"] == "str" and o["params"][1]["kind"] == "keyword" and o["summary"] == "A widget."


def test_summary_keeps_abbreviations():
    assert schema.summary("Keep focus on it, e.g. a face. More.") == "Keep focus on it, e.g. a face."


def test_snapshot_and_sdk_are_current():
    """Change an op, then `film-ue dx gen`: the committed schema snapshot and SDK must match the ops."""
    assert dxcli.stale() == []


def test_real_ops_lint_has_no_broken_modules():
    assert schema.extract()["broken"] == {}


# ------------------------------------------------------------------------------------------------------------ CLI

@pytest.mark.parametrize("raw,kind,want", [
    ("3", "int", 3), ("2.5", "float", 2.5), ("yes", "bool", True), ("off", "bool", False),
    ("0,0,300", "list", [0, 0, 300]), ("[1, 2]", "list", [1, 2]), ("a,b", "list", ["a", "b"]), ("", "list", []),
    ("pitch=-10,yaw=90", "dict", {"pitch": -10, "yaw": 90}), ('{"a": 1}', "dict", {"a": 1}),
    ("null", "any", None), ("pitch=5", "any", {"pitch": 5}), ("1,2,3", "any", [1, 2, 3]), ("hello", "any", "hello"),
    ("/Game/A", "str", "/Game/A"), ("12", "str", "12"),
])
def test_parse_value(raw, kind, want):
    assert opcli.parse_value(raw, kind) == want


def test_parse_value_file(tmp_path):
    f = tmp_path / "v.json"
    f.write_text('{"x": [1, 2]}')
    assert opcli.parse_value(f"@{f}", "dict") == {"x": [1, 2]}
    with pytest.raises(ValueError):
        opcli.parse_value("1.5", "int")


def _fake(calls, answer=None):
    def t(kind, payload, timeout):
        calls.append((kind, payload))
        return answer or {"ok": True, "result": "W1", "stdout": ""}
    return t


def test_run_sends_typed_args(ix, capsys):
    calls = []
    rc = opcli.run(["wid", "make", "--label", "W1", "--loc", "1,2,3", "--rot", "yaw=90", "--no-on", "--json"],
                   ix, _fake(calls))
    assert rc == 0
    assert calls == [("op", {"name": "wid.make", "args": {"label": "W1", "loc": [1, 2, 3], "rot_": {"yaw": 90},
                                                          "on": False}, "async": False})]
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["result"] == "W1"


def test_dry_run_sends_nothing(ix, capsys):
    calls = []
    assert opcli.run(["wid", "make", "--label", "W", "--on", "--dry-run"], ix, _fake(calls)) == 0
    assert calls == [] and json.loads(capsys.readouterr().out)["args"] == {"label": "W", "on": True}


@pytest.mark.parametrize("argv,code,cand", [
    (["wid", "make", "--lable", "W"], "bad_args", "--label"),
    (["wid", "mak", "--label", "W"], "bad_args", "make"),
    (["wid", "make"], "bad_args", None),
    (["wid", "make", "--label", "W", "--kind", "bx"], "bad_value", "box"),
    (["wid", "make", "--label", "W", "--size", "big"], "bad_value", None),
])
def test_usage_errors_are_json_with_candidates(ix, capsys, argv, code, cand):
    assert opcli.run(argv + ["--json"], ix, _fake([])) == opcli.EXIT_USAGE
    err = json.loads(capsys.readouterr().out)["error"]
    assert err["code"] == code and err["hint"]
    if cand:
        assert cand in err["candidates"]


def test_op_error_gets_hint(ix, capsys):
    bad = {"ok": False, "stdout": "", "error": "Traceback (most recent call last):\n  x\nValueError: no actor labelled 'Kye'"}
    assert opcli.run(["wid", "make", "--label", "Kye", "--json"], ix, _fake([], bad)) == opcli.EXIT_OP
    err = json.loads(capsys.readouterr().out)["error"]
    assert err["code"] == "not_found" and "level actors" in err["hint"]


def test_bridge_operror_passes_through(ix, capsys):
    ans = {"ok": False, "code": "not_found", "message": "no actor 'Kye'", "hint": "film-ue level actors",
           "candidates": ["Key"], "error": "tb"}
    assert opcli.run(["wid", "make", "--label", "Kye"], ix, _fake([], ans)) == opcli.EXIT_OP
    err = capsys.readouterr().err
    assert err.startswith("error [not_found]: no actor 'Kye'") and "did you mean: Key" in err


def test_async_returns_job(ix, capsys):
    rc = opcli.run(["wid", "settle", "--label", "W", "--async", "--json"], ix, _fake([], {"ok": True, "job": "j1"}))
    assert rc == 0 and json.loads(capsys.readouterr().out)["job"] == "j1"


def test_timeout_names_job():
    p = errors.explain({"ok": False, "error": "timeout after 600.0s (still running as job ab12)", "job": "ab12"})
    assert p.code == "timeout" and p.job == "ab12" and "film-ue job ab12 --wait" in p.hint


def test_unknown_op_candidates(ix):
    p = errors.explain({"ok": False, "error": "KeyError: \"no op 'wid.mak' (ops.call('list') shows them)\""},
                       "wid.mak", index=ix)
    assert p.code == "unknown_op" and "wid.make" in p.candidates


def test_wants_only_areas():
    assert opcli.wants(["seq", "new"], {"set", "up"})
    assert not opcli.wants(["set", "--os", "linux"], {"set", "up"})
    assert not opcli.wants(["nosuch"], {"set"})


# ------------------------------------------------------------------------------------------------------------ SDK

def test_sdk_matches_schema():
    ue = Unreal(transport=_fake([]))
    ix = schema.index(schema.extract())
    for name, o in ix["ops"].items():
        if not o["area"]:
            continue
        fn = getattr(getattr(ue, o["area"]), gen.ident(o["verb"]))
        assert name in fn.__doc__


def test_sdk_sends_only_given_args():
    calls = []
    ue = Unreal(transport=_fake(calls))
    assert ue.level.move(label="A", loc=[0, 0, 1]) == "W1"
    assert calls[0][1] == {"name": "level.move", "args": {"label": "A", "loc": [0, 0, 1]}, "async": False}


def test_sdk_checks_names_offline():
    ue = Unreal(transport=_fake([]))
    with pytest.raises(OpError) as e:
        ue.call("level.move", lable="A")
    assert e.value.code == "bad_args" and "label" in e.value.candidates


def test_sdk_job_wait():
    answers = iter([{"ok": True, "job": "j9"}, {"done": False}, {"done": True, "ok": True, "result": 7}])
    ue = Unreal(transport=lambda k, p, t: next(answers))
    job = ue.call("seq.stills", wait=False, path="/Game/S", frames=[1])
    assert isinstance(job, Job) and job.wait(every=0) == 7


def test_sdk_raises_operror():
    ue = Unreal(transport=_fake([], {"ok": False, "error": "x\nValueError: no actor labelled 'Q'"}))
    with pytest.raises(OpError) as e:
        ue.level.move(label="Q")
    assert e.value.code == "not_found" and e.value.hint


def test_generated_code_compiles(ix):
    src = gen.generate(ix)
    ns: dict = {}
    exec(compile(src.replace("from . import UNSET, _Area", "from filmtools.unreal.sdk import UNSET, _Area"),
                 "<gen>", "exec"), ns)
    assert "WidOps" in ns and "settle" in dir(ns["WidOps"])


def test_static_schema_equals_live_ops_schema(fmb):
    """The offline schema (AST) and the bridge's ops.schema (inspect, here against the fake engine) are the same."""
    from fakeunreal import run_op
    live = {o["name"]: o for o in run_op("ops.schema")["ops"]}
    static = {o["name"]: o for o in schema.extract()["ops"]}
    assert set(live) == set(static)
    diffs = []
    for n, lo in live.items():
        so = static[n]
        for k in lo:
            if k == "params":
                for lp, sp in zip(lo[k], so[k]):
                    for pk in lp:
                        if pk == "default" and sp["default"] is None and isinstance(lp["default"], str) and \
                                not sp["required"] and lp["default"] not in ("",):
                            continue  # a non-literal default: the live one is its repr, the static one null
                        if lp[pk] != sp[pk]:
                            diffs.append((n, lp["name"], pk, lp[pk], sp[pk]))
                if len(lo[k]) != len(so[k]):
                    diffs.append((n, "params", len(lo[k]), len(so[k])))
            elif lo[k] != so[k]:
                diffs.append((n, k, lo[k], so[k]))
    assert not diffs, diffs[:10]
