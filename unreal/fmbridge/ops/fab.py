"""Fab (WP2): Epic's asset store by code, with no Fab window. Sign-in state, the signed-in account's library,
adding a Fab asset from its signed download URL, and importing Fab/Megascans downloads already on disk.

How the Fab plugin works (UE 5.8.4 source, docs/unreal/assets.md "Fab"): a web page (fab.com) inside an editor tab
talks to C++ through one bound object, UFabBrowserApi. The page mints a signed download URL and calls
AddToProject(url, metadata); the plugin downloads it (no auth needed: the URL is signed), unzips it under
/tmp/FabLibrary/<AssetId>/ and imports it (Megascans: Interchange on the zip's .gltf with Fab's
InterchangeMegascansPipeline). None of UFabBrowserApi is BlueprintCallable, but `call_method` reaches every UFUNCTION
that takes only strings (GetAuthToken, OpenInNewTab, Login). The signed URL itself comes only from the web page:
tools/filmtools/unreal/fab_shim.py gets it headlessly, or a person copies it.

Never run the console commands Fab.Logout or Fab.SetEnvironment: both delete the saved sign-in. Tokens never leave
the editor: no op returns, prints or logs one.
"""
from __future__ import annotations

import base64
import glob
import json
import os
import sys
import tempfile
import time
import zipfile

import unreal

from . import _assetlib as AL
from . import op
from ..errors import OpError

FAB_API_CLASS = "/Script/Fab.FabBrowserApi"
BASE_URLS = {"prod": "https://www.fab.com"}
# Megascans subtype by the json's categories[0] (QuixelAssetTypes.cpp ExtractMeta)
SUBTYPES = {"3d": "3D", "surface": "Surfaces", "3dplant": "Plants", "atlas": "Decals"}
TIERS = {0: "Raw", 1: "High", 2: "Medium", 3: "Low"}
_api = None


def _fab_api():
    """A UFabBrowserApi (the plugin's own class; auth state is global to the plugin, so any instance will do)."""
    global _api
    if _api is not None:
        return _api
    cls = unreal.load_class(None, FAB_API_CLASS)
    if cls is None:
        raise OpError("the Fab plugin is not loaded in this editor", code="unsupported",
                      hint="enable the Fab plugin (editor.plugins) and restart; it does not load in a commandlet")
    _api = unreal.new_object(cls)
    return _api


def _token() -> str:
    """The signed-in Fab user's access token, '' when signed out. Never return or log it."""
    try:
        return str(_fab_api().call_method("GetAuthToken") or "")
    except OpError:
        return ""


def _persist_credentials() -> list:
    if sys.platform.startswith("linux"):
        root = os.path.expanduser("~/.local/share/.eos_sdk")
    elif sys.platform == "win32":
        root = os.path.join(os.environ.get("LOCALAPPDATA", ""), ".eos_sdk")
    else:
        root = os.path.expanduser("~/Library/Application Support/.eos_sdk")
    return glob.glob(os.path.join(root, "keychain", "*", "persistent_auth", "credential"))


def _plugin_dir() -> str:
    return os.path.join(unreal.Paths.engine_dir(), "Plugins", "Fab")


@op("fab.status", mutates=False, idempotent=True, tags=["fab"])
def status() -> dict:
    """Is Fab usable from code here: plugin loaded, signed in, a saved sign-in on disk, the pack installer library
    (Linux needs ThirdParty/libBuildPatchInstallerLib.so for unreal-engine-format packs), the download cache.

    Returns: {"plugin", "signed_in", "saved_sign_ins": int, "pack_installer": bool, "cache_dir", "platform",
             "next": what to do}. No token is returned.
    Example: film-ue op fab.status
    """
    try:
        _fab_api()
        plugin = True
    except OpError:
        plugin = False
    signed = bool(plugin and _token())
    saved = len(_persist_credentials())
    third = os.path.join(_plugin_dir(), "ThirdParty")
    lib = ("libBuildPatchInstallerLib.so" if sys.platform.startswith("linux") else
           "BuildPatchInstallerLib.dll" if sys.platform == "win32" else "libBuildPatchInstallerLib.dylib")
    nxt = ("enable the Fab plugin" if not plugin else "signed in: fab.library, fab.add" if signed else
           "fab.login (uses the saved sign-in)" if saved else
           "fab.login portal=true once (device code: an operator approves it), then fab.login")
    return {"plugin": plugin, "signed_in": signed, "saved_sign_ins": saved,
            "pack_installer": os.path.isfile(os.path.join(third, lib)),
            "cache_dir": os.path.join(tempfile.gettempdir(), "FabLibrary"), "platform": sys.platform, "next": nxt}


@op("fab.login", mutates=True, idempotent=True, tags=["fab", "needs-epic-login"])
def login(*, portal: bool = False, timeout_s: float = 60.0):
    """Sign Fab in: by default with the saved sign-in (opening a Fab tab is what makes the plugin try it, and then
    the editor's -AUTH_TYPE=exchangecode -AUTH_PASSWORD=<code> if that fails); with portal, start the device-code
    sign-in (Fab.Login): its code and URL are in the editor log for a person to approve once.

    Multi-tick: waits up to timeout_s for the sign-in. Already signed in: changes nothing.
    Args: portal: device-code sign-in instead of the saved one. timeout_s: how long to wait.
    Returns: {"signed_in", "changed", "method", "waited_s", "hint"}.
    Example: film-ue op fab.login
    """
    api = _fab_api()
    if _token():
        return {"signed_in": True, "changed": False, "method": "already", "waited_s": 0.0, "hint": ""}
    t0 = time.time()
    if portal:
        unreal.SystemLibrary.execute_console_command(None, "Fab.Login")
        method = "portal"
    else:
        api.call_method("OpenInNewTab", ("",))  # CreateNewFabTab -> LoginUsingPersist (FabBrowser.cpp:337)
        method = "persist"
    while time.time() - t0 < timeout_s:
        yield 0.5
        if _token():
            return {"signed_in": True, "changed": True, "method": method, "waited_s": round(time.time() - t0, 1),
                    "hint": ""}
    hint = ("approve the device code shown in the editor log (film-ue log | grep -i -A3 fab), then run fab.login "
            "again" if portal else "no saved sign-in worked: fab.login portal=true once, or restart the editor with "
                                   "-AUTH_TYPE=exchangecode -AUTH_PASSWORD=<code> (film-ue epic-login --fab)")
    return {"signed_in": False, "changed": False, "method": method, "waited_s": round(time.time() - t0, 1),
            "hint": hint}


def _account_id(token: str) -> str:
    """The Epic account id: the access token is a JWT whose `sub` is the account (unverified assumption: the plugin
    takes it from EOS, FabMyFolderIntegration.cpp)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("sub", ""))
    except Exception:
        return ""


def _get_json(url: str, token: str = "") -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https host)
        return json.loads(r.read().decode("utf-8"))


@op("fab.library", mutates=False, idempotent=True, tags=["fab", "needs-epic-login", "experimental"])
def library(*, query: str = "", limit: int = 100, account_id: str = "") -> dict:
    """The signed-in account's Fab library (what it owns), from the endpoint the plugin's My Folder uses
    (GET <fab>/e/accounts/<account>/ue/library, FabMyFolderIntegration.cpp): title, asset id, listing type, the
    page url, and a thumbnail url.

    Args: query: keep items whose title/description contain these words. limit: at most this many. account_id: the
          Epic account (default: from the token).
    Returns: {"items": [{"title", "asset_id", "asset_namespace", "listing_type", "url", "image", "source"}],
             "count", "next_cursor"}.
    Example: film-ue op fab.library query=chair
    """
    tok = _token()
    if not tok:
        raise OpError("Fab is not signed in", code="conflict", hint="fab.login (fab.status says how)")
    acc = account_id or _account_id(tok)
    if not acc:
        raise OpError("could not tell the Epic account id from the token", code="failed",
                      hint="pass account_id= (the Epic account id)")
    items, cursor, words = [], "", [w.lower() for w in query.split()]
    for _ in range(50):
        url = f"{BASE_URLS['prod']}/e/accounts/{acc}/ue/library?count=100" + (f"&cursor={cursor}" if cursor else "")
        try:
            data = _get_json(url, tok)
        except Exception as e:
            raise OpError(f"Fab library request failed: {type(e).__name__}: {str(e)[:200]}", code="engine",
                          hint="fab.status; the endpoint is private and may have changed") from None
        for it in data.get("results", []):
            text = f"{it.get('title', '')} {it.get('description', '')}".lower()
            if words and not all(w in text for w in words):
                continue
            imgs = it.get("images") or []
            items.append({"title": it.get("title"), "asset_id": it.get("assetId"),
                          "asset_namespace": it.get("assetNamespace"), "listing_type": it.get("listingType"),
                          "url": it.get("url"), "source": it.get("source"),
                          "image": (imgs[0] or {}).get("url") if imgs else None})
        cursor = (data.get("cursors") or {}).get("next") or ""
        if not cursor or len(items) >= limit:
            break
    return {"items": items[:limit], "count": len(items[:limit]), "next_cursor": cursor or None}


# ------------------------------------------------------------------------------------------- downloads on disk

def _unzip(path: str) -> str:
    out = path + "_extracted"
    if not os.path.isdir(out):
        with zipfile.ZipFile(path) as z:
            for m in z.namelist():  # no path escapes
                if m.startswith("/") or ".." in m.replace("\\", "/").split("/"):
                    raise OpError(f"{path} has an unsafe entry {m!r}", code="bad_args")
            z.extractall(out)
    for inner in glob.glob(os.path.join(out, "**", "*.zip"), recursive=True):  # nested zips, as the plugin does
        _unzip(inner)
    return out


def scan_download(folder: str) -> dict:
    """What a Fab/Megascans download holds: {"format": megascans_gltf|gltf|fbx|obj|usd|textures|unknown, "gltf",
    "json", "meshes": [...], "textures": [...], "meta": {...}} (pure filesystem)."""
    files = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs]
    by = lambda *ext: sorted(f for f in files if f.lower().endswith(ext))
    gltf, jsons = by(".gltf", ".glb"), by(".json")
    meshes = by(".fbx", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".abc")
    textures = by(*AL.IMAGE_EXT)
    out = {"folder": folder, "gltf": gltf, "json": jsons, "meshes": meshes, "textures": textures, "meta": {}}
    if len([g for g in gltf if g.endswith(".gltf")]) == 1 and len(jsons) >= 1:
        meta = {}
        try:
            with open(jsons[0], encoding="utf-8") as fh:
                j = json.load(fh)
            cats = [str(c).lower() for c in j.get("categories", [])]
            sub = SUBTYPES.get(cats[0], "3D") if cats else "3D"
            if cats[:1] == ["atlas"] and "imperfections" in cats:
                sub = "Imperfections"
            stem = os.path.splitext(os.path.basename(gltf[0]))[0]
            tier = stem.rsplit("_", 1)[-1]
            meta = {"id": j.get("id"), "name": j.get("name") or stem, "categories": cats, "subtype": sub,
                    "tier": TIERS.get(int(tier), "High") if tier.isdigit() else "High",
                    "displacement_scale": j.get("displacement_scale_tier1"),
                    "displacement_bias": j.get("displacement_bias_tier1")}
        except (OSError, ValueError):
            meta = {}
        if meta:
            out.update(format="megascans_gltf", meta=meta)
            return out
    if gltf:
        out["format"] = "gltf"
    elif meshes:
        ext = os.path.splitext(meshes[0])[1].lower()
        out["format"] = {".fbx": "fbx", ".obj": "obj", ".abc": "abc"}.get(ext, "usd")
    elif textures:
        out["format"] = "textures"
    else:
        out["format"] = "unknown"
    return out


def _megascans_dest(meta: dict) -> str:
    name = AL.safe_name(meta.get("name") or "Asset")
    return f"/Game/Fab/Megascans/{meta.get('subtype', '3D')}/{name}_{AL.safe_name(str(meta.get('id') or 'x'))}/" \
           f"{meta.get('tier', 'High')}"


@op("fab.import", mutates=True, idempotent=True, tags=["fab", "import", "slow"])
def import_download(*, path: str, dest: str = "", kind: str = "", replace: bool = False) -> dict:
    """Import a Fab or Megascans download that is on the box (a zip, or a folder): Fab-plugin format (one .gltf +
    .json) the way the plugin does it (Interchange with InterchangeMegascansPipeline, per type: 3D Nanite, plants,
    surfaces, decals), any other glTF/FBX/OBJ/USD with the generic importer, loose textures as a PBR material.

    Args: path: zip or folder on the box (e.g. /tmp/FabLibrary/<AssetId>/x.zip). dest: content folder (default
          /Game/Fab/Megascans/<Type>/<Name>_<id>/<Tier> like the plugin, or /Game/Fab/<Name>). kind: force the
          Megascans type (3D, Plants, Surfaces, Decals, Imperfections). replace: re-import over what is there (else
          an imported asset is kept: changed false).
    Returns: {"format", "dest", "imported": [paths], "material": path|None, "changed", "meta"}.
    Example: film-ue op fab.import path=/data/fab/rock_4k.zip
    """
    if not os.path.exists(path):
        raise OpError(f"no {path} on the box", code="not_found", hint="push it first (client.push) or fab.add")
    folder = _unzip(path) if path.lower().endswith(".zip") else path
    info = scan_download(folder)
    fmt = info["format"]
    name = AL.safe_name(info["meta"].get("name") or os.path.splitext(os.path.basename(path.rstrip("/\\")))[0])
    from . import assets_import as AI
    if fmt == "megascans_gltf":
        meta = dict(info["meta"])
        if kind:
            meta["subtype"] = kind
        d = dest or _megascans_dest(meta)
        if not replace and AI.folder_has_assets(d):
            return {"format": fmt, "dest": d, "imported": [], "material": None, "changed": False, "meta": meta}
        res = AI.import_megascans_gltf(info["gltf"][0], d, meta["subtype"])
        return {"format": fmt, "dest": d, "imported": res, "material": None, "changed": bool(res), "meta": meta}
    d = dest or f"/Game/Fab/{name}"
    if not replace and AI.folder_has_assets(d):
        return {"format": fmt, "dest": d, "imported": [], "material": None, "changed": False, "meta": info["meta"]}
    if fmt in ("gltf", "fbx", "obj", "usd", "abc"):
        src = (info["gltf"] or info["meshes"])[:1]
        res = AI.import_any(files=src, dest=d, replace=True)
        paths = [p for r in res["imported"] for p in r["assets"]]
        mat = None
        if info["textures"] and fmt in ("fbx", "obj"):  # FBX downloads carry loose textures: one PBR material
            from .mat import pbr
            sets = AL.texture_set(info["textures"])
            sets.pop("_unknown", None)
            if len(sets) == 1:
                mat = pbr(path=f"{d}/MI_{name}", files=list(next(iter(sets.values())).values()))["path"]
        return {"format": fmt, "dest": d, "imported": paths, "material": mat, "changed": bool(paths),
                "meta": info["meta"]}
    if fmt == "textures":
        from .mat import pbr
        sets = AL.texture_set(info["textures"])
        sets.pop("_unknown", None)
        mats = []
        for sname, roles in sorted(sets.items()):
            mats.append(pbr(path=f"{d}/MI_{AL.safe_name(sname)}", files=list(roles.values()))["path"])
        return {"format": fmt, "dest": d, "imported": mats, "material": mats[0] if mats else None,
                "changed": bool(mats), "meta": info["meta"]}
    raise OpError(f"nothing importable in {path}", code="bad_args", details=info,
                  hint="a Fab download holds a .gltf (+.json), an .fbx/.obj, or textures")


@op("fab.add", mutates=True, idempotent=True, tags=["fab", "import", "slow", "experimental"])
def add(*, url: str, metadata: dict = None, dest: str = "", replace: bool = False):
    """Add a Fab asset to the project from its signed download URL (what the Fab page hands the plugin's
    AddToProject; tools/filmtools/unreal/fab_shim.py gets it for a listing without a window): download (no auth:
    the URL is signed), unzip into the plugin's cache, import as fab.import does. With the FabScript project plugin
    installed (unreal/plugins/FabScript) and metadata given, Epic's own AddToProject runs instead, for every format
    (including unreal-engine packs).

    Multi-tick: downloads in the background and yields until done.
    Args: url: the signed download URL. metadata: {"AssetId", "AssetName", "AssetType" (gltf|fbx|unreal-engine|...),
          "ListingType", "AssetNamespace", "DistributionPointBaseUrls", "IsQuixel"} as the page gives it.
          dest: content folder. replace: import again over an earlier import.
    Returns: fab.import's result plus {"download": file on the box, "route": "python"|"native"}.
    Example: film-ue op fab.add url=<signed url> 'metadata={"AssetId": "abc", "AssetName": "Rock", "IsQuixel": true}'
    """
    meta = dict(metadata or {})
    native = getattr(unreal, "FabScript", None)
    if native is not None and meta:
        err = native.add_to_project(url, json.dumps(meta))
        if err:
            raise OpError(f"FabScript.add_to_project: {err}", code="engine",
                          hint="fab.status; without metadata fab.add downloads and imports in Python")
        return {"route": "native", "changed": True, "download": None, "dest": "/Game/Fab",
                "hint": "Epic's workflow runs on its own; assets.find path=/Game/Fab shows them as they land"}
    if meta.get("AssetType") == "unreal-engine":
        raise OpError("unreal-engine packs install through Build Patch Services, which only the plugin does",
                      code="unsupported", hint="install unreal/plugins/FabScript (and on Linux the plugin's "
                                               "libBuildPatchInstallerLib.so), then fab.add with metadata")
    cache = os.path.join(tempfile.gettempdir(), "FabLibrary", AL.safe_name(meta.get("AssetId") or "manual"))
    os.makedirs(cache, exist_ok=True)
    fname = AL.safe_name(os.path.basename(url.split("?", 1)[0]).rsplit(".", 1)[0]) + "." + \
        (os.path.basename(url.split("?", 1)[0]).rsplit(".", 1)[-1] if "." in os.path.basename(url.split("?", 1)[0])
         else "zip")
    target = os.path.join(cache, fname)
    if not os.path.isfile(target):
        box = {"done": False, "error": None}

        def fetch():
            import urllib.request
            try:
                with urllib.request.urlopen(url, timeout=600) as r, open(target + ".part", "wb") as fh:  # noqa: S310
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                os.replace(target + ".part", target)
            except Exception as e:  # reported on the game thread
                box["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            box["done"] = True
        import threading
        threading.Thread(target=fetch, daemon=True).start()  # no unreal calls in the thread
        while not box["done"]:
            yield 0.5
        if box["error"]:
            raise OpError(f"download failed: {box['error']}", code="engine",
                          hint="signed URLs expire within minutes: get a fresh one")
    res = import_download(path=target, dest=dest, replace=replace)
    return {**res, "download": target, "route": "python"}
