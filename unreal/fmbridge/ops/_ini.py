"""Pure helpers for the project's own files (no `unreal`): Unreal .ini values and the .uproject's plugin list, edited
in place so everything else in the file (comments, order, +/- array lines, other sections) stays as it was."""
from __future__ import annotations

import json
import re

SECTION = re.compile(r"^\s*\[(.+)\]\s*$")


def ini_get(text: str, section: str, key: str):
    """The value of key in [section] (the last plain `key=` line wins, as Unreal reads it), or None."""
    cur, val = None, None
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            cur = m.group(1).strip()
            continue
        if cur == section and "=" in line and not line.lstrip().startswith((";", "#", "+", "-", ".", "!")):
            k, v = line.split("=", 1)
            if k.strip() == key:
                val = v.strip()
    return val


def ini_set(text: str, section: str, key: str, value) -> tuple[str, bool]:
    """Set key=value in [section] (adding the section at the end if missing). Returns (new text, changed)."""
    value = ("True" if value else "False") if isinstance(value, bool) else str(value)
    if ini_get(text, section, key) == value:
        return text, False
    lines = text.splitlines()
    out, cur, done, sec_end = [], None, False, None
    for i, line in enumerate(lines):
        m = SECTION.match(line)
        if m:
            if cur == section and not done:
                sec_end = len(out)
            cur = m.group(1).strip()
        if cur == section and not done and "=" in line and not line.lstrip().startswith((";", "#", "+", "-", ".", "!")):
            k = line.split("=", 1)[0]
            if k.strip() == key:
                out.append(f"{key}={value}")
                done = True
                continue
        out.append(line)
    if not done:
        if cur == section:  # the section runs to the end of the file
            sec_end = len(out)
        if sec_end is not None:
            while sec_end > 0 and not out[sec_end - 1].strip():
                sec_end -= 1
            out.insert(sec_end, f"{key}={value}")
        else:
            if out and out[-1].strip():
                out.append("")
            out += [f"[{section}]", f"{key}={value}"]
    return "\n".join(out) + "\n", True


def uproject_plugins(text: str) -> dict:
    """{plugin name: enabled} as the .uproject lists them (plugins it does not list follow their own defaults)."""
    d = json.loads(text)
    return {p["Name"]: bool(p.get("Enabled", True)) for p in d.get("Plugins", []) if "Name" in p}


def uproject_set_plugins(text: str, enable=(), disable=()) -> tuple[str, list]:
    """Turn plugins on or off in the .uproject. Returns (new text, [names changed])."""
    d = json.loads(text)
    plugins = d.setdefault("Plugins", [])
    by_name = {p.get("Name"): p for p in plugins}
    changed = []
    for name, on in [(n, True) for n in enable] + [(n, False) for n in disable]:
        p = by_name.get(name)
        if p is None:
            p = {"Name": name, "Enabled": on}
            plugins.append(p)
            by_name[name] = p
            changed.append(name)
        elif bool(p.get("Enabled", True)) != on:
            p["Enabled"] = on
            changed.append(name)
    if not changed:
        return text, []
    return json.dumps(d, indent="\t") + "\n", changed
