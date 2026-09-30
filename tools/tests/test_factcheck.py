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


def test_an_empty_scenes_dir_is_fine(tmp_path, capsys):
    assert run(tmp_path, capsys) == (0, "facts OK (0 strings in 0 files)\n", "")


def test_a_scenes_dir_that_does_not_exist_fails(tmp_path, capsys):
    rc, out, err = run(tmp_path / "missing", capsys)
    assert rc == 1 and "facts OK" not in out
    assert str(tmp_path / "missing") in err and "does not exist" in err


# --- a scene module draws its strings from its <id>.strings.json: the gate can see nothing else ---

IMPORTS = "import S from './{id}.strings.json';\n"


def test_a_scene_module_that_imports_its_strings_file_passes(tmp_path, capsys):
    (tmp_path / "her.ts").write_text("import * as THREE from 'three';\n" + IMPORTS.format(id="her") + "draw(S[0]);\n")
    strings_file(tmp_path, "her", ["Not me."])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (1 strings in 1 files)\n")


def test_a_scene_module_without_its_strings_file_fails(tmp_path, capsys):
    mod = tmp_path / "loom.ts"  # loom is a scene id in data/script.json
    mod.write_text("c.fillText('gc: expire 3 incidents', 96, 230);\n")
    rc, out, err = run(tmp_path, capsys)
    assert rc == 1 and "facts OK" not in out
    assert f"{mod}: no loom.strings.json" in out and "1 scene module" in err


def test_a_scene_module_that_does_not_import_its_strings_file_fails(tmp_path, capsys):
    mod = tmp_path / "her.ts"
    mod.write_text("// import S from './her.strings.json';\nc.fillText('made up', 96, 230);\n")  # commented out
    strings_file(tmp_path, "her", ["Not me."])
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1 and f"{mod}: does not import ./her.strings.json" in out


def test_harness_scenes_the_card_and_helper_modules_are_not_scene_modules(tmp_path, capsys):
    # _*.ts are test harnesses, card.ts is the animatic's placeholder, her-camera.ts a helper: none is a scene id
    for name in ("_platetest.ts", "card.ts", "her-camera.ts"):
        (tmp_path / name).write_text("c.fillText('made up', 96, 230);\n")
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (0 strings in 0 files)\n")


def test_every_strings_file_under_the_scenes_dir_is_read(tmp_path, capsys):
    strings_file(tmp_path, "ex", ["berlin?"])
    strings_file(tmp_path, "her", ["Not me.", "3f9a1c2"])
    (tmp_path / "sub").mkdir()
    strings_file(tmp_path / "sub", "loom", ["gc: expire 3 incidents"])
    (tmp_path / "notes.json").write_text('["not a strings file"]')
    (tmp_path / "loom-camera.ts").write_text("// not a strings file")
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
    "illustrative_patterns": [{"pattern": r"^#\d{3}$", "why": "a pattern for these tests"}],
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
    ("no history", "copy"),  # a substring of whole words
    ("cosine 0.8127", "illustrative"),
    ("0.8127", "illustrative"),  # a whole number
    ("#123", "illustrative"),  # a pattern, matched in full
    ("Your agent forgets.", "vo"),  # one of her lines
    ("forgets.", "vo"),  # one of her words, as displayed
    ("Your", "vo"),
    ("Your agent", "vo"),  # a phrase of one of her lines: whole words, in order
    ("forgets", "vo"),  # her word without its punctuation
    ("you... it's", "vo"),  # a run that crosses her ellipsis
    ("thread", "label"),  # a scene id
    ("The Ex", "label"),  # an act name
])
def test_what_passes(s, kind):
    assert classify(s, SMALL) == kind


@pytest.mark.parametrize("s", [
    "gitloom diff a b c",  # longer than the entry it starts like
    "no hist",  # a word cut short: a substring must start and end on a token boundary
    "0.81",  # a number cut short
    "8127",  # a number's tail: "0." before it continues the number
    "cosine 0",  # a number's head: ".8127" after it continues the number
    "Gitloom diff a b",  # the sheet is case sensitive
    "cosine 0.8128",
    "#12", "#1234", "x#123", "#123\n",  # off the pattern: a pattern has to match the whole string
    "#١٢٣",  # \d in a pattern is an ASCII digit
    "Your forgets",  # not contiguous
    "agent Your",  # not in her order
    "agen",  # not whole words
    "thre",  # scene ids and act names are matched whole
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
    assert classify(f"{LDQ}Your agent{RDQ}", SMALL) == "vo"
    assert classify(f"not you{ELLIPSIS} it{RSQ}s", SMALL) == "vo"
    assert classify("it's a \"quote\"", SMALL) == "copy"  # typed input against typographic copy
    assert classify(f"{LDQ}quote{RDQ}", SMALL) == "copy"


# --- phrases of her lines: a contiguous run of her whole words, punctuation aside ---


@functools.cache
def her_words_only():
    """Her real lines and the real scenes on a sheet with nothing on it: only her words and the labels can pass."""
    nothing = {"verbatim": [], "copy": [], "illustrative": []}
    return build_allowed(nothing, json.loads((DATA / "vo.json").read_text(encoding="utf-8")),
                         json.loads((DATA / "script.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("s, kind", [
    ("back to zero.", "vo"),  # L02 "Every conversation... back to zero."
    ("vector store", "vo"),  # L03 "It's not you... it's your vector store."
    ("to zer", None),  # not whole words
    ("zero back", None),  # not contiguous
])
def test_a_phrase_of_her_lines_passes_if_it_is_whole_words_in_order(s, kind):
    assert classify(s, her_words_only()) == kind


def test_the_phrases_pass_the_real_gate():
    # `to zer` fails the real gate too: test_cut_off_words_of_her_lines_fail
    assert classify("back to zero.", real()) is not None
    assert classify("vector store", real()) is not None


def test_a_phrase_of_her_lines_passes_the_command(tmp_path, capsys):
    strings_file(tmp_path, "ex", ["back to zero.", "vector store", f"It{RSQ}s not you{ELLIPSIS}"])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (3 strings in 1 files)\n")


@pytest.mark.parametrize("s", [
    f"Every conversation{ELLIPSIS} back to zero.",  # a whole line, typographic
    "  back to zero  ",  # whitespace at the ends
    "— back to zero —",  # and punctuation
    f"{LDQ}vector store{RDQ}",
    f"{ELLIPSIS}I say so.",  # L23 begins with its ellipsis
    "back to\nzero",  # broken over two lines
    "conversation",  # a word without its punctuation
    "Forty-four",  # a hyphen inside a word stays
])
def test_punctuation_and_whitespace_at_the_ends_do_not_count(s):
    assert classify(s, her_words_only()) == "vo"


@pytest.mark.parametrize("s", [
    "", " ", "...", "—",  # no words at all is not a run of hers
    "Back to zero",  # case sensitive
    "back · to zero",  # a mark standing between her words is not one of her words
    "forgets. Every conversation",  # a run stays inside one of her lines
    "back to zero please",
])
def test_what_is_not_a_phrase_of_hers(s):
    assert classify(s, her_words_only()) is None


def test_a_sheet_needs_all_four_lists(tmp_path):
    p = tmp_path / "facts.json"
    p.write_text(json.dumps({"verbatim": [], "copy": []}))
    with pytest.raises(SystemExit, match="illustrative"):
        factcheck.load_facts(p)
    p.write_text(json.dumps({"verbatim": [{"text": ""}], "copy": [], "illustrative": [], "illustrative_patterns": []}))
    with pytest.raises(SystemExit, match=r"verbatim\[0\]"):
        factcheck.load_facts(p)
    p.write_text(json.dumps({"verbatim": [], "copy": [], "illustrative": []}))
    with pytest.raises(SystemExit, match="illustrative_patterns"):
        factcheck.load_facts(p)
    for bad, why in [({"pattern": "("}, r"needs a pattern and a why"), ({"pattern": "(", "why": "x"}, "not a regex"),
                     ({"why": "x"}, r"needs a pattern and a why")]:
        p.write_text(json.dumps({"verbatim": [], "copy": [], "illustrative": [], "illustrative_patterns": [bad]}))
        with pytest.raises(SystemExit, match=rf"illustrative_patterns\[0\].*{why}"):
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
    assert list(facts) == ["verbatim", "copy", "illustrative", "illustrative_patterns"]
    for kind in ("verbatim", "copy"):
        for e in facts[kind]:
            assert sorted(e) == ["source", "text"] and e["text"].strip() and e["source"].strip(), e
    assert all(sorted(e) == ["text"] and e["text"].strip() for e in facts["illustrative"])
    for e in facts["illustrative_patterns"]:
        assert sorted(e) == ["pattern", "why"] and e["why"].strip(), e
        re.compile(e["pattern"], re.ASCII)
    for e in facts["verbatim"]:  # a path and the line(s) in it
        assert re.search(r"[\w./-]+\.\w+:\d+", e["source"]), e
    for e in facts["copy"]:
        m = re.fullmatch(r"spec §4 (\w+)", e["source"])
        assert m and m.group(1) in scene_ids(), e
    every = [(kind, e["text"], e.get("source")) for kind in ("verbatim", "copy", "illustrative") for e in facts[kind]]
    assert len(every) == len(set(every)), "an entry is listed twice"


def test_every_scene_has_copy_unless_it_shows_only_her_words():
    # thread shows only her words ("Your agent forgets.", "back to", "zero."), which pass as hers: a copy entry that
    # repeated them would let their cut-off substrings through
    assert scene_ids() - {e["source"].split()[-1] for e in sheet()["copy"]} == {"thread"}


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
    assert classify("0.5512", real()) == "illustrative"  # 11.10: a float numeral, by its pattern
    assert classify("forgets.", real()) == "vo"
    assert classify("The Tour", real()) == "label"
    assert classify("merkle", real()) == "label"


def test_display_type_uses_the_same_sheet_as_typed_input():
    assert classify(f"Every round was diagnosed from the previous round{RSQ}s failures.", real()) == "verbatim"
    assert classify(f"{LDQ}candidates{RDQ}: 2", real()) == "copy"
    assert classify(f"It{RSQ}s not you{ELLIPSIS} it{RSQ}s your vector store.", real()) == "vo"
    assert classify(f"user-0001 {ELLIPSIS} user-2048", real()) == "copy"


# --- the illustrative patterns: the shapes of values that are invented (spec 11.10) ---

PATTERNS = ["^[" + MINUS + r"-]?\d\.\d{4}$", r"^user-\d{4}$", "^(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7}$"]


def without_patterns():
    facts = {k: v for k, v in sheet().items() if k != "illustrative_patterns"}
    return build_allowed(facts, json.loads((DATA / "vo.json").read_text(encoding="utf-8")),
                         json.loads((DATA / "script.json").read_text(encoding="utf-8")))


def test_the_sheet_holds_exactly_the_three_patterns_of_spec_11_10():
    patterns = sheet()["illustrative_patterns"]
    assert [p["pattern"] for p in patterns] == PATTERNS
    assert all("§11.10" in p["why"] for p in patterns)


@pytest.mark.parametrize("s, passes", [
    (f"{MINUS}0.0931", True),  # a float numeral
    ("0.2143", True),
    ("user-0042", True),  # a namespace row
    ("a41c9d0", True),  # an illustrative commit hash
    ("0.21435", False),  # five decimals
    ("user-42", False),  # two digits
])
def test_the_patterns_let_invented_values_through(s, passes):
    assert (classify(s, real()) is not None) == passes


@pytest.mark.parametrize("s", ["0.5512", f"{MINUS}0.7301", "-0.7301", "user-0042", "user-9999", "b7e3a19"])
def test_a_value_the_sheet_does_not_list_passes_on_its_pattern_alone(s):
    assert classify(s, without_patterns()) is None
    assert classify(s, real()) == "illustrative"


@pytest.mark.parametrize("s", [
    "0.551", "12.5512", ".5512", "0,5512", "0.5512 ", "0.5512\n", "x0.5512", "--0.5512",  # not a four decimal numeral
    "user-00042", "User-0042", "user_0042", "user-0042\n", "user-٤٢٠٠",  # not a namespace row
    "b7e3a1", "b7e3a19f", "B7E3A19", "g7e3a19", "b7e3a1\n",  # not seven lowercase hex digits
])
def test_a_value_off_its_pattern_fails(s):
    assert classify(s, real()) is None


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


def test_truncated_numbers_and_words_of_the_sheet_fail():
    # each is a substring of a verbatim or copy entry cut inside a number or a word: a digit dropped from the proof
    # scene's strings must not pass
    for s in ["56/499", "456/49",  # LongMemEval 456/499
              "preference 10",  # preference 100
              "0 of 10,000 files visited",  # 50 of 10,000 files visited
              "536 dims",  # 1536 dims
              "Storage is fre"]:  # Storage is free.
        assert classify(s, real()) is None, s
    for s in ["456/499", "preference 100", "50 of 10,000 files visited", "1536 dims", "Storage is free"]:
        assert classify(s, real()) is not None, s  # the whole tokens still pass


def test_cut_off_words_of_her_lines_fail():
    # her lines pass word by word; a word cut short is nobody's (a copy entry that only repeats her words would let
    # its substrings through, so the sheet holds none)
    for s in ["to zer", "t's not yo", "your vector sto", "n your machin", "r in my clo", "I don't kno"]:
        assert classify(s, real()) is None, s


def test_her_phrases_pass_as_hers():
    for s in ["back to zero", "It's not you.", "it's your vector store", "why?", "I don't know.", "On your machine",
              "or in my cloud"]:
        assert classify(s, real()) == "vo", s


def test_an_invented_hash_has_a_digit_and_a_letter():
    for s in ["7d3e9b0", "e4a1f07", "0c5b2a9"]:
        assert classify(s, real()) == "illustrative", s
    for s in ["1234567", "defaced", "acceded"]:  # seven digits, or a word spelt in a-f, is not a commit hash
        assert classify(s, real()) is None, s
