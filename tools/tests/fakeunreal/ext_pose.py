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

    def get_controls(self, traverse=True):  # Python name of GetControlKeys (ScriptName GetControls)
        out = []
        for n in self.names:
            k = _Name(n)
            k._props["name"] = n
            out.append(k)
        return out


BIND_LAG = 20  # ticks before a new rig track's rig is bound to the mesh
LAG = 6  # ticks before a keyed control moves its bones: the engine re-evaluates later, not in the call (day-1 probe)


class FakeControlRig(core.Object):
    """`bound_at`: the fake tick from which Sequencer has bound the rig to the mesh. Before it the mesh has no anim
    instance, a control reads the origin and a world write lands nowhere, as on the box."""
    def __init__(self, actor, controls: dict, gain: float, bound_at: int = 0):
        super().__init__("FakeBodyRig")
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_controls", dict(controls))
        object.__setattr__(self, "_gain", gain)
        object.__setattr__(self, "writes", [])
        object.__setattr__(self, "bound_at", bound_at)
        object.__setattr__(self, "pending", [])  # [(tick due, {bone: delta})]
        comp = actor.get_components_by_class(core.SkeletalMeshComponent)[0]
        object.__setattr__(comp, "get_anim_instance",
                           lambda: core.Object("ControlRigLayerInstance") if self.bound() else None)

    def bound(self) -> bool:
        return core._fake().ticks >= self.bound_at

    def _settle(self):
        now, keep = core._fake().ticks, []
        bones = self._bones()
        for due, moves in self.pending:
            if due > now:
                keep.append((due, moves))
                continue
            for b, d in moves.items():
                bones[b] = [bones[b][0] + d[0], bones[b][1] + d[1], bones[b][2] + d[2]]
        object.__setattr__(self, "pending", keep)

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

    classes: dict = {}  # rig class name -> {control: bone}, for find_or_create_control_rig_track

    @staticmethod
    def get_control_rigs(level_sequence):
        out = []
        for p in ControlRigSequencerLibrary.rigs:
            b = getattr(p, "_binding", None)
            if b is None:
                out.append(p)
            elif b.seq is level_sequence:  # the engine makes the proxy (and its BindingID) afresh on every call
                out.append(_Proxy("proxy", proxy=type(b)(b.seq, b.data), control_rig=p.control_rig))
        return out

    @staticmethod
    def find_or_create_control_rig_track(world, level_sequence, control_rig_class, binding, is_layered_control_rig=False):
        """FindOrCreateControlRigTrack: the track on `binding` (a MovieSceneBindingProxy), made with a new rig."""
        for p in ControlRigSequencerLibrary.rigs:
            b = getattr(p, "_binding", None)
            if b is not None and b.seq is level_sequence and b.data is binding.data:
                return p
        name = control_rig_class.__name__ if isinstance(control_rig_class, type) else str(control_rig_class)
        controls = ControlRigSequencerLibrary.classes.get(name)
        if controls is None:
            return None
        a = core._fake().actor(binding.data.obj_label)
        p = _Proxy("proxy", control_rig=FakeControlRig(a, controls, 0.8, bound_at=core._fake().ticks + BIND_LAG))
        object.__setattr__(p, "_binding", binding)
        ControlRigSequencerLibrary.rigs.append(p)
        return p

    @staticmethod
    def get_control_rig_world_transform(level_sequence, control_rig, control_name, frame, time_unit=None):
        if not control_rig.bound():
            return core.Transform(location=core.Vector(0.0, 0.0, 0.0), rotation=core.Rotator())
        b = control_rig._bones()[control_rig._controls[str(control_name)]]
        return core.Transform(location=core.Vector(b[0], b[1], b[2] + 2.0), rotation=core.Rotator())

    @staticmethod
    def set_control_rig_world_transform(level_sequence, control_rig, control_name, frame, world_transform,
                                        time_unit=None, set_key=True):
        name = str(control_name)
        if not control_rig.bound():
            return
        bones = control_rig._bones()
        bone = control_rig._controls[name]
        cur = bones[bone]
        t = world_transform.translation
        d = [(t.x - cur[0]) * control_rig._gain, (t.y - cur[1]) * control_rig._gain,
             (t.z - 2.0 - cur[2]) * control_rig._gain]
        movers = [b for b in bones if b not in IK] if bone == "pelvis" else [bone]
        control_rig.pending.append((core._fake().ticks + LAG, {b: d for b in movers}))
        control_rig.writes.append((name, int(getattr(frame, "value", frame))))


def install(fake):
    ControlRigSequencerLibrary.rigs = []
    ControlRigSequencerLibrary.classes = {}
    fake.ControlRigSequencerLibrary = ControlRigSequencerLibrary
    fake._classes["ControlRigSequencerLibrary"] = ControlRigSequencerLibrary

    def settle(_dt):
        for p in ControlRigSequencerLibrary.rigs:
            r = p.get_editor_property("control_rig")
            if isinstance(r, FakeControlRig):
                r._settle()
    fake.register_slate_post_tick_callback(settle)

    def rig(label, controls: dict, gain: float = 0.8):
        a = fake.actor(label)
        r = FakeControlRig(a, controls, gain)
        p = _Proxy("proxy", proxy=_Binding(label), control_rig=r)
        ControlRigSequencerLibrary.rigs.append(p)
        return r
    fake.rig = rig
