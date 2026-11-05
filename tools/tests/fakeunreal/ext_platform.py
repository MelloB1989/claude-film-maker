"""WP1 (editor., bridge., jobs.): the console behaves like the engine's for console variables: "name value" sets
`fake.cvars[name]` (for a variable that exists), get_console_variable_string_value reads it back ("" for an unknown
name, as the engine does); dirty packages come from `fake.dirty = {"maps": [...], "content": [...]}`."""
from __future__ import annotations

from . import core

_ORIG = core.SystemLibrary.__dict__["execute_console_command"]  # the core fake's, before any extension


class _Package:
    def __init__(self, name):
        self._name = name

    def get_name(self):
        return self._name


def _execute_console_command(world_context_object, command, specific_player=None):
    _ORIG.__func__(world_context_object, command, specific_player)
    fake = core._fake()
    parts = str(command).split()
    if len(parts) == 2 and "." in parts[0] and parts[0] in fake.cvars:
        fake.cvars[parts[0]] = parts[1]


def _get_console_variable_string_value(name):
    cvars = core._fake().cvars
    return str(cvars[name]) if name in cvars else ""


class EditorLoadingAndSavingUtils(core.Object):
    @staticmethod
    def get_dirty_map_packages():
        return [_Package(n) for n in core._fake().dirty["maps"]]

    @staticmethod
    def get_dirty_content_packages():
        return [_Package(n) for n in core._fake().dirty["content"]]


class _PerformanceSettings(core.Object):
    """UEditorPerformanceSettings' defaults object: not exposed to Python by name, found by path (as on a box)."""


PERF_SETTINGS = "/Script/UnrealEd.Default__EditorPerformanceSettings"


def install(fake):
    core.SystemLibrary.execute_console_command = staticmethod(_execute_console_command)
    core.SystemLibrary.get_console_variable_string_value = staticmethod(_get_console_variable_string_value)
    fake.dirty = {"maps": [], "content": []}
    fake.cvars.setdefault("t.MaxFPS", "0")
    fake.cvars.setdefault("r.RayTracing", "1")
    fake.EditorLoadingAndSavingUtils = EditorLoadingAndSavingUtils
    fake.assets[core._package(PERF_SETTINGS)] = _PerformanceSettings("Default__EditorPerformanceSettings")
