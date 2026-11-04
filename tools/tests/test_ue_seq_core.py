"""WP8 Sequencer core, the pure half (no engine, no fake): time, keys, spec compile, plan, retime, lint, chunks."""
import copy

import pytest

from filmtools.unreal import seq_spec

C = seq_spec.core()
Rate, SpecError = C.time.Rate, C.spec.SpecError


# --- time --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("v,want", [(24, (24, 1)), ("23.976", (24000, 1001)), ("30000/1001", (30000, 1001)),
                                    (29.97, (30000, 1001)), ("ntsc", (30000, 1001)), ([25, 1], (25, 1)),
                                    ("60fps", (60, 1)), ({"numerator": 48, "denominator": 1}, (48, 1))])
def test_rate_parse(v, want):
    r = Rate.parse(v)
    assert (r.numerator, r.denominator) == want


def test_rate_parse_rejects():
    with pytest.raises(ValueError, match="frame rate"):
        Rate.parse("fast")
    with pytest.raises(ValueError):
        Rate.parse(0)


def test_seconds_frames_ticks():
    r = Rate(24)
    assert r.seconds(48) == 2.0 and r.frame(2.5) == 60.0
    assert r.to_ticks(1) == 1000 and r.from_ticks(24000) == 24.0
    ntsc = Rate(24000, 1001)
    assert ntsc.to_ticks(48) == 48048
    assert ntsc.frames_ceil(2.0) == 48  # 47.952 -> 48
    assert C.time.convert(48, Rate(24), Rate(30)) == 60.0


def test_parse_time_forms():
    r = Rate(24)
    assert r.parse_time(10) == 10 and r.parse_time("2s") == 48 and r.parse_time("48f") == 48
    assert r.parse_time("1m30s") == 2160 and r.parse_time("500ms") == 12
    assert r.parse_time("00:00:02:12") == 60
    with pytest.raises(ValueError, match="not a time"):
        r.parse_time("soon")


def test_timecode_roundtrip_nondrop_and_drop():
    r = Rate(24)
    assert r.timecode(86400 + 12) == "01:00:00:12"
    assert r.from_timecode("01:00:00:12") == 86412
    d = Rate(30000, 1001)
    assert d.timecode(1800) == "00:01:00;02"  # frames 00 and 01 of minute 1 are dropped
    assert d.timecode(17982) == "00:10:00;00"  # no drop at every tenth minute
    for f in (0, 1799, 1800, 17981, 17982, 107892, 123456):
        assert d.from_timecode(d.timecode(f)) == f


# --- keys --------------------------------------------------------------------------------------------------------------

def test_normalize_keys_forms_sort_dedupe():
    ks = C.curves.normalize_keys([[10, 1], {"frame": 0, "value": 0, "interp": "linear"}, [10, 2, "step"]],
                                 value=float)
    assert ks == [[0, 0.0, "linear"], [10, 2.0, "constant"]]


def test_normalize_keys_tangents_make_user_or_break():
    ks = C.curves.normalize_keys([[0, 0, "auto", {"arrive": 1, "leave": 1}], [5, 1, "auto", {"arrive": 0, "leave": 2}]])
    assert ks[0][2] == "user" and ks[1][2] == "break"


def test_normalize_keys_errors_name_the_key():
    with pytest.raises(C.curves.KeyError_, match=r"keys\[1\]"):
        C.curves.normalize_keys([[0, 1], [1]])
    with pytest.raises(C.curves.KeyError_, match="unknown interpolation"):
        C.curves.normalize_keys([[0, 1, "wobbly"]])


def test_evaluate_holds_steps_lines_and_eases():
    ev = C.curves.evaluate
    ks = [[0, 0.0, "linear"], [10, 10.0, "constant"], [20, 0.0, "auto"]]
    assert ev(ks, -5) == 0.0 and ev(ks, 5) == 5.0 and ev(ks, 15) == 10.0 and ev(ks, 30) == 0.0
    smooth = [[0, 0.0, "auto"], [10, 1.0, "auto"]]
    v = ev(smooth, 5)
    assert abs(v - 0.5) < 1e-9 and ev(smooth, 2) < 0.2  # eased (flat ends), symmetric
    assert ev([[0, True, "constant"], [5, False, "constant"]], 7) is False


def test_unwrap_and_look_at():
    assert C.curves.unwrap([170, -170, -10]) == [170, 190, 350]
    r = C.curves.look_at([0, 0, 0], [100, 100, 0])
    assert abs(r["yaw"] - 45) < 1e-9 and r["pitch"] == 0
    r = C.curves.look_at([0, 0, 0], [0, 0, -10])
    assert abs(r["pitch"] + 90) < 1e-9


def test_reduce_keeps_shape_within_tolerance():
    samples = [[f, (f / 10.0) if f < 50 else 5.0] for f in range(101)]
    ks = C.curves.reduce(samples, 1e-3)
    assert len(ks) == 3 and ks[0][0] == 0 and ks[-1][0] == 100
    for f, v in samples:
        assert abs(C.curves.evaluate(ks, f) - v) <= 1e-3


# --- spec ---------------------------------------------------------------------------------------------------------------

SPEC = {
    "kind": "sequence", "version": 1, "name": "t",
    "sequence": "/Game/T/SEQ_T", "fps": 24, "range": [0, "10s"],
    "markers": [[48, "beat"]],
    "bindings": {
        "Hero": {
            "transform": {"keys": [[0, [0, 0, 0], {"yaw": 170}], [48, [100, 0, 0], {"yaw": -170}]]},
            "visible": [[0, True], [100, False]],
            "anim": {"component": "Body", "sections": [{"anim": "/Game/A/Idle", "start": 0, "end": 120,
                                                        "blend_in": 6}]},
            "props": {"LightComponent0/LightColor": {"type": "color", "srgb": True, "keys": [[0, [1, 0.5, 0.2]]]},
                      "Intensity": [[0, 5], [24, 10]]},
            "materials": [{"component": "Mesh", "slot": 0, "param": "Glow", "keys": [[0, 0], [24, 1]]},
                          {"component": "Mesh", "slot": 0, "param": "Tint", "keys": [[0, [1, 0, 0]]]}],
        },
        "CamA": {"spawn": {"class": "CineCameraActor"},
                 "transform": [[0, [0, -300, 160], [0, 0, 150]]]},
    },
    "camera_cuts": [["CamA", 0], ["Hero", "5s"]],
    "audio": {"VO": [{"sound": "/Game/Au/L1", "start": 12, "end": 60, "volume": 0.8}]},
    "fade": {"color": [0, 0, 0], "keys": [[0, 1], [12, 0]]},
    "shots": [{"sequence": "/Game/S/sh010", "start": 0, "end": 120, "name": "sh010", "preroll": 8},
              {"sequence": "/Game/S/sh020", "start": 120, "end": 240, "name": "sh020"}],
}


def compiled(spec=SPEC, resolver=None):
    return C.spec.compile_spec(copy.deepcopy(spec), resolver)[0]


def by(doc, kind, binding="", name=""):
    return next(t for t in doc["tracks"] if t["kind"] == kind and t["binding"] == binding
                and (not name or t["name"] == name))


def test_compile_spec_shapes():
    doc = compiled()
    assert doc["range"] == [0, 240] and doc["markers"] == [{"frame": 48, "label": "beat"}]
    tr = by(doc, "transform", "Hero")
    ch = tr["sections"][0]["channels"]
    assert [k[1] for k in ch["rotation.yaw"]["keys"]] == [170.0, 190.0]  # unwrapped
    assert ch["location.x"]["keys"][1][:2] == [48, 100.0]
    cam = by(doc, "transform", "CamA")["sections"][0]["channels"]
    assert abs(cam["rotation.pitch"]["keys"][0][1] - C.curves.look_at([0, -300, 160], [0, 0, 150])["pitch"]) < 1e-9
    col = by(doc, "color", "Hero")
    assert col["component"] == "LightComponent0" and col["name"] == "LightColor"
    assert abs(col["sections"][0]["channels"]["g"]["keys"][0][1] - C.curves.srgb_to_linear(0.5)) < 1e-9
    mat = by(doc, "material", "Hero")
    assert set(mat["sections"][0]["channels"]) == {"Glow", "Tint"} and mat["name"] == "slot:0"
    cuts = by(doc, "camera_cut")["sections"]
    assert [(s["range"], s["params"]["camera"]) for s in cuts] == [([0, 120], "CamA"), ([120, 240], "Hero")]
    assert [b["kind"] for b in doc["bindings"]] == ["possessable", "spawnable"]
    shots = by(doc, "shot")["sections"]
    assert shots[0]["params"]["preroll"] == 8


def test_compile_spec_reports_every_problem():
    bad = {"sequence": "Game/no-slash", "fps": 24, "range": [10, 5], "colour": 1,
           "bindings": {"Hero": {"transform": [[0, [0, 0], {"yaw": 1}]], "visibel": []}},
           "camera_cuts": [[0, "Cam"]]}
    with pytest.raises(SpecError) as e:
        C.spec.compile_spec(bad)
    msg = str(e.value)
    for want in ("sequence:", "range:", "colour", "location", "visibel", "camera_cuts[0]"):
        assert want in msg, want


def test_validate_offline():
    assert seq_spec.validate(SPEC)["ok"]
    assert not seq_spec.validate({"sequence": "/Game/X", "shots": [{"sequence": "/Game/a", "start": 0}]})["ok"]


def test_shot_overlap_on_one_row_is_an_error():
    s = {"sequence": "/Game/X", "shots": [{"sequence": "/Game/a", "start": 0, "end": 50},
                                          {"sequence": "/Game/b", "start": 40, "end": 90}]}
    with pytest.raises(SpecError, match="overlaps"):
        C.spec.compile_spec(s)


# --- plan ---------------------------------------------------------------------------------------------------------------

def described(doc):
    """What seq.describe would say after applying `doc` exactly (bindings bound, all tracks present)."""
    have = copy.deepcopy(doc)
    have.pop("prune", None)
    for b in have["bindings"]:
        b["bound"] = True
    return have


def test_plan_from_nothing_then_converged():
    want = compiled()
    steps = C.plan.plan(want, None)
    ops = [s["op"] for s in steps]
    assert ops[0] == "seq.add" and ops.count("seq.bind") == 2 and "seq.markers" in ops
    assert ops.count("seq.write") == len(want["tracks"])
    assert C.plan.plan(want, described(want)) == []


def test_plan_only_what_changed():
    want = compiled()
    have = described(want)
    by(have, "float", "Hero")["sections"][0]["channels"]["value"]["keys"][1][1] = 11.0
    have["range"] = [0, 200]
    steps = C.plan.plan(want, have)
    assert [s["op"] for s in steps] == ["seq.add", "seq.write"]
    assert steps[1]["args"]["track"]["name"] == "Intensity" and steps[0]["args"]["end"] == 240


def test_plan_partial_material_ignores_other_params():
    want = compiled()
    have = described(want)
    by(have, "material", "Hero")["sections"][0]["channels"]["Other"] = {"keys": [[0, 3.0, "auto"]], "default": None}
    assert C.plan.plan(want, have) == []


def test_plan_prune_removes_unlisted_tracks_of_named_bindings_only():
    want = compiled()
    have = described(want)
    have["tracks"].append({"kind": "float", "binding": "Hero", "component": "", "name": "Old", "params": {},
                           "sections": []})
    have["tracks"].append({"kind": "float", "binding": "Other", "component": "", "name": "Keep", "params": {},
                           "sections": []})
    assert C.plan.plan(want, have) == []
    steps = C.plan.plan(want, have, prune=True)
    assert [(s["op"], s["args"]["binding"], s["args"]["name"]) for s in steps] == [("seq.remove_track", "Hero", "Old")]


def test_plan_unbound_binding_gets_rebind():
    want = compiled()
    have = described(want)
    have["bindings"][0]["bound"] = False
    assert [s["op"] for s in C.plan.plan(want, have)] == ["seq.rebind"]


def test_seq_spec_plan_uses_state_want():
    want = compiled()
    state = dict(described(want), want=want)
    assert seq_spec.plan(SPEC, state) == []
    assert seq_spec.plan(SPEC, {"exists": False})[0]["op"] == "seq.add"


# --- retime / clip ------------------------------------------------------------------------------------------------------

def test_transform_time_offset_scale_and_ripple():
    doc = compiled()
    moved, _ = C.model.transform_time(doc, offset=10)
    assert moved["range"] == [10, 250]
    assert by(moved, "camera_cut")["sections"][1]["range"] == [130, 250]
    slow, notes = C.model.transform_time(doc, scale=2.0)
    a = by(slow, "anim", "Hero")["sections"][0]
    assert a["range"] == [0, 240] and a["params"]["rate"] == 0.5
    au = by(slow, "audio", name="VO")["sections"][0]
    assert au["range"] == [24, 72] and notes  # moved, not stretched
    rip, _ = C.model.transform_time(doc, offset=5, after=100)
    assert by(rip, "transform", "Hero")["sections"][0]["channels"]["location.x"]["keys"][1][0] == 48
    assert by(rip, "camera_cut")["sections"][1]["range"] == [125, 245]


def test_clip_cuts_window_and_shifts_clip_offsets():
    doc = compiled()
    out, _ = C.model.clip(doc, 24, 72, to=0, fps=24)
    assert out["range"] == [0, 48]
    a = by(out, "anim", "Hero")["sections"][0]
    assert a["range"] == [0, 48] and a["params"]["offset"] == 1.0
    x = by(out, "transform", "Hero")["sections"][0]["channels"]["location.x"]["keys"]
    assert x[0][0] == 0 and abs(x[0][1] - C.curves.evaluate(
        by(doc, "transform", "Hero")["sections"][0]["channels"]["location.x"]["keys"], 24)) < 1e-9
    assert out["markers"] == [{"frame": 24, "label": "beat"}]


# --- lint / shots / chunks ----------------------------------------------------------------------------------------------

def test_lint_finds_gaps_flips_and_unbound():
    doc = described(compiled())
    doc["bindings"][0]["bound"] = False
    by(doc, "camera_cut")["sections"][1]["range"] = [130, 240]
    by(doc, "transform", "Hero")["sections"][0]["channels"]["rotation.yaw"]["keys"][1][1] = -170.0
    res = C.plan.lint(doc)
    codes = {i["code"] for i in res["issues"]}
    assert {"seq.binding_unbound", "seq.cut_gap", "seq.rotation_flip"} <= codes and res["pass"] is False


def test_chunks_respect_shot_starts_and_preroll():
    doc = compiled()
    res = C.plan.chunks(doc, start=100, end=200, max_frames=40, preroll=4)
    got = [(c["start"], c["end"], c["shot"], c["preroll_frames"]) for c in res["chunks"]]
    assert got == [(100, 120, "sh010", 108), (120, 160, "sh020", 4), (160, 200, "sh020", 44)]
    assert res["chunks"][1]["first_after_cut"] and not res["chunks"][0]["first_after_cut"]
    capped = C.plan.chunks(doc, start=100, end=120, max_preroll=20)
    assert capped["chunks"][0]["cold"] and capped["chunks"][0]["preroll_frames"] == 20


def test_shots_fall_back_to_camera_cuts():
    doc = compiled()
    doc["tracks"] = [t for t in doc["tracks"] if t["kind"] != "shot"]
    assert [s["camera"] for s in C.plan.shots_of(doc)] == ["CamA", "Hero"]


# --- the kind: examples, schema, WP11's engine ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "examples/unreal/sequence").glob("*.yaml"))


def test_examples_validate_against_schema_and_compile():
    import json
    from filmtools.unreal import jsonschema_lite
    schema = json.loads((ROOT / "tools/filmtools/unreal/schemas/sequence.schema.json").read_text())
    assert EXAMPLES
    for p in EXAMPLES:
        for doc in seq_spec.load(str(p)):
            assert jsonschema_lite.validate(doc, schema) == [], p.name
            v = seq_spec.validate(doc)
            assert v["ok"], (p.name, v["problems"])


def test_schema_rejects_a_typo():
    import json
    from filmtools.unreal import jsonschema_lite
    schema = json.loads((ROOT / "tools/filmtools/unreal/schemas/sequence.schema.json").read_text())
    assert jsonschema_lite.validate({"sequence": "/Game/X", "camera_cut": []}, schema)


def test_kind_registered_with_the_spec_engine():
    from filmtools.unreal import spec as engine
    k = engine.kinds()["sequence"]
    assert k.order == 60
    doc = seq_spec.load(str(EXAMPLES[-1]))[0]
    assert k.plan(doc, None)[0]["op"] == "seq.add"


def test_diff_says_where_tracks_first_differ():
    a = described(compiled())
    b = copy.deepcopy(a)
    assert C.plan.diff(a, b)["same"]
    by(b, "float", "Hero")["sections"][0]["channels"]["value"]["keys"][1][1] = 11.0
    b["tracks"] = [t for t in b["tracks"] if t["kind"] != "fade"]
    b["range"] = [0, 200]
    d = C.plan.diff(a, b)
    assert not d["same"] and d["sequence"]["range"] == {"a": [0, 240], "b": [0, 200]}
    ch = {t["track"]: t for t in d["tracks"]}
    assert ch["/fade"]["change"] == "removed"
    f = ch["Hero/float:Intensity"]
    assert f["where"] == "sections[0].channels.value" and f["key"] == 1 and f["b"][1] == 11.0
