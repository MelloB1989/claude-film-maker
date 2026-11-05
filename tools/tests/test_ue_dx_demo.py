"""B48: THE DEMO (examples/unreal/demo) end to end on the fake engine, through the real spec engine, the SDK and every
area's ops: apply all of it, then the second plan must be empty. The box's own content that the fake does not have
(a MetaHuman preset, the Epic sign-in, MetaHuman Animator's audio solve, a WAV on disk, a writable output folder, a
built MetaHuman's Body/Face components) is provided here, and only that. Whatever still cannot converge on the fake is
listed in KNOWN with the reason, so this test is also the list of what tomorrow's box must prove."""
import json
import struct
import wave
from pathlib import Path

import pytest

from fakeunreal import core
from filmtools.unreal import spec
from filmtools.unreal.sdk import Unreal
from test_ue_dx_e2e import FakeBridge

DEMO = Path(__file__).resolve().parents[2] / "examples" / "unreal" / "demo"

STANDING = {  # a 170 cm adult at the origin, facing +X: the bones the framing solver reads (camkit.framing.BONES)
    "head": [0, 0, 160], "neck_01": [0, 0, 150], "clavicle_l": [0, -15, 145], "clavicle_r": [0, 15, 145],
    "upperarm_l": [0, -20, 140], "upperarm_r": [0, 20, 140], "spine_04": [0, 0, 130], "spine_01": [0, 0, 105],
    "pelvis": [0, 0, 95], "calf_l": [0, -10, 50], "calf_r": [0, 10, 50], "foot_l": [0, -10, 8], "foot_r": [0, 10, 8],
    "ball_l": [12, -10, 2], "ball_r": [12, 10, 2], "FACIAL_L_Eye": [8, -3, 165], "FACIAL_R_Eye": [8, 3, 165]}

# (kind, name) -> why it cannot converge on the fake (empty when everything converges)
KNOWN: dict = {}


def _box_content(ue, fmb, tmp_path, monkeypatch, docs_vars):
    """What a real box has and the fake does not."""
    import fakeunreal.ext_mh as em
    em.add_presets(ue, names=(docs_vars["preset"],))
    import fmbridge.ops.mh._core as mhcore
    monkeypatch.setattr(mhcore, "signed_in", lambda: True)          # the Epic sign-in (epic-login on the box)
    ue.skeletal_mesh(docs_vars["face_mesh"], docs_vars["face_mesh"] + "_Skeleton")
    idle = ue.anim(docs_vars["idle"], length_s=7.0, skeleton="/Game/MH/Body/BodyMesh_Skeleton")  # the engine's idle
    idle._props.setdefault("sequence_length", 7.0)  # older ext_anim without it

    host_bp = docs_vars["host_bp"]
    orig = core.EditorActorSubsystem.spawn_actor_from_object

    def spawn(self, obj, location=None, rotation=None, transient=False):
        """A built MetaHuman Blueprint spawns with its Body and Face skeletal mesh components."""
        if getattr(obj, "get_path_name", lambda: "")().split(".")[0] == host_bp:
            a = ue.metahuman("__mh", face_mesh=docs_vars["face_mesh"])
            # an actor of the Blueprint's generated class (BP_Host_C), as the engine spawns it: scene.state reports
            # that Blueprint, so the set converges instead of respawning the host
            a.__class__ = core._AutoMeta(host_bp.rsplit("/", 1)[-1] + "_C", (type(a),),
                                         {"__module__": "unreal", "_bp_path": host_bp})
            ue.pose(a, STANDING)
            if location is not None:
                a.set_actor_location(location, False, False)
            a._props["spawned_from"] = obj
            return a
        return orig(self, obj, location, rotation, transient)
    monkeypatch.setattr(core.EditorActorSubsystem, "spawn_actor_from_object", spawn)

    class Perf(core.Object):
        """MetaHuman Animator's performance: the audio solve finishes at once here."""
        def set_blocking_processing(self, v):
            pass

        def start_pipeline(self, v=True):
            return "PipelineStarted"

        def is_processing(self):
            return False

        def get_number_of_processed_frames(self):
            return 90

    class Export:
        @staticmethod
        def get_export_animation_sequence_settings(perf):
            return core.Object("ExportSettings")

        @staticmethod
        def export_animation_sequence(perf, st):
            path = f"{st.get_editor_property('package_path')}/{st.get_editor_property('asset_name')}"
            a = ue.anim(path, length_s=3.0, skeleton=docs_vars["face_mesh"] + "_Skeleton")
            a._props.setdefault("sequence_length", 3.0)
            return a
    if "MetaHumanPerformance" not in ue._classes:  # ext_anim has its own since agent-01's 15c0d5b: use it then
        ue.MetaHumanPerformance = Perf
        ue._classes["MetaHumanPerformance"] = Perf
        ue.MetaHumanPerformanceExportUtils = Export

    wav = tmp_path / "demo_line.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(struct.pack("<h", 0) * 48000 * 3)
    return [f"voice_wav={wav}", f"out={tmp_path / 'out'}"]


def test_the_demo_converges_on_the_fake(fmb, ue, tmp_path, monkeypatch):
    import yaml
    docs_vars = yaml.safe_load((DEMO / "vars.yaml").read_text())["vars"]
    sets = _box_content(ue, fmb, tmp_path, monkeypatch, docs_vars)
    sdk = Unreal(transport=FakeBridge(fmb))
    docs = spec.load(DEMO / "demo.yaml", sets)
    res = spec.apply(docs, sdk)
    failed = {(i["kind"], i["name"]): f"[{i['error'].get('code')}] {i['error'].get('message')}"
              for i in res["items"] if i.get("error")}
    left = {(x["kind"], x["name"]): [s["op"] for s in x["steps"]] or (x.get("error") or {}).get("message")
            for x in res.get("left", [])}
    unexpected = {k: v for k, v in {**failed, **left}.items() if k not in KNOWN}
    assert not unexpected, json.dumps({str(k): v for k, v in unexpected.items()}, indent=1)
    again = spec.plan(docs, sdk)  # the second plan: nothing pending but the always-run op steps (and KNOWN)
    pending = {(i.kind, i.name) for i in again if [s for s in i.steps if not s.get("always")] or i.error}
    assert pending <= set(KNOWN), pending
    stages = {(i["kind"], i["name"]) for i in res["items"]}
    assert len(stages) == len(docs) and {"level", "op", "scene", "audio", "shot"} <= {k for k, _ in stages}
    assert ue.dialogs == []
