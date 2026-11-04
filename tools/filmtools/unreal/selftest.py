"""`film-ue selftest [area ...|all]`: run each area's acceptance test on the box (the bridge's selftest.run, one job
per area), then the area's client-side phase if it has one (filmtools/unreal/selftests/<area>.py: what only the
client can test, such as plan/apply through the SDK), pull the reports and stills, and write ONE report:

    selftest-reports/<time>/summary.json     {"ok", "box", "areas": {area: {...}}, "failures": [...]}
    selftest-reports/<time>/summary.md       the same for reading: per area status, failures with got/want, stills
    selftest-reports/<time>/<area>.json      each area's full report;  stills/<area>_<name>.png

A client phase is `def run(ue, t)` with ue the SDK (filmtools.unreal.sdk.Unreal) and t a ClientT (check, ok, note,
metric, skip), like the bridge-side T without ops coverage.
"""
from __future__ import annotations

import importlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path


class Skip(Exception):
    pass


class ClientT:
    def __init__(self, area: str):
        self.area = area
        self.prefix = f"ST_{area}_"
        self.scratch = f"/Game/_Selftest/{area}_client"
        self.checks, self.notes, self.metrics = [], [], {}
        self._t0 = time.time()

    def _add(self, name, ok, got=None, want=None, detail=""):
        c = {"name": name, "ok": bool(ok), "ms": int((time.time() - self._t0) * 1000)}
        if got is not None or want is not None:
            c["got"], c["want"] = got, want
        if detail:
            c["detail"] = str(detail)[:2000]
        self.checks.append(c)
        return bool(ok)

    def check(self, name, got, want, tol: float = 1e-3) -> bool:
        def close(g, w):
            if isinstance(w, bool) or isinstance(g, bool):
                return g == w
            if isinstance(w, (int, float)) and isinstance(g, (int, float)):
                return math.isclose(float(g), float(w), abs_tol=tol)
            if isinstance(w, (list, tuple)) and isinstance(g, (list, tuple)):
                return len(g) == len(w) and all(close(a, b) for a, b in zip(g, w))
            if isinstance(w, dict) and isinstance(g, dict):
                return all(k in g and close(g[k], v) for k, v in w.items())
            return g == w
        return self._add(name, close(got, want), got, want)

    def ok(self, name, cond, detail="") -> bool:
        return self._add(name, cond, detail=detail)

    def note(self, text):
        self.notes.append(str(text))

    def metric(self, name, value, unit=""):
        self.metrics[name] = {"value": value, "unit": unit}

    def skip(self, reason):
        raise Skip(reason)


def client_phase(area: str, ue) -> dict | None:
    try:
        mod = importlib.import_module(f"filmtools.unreal.selftests.{area}")
    except ModuleNotFoundError as e:
        if e.name and e.name.endswith(f"selftests.{area}") or e.name == "filmtools.unreal.selftests":
            return None
        raise
    t = ClientT(area)
    out = {"status": "done"}
    try:
        res = mod.run(ue, t)
        out["extra"] = res
    except Skip as e:
        out.update(status="skipped", skipped=str(e))
    except Exception:
        out.update(status="error", error=traceback.format_exc()[-3000:])
    out.update(checks=t.checks, notes=t.notes, metrics=t.metrics,
               passed=sum(1 for c in t.checks if c["ok"]), failed=sum(1 for c in t.checks if not c["ok"]))
    out["ok"] = out["status"] != "error" and out["failed"] == 0
    return out


def _areas(ue, wanted: list) -> tuple[list, dict]:
    listing = ue.call("selftest.list")
    known = listing["areas"]
    if not wanted or wanted == ["all"]:
        from . import selftest_plan
        order = [n for n in selftest_plan.plan()["order"] if n in known]
        return order + sorted(n for n in known if n not in order), listing
    from .errors import close
    bad = [a for a in wanted if a not in known]
    if bad:
        raise SystemExit(f"no selftest {', '.join(bad)} on the box; have: {', '.join(sorted(known))}"
                         + (f" (did you mean {', '.join(close(bad[0], known))}?)" if close(bad[0], known) else "")
                         + "\n  (film-ue install first if you just added one)")
    return wanted, listing


def run_all(ue, wanted: list, out: Path, keep=False, timeout=3600, pull=True, log=print, baseline="auto",
            keep_going: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    areas, listing = _areas(ue, wanted)
    summary = {"ok": True, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "capabilities": listing.get("capabilities"),
               "areas": {}, "failures": [], "out": str(out)}
    box_dir = ""
    from .sdk import OpError
    for area in areas:
        info = listing["areas"].get(area, {})
        log(f"[selftest] {area}: running (timeout {info.get('timeout', '?')} s) ...")
        t0 = time.time()
        rep: dict
        if info.get("error"):
            rep = {"area": area, "ok": False, "status": "error", "errors": [{"where": "import", "error": info["error"]}],
                   "checks": [], "passed": 0, "failed": 0}
        else:
            try:
                job = ue.call("selftest.run", wait=False, area=area, out_dir=box_dir, keep=keep, baseline=baseline)
                rep = job.wait(timeout, every=2.0) if hasattr(job, "wait") else job
            except OpError as e:
                rep = {"area": area, "ok": False, "status": "error", "checks": [], "passed": 0, "failed": 0,
                       "errors": [{"where": "bridge", "error": e.problem.text(True)}]}
        if rep.get("report") and not box_dir:
            box_dir = rep["report"].rsplit("/", 1)[0]
        try:
            cp = client_phase(area, ue)
        except Exception:
            cp = {"ok": False, "status": "error", "error": traceback.format_exc()[-2000:], "checks": [], "passed": 0,
                  "failed": 0}
        if cp:
            rep["client"] = cp
        if pull:
            rep["local_stills"] = _pull(rep.get("stills") or [], out / "stills", log)
        (out / f"{area}.json").write_text(json.dumps(rep, indent=1, default=str))
        ok = bool(rep.get("ok")) and (not cp or cp["ok"])
        summary["areas"][area] = {"ok": ok, "status": rep.get("status"), "passed": rep.get("passed", 0) +
                                  (cp or {}).get("passed", 0), "failed": rep.get("failed", 0) + (cp or {}).get("failed", 0),
                                  "skipped": rep.get("skipped", ""), "ms": int((time.time() - t0) * 1000),
                                  "ops_missed": rep.get("ops_missed", []), "stills": rep.get("local_stills", []),
                                  "errors": len(rep.get("errors", [])) + (1 if (cp or {}).get("error") else 0),
                                  "baselines": rep.get("baselines", []),
                                  "doc": info.get("doc", "")}
        for c in rep.get("checks", []) + (cp or {}).get("checks", []):
            if not c["ok"]:
                summary["failures"].append({"area": area, **c})
        for e in rep.get("errors", []) + ([{"where": "client", "error": cp["error"]}] if (cp or {}).get("error") else []):
            summary["failures"].append({"area": area, "name": f"ERROR in {e['where']}", "ok": False,
                                        "detail": e["error"][-1500:]})
        summary["ok"] = summary["ok"] and ok
        a = summary["areas"][area]
        log(f"[selftest] {area}: {a['status']} {'OK' if ok else 'FAIL'}  {a['passed']} passed, {a['failed']} failed"
            + (f", skipped: {a['skipped']}" if a["skipped"] else "") + f"  ({a['ms'] / 1000:.0f} s)")
        from .selftest_plan import GATES
        if not ok and area in GATES and not keep_going and len(areas) > 1:
            rest = areas[areas.index(area) + 1:]
            summary["stopped"] = {"after": area, "not_run": rest}
            log(f"[selftest] {area} is a gate and failed: not running {', '.join(rest)} (--keep-going runs them)")
            break
    summary["box_dir"] = box_dir
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "summary.md").write_text(markdown(summary))
    return summary


def _pull(paths: list, dest: Path, log) -> list:
    from . import client
    got = []
    for p in paths:
        local = dest / p.rsplit("/", 1)[-1]
        try:
            client.pull(p, str(local))
            got.append(str(local))
        except (SystemExit, OSError) as e:
            log(f"[selftest] could not pull {p}: {e}")
    return got


def markdown(s: dict) -> str:
    out = [f"# Selftest report ({s['started']})", "", f"**{'ALL OK' if s['ok'] else 'FAILURES'}**  "
           f"capabilities: {', '.join(k for k, v in (s.get('capabilities') or {}).items() if v)}", "",
           "| area | status | passed | failed | time | ops not exercised |", "|---|---|---|---|---|---|"]
    for area, a in s["areas"].items():
        st = ("ok" if a["ok"] else "**FAIL**") + f" ({a['status']}{': ' + a['skipped'] if a['skipped'] else ''})"
        missed = ", ".join(a["ops_missed"][:8]) + (" ..." if len(a["ops_missed"]) > 8 else "")
        out.append(f"| {area} | {st} | {a['passed']} | {a['failed']} | {a['ms'] / 1000:.0f} s | {missed} |")
    if s.get("stopped"):
        out += ["", f"**Stopped after the gate `{s['stopped']['after']}` failed**; not run: "
                    f"{', '.join(s['stopped']['not_run'])} (`film-ue selftest --keep-going` runs them anyway)."]
    if s["failures"]:
        out += ["", "## Failures", ""]
        for f in s["failures"]:
            line = f"- **{f['area']}** {f['name']}"
            if "got" in f:
                line += f": got `{json.dumps(f.get('got'), default=str)[:200]}`, want `{json.dumps(f.get('want'), default=str)[:200]}`"
            out.append(line)
            if f.get("detail"):
                out.append("  ```\n  " + f["detail"][-800:].replace("\n", "\n  ") + "\n  ```")
    stills = [(a, p) for a, x in s["areas"].items() for p in x.get("stills", [])]
    if stills:
        out += ["", "## Stills", ""] + [f"- {a}: {p}" for a, p in stills]
    return "\n".join(out) + "\n"


def main(a) -> int:
    if a.areas == ["plan"]:
        from . import selftest_plan as sp
        p = sp.plan()
        print(json.dumps(p, indent=1) if a.json else sp.markdown(p) if getattr(a, "md", False) else sp.text(p))
        return 0
    from .sdk import Unreal
    ue = Unreal()
    if a.list or a.areas == ["list"]:
        r = ue.call("selftest.list")
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            caps = r.get("capabilities", {})
            print("capabilities: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in caps.items()))
            for area, i in sorted(r["areas"].items()):
                req = i.get("requires") or []
                unmet = [x for x in req if not caps.get(x, True)]
                print(f"  {area:<12} {('BROKEN: ' + i['error']) if i.get('error') else i.get('doc', '')[:100]}"
                      + (f"  needs {', '.join(req)}" if req else "") + ("  (will skip)" if unmet else ""))
        return 0
    out = Path(a.out or Path("selftest-reports") / time.strftime("%Y%m%d-%H%M%S"))
    log = (lambda m: sys.stderr.write(m + "\n")) if a.json else print
    s = run_all(ue, a.areas, out, a.keep, a.timeout, not a.no_pull, log, a.baseline, a.keep_going)
    if a.json:
        print(json.dumps(s, indent=1, default=str))
    else:
        print(f"\n{'ALL OK' if s['ok'] else 'FAILURES'}: {out / 'summary.md'}")
    return 0 if s["ok"] else 1
