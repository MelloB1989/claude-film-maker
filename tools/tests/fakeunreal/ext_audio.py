"""WP12's fakes: SoundWaves that know their WAV's duration, and level sequences with audio tracks and sections (the
part of Sequencer the audio ops use). Sequence methods are added only where WP8's own fake (ext_seq) has not
defined them, so the two can live together."""
from __future__ import annotations

import wave

from . import core


class SoundWave(core.SoundWave):
    """duration (s) from the imported file's WAV header, unless set."""

    def get_editor_property(self, name: str):
        if name == "duration" and "duration" not in self._props:
            src = self._props.get("source_file")
            try:
                with wave.open(src, "rb") as w:
                    return w.getnframes() / float(w.getframerate())
            except Exception:
                return 0.0
        return super().get_editor_property(name)


_SERIAL = {"n": 0}


class _Channel(core.Object):
    """As the engine: channel_name is the channel's ("Volume"); get_name() is the scripting object's, unique per
    get_all_channels() call ("Volume_3"), so code must not match on it."""

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props["channel_name"] = core.Name(name)
        object.__setattr__(self, "_default", None)
        object.__setattr__(self, "_keys", [])

    def add_key(self, time, new_value, sub_frame=0.0, time_unit=None, interpolation=None):
        k = _Key(time, float(new_value))
        self._keys.append(k)
        return k

    def get_keys(self):
        return sorted(self._keys, key=lambda k: k._time.value)

    def get_name(self):
        _SERIAL["n"] += 1
        return f"{self._name}_{_SERIAL['n']}"

    def set_default(self, v):
        object.__setattr__(self, "_default", float(v))

    def get_default(self):
        return self._default if self._default is not None else 0.0

    def has_default(self):
        return self._default is not None


class _Key:
    def __init__(self, time, value):
        self._time, self._value = time, value

    def get_time(self, time_unit=None):
        return core.FrameTime(self._time)

    def get_value(self):
        return self._value


class MovieSceneAudioSection(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        for k, v in (("_range", (0, 0)), ("_row", 0), ("_sound", None), ("_offset", core.FrameNumber(0)),
                     ("_channels", [_Channel("Volume"), _Channel("Pitch")])):
            object.__setattr__(self, k, v)

    def set_range(self, a, b):
        object.__setattr__(self, "_range", (int(a), int(b)))

    def get_start_frame(self):
        return self._range[0]

    def get_end_frame(self):
        return self._range[1]

    def set_row_index(self, r):
        object.__setattr__(self, "_row", int(r))

    def get_row_index(self):
        return self._row

    def set_sound(self, s):
        object.__setattr__(self, "_sound", s)

    def get_sound(self):
        return self._sound

    def set_start_offset(self, f):
        object.__setattr__(self, "_offset", f)

    def get_start_offset(self):
        return self._offset

    def get_all_channels(self):
        return list(self._channels)


class MovieSceneAudioTrack(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_sections", [])
        object.__setattr__(self, "_display", "Audio")

    def set_display_name(self, n):
        object.__setattr__(self, "_display", str(n))

    def get_display_name(self):
        return core.Text(self._display)

    def add_section(self):
        s = MovieSceneAudioSection("MovieSceneAudioSection", self)
        self._sections.append(s)
        return s

    def get_sections(self):
        return list(self._sections)

    def remove_section(self, s):
        self._sections.remove(s)


def _st(self, k, default):
    if k not in self.__dict__:
        object.__setattr__(self, k, default() if callable(default) else default)
    return self.__dict__[k]


def _tracks(self):
    return _st(self, "_tracks", list)


SEQ_METHODS = {
    "get_display_rate": lambda self: core.FrameRate(int(_st(self, "_fps", 24)), 1),
    "get_tick_resolution": lambda self: core.FrameRate(24000, 1),
    "find_tracks_by_type": lambda self, cls: [t for t in _tracks(self) if isinstance(t, cls)],
    "get_tracks": lambda self: list(_tracks(self)),
    "add_track": lambda self, cls: (_tracks(self).append(cls(cls.__name__, self)) or _tracks(self)[-1]),
    "remove_track": lambda self, t: (_tracks(self).remove(t) or True),
    "get_playback_start": lambda self: _st(self, "_pb", lambda: [0, 120])[0],
    "get_playback_end": lambda self: _st(self, "_pb", lambda: [0, 120])[1],
    "set_playback_end": lambda self, f: _st(self, "_pb", lambda: [0, 120]).__setitem__(1, int(f)),
}


def install(fake) -> None:
    fake.SoundWave = SoundWave
    fake._classes["SoundWave"] = SoundWave
    for n, cls in (("MovieSceneAudioTrack", MovieSceneAudioTrack), ("MovieSceneAudioSection", MovieSceneAudioSection)):
        if n not in fake._classes or not hasattr(fake._classes[n], "add_section" if "Track" in n else "set_sound"):
            setattr(fake, n, cls)
            fake._classes[n] = cls
    seq = fake.LevelSequence
    for name, fn in SEQ_METHODS.items():
        if name not in vars(seq) and not any(name in vars(b) for b in seq.__mro__[1:] if b is not core.Object):
            setattr(seq, name, fn)
