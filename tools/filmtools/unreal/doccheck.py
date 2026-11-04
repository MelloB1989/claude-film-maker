"""Docs that cannot drift: every `film-ue <area> <verb> --flag ...` line in the docs (docs/unreal/*.md, examples/**/
README.md, .claude/skills/**/SKILL.md, unreal/README.md) is parsed against the op schema: the area, the verb and every
flag must exist. `film-ue dx docs` lists the problems; tests/test_ue_dx.py holds WP11's own docs to it.

Lines with placeholders (`...`, `<x>`, `NAME`) are checked only up to them; required arguments may be left out
(docs abbreviate); a line marked `# exit 2` or `dx-docs: skip` is a deliberate bad call; film-ue's own commands (plan, apply, selftest, ...) are not op commands and are skipped."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from . import opcli, schema as _schema

ROOT = _schema.ROOT
GLOBS = ("docs/unreal/*.md", "examples/**/README.md", ".claude/skills/**/SKILL.md", "unreal/README.md")


def commands(text: str) -> list:
    """(line number, argv after film-ue) for each film-ue command line in a markdown text (code and inline code)."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if "# exit 2" in line or "dx-docs: skip" in line:  # a deliberately bad call (it shows the error)
            continue
        for m in re.finditer(r"(?:^|`|\s)film-ue\s+([^`\n|]+)", line):
            cmd = m.group(1).split(" #")[0].strip()
            try:
                argv = shlex.split(cmd)
            except ValueError:
                continue
            out.append((n, argv))
    return out


def _clean(argv: list) -> list | None:
    out, skip = [], False
    for w in argv:
        if skip:
            skip = False
            continue
        if w == "--box":
            skip = True
            continue
        if w.startswith("--box="):
            continue
        if "..." in w or re.search(r"<[^>]+>", w) or w in ("|", "&&", ";", ">", "2>&1") or w.startswith(">"):
            if out and out[-1].startswith("--") and "=" not in out[-1]:
                out.append("X")  # the placeholder was this flag's value
            break
        out.append(w)
    return out


def check(paths=None, ix: dict | None = None) -> list:
    """[(file, line, command, problem)]"""
    ix = ix or _schema.index(_schema.load())
    parser = opcli.build(ix)
    files = paths or sorted({p for g in GLOBS for p in ROOT.glob(g)})
    problems = []
    for f in files:
        f = Path(f)
        for n, argv in commands(f.read_text(errors="replace")):
            argv = _clean(argv)
            if not argv or argv[0] not in ix["areas"] or argv[0] in BUILTIN:
                continue
            if len(argv) < 2 or argv[1].startswith("-"):
                continue
            if opcli.extension(argv, ix) or argv[0] in opcli.EXTENSIONS and f"{argv[0]}.{argv[1]}" not in ix["ops"]:
                continue  # an area's hand-written command (film-ue render validate ...)
            rel = f.relative_to(ROOT).as_posix() if f.is_relative_to(ROOT) else str(f)
            name = f"{argv[0]}.{argv[1]}"
            if name not in ix["ops"]:
                from .errors import close
                problems.append((rel, n, " ".join(argv), f"no op {name}" + (f" (did you mean {', '.join(close(name, ix['ops']))}?)"
                                                                            if close(name, ix["ops"]) else "")))
                continue
            try:
                ns, extra = parser.parse_known_args(argv)
            except opcli.Usage as u:
                problems.append((rel, n, " ".join(argv), u.problem.message))
                continue
            bad = [w for w in extra if w.startswith("--")]
            if bad:
                flags = ["--" + p["flag"] for p in ix["ops"][name]["params"]]
                from .errors import close
                problems.append((rel, n, " ".join(argv), f"{name} has no {bad[0]}" +
                                 (f" (did you mean {', '.join(close(bad[0], flags))}?)" if close(bad[0], flags) else "")))
    return problems


# film-ue's own commands that share no name with an area today; kept here so a future area named like one is skipped
BUILTIN = {"set", "up", "down", "status", "password", "install", "health", "tunnel", "close", "provision", "editor",
           "desktop", "epic-login", "poc", "ops", "op", "exec", "screen", "gui", "push", "pull", "pull-dir", "log",
           "describe", "job", "plan", "apply", "selftest", "dx"}
