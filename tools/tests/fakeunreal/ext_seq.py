"""WP8's fake Sequencer for the shared fake engine: level sequences with bindings (possessables, component bindings,
spawnables with their spawn track), master and binding tracks, sections and scripting channels whose keys are kept in
TICKS (as the engine keeps them) and converted at the scripting boundary, parameter sections (material / collection,
ticks), marked frames, the LevelSequenceEditorBlueprintLibrary's open/close state, and ControlRig's world-transform
evaluation. Faithful to the units and names in docs/unreal/sequencer.md API_NOTES; evaluation uses the pure
predictor (seqcore._curves.evaluate), not the engine's exact tangents.

    seq = ue.LevelSequence("SEQ_A")              # or through seq.add / AssetTools
    install(fake) is called by fakeunreal.install() for every test.
"""
from __future__ import annotations

import copy
import itertools

from . import core

_GUIDS = itertools.count(1)


def _curves():
    from filmtools.unreal import seq_spec
    return seq_spec.core().curves


class _ClassRef:
    def __init__(self, name: str):
        self._n = name

    def get_name(self) -> str:
        return self._n

    def __eq__(self, o):
        return isinstance(o, _ClassRef) and o._n == self._n

    def __hash__(self):
        return hash(self._n)


class Guid:
    def __init__(self, n: int | None = None):
        self.n = next(_GUIDS) if n is None else n

    def export_text(self) -> str:
        return f"{self.n:032X}"

    def __eq__(self, o):
        return isinstance(o, Guid) and o.n == self.n

    def __hash__(self):
        return hash(self.n)


def _clone(obj):
    """A copy of a fake Object with its own editor-property dict (copy.copy would share it)."""
    c = copy.copy(obj)
    object.__setattr__(c, "_props", dict(obj._props))
    return c


def _enum(enum: str, name: str):
    return getattr(getattr(core.FAKE, enum), name)


_INTERP = {"AUTO": ("RCIM_CUBIC", "RCTM_AUTO"), "SMART_AUTO": ("RCIM_CUBIC", "RCTM_SMART_AUTO"),
           "USER": ("RCIM_CUBIC", "RCTM_USER"), "BREAK": ("RCIM_CUBIC", "RCTM_BREAK"),
           "LINEAR": ("RCIM_LINEAR", "RCTM_AUTO"), "CONSTANT": ("RCIM_CONSTANT", "RCTM_AUTO")}


# --- channels and keys ------------------------------------------------------------------------------------------------

class FakeKey:
    def __init__(self, ch, tick: int, value, interp: str = "AUTO"):
        self.ch, self.tick, self.value = ch, tick, value
        self.interp, self.tangent = _INTERP[interp]
        self.arrive = self.leave = 0.0
        self.arrive_w = self.leave_w = 0.0

    def get_time(self, time_unit=None):
        tpf = self.ch.seq_tpf()
        if time_unit is not None and getattr(time_unit, "name", "") == "TICK_RESOLUTION":
            return core.FrameTime(core.FrameNumber(self.tick), 0.0)
        f = self.tick / tpf
        whole = int(f // 1)
        return core.FrameTime(core.FrameNumber(whole), f - whole)

    def get_value(self):
        return self.value

    def set_value(self, v):
        self.value = v

    def get_interpolation_mode(self):
        return _enum("RichCurveInterpMode", self.interp)

    def get_tangent_mode(self):
        return _enum("RichCurveTangentMode", self.tangent)

    def set_interpolation_mode(self, m):
        self.interp = m.name

    def set_tangent_mode(self, m):
        self.tangent = m.name

    def get_arrive_tangent(self):
        return self.arrive

    def get_leave_tangent(self):
        return self.leave

    def set_arrive_tangent(self, v):
        self.arrive = float(v)

    def set_leave_tangent(self, v):
        self.leave = float(v)

    def set_tangent_weight_mode(self, m):
        self.weight_mode = m

    def set_arrive_tangent_weight(self, v):
        self.arrive_w = float(v)

    def set_leave_tangent_weight(self, v):
        self.leave_w = float(v)


class FakeChannel:
    """A scripting channel: kind double/float/bool/int/byte/string; keys in ticks."""

    def __init__(self, name: str, kind: str, section):
        self.channel_name, self.kind, self.section = name, kind, section
        self.keys: list = []
        self.default = None

    def seq_tpf(self) -> float:
        s = self.section.track.seq
        t, d = s.tick_resolution, s.display_rate
        return (t.numerator / t.denominator) / (d.numerator / d.denominator)

    def get_name(self):
        return self.channel_name

    def add_key(self, time, value, sub_frame: float = 0.0, time_unit=None, interpolation=None):
        if self.kind in ("bool",) and not isinstance(value, bool):
            raise TypeError(f"bool channel add_key got {type(value).__name__}")
        if interpolation is not None and self.kind not in ("double", "float", "byte"):
            raise TypeError(f"{self.kind} channel add_key takes no interpolation")
        unit = getattr(time_unit, "name", "DISPLAY_RATE")
        tick = time.value if unit == "TICK_RESOLUTION" else int(round((time.value + sub_frame) * self.seq_tpf()))
        k = FakeKey(self, tick, value, getattr(interpolation, "name", "AUTO") if self.kind in ("double", "float")
                    else "CONSTANT")
        if not self.keys or self.keys[-1].tick < tick:  # the usual case: keys arrive in order
            self.keys.append(k)
        else:
            import bisect
            ticks = [x.tick for x in self.keys]
            i = bisect.bisect_left(ticks, tick)
            if i < len(ticks) and ticks[i] == tick:
                self.keys[i] = k
            else:
                self.keys.insert(i, k)
        seq = self.section.track.seq
        object.__setattr__(seq, "key_writes", seq.key_writes + 1)
        return k

    def get_keys(self):
        return list(self.keys)

    def get_num_keys(self):
        return len(self.keys)

    def remove_key(self, key):
        self.keys = [k for k in self.keys if k is not key]

    def set_default(self, v):
        self.default = v

    def get_default(self):
        return self.default

    def has_default(self):
        return self.default is not None

    def remove_default(self):
        self.default = None

    def canonical(self) -> list:
        tpf = self.seq_tpf()
        out = []
        for k in self.keys:
            how = _curves().interp_from_engine(k.interp, k.tangent)
            key = [k.tick / tpf, k.value, how]
            if how in ("user", "break"):
                key.append({"arrive": k.arrive * tpf, "leave": k.leave * tpf})
            out.append(key)
        return out

    def evaluate_keys(self, rng, frame_rate):
        ks = self.canonical()
        return [_curves().evaluate(ks, f, self.default if self.default is not None else 0.0)
                for f in range(rng.start, rng.start + rng.duration)]


# --- sections ---------------------------------------------------------------------------------------------------------

_CHANNELS = {
    "MovieScene3DTransformTrack": [(n, "double") for n in ("Location.X", "Location.Y", "Location.Z", "Rotation.X",
                                                           "Rotation.Y", "Rotation.Z", "Scale.X", "Scale.Y", "Scale.Z")],
    "MovieSceneFloatTrack": [("Float", "float")], "MovieSceneDoubleTrack": [("Double", "double")],
    "MovieSceneBoolTrack": [("Bool", "bool")], "MovieSceneVisibilityTrack": [("Bool", "bool")],
    "MovieSceneSpawnTrack": [("Bool", "bool")], "MovieSceneByteTrack": [("Byte", "byte")],
    "MovieSceneIntegerTrack": [("Integer", "int")], "MovieSceneStringTrack": [("String", "string")],
    "MovieSceneColorTrack": [(f"Color.{c}", "float") for c in "RGBA"],
    "MovieSceneSkeletalAnimationTrack": [("Weight", "float")],
    "MovieSceneAudioTrack": [("Volume", "float"), ("Pitch", "float")],
    "MovieSceneFadeTrack": [("Fade", "float")],
}


class Struct(core.Object):
    """A struct value (params, parameters, infos): editor properties, copied on get as the engine does."""


class FakeSection(core.Object):
    def __init__(self, track):
        super().__init__("Section")
        object.__setattr__(self, "track", track)
        object.__setattr__(self, "start", track.seq.ms.playback[0])  # ticks, as the engine keeps them
        object.__setattr__(self, "end", track.seq.ms.playback[1])
        object.__setattr__(self, "bounded", [True, True])
        object.__setattr__(self, "row", 0)
        cls = track.cls
        if cls == "MovieSceneDoubleVectorTrack":
            spec = [(f"Vector.{c}", "double") for c in "XYZW"[:track.num_channels]]
        else:
            spec = _CHANNELS.get(cls, [])
        object.__setattr__(self, "channels", [FakeChannel(n, k, self) for n, k in spec])
        object.__setattr__(self, "ease", [0, 0])
        object.__setattr__(self, "roll", [0, 0])
        if cls == "MovieSceneSkeletalAnimationTrack":
            self._props["params"] = Struct("Params", animation=None, start_frame_offset=core.FrameNumber(0),
                                           play_rate=TimeWarp(1.0), slot_name="DefaultSlot", reverse=False)
            self.channels[0].default = 1.0
        if cls in ("MovieSceneSubTrack", "MovieSceneCinematicShotTrack"):
            self._props["parameters"] = Struct("Parameters", start_frame_offset=core.FrameNumber(0),
                                               time_scale=TimeWarp(1.0))
        if cls == "MovieSceneFadeTrack":
            self._props["fade_color"] = core.LinearColor(0, 0, 0, 1)
            self._props["fade_audio"] = False

    def get_editor_property(self, name):
        v = super().get_editor_property(name)
        return _clone(v) if isinstance(v, Struct) else v

    # range
    def _t(self, f):
        return int(round(int(f) * self.track.seq._tpf()))

    def _f(self, t):
        return int(t // self.track.seq._tpf())  # whole display frames, floored

    def set_range(self, a, b):
        object.__setattr__(self, "start", self._t(a))
        object.__setattr__(self, "end", self._t(b))
        self.bounded[:] = [True, True]

    def set_start_frame(self, a):
        object.__setattr__(self, "start", self._t(a))

    def set_end_frame(self, b):
        object.__setattr__(self, "end", self._t(b))

    def set_start_frame_bounded(self, v):
        self.bounded[0] = bool(v)

    def set_end_frame_bounded(self, v):
        self.bounded[1] = bool(v)

    def has_start_frame(self):
        return self.bounded[0]

    def has_end_frame(self):
        return self.bounded[1]

    def get_start_frame(self):
        return self._f(self.start)

    def get_end_frame(self):
        return self._f(self.end)

    def set_row_index(self, r):
        object.__setattr__(self, "row", int(r))

    def get_row_index(self):
        return self.row

    # channels
    def get_all_channels(self):
        return list(self.channels)

    def get_channel(self, name):
        return next((c for c in self.channels if c.channel_name == name), None)

    def get_channels_by_type(self, cls):
        return list(self.channels)

    # easing / roll (ticks)
    def set_ease_in_duration(self, v):
        self.ease[0] = int(v)

    def set_ease_out_duration(self, v):
        self.ease[1] = int(v)

    def get_ease_in_duration(self):
        return self.ease[0]

    def get_ease_out_duration(self):
        return self.ease[1]

    def set_pre_roll_frames(self, v):
        if not isinstance(v, int):
            raise TypeError("set_pre_roll_frames takes an int (ticks)")
        self.roll[0] = v

    def set_post_roll_frames(self, v):
        self.roll[1] = int(v)

    def get_pre_roll_frames(self):
        return self.roll[0]

    def get_post_roll_frames(self):
        return self.roll[1]

    # audio
    def set_sound(self, s):
        self._props["sound"] = s

    def get_sound(self):
        return self._props.get("sound")

    def set_start_offset(self, fn):
        self._props["start_frame_offset"] = fn

    def get_start_offset(self):
        return self._props.get("start_frame_offset", core.FrameNumber(0))

    # camera cut
    def set_camera_binding_id(self, bid):
        self._props["camera"] = bid

    def get_camera_binding_id(self):
        return self._props["camera"]

    # level visibility
    def set_visibility(self, v):
        self._props["visibility"] = v

    def get_visibility(self):
        return self._props.get("visibility", _enum("LevelVisibility", "VISIBLE"))

    def set_level_names(self, names):
        self._props["levels"] = [str(n) for n in names]

    def get_level_names(self):
        return list(self._props.get("levels", []))

    # sub / shot
    def set_sequence(self, s):
        self._props["sequence"] = s

    def get_sequence(self):
        return self._props.get("sequence")

    def set_shot_display_name(self, n):
        self._props["shot_name"] = n

    def get_shot_display_name(self):
        s = self._props.get("sequence")
        return self._props.get("shot_name") or (s.get_name() if s else "")

    # parameter sections (material track: MaterialParameterInfo; collection track: FName); times in TICKS
    def _param_name(self, p):
        return p if isinstance(p, str) else p.get_editor_property("name")

    def _param_channel(self, name, kind="float"):
        ch = self.get_channel(name)
        if ch is None:
            ch = FakeChannel(name, kind, self)
            self.channels.append(ch)
        return ch

    def add_scalar_parameter_key(self, param, time, value, *args, default_interpolation=None):
        if self.track.cls == "MovieSceneComponentMaterialTrack" and len(args) < 2:
            raise TypeError("add_scalar_parameter_key(info, time, value, layer_name, asset_name, ...)")
        u = _enum("MovieSceneTimeUnit", "TICK_RESOLUTION")
        self._param_channel(self._param_name(param)).add_key(time, float(value), 0.0, u, default_interpolation)

    def add_color_parameter_key(self, param, time, value, *args, default_interpolation=None):
        u = _enum("MovieSceneTimeUnit", "TICK_RESOLUTION")
        n = self._param_name(param)
        for c in "RGBA":
            self._param_channel(n + c).add_key(time, float(getattr(value, c.lower())), 0.0, u, default_interpolation)

    def remove_scalar_parameter(self, param):
        n = self._param_name(param)
        before = len(self.channels)
        object.__setattr__(self, "channels", [c for c in self.channels if c.channel_name != n])
        return len(self.channels) != before

    def remove_color_parameter(self, param):
        n = self._param_name(param)
        before = len(self.channels)
        object.__setattr__(self, "channels", [c for c in self.channels if c.channel_name not in
                                              {n + x for x in "RGBA"}])
        return len(self.channels) != before


class TimeWarp:
    def __init__(self, rate: float = 1.0):
        self.rate = float(rate)

    def to_fixed_play_rate(self):
        return self.rate


class MovieSceneTimeWarpExtensions(core.Object):
    @staticmethod
    def make_time_warp(rate):
        return TimeWarp(rate)


# --- tracks -----------------------------------------------------------------------------------------------------------

class FakeTrack(core.Object):
    def __init__(self, seq, cls: str):
        super().__init__(cls)
        object.__setattr__(self, "seq", seq)
        object.__setattr__(self, "cls", cls)
        object.__setattr__(self, "sections", [])
        object.__setattr__(self, "num_channels", 3)
        object.__setattr__(self, "prop", ("", ""))
        object.__setattr__(self, "display", "")
        if cls == "MovieSceneComponentMaterialTrack":
            self._props["material_info"] = Struct("Info", material_slot_index=0, material_slot_name="",
                                                  material_type=_enum("ComponentMaterialType", "EMPTY"))

    def get_class(self):
        return _ClassRef(self.cls)

    def add_section(self):
        s = FakeSection(self)
        self.sections.append(s)
        return s

    def get_sections(self):
        return list(self.sections)

    def remove_section(self, s):
        self.sections.remove(s)

    def set_property_name_and_path(self, name, path):
        object.__setattr__(self, "prop", (str(name), str(path)))

    def get_property_path(self):
        return self.prop[1]

    def get_property_name(self):
        return self.prop[0]

    def set_display_name(self, n):
        object.__setattr__(self, "display", str(n))

    def get_display_name(self):
        return self.display or self.cls.replace("MovieScene", "").replace("Track", "")

    def set_num_channels_used(self, n):
        object.__setattr__(self, "num_channels", int(n))

    def get_material_info(self):
        return _clone(self._props["material_info"])

    def set_material_info(self, info):
        self._props["material_info"] = _clone(info)


class _Owner:
    """Tracks on a sequence or a binding."""

    def _tracks(self) -> list:
        raise NotImplementedError

    def add_track(self, cls):
        t = FakeTrack(self._seq(), cls.__name__)
        self._tracks().append(t)
        return t

    def get_tracks(self):
        return list(self._tracks())

    def find_tracks_by_exact_type(self, cls):
        return [t for t in self._tracks() if t.cls == cls.__name__]

    def find_tracks_by_type(self, cls):
        return self.find_tracks_by_exact_type(cls)

    def remove_track(self, t):
        self._tracks().remove(t)


class BindingData:
    def __init__(self, name, guid, obj_label="", comp="", parent=None, spawn_class=None):
        self.name, self.guid, self.obj_label, self.comp, self.parent = name, guid, obj_label, comp, parent
        self.spawn_class = spawn_class
        self.tracks: list = []


class MovieSceneBindingProxy(_Owner):
    def __init__(self, seq, data: BindingData):
        self.seq, self.data = seq, data

    def _seq(self):
        return self.seq

    def _tracks(self):
        return self.data.tracks

    def __eq__(self, o):
        return isinstance(o, MovieSceneBindingProxy) and o.data.guid == self.data.guid

    def __hash__(self):
        return hash(self.data.guid)

    def is_valid(self):
        return self.data in self.seq.ms.bindings

    def get_id(self):
        return self.data.guid

    def get_display_name(self):
        return core.Text(self.data.name)

    def get_name(self):
        return self.data.name

    def set_display_name(self, n):
        self.data.name = str(n)

    def set_name(self, n):
        self.data.name = str(n)

    def get_parent(self):
        if self.data.parent is None:
            return None
        p = next((b for b in self.seq.ms.bindings if b.guid == self.data.parent), None)
        return MovieSceneBindingProxy(self.seq, p) if p else None

    def set_parent(self, p):
        self.data.parent = p.data.guid

    def get_child_possessables(self):
        return [MovieSceneBindingProxy(self.seq, b) for b in self.seq.ms.bindings if b.parent == self.data.guid]

    def get_possessed_object_class(self):
        if self.data.spawn_class:
            return _ClassRef(self.data.spawn_class)
        obj = self.seq._object(self.data)
        return _ClassRef(type(obj).__name__) if obj is not None else None

    def remove(self):
        self.seq.ms.bindings = [b for b in self.seq.ms.bindings
                                if b is not self.data and b.parent != self.data.guid]


class MovieSceneData:
    """Everything a LevelSequence holds (deep-copied when the asset is duplicated)."""

    def __init__(self):
        # the engine's default is 30 (CVar LevelSequence.DefaultDisplayRate); the fakes agree on 24 (ext_audio's tests)
        self.display_rate = core.FrameRate(24, 1)
        self.tick_resolution = core.FrameRate(24000, 1)
        self.playback = [0, 150 * 1000]  # ticks (150 frames at 24 fps)
        self.bindings: list = []
        self.tracks: list = []
        self.marks: list = []


class _Range:
    def __init__(self, start, duration):
        self.start, self.duration = int(start), int(duration)


class LevelSequence(core.MovieSceneSequence, _Owner):
    def __init__(self, name=None, outer=None, **props):
        ms = props.pop("movie_scene", None)
        super().__init__(name, outer, **props)
        self._props["movie_scene"] = copy.deepcopy(ms) if ms is not None else MovieSceneData()
        object.__setattr__(self, "key_writes", 0)
        if ms is not None:
            for t in self._all_tracks():
                object.__setattr__(t, "seq", self)

    @property
    def ms(self) -> MovieSceneData:
        return self._props["movie_scene"]

    @property
    def display_rate(self):
        return self.ms.display_rate

    @property
    def tick_resolution(self):
        return self.ms.tick_resolution

    @property
    def playback(self):
        return self.ms.playback

    def _all_tracks(self):
        return self.ms.tracks + [t for b in self.ms.bindings for t in b.tracks]

    def _seq(self):
        return self

    def _tracks(self):
        return self.ms.tracks

    def get_class(self):
        return _ClassRef("LevelSequence")

    def get_display_rate(self):
        return self.ms.display_rate

    def set_display_rate(self, r):
        self.ms.display_rate = r

    def get_tick_resolution(self):
        return self.ms.tick_resolution

    def set_tick_resolution(self, r):
        old = self.ms.tick_resolution
        for t in self._all_tracks():
            for s in t.sections:
                for c in s.channels:
                    for k in c.keys:
                        k.tick = int(round(k.tick * (r.numerator / r.denominator) / (old.numerator / old.denominator)))
        k = (r.numerator / r.denominator) / (old.numerator / old.denominator)
        for t in self._all_tracks():
            for s in t.sections:
                object.__setattr__(s, "start", int(round(s.start * k)))
                object.__setattr__(s, "end", int(round(s.end * k)))
                s.ease[:] = [int(round(x * k)) for x in s.ease]
                s.roll[:] = [int(round(x * k)) for x in s.roll]
        self.ms.playback = [int(round(x * k)) for x in self.ms.playback]
        for m in self.ms.marks:
            m.set_editor_property("frame_number", core.FrameNumber(int(round(m.frame_number.value * k))))
        self.ms.tick_resolution = r

    def _tpf(self) -> float:
        t, d = self.ms.tick_resolution, self.ms.display_rate
        return (t.numerator / t.denominator) / (d.numerator / d.denominator)

    def get_playback_start(self):
        return int(round(self.ms.playback[0] / self._tpf()))

    def get_playback_end(self):
        return int(round(self.ms.playback[1] / self._tpf()))

    def set_playback_start(self, v):
        self.ms.playback[0] = int(round(int(v) * self._tpf()))

    def set_playback_end(self, v):
        self.ms.playback[1] = int(round(int(v) * self._tpf()))

    def make_range(self, start, duration):
        return _Range(start, duration)

    # bindings
    def _object(self, data: BindingData):
        if data.spawn_class:
            return None
        try:
            a = core.FAKE.actor(data.obj_label)
        except Exception:
            return None
        if data.comp:
            return next((c for c in a.get_components_by_class(core.ActorComponent) if c.get_name() == data.comp), None)
        return a

    def get_bindings(self):
        return [MovieSceneBindingProxy(self, b) for b in self.ms.bindings]

    def get_possessables(self):
        return self.get_bindings()

    def get_spawnables(self):
        return []

    def add_possessable(self, obj):
        if isinstance(obj, core.Actor):
            d = BindingData(obj.get_actor_label(), Guid(), obj.get_actor_label())
        else:
            owner = obj.get_owner()
            label = owner.get_actor_label()
            parent = next((b for b in self.ms.bindings if b.obj_label == label and not b.comp and b.parent is None),
                          None)
            if parent is None:
                parent = BindingData(label, Guid(), label)
                self.ms.bindings.append(parent)
            d = BindingData(obj.get_name(), Guid(), label, obj.get_name(), parent.guid)
        self.ms.bindings.append(d)
        return MovieSceneBindingProxy(self, d)

    def _spawnable(self, name, cls_name):
        d = BindingData(name, Guid(), spawn_class=cls_name)
        self.ms.bindings.append(d)
        b = MovieSceneBindingProxy(self, d)
        t = b.add_track(core.FAKE.MovieSceneSpawnTrack)
        s = t.add_section()
        s.set_start_frame_bounded(False)
        s.set_end_frame_bounded(False)
        s.channels[0].default = True
        return b

    def add_spawnable_from_class(self, cls):
        return self._spawnable(cls.__name__, cls.__name__)

    def add_spawnable_from_instance(self, a):
        return self._spawnable(a.get_actor_label(), type(a).__name__)

    def get_binding_id(self, proxy):
        bid = core.Object("MovieSceneObjectBindingID")
        bid.set_editor_property("guid", proxy.data.guid)
        return bid

    def locate_bound_objects(self, proxy, context):
        o = self._object(proxy.data)
        return [o] if o is not None else []

    # markers (display-rate variants)
    def get_marked_frames_from_sequence(self, time_unit=None):
        out = []
        for m in self.ms.marks:  # kept in ticks
            c = _clone(m)
            c.set_editor_property("frame_number", core.FrameNumber(int(round(m.frame_number.value / self._tpf()))))
            out.append(c)
        return out

    def add_marked_frame_to_sequence(self, mf, time_unit=None):
        c = _clone(mf)
        c.set_editor_property("frame_number", core.FrameNumber(int(round(mf.frame_number.value * self._tpf()))))
        self.ms.marks.append(c)
        return len(self.ms.marks) - 1

    def delete_marked_frames(self):
        self.ms.marks = []


class MovieSceneMarkedFrame(core.Object):
    pass


class MaterialParameterInfo(core.Object):
    pass


class LevelSequenceEditorBlueprintLibrary(core.Object):
    current = None

    @staticmethod
    def open_level_sequence(s):
        LevelSequenceEditorBlueprintLibrary.current = s
        return True

    @staticmethod
    def close_level_sequence():
        LevelSequenceEditorBlueprintLibrary.current = None

    @staticmethod
    def get_current_level_sequence():
        return LevelSequenceEditorBlueprintLibrary.current

    @staticmethod
    def refresh_current_level_sequence():
        core.FAKE.calls.append(("LSE.refresh", (), {}))

    @staticmethod
    def get_bound_objects(bid):
        return []


class LevelSequenceEditorSubsystem(core.Object):
    def replace_binding_with_actors(self, actors, binding):
        if LevelSequenceEditorBlueprintLibrary.current is not binding.seq:
            raise RuntimeError("replace_binding_with_actors needs the sequence open in Sequencer")
        binding.data.obj_label = actors[0].get_actor_label()


class _XQuat:
    def __init__(self, rot):
        self._r = rot

    def rotator(self):
        return self._r


class _Xform:
    def __init__(self, loc, rot):
        self.translation, self.rotation = loc, _XQuat(rot)


class ControlRigSequencerLibrary(core.Object):
    """UControlRigSequencerEditorLibrary, by its ScriptName (Python sees only this name)."""
    @staticmethod
    def get_actor_world_transforms(level_sequence, a, frames, time_unit=None):
        seq = LevelSequenceEditorBlueprintLibrary.current  # the engine evaluates the OPEN sequence
        if seq is None:
            raise RuntimeError("no level sequence open (ControlRigSequencerLibrary needs one)")
        label = a.get_actor_label()
        b = next((x for x in seq.ms.bindings if x.obj_label == label and not x.comp), None)
        tr = None
        if b is not None:
            tr = next((t for t in b.tracks if t.cls == "MovieScene3DTransformTrack"), None)
        p0, r0 = a.get_actor_location(), a.get_actor_rotation()
        base = [p0.x, p0.y, p0.z, r0.roll, r0.pitch, r0.yaw]
        out = []
        for f in frames:
            vals = list(base)
            if tr is not None and tr.sections:
                for i, ch in enumerate(tr.sections[0].channels[:6]):
                    if ch.keys or ch.default is not None:
                        vals[i] = _curves().evaluate(ch.canonical(), f.value, ch.default)
            out.append(_Xform(core.Vector(*vals[:3]), core.Rotator(roll=vals[3], pitch=vals[4], yaw=vals[5])))
        return out


TRACK_CLASSES = ["MovieScene3DTransformTrack", "MovieSceneFloatTrack", "MovieSceneDoubleTrack", "MovieSceneBoolTrack",
                 "MovieSceneByteTrack", "MovieSceneEnumTrack", "MovieSceneIntegerTrack", "MovieSceneStringTrack",
                 "MovieSceneVisibilityTrack", "MovieSceneSpawnTrack", "MovieSceneColorTrack",
                 "MovieSceneDoubleVectorTrack", "MovieSceneFloatVectorTrack", "MovieSceneSkeletalAnimationTrack",
                 "MovieSceneAudioTrack", "MovieSceneCameraCutTrack", "MovieSceneFadeTrack",
                 "MovieSceneLevelVisibilityTrack", "MovieSceneComponentMaterialTrack",
                 "MovieSceneMaterialParameterCollectionTrack", "MovieSceneEventTrack", "MovieSceneCinematicShotTrack",
                 "MovieSceneSubTrack", "MovieSceneCameraShakeTrack"]


def install(fake) -> None:
    for name in TRACK_CLASSES:
        setattr(fake, name, type(name, (), {}))  # class tokens: add_track(cls) makes a FakeTrack named after it
    for cls in (LevelSequence, MovieSceneMarkedFrame, MaterialParameterInfo, LevelSequenceEditorBlueprintLibrary,
                LevelSequenceEditorSubsystem, MovieSceneTimeWarpExtensions):
        setattr(fake, cls.__name__, cls)
    LevelSequenceEditorBlueprintLibrary.current = None
    # another area's fake may own ControlRigSequencerLibrary (ext_pose: rigs): add the Sequencer evaluation to it
    crl = fake.__dict__.get("ControlRigSequencerLibrary")
    if isinstance(crl, type) and crl is not ControlRigSequencerLibrary:
        if not hasattr(crl, "get_actor_world_transforms") or isinstance(getattr(crl, "get_actor_world_transforms"),
                                                                      core.Stub):
            crl.get_actor_world_transforms = staticmethod(ControlRigSequencerLibrary.get_actor_world_transforms)
    else:
        fake.ControlRigSequencerLibrary = ControlRigSequencerLibrary
