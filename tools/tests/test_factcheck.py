import functools
import json
import re
import tomllib

import pytest

from gitloom_film import factcheck
from gitloom_film.factcheck import build_allowed, classify, load_allowed, main, norm
from gitloom_film.paths import APP, DATA, ROOT

SPEC = ROOT / "docs" / "specs" / "2026-09-30-gitloom-launch-film-design.md"
MINUS, ELLIPSIS, LSQ, RSQ, LDQ, RDQ = "−", "…", "‘", "’", "“", "”"


def strings_file(d, name, strings):
    p = d / f"{name}.strings.json"
    p.write_text(json.dumps(strings, ensure_ascii=False), encoding="utf-8")
    return p


def run(d, capsys):
    rc = main(["--scenes", str(d)])
    out, err = capsys.readouterr()
    return rc, out, err


# --- the film-facts command, against the real facts sheet, her real words and the real script ---


def test_a_known_snippet_passes(tmp_path, capsys):
    strings_file(tmp_path, "diff", ["$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2",
                                    "1 file changed, 2 insertions(+), 2 deletions(-)"])
    assert run(tmp_path, capsys) == (0, "facts OK (2 strings in 1 files)\n", "")


def test_a_substring_of_a_verbatim_snippet_passes(tmp_path, capsys):
    strings_file(tmp_path, "connect", ["npx -y @gitloomhq/mcp", '"args": ["-y", "@gitloomhq/mcp"]',
                                       "8b21e04 3f9a1c2", "Uses neovim. Has since 2019."])
    rc, out, _ = run(tmp_path, capsys)
    assert (rc, out) == (0, "facts OK (4 strings in 1 files)\n")


def test_a_made_up_command_fails_with_its_file(tmp_path, capsys):
    p = strings_file(tmp_path, "cite", ["gitloom log --blame"])  # spec 11.7: no such flag
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1
    assert out.splitlines() == [f'{p}: "gitloom log --blame"']


def test_a_voiceover_word_passes(tmp_path, capsys):
    strings_file(tmp_path, "thread", ["forgets.", "vector", "Commitment issues.", "Every conversation... back to zero."])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (4 strings in 1 files)\n")


def test_any_failure_exits_1_and_only_the_failures_are_printed(tmp_path, capsys):
    a = strings_file(tmp_path, "ex", [f"{MINUS} no history", "cosine 0.8127", f"{MINUS} made up label"])
    b = strings_file(tmp_path, "her", ["Not me.", "also made up", "3f9a1c2"])
    rc, out, err = run(tmp_path, capsys)
    assert rc == 1
    assert out.splitlines() == [f'{a}: "{MINUS} made up label"', f'{b}: "also made up"']
    assert "facts OK" not in out and "2 of 6 strings" in err


def test_no_strings_files_is_fine(tmp_path, capsys):
    assert run(tmp_path, capsys) == (0, "facts OK (0 strings in 0 files)\n", "")
    assert run(tmp_path / "missing", capsys) == (0, "facts OK (0 strings in 0 files)\n", "")


def test_every_strings_file_under_the_scenes_dir_is_read(tmp_path, capsys):
    strings_file(tmp_path, "ex", ["berlin?"])
    strings_file(tmp_path, "her", ["Not me.", "3f9a1c2"])
    (tmp_path / "sub").mkdir()
    strings_file(tmp_path / "sub", "loom", ["gc: expire 3 incidents"])
    (tmp_path / "notes.json").write_text('["not a strings file"]')
    (tmp_path / "loom.ts").write_text("// not a strings file")
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (4 strings in 3 files)\n")


def test_a_repeated_failure_is_reported_once_per_file(tmp_path, capsys):
    strings_file(tmp_path, "ex", ["made up", "berlin?", "made up"])
    _, out, _ = run(tmp_path, capsys)
    assert len(out.splitlines()) == 1


@pytest.mark.parametrize("body, problem", [
    ('{"a": 1}', "not a JSON array of strings"),
    ('["fine", 7]', "not a JSON array of strings"),
    ('["unterminated', "not valid JSON"),
])
def test_a_malformed_strings_file_fails(tmp_path, capsys, body, problem):
    p = tmp_path / "ex.strings.json"
    p.write_text(body)
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1 and str(p) in out and problem in out


def test_scenes_default_to_the_apps_scenes_dir():
    assert factcheck.SCENES == APP / "src" / "scenes"


def test_film_facts_is_a_registered_command():
    scripts = tomllib.loads((ROOT / "tools" / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["film-facts"] == "gitloom_film.factcheck:main"


# --- the matching rules, on a small sheet ---

FACTS = {
    "verbatim": [{"text": "gitloom diff a b\nsecond line", "source": "docs/x.md:1-2"}],
    "copy": [{"text": f"{MINUS} no history", "source": "spec §4 ex"},
             {"text": f"it{RSQ}s a {LDQ}quote{RDQ}", "source": "spec §4 her"}],
    "illustrative": [{"text": "cosine 0.8127"}],
}
VO = {"lines": [{"id": "L1", "text": "Your agent forgets.", "words": [{"w": "Your"}, {"w": "agent"}, {"w": "forgets."}]},
                {"id": "L2", "text": "It's not you... it's me.", "words": [{"w": "It's"}, {"w": "you..."}, {"w": "me."}]}]}
SCRIPT = {"acts": [{"id": "I", "name": "The Ex", "scenes": ["thread", "ex"]}]}
SMALL = build_allowed(FACTS, VO, SCRIPT)


@pytest.mark.parametrize("s, kind", [
    ("gitloom diff a b\nsecond line", "verbatim"),  # equals
    ("diff a", "verbatim"),  # a substring
    ("a b\nsecond", "verbatim"),  # a substring across a line break
    (f"{MINUS} no history", "copy"),
    ("no hist", "copy"),
    ("cosine 0.8127", "illustrative"),
    ("0.81", "illustrative"),
    ("Your agent forgets.", "vo"),  # one of her lines
    ("forgets.", "vo"),  # one of her words, as displayed
    ("Your", "vo"),
    ("thread", "label"),  # a scene id
    ("The Ex", "label"),  # an act name
])
def test_what_passes(s, kind):
    assert classify(s, SMALL) == kind


@pytest.mark.parametrize("s", [
    "gitloom diff a b c",  # longer than the entry it starts like
    "Gitloom diff a b",  # the sheet is case sensitive
    "cosine 0.8128",
    "Your agent",  # her words are matched whole: a line or a single word, never a phrase of a line
    "forgets",  # as displayed: the word carries its punctuation
    "thre",  # scene ids and act names are matched whole too
    "The",
    "I",  # an act's roman numeral is not an act name
    "gitloom log --blame",
])
def test_what_fails(s):
    assert classify(s, SMALL) is None


def test_typographic_punctuation_matches_the_typed_forms():
    assert norm(f"it{RSQ}s {LDQ}x{RDQ} {LSQ}y{RSQ} wait{ELLIPSIS}") == "it's \"x\" 'y' wait..."
    assert classify(f"It{RSQ}s not you{ELLIPSIS} it{RSQ}s me.", SMALL) == "vo"
    assert classify(f"you{ELLIPSIS}", SMALL) == "vo"
    assert classify("it's a \"quote\"", SMALL) == "copy"  # typed input against typographic copy
    assert classify(f"{LDQ}quote{RDQ}", SMALL) == "copy"


def test_a_sheet_needs_all_three_lists(tmp_path):
    p = tmp_path / "facts.json"
    p.write_text(json.dumps({"verbatim": [], "copy": []}))
    with pytest.raises(SystemExit, match="illustrative"):
        factcheck.load_facts(p)
    p.write_text(json.dumps({"verbatim": [{"text": ""}], "copy": [], "illustrative": []}))
    with pytest.raises(SystemExit, match=r"verbatim\[0\]"):
        factcheck.load_facts(p)


# --- the real sheet ---


@functools.cache
def real():
    return load_allowed()


def sheet():
    return json.loads((DATA / "facts.json").read_text(encoding="utf-8"))


def scene_ids():
    return {s for a in json.loads((DATA / "script.json").read_text())["acts"] for s in a["scenes"]}


def test_the_sheet_is_well_formed():
    facts = sheet()
    assert list(facts) == ["verbatim", "copy", "illustrative"]
    for kind in ("verbatim", "copy"):
        for e in facts[kind]:
            assert sorted(e) == ["source", "text"] and e["text"].strip() and e["source"].strip(), e
    assert all(sorted(e) == ["text"] and e["text"].strip() for e in facts["illustrative"])
    for e in facts["verbatim"]:  # a path and the line(s) in it
        assert re.search(r"[\w./-]+\.\w+:\d+", e["source"]), e
    for e in facts["copy"]:
        m = re.fullmatch(r"spec §4 (\w+)", e["source"])
        assert m and m.group(1) in scene_ids(), e
    every = [(kind, e["text"], e.get("source")) for kind, entries in facts.items() for e in entries]
    assert len(every) == len(set(every)), "an entry is listed twice"


def test_every_scene_has_copy():
    assert {e["source"].split()[-1] for e in sheet()["copy"]} == scene_ids()


@pytest.mark.parametrize("s", [
    "gitloom log --blame",  # 11.7: no such flag
    "gitloom diff A..B -- path",  # 11.7: the real syntax is diff PATH FROM TO
    "15 ms",  # 11.8: not to be shown for hosted retrieval
    "10,000 shards / 100M memories",  # 11.8: not a deployed fact
    "10,000 shards",
    "100M memories",
])
def test_what_the_spec_forbids_is_not_on_the_sheet(s):
    assert classify(s, real()) is None


def test_the_real_sheet_sorts_strings_into_the_right_kinds():
    assert classify("$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2", real()) == "verbatim"
    assert classify(f"{MINUS} no history", real()) == "copy"
    assert classify("hotel", real()) == "illustrative"  # 11.10: a graph node
    assert classify("forgets.", real()) == "vo"
    assert classify("The Tour", real()) == "label"
    assert classify("merkle", real()) == "label"


def test_display_type_uses_the_same_sheet_as_typed_input():
    assert classify(f"Every round was diagnosed from the previous round{RSQ}s failures.", real()) == "verbatim"
    assert classify(f"{LDQ}candidates{RDQ}: 2", real()) == "copy"
    assert classify(f"It{RSQ}s not you{ELLIPSIS} it{RSQ}s your vector store.", real()) == "vo"
    assert classify(f"user-0001 {ELLIPSIS} user-2048", real()) == "copy"


def spec_lines():
    return SPEC.read_text(encoding="utf-8").split("\n")


def between(lines, first, last):
    a = next(i for i, l in enumerate(lines) if l.startswith(first))
    b = next(i for i, l in enumerate(lines) if l.startswith(last))
    return lines[a:b]


def test_every_label_written_in_spec_4_passes():
    """Section 4's scene treatments name every on-screen label in backticks; none may be missing from the sheet."""
    not_labels = {"web/src/app"}  # where the console layouts live: a source, not a label
    spans = [s for l in between(spec_lines(), "### 01 ", "## 5. ") for s in re.findall(r"`([^`]+)`", l)]
    assert len(spans) > 100
    missing = [s for s in spans if s not in not_labels and classify(s, real()) is None]
    assert missing == []


def test_every_snippet_in_spec_11_is_verbatim_or_illustrative():
    blocks, spans, block = [], [], None
    for l in between(spec_lines(), "**11.1 ", "## 12. "):
        if l.startswith("```"):
            if block is None:
                block = []
            else:
                blocks.append("\n".join(block))
                block = None
        elif block is not None:
            block.append(l)
        else:
            spans += re.findall(r"`([^`]+)`", l)
    verbatim = {e["text"] for e in sheet()["verbatim"]}
    assert len(blocks) == 5 and all(b in verbatim for b in blocks)
    skipped = {
        "gitloom log --blame", "gitloom diff A..B -- path", "diff PATH FROM TO",  # 11.7: named as not real
        "gitloom write -m",  # 11.10: says what kind of message the log holds
    }
    source = re.compile(r"(docs|web)/.*|\w+\.tsx:\d+")  # where a snippet comes from, not a snippet
    missing = [s for s in spans if not source.fullmatch(s) and s not in skipped and classify(s, real()) is None]
    assert missing == []


def test_quoted_lines_and_footnotes_from_the_spec_pass():
    text = SPEC.read_text(encoding="utf-8")
    shown = [
        # 11.8 and 11.9
        "oracle split", "50 of 10,000 files visited", "milliseconds", "Free is ₹0 with no card", "Storage is free.",
        "Nothing about that is a metaphor — you can cd into it.",
        "the engine returns nothing rather than the nearest vector.",
        "Every round was diagnosed from the previous round's failures.",
        "a storage boundary, not a WHERE clause",
        # 4: the italic footnotes, labels and display type written in the treatments
        "Ranked memories, no model call. Milliseconds.", "I don't know.",
        "one per end user · a storage boundary, not a WHERE clause", "On your machine", "or in my cloud",
        "It's not you.", "it's your vector store", "back to zero",
        # 4, scene 12: the per-category strip, as it is abbreviated there
        "knowledge-update 94.9", "multi-session 87.9", "single-session-assistant 96.4", "preference 100",
        "single-session-user 97.1", "temporal 85.7",
        # 4, scenes 13 and 14: card labels and console panels
        "TypeScript", "Python", "Go", "Rust", "Playground", "Memory Graph", "Namespaces",
    ]
    for s in shown:
        assert s in text, f"{s!r} is not in the spec"
        assert classify(s, real()) is not None, f"{s!r} is not on the sheet"
