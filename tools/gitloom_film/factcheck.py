"""The facts gate: every string a scene puts on screen is verbatim from GitLoom's docs and site, approved copy,
illustrative, or her voice.

A scene declares its text in app/src/scenes/<id>.strings.json (a JSON array of strings) and imports that file, so no
string is written twice. A string passes if, after typographic punctuation is folded to its typed form (’ → ', “ ” → ",
… → ...):

  1. it equals, or is a substring of, a `verbatim` or `copy` entry of data/facts.json;
  2. it equals, or is a substring of, an `illustrative` entry;
  3. it equals a line of hers or a word of hers in data/vo.json, as displayed (a word carries its punctuation); or
  4. it equals a scene id or an act name in data/script.json.

Anything else is printed with its file, and the exit code is 1.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import APP, DATA, ROOT

SCENES = APP / "src" / "scenes"
KINDS = ("verbatim", "copy", "illustrative")

# Display type uses typographic punctuation and typed input keeps typewriter quotes. The sheet and vo.json hold the
# typed forms, so both sides are folded to them before anything is compared.
_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."})


def norm(s: str) -> str:
    return s.translate(_FOLD)


@dataclass(frozen=True)
class Allowed:
    """What a string may be, everything already folded by `norm`."""
    verbatim: tuple[str, ...]  # equal to an entry, or a substring of one
    copy: tuple[str, ...]  # likewise
    illustrative: tuple[str, ...]  # likewise
    voice: frozenset[str]  # her lines and her words: equality only
    labels: frozenset[str]  # scene ids and act names: equality only


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: {e}") from None


def load_facts(path: Path = DATA / "facts.json") -> dict:
    facts = _read_json(path)
    if not isinstance(facts, dict):
        raise SystemExit(f"{path}: expected an object with the lists {', '.join(KINDS)}")
    for kind in KINDS:
        entries = facts.get(kind)
        if not isinstance(entries, list):
            raise SystemExit(f"{path}: '{kind}' must be a list")
        for i, e in enumerate(entries):
            if not (isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"]):
                raise SystemExit(f"{path}: {kind}[{i}] needs a non-empty text")
    return facts


def build_allowed(facts: dict, vo: dict, script: dict) -> Allowed:
    voice = {norm(l["text"]) for l in vo["lines"]} | {norm(w["w"]) for l in vo["lines"] for w in l.get("words", [])}
    labels = {norm(s) for a in script["acts"] for s in (a["name"], *a["scenes"])}

    def texts(kind: str) -> tuple[str, ...]:
        return tuple(norm(e["text"]) for e in facts[kind])

    return Allowed(texts("verbatim"), texts("copy"), texts("illustrative"), frozenset(voice), frozenset(labels))


def load_allowed(facts: Path = DATA / "facts.json", vo: Path = DATA / "vo.json",
                 script: Path = DATA / "script.json") -> Allowed:
    return build_allowed(load_facts(facts), _read_json(vo), _read_json(script))


def classify(s: str, allowed: Allowed) -> str | None:
    """Which rule lets `s` through: 'verbatim', 'copy', 'illustrative', 'vo' or 'label'; None if none does."""
    n = norm(s)
    for kind in KINDS:
        if any(n in t for t in getattr(allowed, kind)):
            return kind
    if n in allowed.voice:
        return "vo"
    if n in allowed.labels:
        return "label"
    return None


def read_strings(path: Path) -> list[str]:
    """A scene's strings file, or a ValueError saying what is wrong with it."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ValueError(f"cannot be read ({e})") from None
    except ValueError as e:
        raise ValueError(f"not valid JSON ({e})") from None
    if not (isinstance(data, list) and all(isinstance(s, str) for s in data)):
        raise ValueError("not a JSON array of strings")
    return data


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check that every string a scene shows is on the facts sheet or is hers")
    ap.add_argument("--scenes", type=Path, default=SCENES,
                    help="where the <scene>.strings.json files are (default: app/src/scenes)")
    a = ap.parse_args(argv)
    allowed = load_allowed()
    files = sorted(a.scenes.rglob("*.strings.json")) if a.scenes.is_dir() else []
    total = bad = unreadable = 0
    for f in files:
        try:
            strings = read_strings(f)
        except ValueError as e:
            print(f"{_shown(f)}: {e}")
            unreadable += 1
            continue
        total += len(strings)
        for s in dict.fromkeys(strings):  # a repeated string is reported once
            if classify(s, allowed) is None:
                print(f"{_shown(f)}: {json.dumps(s, ensure_ascii=False)}")
                bad += 1
    if bad or unreadable:
        why = f"{bad} of {total} strings are not verbatim, approved copy, illustrative or her words"
        if unreadable:
            why += f"; {unreadable} unreadable file{'s' if unreadable > 1 else ''}"
        print(f"facts FAILED: {why}", file=sys.stderr)
        return 1
    print(f"facts OK ({total} strings in {len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
