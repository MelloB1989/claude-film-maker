"""B31's fakes: a Control Rig on a skeletal actor in a sequence, whose controls drive bones, for pose.* tests.

`fake.rig(label, {control: bone}, gain=0.8)` puts a rig on the actor's binding: ControlRigSequencerLibrary
(the engine's ScriptName for UControlRigSequencerEditorLibrary) lists it, a control's world transform is its bone's
position + 2 cm up, and setting it moves the bone by `gain` of the change (a real rig is never exactly 1:1, so the
solve has to iterate). Moving the body control (pelvis) carries every bone but the IK-pinned hands and feet."""
from . import core

IK = ("hand_l", "hand_r", "foot_l", "foot_r")


class _Name(core.Object):
    pass


class _Hierarchy:
    def __init__(self, names):
        self.names = names

    def get_control_keys(self):
        out = []
        for n in self.names:
            k = _Name(n)
            k._props["name"] = n
            out.append(k)
        return out


class FakeControlRig(core.Object):
    def __init__(self, actor, controls: dict, gain: float):
        super().__init__("FakeBodyRig")
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_controls", dict(controls))
        object.__setattr__(self, "_gain", gain)
        object.__setattr__(self, "writes", [])

    def get_hierarchy(self):
        return _Hierarchy(list(self._controls))

    def _bones(self):
        return self._actor.get_components_by_class(core.SkeletalMeshComponent)[0]._props["bones"]


class _Proxy(core.Object):
    pass


class _Binding:
    def __init__(self, label):
        self.label = label

    def get_display_name(self):
        return self.label


class ControlRigSequencerLibrary(core.Object):
    rigs: list = []

    @staticmethod
    def get_control_rigs(level_sequence):
        return [p for p in ControlRigSequencerLibrary.rigs]

    @staticmethod
    def get_control_rig_world_transform(level_sequence, control_rig, control_name, frame, time_unit=None):
        b = control_rig._bones()[control_rig._controls[str(control_name)]]
        return core.Transform(location=core.Vector(b[0], b[1], b[2] + 2.0), rotation=core.Rotator())

    @staticmethod
    def set_control_rig_world_transform(level_sequence, control_rig, control_name, frame, world_transform,
                                        time_unit=None, set_key=True):
        name = str(control_name)
        bones = control_rig._bones()
        bone = control_rig._controls[name]
        cur = bones[bone]
        t = world_transform.translation
        d = [(t.x - cur[0]) * control_rig._gain, (t.y - cur[1]) * control_rig._gain,
             (t.z - 2.0 - cur[2]) * control_rig._gain]
        movers = [b for b in bones if b not in IK] if bone == "pelvis" else [bone]
        for b in movers:
            bones[b] = [bones[b][0] + d[0], bones[b][1] + d[1], bones[b][2] + d[2]]
        control_rig.writes.append((name, int(getattr(frame, "value", frame))))


def install(fake):
    ControlRigSequencerLibrary.rigs = []
    fake.ControlRigSequencerLibrary = ControlRigSequencerLibrary
    fake._classes["ControlRigSequencerLibrary"] = ControlRigSequencerLibrary

    def rig(label, controls: dict, gain: float = 0.8):
        a = fake.actor(label)
        r = FakeControlRig(a, controls, gain)
        p = _Proxy("proxy", proxy=_Binding(label), control_rig=r)
        ControlRigSequencerLibrary.rigs.append(p)
        return r
    fake.rig = rig
