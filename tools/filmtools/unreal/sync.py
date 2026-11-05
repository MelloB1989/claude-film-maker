"""What a box keeps in S3, both ways: the project, the derived-data cache (compiled shaders), the engine and the Epic
sign-in. A temporary box starts from S3 and puts back what it changed before it ends.

    film-ue sync project up|down [--delete] [--allow-dirty] [--stop-editor] [--dry-run]
    film-ue sync ddc save|restore [--version 5.8.4] [--dry-run]
    film-ue sync epic save|restore|status
    film-ue sync engine restore --engine-s3 S3 --version 5.8.4
    film-ue sync status                 what is where (S3 sizes and dates, the box's copies)

Where (the box's settings): `bucket`; the project under s3://<bucket>/ue-projects/<project name>/ (or `project_s3`),
the DDC under s3://<bucket>/ue-linux/ddc/<engine version>/ (or `ddc_s3`), the sign-in at `epic_s3`. Commands run on
the box (its role reads and writes the bucket), as the editor's user. Everything has a --dry-run that prints the exact
script instead of running it.

  project up      box -> S3: Content, Config, Plugins (source, and a C++ plugin's Linux build), the .uproject. Refused while the editor
                  holds unsaved packages (they are not on disk yet): save them (assets.save_all / level.save) or pass
                  --allow-dirty. Saved/, Intermediate/, DerivedDataCache/ and Binaries/ never travel.
  project down    S3 -> box. The editor must not be running (it holds files open): --stop-editor stops it first.
  ddc save        box -> S3: the Zen store and the file DDCs (engine and project) after shaders compiled, so the next
                  box skips the ~20 min first-open compile. Best with the editor stopped (the Zen store is copied as
                  is otherwise).
  ddc restore     S3 -> box, before the editor's first start.
"""
from __future__ import annotations

import json
import shlex

from . import workstation as ws
from .boxpaths import BoxPaths

PROJECT_EXCLUDES = ("Saved/*", "Intermediate/*", "DerivedDataCache/*", "Binaries/*", "*/Binaries/*",
                    "*/Intermediate/*", ".vs/*", "*.sln", "*.code-workspace",
                    "Content/_Selftest/*")  # what film-ue selftest makes (and cleans up) never reaches the project
# A C++ plugin's Linux build travels with its source (film-ue plugin-build made it against the same engine): a box
# that got the source alone could not start the editor (a module it cannot load)
PROJECT_INCLUDES = ("Plugins/*/Binaries/Linux/*",)
# Face-derived assets of a real person (the operator's MetaHuman, round 3): they stay on the box and Epic's cloud and
# are never synced up. Applied last, so no include can bring them back; a `private_paths` list in the box settings adds more.
PRIVATE_EXCLUDES = ("Content/Host/OperatorCapture/*", "Content/Host/Host_Op*", "Content/Host/Unpacked/Host/*",
                    "Content/Host/Unpacked/Host_Op*", "*/OperatorCapture/*")
ZEN = "$HOME/.config/Epic/UnrealEngine/Common/Zen/Data"


def _bucket() -> str:
    b = ws.conf().get("bucket")
    if not b:
        raise SystemExit("no bucket set: film-ue set --bucket NAME (one the box's role can read and write)")
    return b


def project_name() -> str:
    return BoxPaths.current().name()


def project_s3() -> str:
    return ws.conf().get("project_s3") or f"s3://{_bucket()}/ue-projects/{project_name()}"


def ddc_s3(version: str = "") -> str:
    c = ws.conf()
    return c.get("ddc_s3") or f"s3://{_bucket()}/ue-linux/ddc/{version or c.get('engine_version') or '5.8.4'}"


def private_paths() -> tuple:
    extra = ws.conf().get("private_paths") or []
    return PRIVATE_EXCLUDES + tuple(extra if isinstance(extra, (list, tuple)) else [extra])


def _excl() -> str:
    return " ".join([f"--exclude {shlex.quote(x)}" for x in PROJECT_EXCLUDES] +
                    [f"--include {shlex.quote(x)}" for x in PROJECT_INCLUDES] +  # the later filter wins
                    [f"--exclude {shlex.quote(x)}" for x in private_paths()])  # so the private ones go last


def project_script(direction: str, delete: bool = False) -> str:
    """The shell (bash, on the box, as the editor's user) for a project sync."""
    if direction not in ("up", "down"):
        raise SystemExit(f"sync project {direction}: up (box -> S3) or down (S3 -> box)")
    pd, s3 = shlex.quote(ws.conf()["project_dir"]), shlex.quote(project_s3())
    region = shlex.quote(ws.conf()["region"])
    d = " --delete" if delete else ""
    src, dst = (pd, s3) if direction == "up" else (s3, pd)
    return (f"mkdir -p {pd}\n"
            f"aws s3 sync --only-show-errors --no-progress --region {region}{d} {_excl()} {src} {dst}\n"
            f"echo synced={direction}\n")


def ddc_script(direction: str, version: str = "") -> str:
    if direction not in ("save", "restore"):
        raise SystemExit(f"sync ddc {direction}: save (box -> S3) or restore (S3 -> box)")
    c = ws.conf()
    s3, region = ddc_s3(version), shlex.quote(c["region"])
    engine = c.get("engine_dir") or "/srv/ue/engine"
    pairs = [(ZEN, f"{s3}/zen-data"), (f"{engine}/Engine/DerivedDataCache", f"{s3}/engine-ddc"),
             (BoxPaths.current().ddc(), f"{s3}/project-ddc")]
    lines = []
    for local, remote in pairs:
        q_local = f'"{local}"'  # $HOME expands on the box
        if direction == "save":
            lines.append(f"[ -d {q_local} ] && aws s3 sync --only-show-errors --no-progress --region {region} "
                         f"{q_local} {shlex.quote(remote)} || echo skipped={local}")
        else:
            lines.append(f"mkdir -p {q_local} && aws s3 sync --only-show-errors --no-progress --region {region} "
                         f"{shlex.quote(remote)} {q_local}")
    lines.append(f"echo ddc={direction}")
    return "\n".join(lines) + "\n"


def _editor_running() -> bool:
    if not ws.linux():
        return "UnrealEditor" in ws.ps("Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -Expand Name")
    return ws.sh(f"systemctl is-active {shlex.quote(ws.conf().get('service') or 'ue-editor')} || true", 60,
                 root=True).strip() == "active"


def _dirty() -> dict:
    from . import client
    try:
        r = client.op("editor.describe", timeout=60)
    except SystemExit:
        return {}
    return (r.get("result") or {}).get("dirty") or {} if r.get("ok") else {}


def project(direction: str, *, delete: bool = False, allow_dirty: bool = False, stop_editor: bool = False,
            dry_run: bool = False) -> dict:
    if not ws.linux():
        raise SystemExit("project sync runs on a Linux box (a Windows workstation: push-dir/pull-dir)")
    script = project_script(direction, delete)
    if dry_run:
        return {"dry_run": True, "script": script, "s3": project_s3()}
    if direction == "up" and not allow_dirty:
        d = _dirty()
        if d.get("maps") or d.get("content"):
            raise SystemExit(f"unsaved packages in the editor ({len(d.get('maps', []))} levels, "
                             f"{len(d.get('content', []))} assets): they are not on disk yet. Save them "
                             "(film-ue op assets.save_all / level.save) or pass --allow-dirty")
    if direction == "down" and _editor_running():
        if not stop_editor:
            raise SystemExit("the editor is running and holds the project's files: --stop-editor, or film-ue editor stop")
        ws.editor("stop")
    out = ws.sh(script, 7200)
    return {"direction": direction, "s3": project_s3(), "ok": f"synced={direction}" in out}


def ddc(direction: str, *, version: str = "", dry_run: bool = False) -> dict:
    if not ws.linux():
        raise SystemExit("DDC sync is for a Linux box")
    script = ddc_script(direction, version)
    if dry_run:
        return {"dry_run": True, "script": script, "s3": ddc_s3(version)}
    out = ws.sh(script, 7200)
    return {"direction": direction, "s3": ddc_s3(version), "ok": f"ddc={direction}" in out,
            "skipped": [line.split("=", 1)[1] for line in out.splitlines() if line.startswith("skipped=")]}


def epic(action: str) -> str:
    """The Epic sign-in (ue-epic.sh on the box): save, restore or status. Never prints the credential."""
    if action not in ("save", "restore", "status"):
        raise SystemExit(f"sync epic {action}: save, restore or status")
    from . import linuxbox
    linuxbox.upload_kit()
    return linuxbox.step("epic", action, timeout=300).strip()


def engine(engine_s3: str, version: str, dest: str = "/srv/ue/engine") -> str:
    from . import linuxbox
    linuxbox.upload_kit()
    return linuxbox.step("engine", engine_s3, version, dest, timeout=3600).strip()


def status() -> dict:
    """What is where: the S3 copies (size, newest object) and whether the box has each."""
    c = ws.conf()
    region = shlex.quote(c["region"])
    rows = {"project": project_s3(), "ddc": ddc_s3(), "epic": c.get("epic_s3") or ""}
    script = []
    for k, s3 in rows.items():
        if s3:
            script.append(f"echo {k}=$(aws s3 ls --recursive --summarize --region {region} {shlex.quote(s3)} 2>/dev/null"
                          " | awk '/Total Objects/{o=$3} /Total Size/{s=$3} END{print o\"/\"s}')")
    out = ws.sh("\n".join(script), 600) if script else ""
    got = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    res = {}
    for k, s3 in rows.items():
        objs, _, size = (got.get(k) or "/").partition("/")
        res[k] = {"s3": s3 or None, "objects": int(objs) if objs.isdigit() else 0,
                  "bytes": int(size) if size.isdigit() else 0}
    return json.loads(json.dumps(res))
