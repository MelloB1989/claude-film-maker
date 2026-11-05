"""fab.* against the fake engine: sign-in state without ever returning a token, the library request, Megascans
and generic downloads on disk, add from a signed URL (download faked), and the shim's pure parts."""
from __future__ import annotations

import base64
import json
import zipfile

import pytest

from fakeunreal import run_op

TOKEN = "h." + base64.urlsafe_b64encode(json.dumps({"sub": "acc123"}).encode()).decode().rstrip("=") + ".sig"


@pytest.fixture
def fab(ue):
    """A Fab plugin whose sign-in completes after `ticks` polls."""
    state = {"token": "", "calls": [], "after": 0}

    class FabBrowserApi(ue.Object):
        def call_method(self, name, args=(), kwargs=None):
            state["calls"].append((name, args))
            if name == "GetAuthToken":
                if state["after"] > 0:
                    state["after"] -= 1
                    if state["after"] == 0:
                        state["token"] = TOKEN
                return state["token"]
            return None

    ue.FabBrowserApi = FabBrowserApi
    ue._classes["FabBrowserApi"] = FabBrowserApi
    ue.FabScript = None  # the reflection plugin is not installed (the fake would invent any class)
    return state


def _err(fn, **kw):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op(fn, **kw)
    return e.value


def test_status_never_returns_the_token(ue, fab):
    s = run_op("fab.status")
    assert s["plugin"] and s["signed_in"] is False and "fab.login" in s["next"]
    fab["token"] = TOKEN
    s = run_op("fab.status")
    assert s["signed_in"] is True and TOKEN not in json.dumps(s)


def test_login_waits_for_the_saved_sign_in(ue, fab):
    fab["after"] = 3
    r = run_op("fab.login")
    assert r["signed_in"] and r["method"] == "persist" and r["changed"]
    assert ("OpenInNewTab", ("",)) in fab["calls"]
    assert run_op("fab.login")["changed"] is False
    assert TOKEN not in json.dumps(r)


def test_login_portal_runs_fab_login_never_logout(ue, fab):
    r = run_op("fab.login", portal=True, timeout_s=0.0)
    assert r["signed_in"] is False and "device code" in r["hint"]
    assert any("Fab.Login" in str(a) for a, _ in ue.called("SystemLibrary.execute_console_command")) or \
        any("Fab.Login" in c for c in ue.console)
    assert not any("Logout" in c or "SetEnvironment" in c for c in ue.console)


def test_library_uses_the_account_from_the_token(ue, fab, monkeypatch):
    from fmbridge.ops import fab as F
    fab["token"] = TOKEN
    seen = []

    def fake_get(url, token=""):
        seen.append((url, token == TOKEN))
        return {"results": [{"title": "Oak Chair", "assetId": "a1", "listingType": "3d-model", "images": [{"url": "i"}]},
                            {"title": "Mossy Rock", "assetId": "a2"}], "cursors": {}}
    monkeypatch.setattr(F, "_get_json", fake_get)
    r = run_op("fab.library", query="chair")
    assert [i["asset_id"] for i in r["items"]] == ["a1"] and r["items"][0]["image"] == "i"
    assert seen[0][0].endswith("/e/accounts/acc123/ue/library?count=100") and seen[0][1]
    assert TOKEN not in json.dumps(r)


class _FabEdge:
    """fab.com as the live box saw it (day 1): the private /e/ API answers on the plugin's host, https://fab.com
    (UFabSettings::GetUrlFromEnvironment), and refuses www.fab.com and Python's default User-Agent with 403."""

    def __init__(self, pages):
        self.pages, self.seen = list(pages), []

    def __call__(self, req, timeout=None):
        import io
        import urllib.error
        url, h = req.full_url, {k.lower(): v for k, v in req.header_items()}
        self.seen.append((url, h))
        if not url.startswith("https://fab.com/") or "python-urllib" in h.get("user-agent", "python-urllib").lower():
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b"forbidden"))
        assert h.get("authorization") == f"Bearer {TOKEN}" and h.get("accept") == "application/json"
        body = json.dumps(self.pages.pop(0)).encode()

        class R(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(body)


def test_library_asks_the_plugins_host_with_its_headers(ue, fab, monkeypatch):
    """Day 1: www.fab.com + Python's UA got HTTP 403; the plugin asks https://fab.com (FabMyFolderIntegration.cpp
    :66-71) with accept + Bearer and the engine's User-Agent, and quotes the cursor."""
    import urllib.request
    fab["token"] = TOKEN
    edge = _FabEdge([{"results": [{"title": "Oak Chair", "assetId": "a1"}], "cursors": {"next": "c2"}},
                     {"results": [{"title": "Mossy Rock", "assetId": "a2"}], "cursors": {}}])
    monkeypatch.setattr(urllib.request, "urlopen", edge)
    r = run_op("fab.library")
    assert [i["asset_id"] for i in r["items"]] == ["a1", "a2"]
    assert edge.seen[0][0] == "https://fab.com/e/accounts/acc123/ue/library?count=100"
    assert edge.seen[1][0].endswith("&cursor=%22c2%22")
    assert edge.seen[0][1]["user-agent"].startswith("Fake/")
    assert TOKEN not in json.dumps(r)


def test_library_403_says_why(ue, fab, monkeypatch):
    import urllib.request
    from fmbridge.ops import fab as F
    fab["token"] = TOKEN
    monkeypatch.setattr(F, "_base_url", lambda: "https://www.fab.com")  # the old host
    monkeypatch.setattr(urllib.request, "urlopen", _FabEdge([]))
    e = _err("fab.library")
    assert e.code == "engine" and "403" in str(e) and "fab.login" in e.hint and TOKEN not in str(e)


def test_host_follows_fab_settings(ue, fab):
    from fmbridge.ops import fab as F
    s = ue.get_default_object(ue.load_class(None, "/Script/Fab.FabSettings"))
    assert F._base_url() == "https://fab.com"
    s.set_editor_property("environment", "FabEnvironment.TEST")
    assert F._base_url() == "https://fab.daec.live.use1a.on.epicgames.com"
    s.set_editor_property("environment", "FabEnvironment.CUSTOM_URL")
    s.set_editor_property("custom_url", "https://fab.example.com/")
    assert F._base_url() == "https://fab.example.com"
    assert run_op("fab.status")["host"] == "https://fab.example.com"


def test_library_needs_sign_in(ue, fab):
    assert _err("fab.library").code == "conflict"


def _megascans_zip(tmp_path):
    z = tmp_path / "rock.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("rock_2.gltf", "{}")
        f.writestr("rock.json", json.dumps({"id": "xyz", "name": "Mossy Rock", "categories": ["3d", "rock"]}))
        f.writestr("rock_BaseColor.png", b"x")
    return str(z)


def test_scan_download_reads_megascans_meta(ue, tmp_path):
    from fmbridge.ops import fab as F
    d = F._unzip(_megascans_zip(tmp_path))
    info = F.scan_download(d)
    assert info["format"] == "megascans_gltf"
    assert info["meta"]["subtype"] == "3D" and info["meta"]["tier"] == "Medium" and info["meta"]["id"] == "xyz"
    assert F._megascans_dest(info["meta"]) == "/Game/Fab/Megascans/3D/Mossy_Rock_xyz/Medium"


def test_unzip_refuses_path_escape(ue, tmp_path):
    from fmbridge.ops import fab as F
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../evil.txt", "x")
    with pytest.raises(Exception):
        F._unzip(str(z))


def test_import_megascans_through_interchange(ue, tmp_path):
    ue.add_asset("/Interchange/Pipelines/DefaultGLTFPipeline", "InterchangeGLTFPipeline")

    class Mgr(ue.InterchangeManager):
        def import_asset(self, content_path, source_data, import_asset_parameters):
            self._props["got"] = (content_path, import_asset_parameters)
            return [ue.add_asset(content_path + "/SM_Rock", "StaticMesh")]
    mgr = Mgr("mgr")
    ue._singletons[ue.InterchangeManager] = mgr  # what get_interchange_manager_scripted returns
    r = run_op("fab.import", path=_megascans_zip(tmp_path))
    assert r["format"] == "megascans_gltf" and r["imported"] == ["/Game/Fab/Megascans/3D/Mossy_Rock_xyz/Medium/SM_Rock"]
    dest, params = mgr._props["got"]
    assert dest == "/Game/Fab/Megascans/3D/Mossy_Rock_xyz/Medium"
    assert params._props["is_automated"] is True and len(params._props["override_pipelines"]) == 3
    again = run_op("fab.import", path=_megascans_zip(tmp_path))
    assert again["changed"] is False  # already there: kept


def test_import_loose_textures_makes_a_material(ue, tmp_path):
    d = tmp_path / "planks"
    d.mkdir()
    for n in ("Planks_BaseColor.png", "Planks_Normal.png", "Planks_Roughness.png"):
        (d / n).write_bytes(b"x")
    r = run_op("fab.import", path=str(d))
    assert r["format"] == "textures" and r["material"] == "/Game/Fab/planks/MI_planks"
    assert "/Game/Fab/planks/MI_planks" in ue.assets


def test_add_downloads_then_imports(ue, fab, tmp_path, monkeypatch):  # noqa: ARG001 (fab: no native plugin)
    import urllib.request
    src = _megascans_zip(tmp_path)

    class Resp:
        def __init__(self):
            self.f = open(src, "rb")

        def read(self, n=-1):
            return self.f.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: Resp())

    class InlineThread:  # the download runs at start(): no race with the fake's instant ticks
        def __init__(self, target, daemon=None):
            self.target = target

        def start(self):
            self.target()
    import threading
    monkeypatch.setattr(threading, "Thread", InlineThread)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "tmp"))
    ue.add_asset("/Interchange/Pipelines/DefaultGLTFPipeline", "InterchangeGLTFPipeline")
    made = ue.add_asset("/Game/X/SM_A", "StaticMesh")

    class Mgr(ue.InterchangeManager):
        def import_asset(self, content_path, source_data, import_asset_parameters):
            return [made]
    ue._singletons[ue.InterchangeManager] = Mgr("m")
    r = run_op("fab.add", url="https://download.example/rock.zip?sig=abc", metadata={"AssetId": "a1"})
    assert r["route"] == "python" and r["download"].endswith("rock.zip") and r["format"] == "megascans_gltf"


def test_add_refuses_packs_without_the_plugin(ue, fab):
    e = _err("fab.add", url="https://x/y", metadata={"AssetId": "a", "AssetType": "unreal-engine"})
    assert e.code == "unsupported" and "FabScript" in e.hint


def test_add_native_route(ue):
    got = []

    class FabScript(ue.Object):
        @staticmethod
        def add_to_project(url, meta):
            got.append((url, json.loads(meta)))
            return ""
    ue.FabScript = FabScript
    r = run_op("fab.add", url="https://x/y", metadata={"AssetId": "a", "AssetType": "unreal-engine"})
    assert r["route"] == "native" and got == [("https://x/y", {"AssetId": "a", "AssetType": "unreal-engine"})]


# ----------------------------------------------------------------------------------------------- the shim, pure

def test_shim_script_and_metadata():
    from filmtools.unreal import fab_shim
    s = fab_shim.shim_script("tok", "ref")
    assert "addtoproject" in s and '"tok"' in s and "window.ue" in s
    url, meta = fab_shim.metadata_from_call({"name": "addtoproject", "args": [
        "https://dl/x.zip", {"assetId": "a1", "assetName": "Rock", "isQuixel": True}]})
    assert url == "https://dl/x.zip" and meta == {"AssetId": "a1", "AssetName": "Rock", "IsQuixel": True}
