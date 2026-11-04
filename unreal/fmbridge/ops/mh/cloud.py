"""Epic's MetaHuman cloud services, driven without blocking the editor: the sign-in, the auto-rig (the face DNA a
build needs) and the high-resolution texture sources. Both requests run as multi-tick jobs: the request is sent
non-blocking, then the job polls the character and the editor log once a second, and ends at the outcome the engine
logs ("Auto-Rigging finished in N seconds", "... failed with code ...") or at its timeout. Nothing waits on a dialog
or a browser.

Sign-in (docs/linux/engine.md §12b/§12c, P10): the services use their own EOS client. In order they try an exchange
code (CVar MetaHuman.Cloud.Config.ExchangeCode), the saved sign-in (persistent auth: on Linux
~/.local/share/.eos_sdk/keychain/<client>/persistent_auth/credential), then the account portal, which on Linux is a
device-code page the system browser gets (`film-ue epic-login` shows the code). Launch the editor with
-NoMetaHumanAccountPortalLoginFallback to make a missing sign-in fail at once instead of waiting.
"""
from __future__ import annotations

import time

import unreal

from .. import op
from ...errors import OpError
from . import _core as K

RIG_OK = (r"Auto-Rigging finished in",)
RIG_FAIL = (r"Auto-Rigging of Face failed with code", r"Auto-Rigging failed due to incompatible DNA",
            r"Failed to align face DNA from autorigging", r"Service returned invalid DNA")
TEX_OK_FACE, TEX_OK_BODY = r"Download of source face textures finished in", r"Download of source body textures finished in"
TEX_FAIL = (r"Download of source (face|body) textures failed", r"User not logged in, please autorig")
AUTH_FAIL = (r"LogMetaHumanAuth: .*Login failed", r"LogMetaHumanAuth: .*Invalid user", r"LogMetaHumanAuth: .*MFA required",
             r"LogMetaHumanAuth: .*account is restricted", r"LogMetaHumanAuth: .*pin grant code")
PORTAL = (r"LaunchAccountPortalWithPlatformBrowser", r"Login using account portal")
EXCHANGE_CVAR = "MetaHuman.Cloud.Config.ExchangeCode"
POLL_S = 1.0  # how often a cloud job looks at the character and the log


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


@op("mh.auth_status", mutates=False, idempotent=True, tags=["needs-epic-login"])
def auth_status() -> dict:
    """Whether the MetaHuman cloud services can sign in to Epic without asking.

    Returns: {"signed_in": true|false|null (Windows: unknown, kept in the credential store), "credentials": n saved
    EOS sign-ins on this machine, "platform"}.
    Example: film-ue op mh.auth_status
    """
    import sys
    return {"signed_in": K.signed_in(), "credentials": len(K.eos_credentials()), "platform": sys.platform}


@op("mh.login", mutates=True, idempotent=True, tags=["needs-epic-login"])
def login(preset: str = "", folder: str = "/Game/FM/Login", *, exchange_code: str = "") -> dict:
    """Start Epic's sign-in for the MetaHuman cloud services if there is none, and return at once.

    With `exchange_code` (a one-time code from Epic's account service, valid ~5 minutes) the next cloud request signs
    in with it, no browser (the code is set in the CVar MetaHuman.Cloud.Config.ExchangeCode; the console echoes it to
    the log, so use a fresh single-use code). Without it, a rig is requested on a throwaway character so the service
    starts its device sign-in: the engine hands the page to the system browser, which on a box without a desktop
    keeps it for `film-ue epic-login`. The sign-in then persists across editor restarts.
    Returns: {"signed_in", "requested", "exchange_code_set"}.
    Example: film-ue op mh.login
    """
    if exchange_code:
        unreal.SystemLibrary.execute_console_command(_world(), f"{EXCHANGE_CVAR} {exchange_code}")
        return {"signed_in": K.signed_in(), "requested": False, "exchange_code_set": True}
    if K.signed_in():
        return {"signed_in": True, "requested": False, "exchange_code_set": False}
    from .character import add, presets
    dest = f"{folder}/MH_Login"
    add(path=dest, preset=preset or presets()[0])
    p = unreal.MetaHumanCharacterAutoRiggingRequestParams()
    p.set_editor_property("rig_type", unreal.MetaHumanRigType.JOINTS_ONLY)
    p.set_editor_property("blocking", False)
    p.set_editor_property("report_progress", False)
    K.sub().request_auto_rigging(K.char(dest), p)
    return {"signed_in": False, "requested": True, "exchange_code_set": False}


def _need_login(require_login: bool):
    if require_login and K.signed_in() is False:
        code = ""
        try:
            code = unreal.SystemLibrary.get_console_variable_string_value(EXCHANGE_CVAR)
        except Exception:
            pass
        if not code:
            raise OpError("no Epic sign-in saved on this machine for the MetaHuman cloud services", code="unsupported",
                          hint="sign in once: film-ue epic-login (device code), or mh.login exchange_code=<code>; "
                               "or pass require_login=false to let the service ask (it waits for the sign-in)")


def _wait(watch, ok, fail, done, timeout_s: float, what: str, poll_s: float | None = None):
    """Poll once a second (yielding to the editor) until `done()` or an `ok` log line; raise on a `fail` line, an
    auth failure or the timeout. Returns (seconds, the outcome line)."""
    t0 = time.time()
    portal_seen = False
    while True:
        yield POLL_S if poll_s is None else poll_s
        lines = watch.new()
        bad = K.find(lines, fail)
        if bad:
            raise OpError(f"{what} failed: {bad}", code="engine", details={"log": bad},
                          hint="see the editor log (LogMetaHumanCharacterEditor, LogAutorigServiceRequest); a "
                               "face mesh far from MetaHuman topology fails to rig")
        auth = K.find(lines, AUTH_FAIL)
        if auth:
            raise OpError(f"{what}: Epic sign-in failed: {auth}", code="engine", hint="sign in again: film-ue epic-login")
        if K.find(lines, PORTAL):
            portal_seen = True
        good = K.find(lines, ok)
        if good or done():
            return round(time.time() - t0, 1), good or ""
        if time.time() - t0 > timeout_s:
            raise OpError(f"{what} did not finish in {timeout_s:.0f} s", code="timeout",
                          hint=("the service is waiting for an Epic sign-in: complete it (film-ue epic-login shows "
                                "the code) and run again" if portal_seen else
                                "the request may still finish: run mh.describe later, or retry with a longer timeout_s"))


@op("mh.rig", mutates=True, idempotent=True, tags=["slow", "needs-epic-login", "metahuman"])
def rig(character: str, full: bool = True, *, timeout_s: float = 900, force: bool = False,
        require_login: bool = True, save: bool = True):
    """Epic's cloud auto-rig, as a multi-tick job (about 30 s once signed in). Needed before mh.textures and
    mh.build, and again after any body or face change.

    Skips the request when the character is rigged and its body and face are what they were at the last rig
    (`changed: false`); `force` re-rigs anyway. Without a saved Epic sign-in it fails at once (require_login) instead
    of waiting on a browser.
    Args: character: the character. full: joints + blend shapes (what facial animation needs) or joints only.
    timeout_s: give up after. force: rig even if up to date. require_login: fail fast without a sign-in.
    Returns: {"changed", "seconds", "rig": "full"|"joints", "log"}.
    Example: film-ue op mh.rig character=/Game/Characters/Ava/MH_Ava
    """
    c = K.char(character)
    fp = K.fingerprint(K.rig_inputs(c))
    kind = "full" if full else "joints"
    if not force and K.get_tag(c, "Rig") == f"{kind}:{fp}" and K.rigged(c) is not False:
        return {"changed": False, "seconds": 0.0, "rig": kind, "log": "up to date"}
    _need_login(require_login)
    p = unreal.MetaHumanCharacterAutoRiggingRequestParams()
    p.set_editor_property("rig_type", unreal.MetaHumanRigType.JOINTS_AND_BLEND_SHAPES if full
                          else unreal.MetaHumanRigType.JOINTS_ONLY)
    p.set_editor_property("blocking", False)
    p.set_editor_property("report_progress", False)
    watch = K.LogWatch()
    K.sub().request_auto_rigging(c, p)
    done = (lambda: bool(c.get_editor_property("has_face_dna_blendshapes"))) if full else (lambda: False)
    seconds, line = yield from _wait(watch, RIG_OK, RIG_FAIL, done, timeout_s, f"auto-rig of {character}")
    if full and not c.get_editor_property("has_face_dna_blendshapes"):
        yield 0.5  # the DNA is applied a tick after the log line
    K.set_tag(c, "Rig", f"{kind}:{fp}")
    if save:
        K.save(character)
    return {"changed": True, "seconds": seconds, "rig": kind, "log": line}


@op("mh.textures", mutates=True, idempotent=True, tags=["slow", "needs-epic-login", "metahuman"])
def textures(character: str, *, timeout_s: float = 900, force: bool = False, require_login: bool = True,
             save: bool = True):
    """Epic's cloud high-resolution skin texture sources (face and body), as a multi-tick job (about 20 s). Needs a
    rig first (the service signs in during the rig); mh.build needs them.

    Skips when the character already has them (`changed: false`); a skin change (mh.skin) discards them. The
    resolution is the skin setting desired_texture_sources_resolutions (mh.skin texture_resolution=4k).
    Returns: {"changed", "seconds", "has_high_res_textures", "log"}.
    Example: film-ue op mh.textures character=/Game/Characters/Ava/MH_Ava
    """
    c = K.char(character)
    if not force and c.get_editor_property("has_high_resolution_textures"):
        return {"changed": False, "seconds": 0.0, "has_high_res_textures": True, "log": "up to date"}
    if K.rigged(c) is False:
        raise OpError(f"{character} is not rigged", code="conflict", hint="run mh.rig first (it also signs in)")
    _need_login(require_login)
    p = unreal.MetaHumanCharacterTextureRequestParams()
    p.set_editor_property("blocking", False)
    p.set_editor_property("report_progress", False)
    watch = K.LogWatch()
    K.sub().request_texture_sources(c, p)
    def done():  # set once both the face and the body sources are in (P10: body 4 s, face 11 s)
        return bool(c.get_editor_property("has_high_resolution_textures"))

    seconds, line = yield from _wait(watch, (), TEX_FAIL, done, timeout_s, f"texture download for {character}")
    if save:
        K.save(character)
    return {"changed": True, "seconds": seconds, "has_high_res_textures": True, "log": line}
