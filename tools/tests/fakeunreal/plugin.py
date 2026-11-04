"""pytest fixtures for the fake (imported by tools/tests/conftest.py): `ue` is a fresh fake engine per test, `fmb`
the bridge's ops package imported against it."""
import pytest

from . import core


@pytest.fixture
def ue(tmp_path):
    fake = core.install(str(tmp_path / "project"))
    yield fake
    core.uninstall()


@pytest.fixture
def fmb(ue):
    return core.load_fmbridge()
