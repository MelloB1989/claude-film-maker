"""The facts gate: every string a scene puts on screen is verbatim from GitLoom's docs and site, approved copy,
illustrative, or her voice.

A scene declares its text in app/src/scenes/<id>.strings.json (a JSON array of strings) and imports that file, so no
string is written twice. The gate can see no other text, so a scene module (scenes/<id>.ts for a scene id in
data/script.json) without its strings file beside it, or that does not import it, fails; harness scenes (_*.ts), the
animatic's card.ts and helper modules are not scene ids. A --scenes directory that does not exist fails too. A string
passes if, after typographic punctuation is folded to its typed form (’ ‘ → ',
“ ” → ", … → ...):

  1. it equals, or is a substring of, a `verbatim` or `copy` entry of data/facts.json;
  2. it equals, or is a substring of, an `illustrative` entry, or matches in full one of the sheet's
     `illustrative_patterns` (the shape of a value that is invented: a float numeral, a namespace row, a commit hash);
     a substring must start and end on token boundaries: no letter, digit or underscore just outside it on either side,
     and no `.` or `,` that carries a number on across its edge, so "456/49" of "456/499", "preference 10" of
     "preference 100" and "Storage is fre" of "Storage is free." fail;
  3. its words, with the punctuation and whitespace at its ends and on each word stripped, are a contiguous run of
     whole words of one line of hers in data/vo.json (a whole line, a phrase of one, or a single word); or
  4. it equals a scene id or an act name in data/script.json.

Anything else is printed with its file, and the exit code is 1.
"""
import argparse
import json
import re
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


_EDGES = re.compile(r"\A[\W_]+|[\W_]+\Z")  # punctuation and whitespace at either end


def _words(s: str) -> tuple[str, ...]:
    """`s` as whole words: the ends of `s`, and of each word, stripped of punctuation. A mark standing alone between
    words is an empty word, so it matches nothing of hers."""
    return tuple(_EDGES.sub("", w) for w in _EDGES.sub("", s).split())


def _has_run(line: tuple[str, ...], run: tuple[str, ...]) -> bool:
    return any(line[i:i + len(run)] == run for i in range(len(line) - len(run) + 1))


@dataclass(frozen=True)
class Allowed:
    """What a string may be, everything already folded by `norm`."""
    verbatim: tuple[str, ...]  # equal to an entry, or a substring of one
    copy: tuple[str, ...]  # likewise
    illustrative: tuple[str, ...]  # likewise
    patterns: tuple[re.Pattern[str], ...]  # illustrative values by shape: the whole string must match
    lines: tuple[tuple[str, ...], ...]  # each line of hers, as words: a string may be any run of them
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
    patterns = facts.get("illustrative_patterns")
    if not isinstance(patterns, list):
        raise SystemExit(f"{path}: 'illustrative_patterns' must be a list")
    for i, e in enumerate(patterns):
        if not (isinstance(e, dict) and isinstance(e.get("pattern"), str) and e["pattern"]
                and isinstance(e.get("why"), str) and e["why"]):
            raise SystemExit(f"{path}: illustrative_patterns[{i}] needs a pattern and a why")
        try:
            re.compile(e["pattern"], re.ASCII)
        except re.error as err:
            raise SystemExit(f"{path}: illustrative_patterns[{i}] is not a regex ({err})") from None
    return facts


def build_allowed(facts: dict, vo: dict, script: dict) -> Allowed:
    lines = tuple(_words(norm(l["text"])) for l in vo["lines"])
    labels = {norm(s) for a in script["acts"] for s in (a["name"], *a["scenes"])}
    patterns = tuple(re.compile(p["pattern"], re.ASCII) for p in facts.get("illustrative_patterns", ()))

    def texts(kind: str) -> tuple[str, ...]:
        return tuple(norm(e["text"]) for e in facts[kind])

    return Allowed(texts("verbatim"), texts("copy"), texts("illustrative"), patterns, lines, frozenset(labels))


def load_allowed(facts: Path = DATA / "facts.json", vo: Path = DATA / "vo.json",
                 script: Path = DATA / "script.json") -> Allowed:
    return build_allowed(load_facts(facts), _read_json(vo), _read_json(script))


def _within(n: str) -> re.Pattern[str]:
    """`n` as a substring on token boundaries: no word character just before or after it, no digit and `.`/`,` before
    it (that ends a number it would cut) and no `.`/`,` and digit after it (that carries the number on)."""
    return re.compile(r"(?<!\w)(?<!\d[.,])" + re.escape(n) + r"(?!\w|[.,]\d)")


def classify(s: str, allowed: Allowed) -> str | None:
    """Which rule lets `s` through: 'verbatim', 'copy', 'illustrative', 'vo' or 'label'; None if none does."""
    n = norm(s)
    inside = _within(n)
    for kind in KINDS:
        if any(inside.search(t) for t in getattr(allowed, kind)):
            return kind
    if any(p.fullmatch(s) for p in allowed.patterns):
        return "illustrative"
    words = _words(n)
    if words and any(_has_run(line, words) for line in allowed.lines):
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


def scene_ids(script: dict) -> list[str]:
    return [s for act in script["acts"] for s in act["scenes"]]


def imports_strings(module: Path, scene: str) -> bool:
    """Does the module import ./<scene>.strings.json (an import statement at the start of a line, not commented out)?"""
    pattern = r"^\s*import\s[^;]*?\bfrom\s*(['\"])\./" + re.escape(scene) + r"\.strings\.json\1"
    return re.search(pattern, module.read_text(encoding="utf-8"), re.MULTILINE) is not None


def unlinked_scenes(scenes: Path, ids: list[str]) -> list[str]:
    """What is wrong with each scene module (scenes/<id>.ts for a scene id) that draws text the gate cannot see."""
    problems = []
    for sid in ids:
        module = scenes / f"{sid}.ts"
        if not module.is_file():
            continue
        if not (scenes / f"{sid}.strings.json").is_file():
            problems.append(f"{_shown(module)}: no {sid}.strings.json beside it (a scene draws its strings from that "
                            "file, the only text the facts gate sees)")
        elif not imports_strings(module, sid):
            problems.append(f"{_shown(module)}: does not import ./{sid}.strings.json (a scene draws its strings from "
                            "that file, the only text the facts gate sees)")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check that every string a scene shows is on the facts sheet or is hers")
    ap.add_argument("--scenes", type=Path, default=SCENES,
                    help="where the scene modules and their <scene>.strings.json files are (default: app/src/scenes)")
    a = ap.parse_args(argv)
    if not a.scenes.is_dir():
        print(f"facts FAILED: the scenes directory {a.scenes} does not exist", file=sys.stderr)
        return 1
    allowed = load_allowed()
    unlinked = unlinked_scenes(a.scenes, scene_ids(_read_json(DATA / "script.json")))
    for problem in unlinked:
        print(problem)
    files = sorted(a.scenes.rglob("*.strings.json"))
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
    if bad or unreadable or unlinked:
        why = f"{bad} of {total} strings are not verbatim, approved copy, illustrative or her words"
        if unreadable:
            why += f"; {unreadable} unreadable file{'s' if unreadable > 1 else ''}"
        if unlinked:
            why += (f"; {len(unlinked)} scene module{'s' if len(unlinked) > 1 else ''} not drawing from "
                    f"{'their' if len(unlinked) > 1 else 'its'} strings file")
        print(f"facts FAILED: {why}", file=sys.stderr)
        return 1
    print(f"facts OK ({total} strings in {len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
