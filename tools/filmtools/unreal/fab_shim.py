"""Fab listing -> signed download URL, with no editor window (WP2, experimental: written from the Fab plugin's
source, not yet run against fab.com).

The Fab plugin's web page (https://www.fab.com/plugins/ue5) mints the signed download URL in its own JavaScript and
hands it to the editor by calling `window.ue.fab.addtoproject(url, metadata)` on an object the editor binds
(UFabBrowserApi, Engine/Plugins/Fab/Source/Fab/Private/FabBrowserApi.h). This module loads that page in headless
Chromium with a stand-in `window.ue.fab` that answers what the page asks (the access token, the API version,
settings) and records the `addtoproject` call; then it clicks "Add to project" on a listing. The result is exactly
what the editor would get, ready for `fab.add url=... metadata=...`. It also records the page's API requests, which
show the download-info endpoint so a later version can call it directly.

The access token comes from the running editor and is passed in by the caller; it is never printed or written.

    from filmtools.unreal import fab_shim
    got = fab_shim.signed_url(listing_id, token=tok)       # {"url", "metadata", "requests": [...]} or raises
    client.op("fab.add", url=got["url"], metadata=got["metadata"])

Needs `playwright` (uv add playwright; playwright install chromium). The selectors below are the page's as of
2026-11 and are the first thing to check when it fails (`debug_dir` saves a screenshot and the HTML).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

FAB = "https://www.fab.com"
API_VERSION = {"ue": "5.8", "api": "1.1.0", "pluginversion": "0.0.21", "platform": "Linux",
               "supportedfeatures": {"banners": True}, "selectedlocale": "en", "selectedlocalename": "English"}
SETTINGS = {"preferredformat": "gltf", "preferredquality": "high"}
ADD_BUTTONS = ["button:has-text('Add to project')", "button:has-text('Add to Project')",
               "[data-testid='add-to-project']"]

# window.ue.fab as the page expects it: every UFabBrowserApi UFUNCTION, lower-cased, returning promises (the
# editor's binding is async). The recorded calls go to window.__fab_calls.
_SHIM = """
(() => {
  const token = %(token)s, refresh = %(refresh)s;
  window.__fab_calls = [];
  const rec = (name) => (...args) => { window.__fab_calls.push({name, args}); return Promise.resolve(); };
  const fab = {
    geturl: () => Promise.resolve(%(base)s + '/plugins/ue5'),
    getauthtoken: () => Promise.resolve(token),
    getrefreshtoken: () => Promise.resolve(refresh),
    getapiversion: () => Promise.resolve(%(version)s),
    getsettings: () => Promise.resolve(%(settings)s),
    registercallbacks: (cbs) => { window.__fab_callbacks = cbs; if (cbs && cbs.onlogin) cbs.onlogin(token);
                                  return Promise.resolve(); },
    addtoproject: rec('addtoproject'), installtoproject: rec('installtoproject'),
    installtoengine: rec('installtoengine'), dragstart: rec('dragstart'), ondraginfosuccess: rec('ondraginfosuccess'),
    ondraginfofailure: rec('ondraginfofailure'), login: rec('login'), logout: rec('logout'),
    openpluginsettings: rec('openpluginsettings'), setpreferredqualitytier: rec('setpreferredqualitytier'),
    openinnewtab: rec('openinnewtab'), openurlinbrowser: rec('openurlinbrowser'), copytoclipboard: rec('copytoclipboard'),
    pluginopened: rec('pluginopened'), logerror: rec('logerror'), logwarning: rec('logwarning'),
    logdisplay: rec('logdisplay'), logverbose: rec('logverbose'),
  };
  window.ue = Object.assign(window.ue || {}, {fab});
})();
"""


def shim_script(token: str, refresh: str = "", base: str = FAB) -> str:
    """The init script that stands in for the editor's binding (pure: tested without a browser)."""
    return _SHIM % {"token": json.dumps(token), "refresh": json.dumps(refresh), "base": json.dumps(base),
                    "version": json.dumps(API_VERSION), "settings": json.dumps(SETTINGS)}


def metadata_from_call(call: dict) -> tuple:
    """A recorded addtoproject call -> (url, metadata with the plugin's field names)."""
    args = call.get("args") or []
    if len(args) < 2:
        raise ValueError(f"addtoproject was called with {len(args)} arguments, want (url, metadata)")
    url, meta = args[0], dict(args[1] or {})
    keys = ["AssetId", "AssetName", "AssetType", "ListingType", "AssetNamespace", "DistributionPointBaseUrls",
            "IsQuixel"]
    low = {k.lower(): k for k in keys}
    out = {low.get(k.lower(), k): v for k, v in meta.items()}
    return url, out


def signed_url(listing_id: str, *, token: str, refresh: str = "", timeout_s: float = 60.0, quality: str = "high",
               fmt: str = "gltf", debug_dir: str = "", headless: bool = True) -> dict:
    """Load the listing on Fab's plugin page with the shim, click "Add to project", return the recorded call:
    {"url", "metadata", "requests": [API urls the page called]}. Raises RuntimeError with what it saw."""
    from playwright.sync_api import sync_playwright  # optional dependency
    SETTINGS.update(preferredquality=quality, preferredformat=fmt)
    requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) UnrealEngine/5.8 FabPlugin")
        ctx.add_init_script(shim_script(token, refresh))
        page = ctx.new_page()
        page.on("request", lambda r: requests.append(r.url) if "/i/" in r.url or "/e/" in r.url else None)
        page.goto(f"{FAB}/plugins/ue5/listings/{listing_id}", wait_until="networkidle", timeout=timeout_s * 1000)
        clicked = False
        for sel in ADD_BUTTONS:
            btn = page.locator(sel)
            if btn.count():
                btn.first.click()
                clicked = True
                break
        t0 = time.time()
        calls = []
        while time.time() - t0 < timeout_s:
            calls = [c for c in page.evaluate("window.__fab_calls || []") if c.get("name") == "addtoproject"]
            if calls:
                break
            page.wait_for_timeout(500)
        if debug_dir:
            d = Path(debug_dir)
            d.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(d / f"fab_{listing_id}.png"), full_page=True)
            (d / f"fab_{listing_id}.html").write_text(page.content())
        browser.close()
    if not calls:
        raise RuntimeError(f"no addtoproject call for listing {listing_id} (clicked: {clicked}); "
                           f"pass debug_dir= to see the page")
    url, meta = metadata_from_call(calls[-1])
    return {"url": url, "metadata": meta, "requests": sorted(set(requests))}
