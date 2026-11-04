"""The selftest harness: each area's acceptance test, run on a GPU box by `film-ue selftest [area|all]` (the op
`selftest.run`), in a scratch level, writing one JSON report per area plus stills. docs/unreal/dx.md "Selftests".

An area's selftest is `fmbridge/selftest/<area>.py`:

    '''What it proves. Takes ~2 min. Needs: GPU.'''
    REQUIRES = ["gpu"]            # optional: gpu, display, linux, windows, epic_login, mh_cloud (unmet: skipped)
    AREAS = ["light", "look"]     # optional: the op prefixes it covers (default: the module name)
    NEEDS_LEVEL = True            # optional: a fresh scratch level first (default True)
    TIMEOUT = 600                 # optional: seconds (default 900)

    def run(t):                   # may be a generator: `yield` ticks the editor, `yield 0.5` waits
        t.op("light.add", label=t.prefix + "Key", kind="rect", loc=[0, 0, 200])
        t.check("one light", len(t.op("level.actors", contains=t.prefix + "Key")), 1)
        t.idempotent("light.add converges", "light.add", label=t.prefix + "Key", kind="rect", loc=[0, 0, 200])
        t.raises("unknown kind is bad_args", "light.add", code="bad_args", label="x", kind="nope")
        path = yield from t.still("key", camera=t.prefix + "Cam")
        return {"anything": "lands in report['extra']"}

`t` (T below): op() calls an op and records coverage (a multi-tick op comes back as a generator: `r = yield from
t.op(...)`), check / ok / raises / idempotent record results without stopping the test, skip() stops it as skipped,
still() writes a PNG into the report folder, metric() and note() add numbers and words. Everything the test makes goes
under t.scratch (/Game/_Selftest/<area>) and is named with t.prefix (ST_<area>_); the harness opens a fresh level
there first and deletes the folder afterwards unless keep.

This file runs inside the editor: Python 3.11, and the `unreal` API only on the game thread (ops run there).
"""
from __future__ import annotations

import importlib
import inspect
import json
import math
import os
import pkgutil
import sys
import time
import traceback

import unreal

SCRATCH_ROOT = "/Game/_Selftest"
BLANK = SCRATCH_ROOT + "/_Blank/L_Blank"  # where the harness waits when it must leave a scratch level
DEFAULT_TIMEOUT = 900.0
CAPABILITIES = ("gpu", "display", "linux", "windows", "epic_login", "mh_cloud")


class Skip(Exception):
    """t.skip(reason): the test cannot run here (no GPU, no sign-in); reported as skipped, not failed."""


def _jsonable(v, depth=0):
    if depth > 6:
        return str(v)
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else str(v)
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x, depth + 1) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x, depth + 1) for k, x in v.items()}
    for attrs in (("x", "y", "z"), ("pitch", "yaw", "roll"), ("r", "g", "b", "a")):
        if all(hasattr(v, a) for a in attrs) and not isinstance(v, type):
            try:
                return {a: float(getattr(v, a)) for a in attrs}
            except (TypeError, ValueError):
                break
    if hasattr(v, "get_path_name"):
        try:
            return v.get_path_name()
        except Exception:
            pass
    return str(v)[:500]


def _close(got, want, tol) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return got == want
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(want)) <= tol
    if isinstance(want, (list, tuple)) and isinstance(got, (list, tuple)):
        return len(got) == len(want) and all(_close(g, w, tol) for g, w in zip(got, want))
    if isinstance(want, dict) and isinstance(got, dict):
        return all(k in got and _close(got[k], w, tol) for k, w in want.items())
    return got == want


def capabilities() -> dict:
    """What this editor can do, for REQUIRES: gpu (a real RHI: not -nullrhi), display (not -RenderOffscreen and a
    desktop), linux/windows, epic_login (a stored Epic sign-in: Linux ~/.local/share/.eos_sdk; elsewhere assumed),
    mh_cloud (= epic_login: the MetaHuman cloud services need it)."""
    cmd = ""
    try:
        cmd = unreal.SystemLibrary.get_command_line().lower()
    except Exception:
        pass
    linux, windows = sys.platform.startswith("linux"), sys.platform == "win32"
    if linux:
        epic = os.path.isdir(os.path.expanduser("~/.local/share/.eos_sdk"))
    else:
        epic = True
    return {"gpu": "-nullrhi" not in cmd, "display": "-renderoffscreen" not in cmd and (windows or
                                                                                        bool(os.environ.get("DISPLAY"))),
            "linux": linux, "windows": windows, "epic_login": epic, "mh_cloud": epic}


def box() -> dict:
    out = {"platform": sys.platform, "python": sys.version.split()[0]}
    try:
        out["engine"] = unreal.SystemLibrary.get_engine_version()
    except Exception:
        out["engine"] = ""
    try:
        out["command_line"] = unreal.SystemLibrary.get_command_line()[:400]
    except Exception:
        pass
    out["capabilities"] = capabilities()
    return out


class T:
    """One area's test run: what the test calls (see the module docstring)."""

    def __init__(self, area: str, out_dir: str, keep: bool = False, areas=None, baseline_mode: str = "auto"):
        self.area, self.out, self.keep = area, out_dir, keep
        self.baseline_mode = baseline_mode  # WP10's baselines (fmbridge.qa.baseline): auto|compare|update|off
        self.baselines: list = []
        self.areas = list(areas or [area])
        self.scratch = f"{SCRATCH_ROOT}/{area}"
        self.prefix = f"ST_{area}_"
        self.level = f"{self.scratch}/L_{area}"
        self.checks: list = []
        self.covered: dict = {}
        self.stills: list = []
        self.artifacts: list = []
        self.notes: list = []
        self.metrics: dict = {}
        self.box = box()
        self._t0 = time.time()
        os.makedirs(out_dir, exist_ok=True)

    # --- calling ops
    def op(self, op_name: str, /, **args):
        """Call an op (recorded as covered). A multi-tick op returns a generator: `r = yield from t.op(...)`.
        The op's name is positional-only, so an op's own `name` argument passes through."""
        from .. import ops
        name = op_name
        t0 = time.time()
        self.covered.setdefault(name, 0)
        self.covered[name] += 1
        res = ops.call(name, **args)
        if inspect.isgenerator(res):
            return self._timed(res, name, t0)
        self.metrics.setdefault("op_ms", {}).setdefault(name, []).append(int((time.time() - t0) * 1000))
        return res

    def _timed(self, gen, name, t0):
        res = yield from gen
        self.metrics.setdefault("op_ms", {}).setdefault(name, []).append(int((time.time() - t0) * 1000))
        return res

    def call(self, op_name: str, /, **args):
        """t.op for a test that is not a generator: a multi-tick op is run to its end here (only for short ones:
        the editor does not tick meanwhile)."""
        res = self.op(op_name, **args)
        if inspect.isgenerator(res):
            try:
                while True:
                    next(res)
            except StopIteration as e:
                return e.value
        return res

    # --- recording results (never raise)
    def _add(self, name, ok, got=None, want=None, detail="", **extra):
        c = {"name": name, "ok": bool(ok), "ms": int((time.time() - self._t0) * 1000)}
        if got is not None or want is not None:
            c["got"], c["want"] = _jsonable(got), _jsonable(want)
        if detail:
            c["detail"] = str(detail)[:2000]
        c.update(extra)
        self.checks.append(c)
        return bool(ok)

    def check(self, name: str, got, want, tol: float = 1e-3) -> bool:
        """got == want (numbers within tol, lists and dicts element-wise; a dict compares the keys want gives)."""
        return self._add(name, _close(_jsonable(got), _jsonable(want), tol), got, want)

    def ok(self, name: str, cond, detail="") -> bool:
        return self._add(name, cond, detail=detail)

    def near(self, name: str, got, want, rel: float = 0.05) -> bool:
        """|got - want| <= rel * |want| (a relative check, for timings and exposure-like numbers)."""
        good = isinstance(got, (int, float)) and abs(float(got) - float(want)) <= rel * max(abs(float(want)), 1e-9)
        return self._add(name, good, got, want, detail=f"rel {rel}")

    def raises(self, name: str, op: str, /, code: str | None = None, **args) -> bool:
        """The op fails as an agent can act on: an OpError (with `code` when given) that has a hint or candidates."""
        from ..errors import OpError
        try:
            r = self.call(op, **args)
        except OpError as e:
            good = (code is None or e.code == code) and bool(e.hint or e.candidates)
            return self._add(name, good, {"code": e.code, "hint": e.hint, "candidates": e.candidates},
                             {"code": code or "<any>", "hint": "<some>"}, detail=e.message)
        except Exception as e:
            return self._add(name, False, type(e).__name__, "OpError", detail=traceback.format_exc()[-1500:])
        return self._add(name, False, r, "an OpError", detail=f"{op} did not fail")

    def idempotent(self, name: str, op: str, /, **args) -> bool:
        """Run the op twice with the same arguments: the second run reports changed: false (CONVENTIONS §5)."""
        self.call(op, **args)
        r = self.call(op, **args)
        if isinstance(r, dict) and "changed" in r:
            return self._add(name, r["changed"] is False, r.get("changed"), False)
        return self._add(name, True, detail=f"{op} returns no `changed`: only checked that a re-run does not fail")

    def skip(self, reason: str):
        raise Skip(reason)

    # --- pictures, numbers, words
    def still(self, name: str, camera: str | None = None, width: int = 960, height: int = 540):
        """A PNG through `camera` (a CineCamera's label) into the report folder: path = yield from t.still(...).
        Uses view.still (WP10) when the bridge has it, else look.still."""
        from .. import ops
        path = os.path.join(self.out, "stills", f"{self.area}_{name}.png").replace("\\", "/")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not camera:
            self.notes.append(f"still {name}: no camera given, skipped")
            return None
        if "view.still" in ops._OPS:
            res = self.op("view.still", out=path, camera=camera, width_px=width, height_px=height)
        else:
            res = self.op("look.still", camera_label=camera, path=path, width=width, height=height)
        if inspect.isgenerator(res):
            res = yield from res
        ok = os.path.isfile(path) and os.path.getsize(path) > 0
        self._add(f"still {name}", ok, detail=path if ok else f"no file at {path}: {res!r}"[:300])
        if ok:
            self.stills.append(path)
            self._baseline(name, path)
        return path if ok else None

    def _baseline(self, name: str, path: str):
        """Compare the still with its stored baseline (WP10): `different` fails, `differs` (render noise, a small
        change) passes with its status; the first run stores it (`created`). Off when WP10's module is absent."""
        if self.baseline_mode == "off":
            return
        try:
            from ..qa import baseline as _bl
            from ..ops.qa import baseline_root
        except ImportError:
            return
        try:
            r = _bl.check(baseline_root(), f"selftest/{self.area}", name, path, mode=self.baseline_mode,
                          diff_out=path[:-4] + ".diff.png", meta={"engine": self.box.get("engine")})
        except Exception:
            self._add(f"baseline {name}", False, detail=traceback.format_exc()[-1200:])
            return
        self.baselines.append({"name": name, **{k: r.get(k) for k in ("status", "ssim", "stops_shift", "diff")}})
        self._add(f"baseline {name}", r.get("status") != "different", r.get("ssim"),
                  (r.get("thresholds") or {}).get("min_ssim"), detail=r.get("status", ""))

    def artifact(self, path: str):
        self.artifacts.append(str(path))

    def metric(self, name: str, value, unit: str = ""):
        self.metrics[name] = {"value": _jsonable(value), "unit": unit}

    def note(self, text: str):
        self.notes.append(str(text))

    def path(self, name: str) -> str:
        """A file path in the report folder (for an artifact the test writes)."""
        p = os.path.join(self.out, name).replace("\\", "/")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p


# ------------------------------------------------------------------------------------------------------- discovery

def areas() -> dict:
    """{area: {"doc", "requires", "areas", "needs_level", "timeout", "error"?}} for every selftest module here."""
    out = {}
    here = os.path.dirname(__file__)
    for info in sorted(pkgutil.iter_modules([here]), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{__name__}.{info.name}")
        except Exception:
            out[info.name] = {"error": traceback.format_exc().strip().splitlines()[-1]}
            continue
        out[info.name] = {"doc": (inspect.getdoc(m) or "").split("\n\n")[0], "requires": list(getattr(m, "REQUIRES", [])),
                          "areas": list(getattr(m, "AREAS", [info.name])), "needs_level": getattr(m, "NEEDS_LEVEL", True),
                          "timeout": float(getattr(m, "TIMEOUT", DEFAULT_TIMEOUT)), "has_run": callable(getattr(m, "run", None))}
    return out


# ----------------------------------------------------------------------------------------------------------- level

def _eal():
    return unreal.EditorAssetLibrary


def _current_level() -> str:
    try:
        w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return w.get_path_name().split(".")[0] if w else ""
    except Exception:
        return ""


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _fresh_level(path: str) -> None:
    """A new empty level at `path`, opened: whatever was there is deleted first (never an overwrite dialog)."""
    if _current_level() == path:  # cannot delete the open level: step aside to the blank one
        _open_blank()
    if _eal().does_asset_exist(path):
        _eal().delete_asset(path)
    if not _les().new_level(path):
        raise RuntimeError(f"could not create the scratch level {path}")


def _open_blank() -> None:
    if _eal().does_asset_exist(BLANK):
        _les().load_level(BLANK)
    else:
        _les().new_level(BLANK)


def _leave(previous: str, scratch: str) -> str:
    """Back to the level that was open before (when it is a saved one outside the scratch area)."""
    if previous and previous.startswith("/") and not previous.startswith(SCRATCH_ROOT) and _eal().does_asset_exist(previous):
        _les().load_level(previous)
        return previous
    if _current_level().startswith(scratch):
        _open_blank()
    return _current_level()


# ------------------------------------------------------------------------------------------------------------- run

def _coverage(t: T) -> tuple:
    from .. import ops
    mine = sorted(n for n in ops._OPS if any(n.startswith(a + ".") for a in t.areas))
    return sorted(n for n in mine if n in t.covered), sorted(n for n in mine if n not in t.covered)


def run(area: str, out_dir: str, keep: bool = False, baseline: str = "auto"):
    """Run one area's selftest (a generator: the harness ticks the editor while the test does). Returns the report,
    also written to <out_dir>/<area>.json."""
    t0 = time.time()
    report = {"area": area, "ok": False, "status": "error", "passed": 0, "failed": 0, "checks": [], "ops_covered": [],
              "ops_missed": [], "stills": [], "artifacts": [], "notes": [], "metrics": {}, "errors": [], "extra": None}
    os.makedirs(out_dir, exist_ok=True)
    try:
        mod = importlib.import_module(f"{__name__}.{area}")
    except Exception:
        report["errors"].append({"where": "import", "error": traceback.format_exc()[-3000:]})
        return _finish(report, out_dir, t0)
    t = T(area, out_dir, keep, getattr(mod, "AREAS", None), baseline)
    report["box"] = t.box
    report["doc"] = (inspect.getdoc(mod) or "").split("\n\n")[0]
    caps = t.box["capabilities"]
    unmet = [r for r in getattr(mod, "REQUIRES", []) if not caps.get(r, True)]
    if unmet:
        report.update(status="skipped", ok=True, skipped=f"needs {', '.join(unmet)}")
        return _finish(report, out_dir, t0)
    previous = _current_level()
    timeout = float(getattr(mod, "TIMEOUT", DEFAULT_TIMEOUT))
    try:
        if getattr(mod, "NEEDS_LEVEL", True):
            _fresh_level(t.level)
            yield  # let the new level settle for a tick
        res = mod.run(t)
        if inspect.isgenerator(res):
            gen = res
            end = time.time() + timeout
            try:
                while True:
                    if time.time() > end:
                        gen.close()
                        raise TimeoutError(f"{area} selftest ran past its TIMEOUT of {timeout:.0f}s")
                    yield next(gen)
            except StopIteration as e:
                res = e.value
        report["extra"] = _jsonable(res)
        report["status"] = "done"
    except Skip as e:
        report.update(status="skipped", skipped=str(e))
    except Exception:
        report["errors"].append({"where": "run", "error": traceback.format_exc()[-4000:]})
    finally:
        report["checks"], report["stills"], report["artifacts"] = t.checks, t.stills, t.artifacts
        report["notes"], report["metrics"], report["baselines"] = t.notes, t.metrics, t.baselines
        report["ops_covered"], report["ops_missed"] = _coverage(t)
        try:
            report["level_after"] = _leave(previous, t.scratch)
            if not keep and _eal().does_directory_exist(t.scratch):
                _eal().delete_directory(t.scratch)
                report["cleaned"] = t.scratch
        except Exception:
            report["errors"].append({"where": "cleanup", "error": traceback.format_exc()[-1500:]})
    return _finish(report, out_dir, t0)


def _finish(report: dict, out_dir: str, t0: float) -> dict:
    report["passed"] = sum(1 for c in report["checks"] if c["ok"])
    report["failed"] = sum(1 for c in report["checks"] if not c["ok"])
    if report["status"] == "done":
        report["ok"] = report["failed"] == 0 and not report["errors"]
    elif report["status"] == "skipped":
        report["ok"] = not report["errors"]
    report["ms"] = int((time.time() - t0) * 1000)
    path = os.path.join(out_dir, f"{report['area']}.json")
    with open(path, "w") as f:
        json.dump(_jsonable(report), f, indent=1)
    report["report"] = path.replace("\\", "/")
    return report
