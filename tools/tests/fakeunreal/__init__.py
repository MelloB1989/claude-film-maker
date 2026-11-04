"""A fake `unreal` module for the bridge's unit tests (no engine): see README.md here.

    def test_spawn(ue):                       # the `ue` fixture: a fresh fake in sys.modules["unreal"]
        ue.add_asset("/Game/M/SM_Box", "StaticMesh")
        res = run_op("level.spawn", label="Box", asset="/Game/M/SM_Box", loc=[0, 0, 50])
        assert ue.actor("Box").get_actor_location().z == 50
"""
from .core import (FakeUnreal, Stub, EnumValue, install, uninstall, load_fmbridge, drive, run_op)  # noqa: F401
