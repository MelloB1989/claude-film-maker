import json
import re

import pytest

from filmtools import factcheck
from filmtools.factcheck import build_allowed, classify, load_allowed, main, norm

MINUS, ELLIPSIS, LSQ, RSQ, LDQ, RDQ = "−", "…", "‘", "’", "“", "”"

# a film's facts sheet, voiceover and script, as films/<id>/data holds them
SHEET = {
    "verbatim": [{"text": "$ tool sync notes/today.md 8b21e04 3f9a1c2", "source": "docs/cli.md:12"},
                 {"text": "1 file changed, 2 insertions(+), 2 deletions(-)", "source": "docs/cli.md:13"},
                 {"text": 'npx -y @example/mcp\n"args": ["-y", "@example/mcp"]', "source": "docs/setup.md:4-5"},
                 {"text": "Storage is free.", "source": "site/pricing.md:3"},
                 {"text": "Bench score 456/499", "source": "docs/eval.md:9"},
                 {"text": "preference 100", "source": "docs/eval.md:10"}],
    "copy": [{"text": f"{MINUS} no history", "source": "brief"}, {"text": f"{LDQ}candidates{RDQ}: 2", "source": "brief"}],
    "illustrative": [{"text": "cosine 0.8127"}, {"text": "hotel"}],
    "illustrative_patterns": [{"pattern": "^[" + MINUS + r"-]?\d\.\d{4}$", "why": "a float numeral"},
                              {"pattern": r"^user-\d{4}$", "why": "a namespace row"},
                              {"pattern": "^(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7}$", "why": "a commit hash"}],
}
VO = {"lines": [{"id": "L1", "text": "Every morning starts the same."},
                {"id": "L2", "text": "Nothing you said... survives the night."},
                {"id": "L3", "text": "It's not you... it's the tool you trusted."},
                {"id": "L4", "text": "...I say so. Forty-four of them."}]}
SCRIPT = {"acts": [{"id": "I", "name": "The Problem", "scenes": ["open", "problem"]},
                   {"id": "II", "name": "The Turn", "scenes": ["turn", "proof"]}]}


@pytest.fixture
def sheet_film(film):
    for name, doc in (("facts", SHEET), ("vo", VO), ("script", SCRIPT)):
        (film.data / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False))
    return film


def strings_file(d, name, strings):
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.strings.json"
    p.write_text(json.dumps(strings, ensure_ascii=False), encoding="utf-8")
    return p


def run(d, capsys):
    rc = main(["--scenes", str(d)])
    out, err = capsys.readouterr()
    return rc, out, err


# --- the film-facts command, against the film's facts sheet, its voiceover and its script ---


def test_a_known_snippet_passes(sheet_film, tmp_path, capsys):
    strings_file(tmp_path, "diff", ["$ tool sync notes/today.md 8b21e04 3f9a1c2",
                                    "1 file changed, 2 insertions(+), 2 deletions(-)"])
    assert run(tmp_path, capsys) == (0, "facts OK (2 strings in 1 files)\n", "")


def test_the_scenes_default_to_the_films_own(sheet_film, capsys):
    strings_file(sheet_film.dir / "scenes", "open", ["Storage is free.", "made up"])
    rc = main([])
    out, err = capsys.readouterr()
    assert rc == 1 and out.splitlines() == [f'{sheet_film.dir / "scenes" / "open.strings.json"}: "made up"']
    assert "1 of 2 strings" in err


def test_a_film_without_scenes_fails_clearly(sheet_film, capsys):
    assert main([]) == 1 and "scenes directory" in capsys.readouterr().err


def test_a_film_without_a_sheet_fails_clearly(film, tmp_path):
    strings_file(tmp_path / "s", "open", ["x"])
    with pytest.raises(SystemExit, match="facts.json is missing"):
        main(["--scenes", str(tmp_path / "s")])


def test_a_substring_of_a_verbatim_snippet_passes(sheet_film, tmp_path, capsys):
    strings_file(tmp_path, "setup", ["npx -y @example/mcp", '"args": ["-y", "@example/mcp"]', "8b21e04 3f9a1c2"])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (3 strings in 1 files)\n")


def test_a_made_up_command_fails_with_its_file(sheet_film, tmp_path, capsys):
    p = strings_file(tmp_path, "setup", ["tool sync --force"])
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1 and out.splitlines() == [f'{p}: "tool sync --force"']


def test_a_voiceover_word_passes(sheet_film, tmp_path, capsys):
    strings_file(tmp_path, "open", ["morning", "same.", "Every morning starts the same.", "Nothing you said... survives"])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (4 strings in 1 files)\n")


def test_any_failure_exits_1_and_only_the_failures_are_printed(sheet_film, tmp_path, capsys):
    a = strings_file(tmp_path, "problem", [f"{MINUS} no history", "cosine 0.8127", f"{MINUS} made up label"])
    b = strings_file(tmp_path, "turn", ["The Turn", "also made up", "3f9a1c2"])
    rc, out, err = run(tmp_path, capsys)
    assert rc == 1
    assert out.splitlines() == [f'{a}: "{MINUS} made up label"', f'{b}: "also made up"']
    assert "facts OK" not in out and "2 of 6 strings" in err


def test_an_empty_scenes_dir_is_fine(sheet_film, tmp_path, capsys):
    assert run(tmp_path, capsys) == (0, "facts OK (0 strings in 0 files)\n", "")


def test_a_scenes_dir_that_does_not_exist_fails(sheet_film, tmp_path, capsys):
    rc, out, err = run(tmp_path / "missing", capsys)
    assert rc == 1 and "facts OK" not in out
    assert str(tmp_path / "missing") in err and "does not exist" in err


def test_a_film_without_a_voiceover_passes_on_its_sheet_and_labels(film, tmp_path, capsys):
    (film.data / "facts.json").write_text(json.dumps(SHEET))
    (film.data / "timeline.json").write_text(json.dumps({"fps": 30, "duration": 4, "scenes": [
        {"id": "hello", "start": 0, "end": 4}]}))
    strings_file(tmp_path, "hello", ["hello", "Storage is free."])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (2 strings in 1 files)\n")


# --- a scene module draws its strings from its <id>.strings.json: the gate can see nothing else ---

IMPORTS = "import S from './{id}.strings.json';\n"


def test_a_scene_module_that_imports_its_strings_file_passes(sheet_film, tmp_path, capsys):
    (tmp_path / "turn.ts").write_text("import * as THREE from 'three';\n" + IMPORTS.format(id="turn") + "draw(S[0]);\n")
    strings_file(tmp_path, "turn", ["The Turn"])
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (1 strings in 1 files)\n")


def test_a_scene_module_without_its_strings_file_fails(sheet_film, tmp_path, capsys):
    mod = tmp_path / "proof.ts"  # proof is a scene id in the script
    mod.write_text("c.fillText('made up', 96, 230);\n")
    rc, out, err = run(tmp_path, capsys)
    assert rc == 1 and "facts OK" not in out
    assert f"{mod}: no proof.strings.json" in out and "1 scene module" in err


def test_a_scene_module_that_does_not_import_its_strings_file_fails(sheet_film, tmp_path, capsys):
    mod = tmp_path / "turn.ts"
    mod.write_text("// import S from './turn.strings.json';\nc.fillText('made up', 96, 230);\n")  # commented out
    strings_file(tmp_path, "turn", ["The Turn"])
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1 and f"{mod}: does not import ./turn.strings.json" in out


def test_harness_scenes_and_helper_modules_are_not_scene_modules(sheet_film, tmp_path, capsys):
    for name in ("_platetest.ts", "card.ts", "turn-camera.ts"):
        (tmp_path / name).write_text("c.fillText('made up', 96, 230);\n")
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (0 strings in 0 files)\n")


def test_every_strings_file_under_the_scenes_dir_is_read(sheet_film, tmp_path, capsys):
    strings_file(tmp_path, "problem", ["hotel"])
    strings_file(tmp_path, "turn", ["The Turn", "3f9a1c2"])
    strings_file(tmp_path / "sub", "proof", ["preference 100"])
    (tmp_path / "notes.json").write_text('["not a strings file"]')
    (tmp_path / "proof-camera.ts").write_text("// not a strings file")
    assert run(tmp_path, capsys)[:2] == (0, "facts OK (4 strings in 3 files)\n")


def test_a_repeated_failure_is_reported_once_per_file(sheet_film, tmp_path, capsys):
    strings_file(tmp_path, "problem", ["made up", "hotel", "made up"])
    _, out, _ = run(tmp_path, capsys)
    assert len(out.splitlines()) == 1


@pytest.mark.parametrize("body, problem", [
    ('{"a": 1}', "not a JSON array of strings"),
    ('["fine", 7]', "not a JSON array of strings"),
    ('["unterminated', "not valid JSON"),
])
def test_a_malformed_strings_file_fails(sheet_film, tmp_path, capsys, body, problem):
    p = tmp_path / "problem.strings.json"
    p.write_text(body)
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 1 and str(p) in out and problem in out


def test_film_facts_is_a_registered_command():
    import tomllib

    from filmtools import paths
    scripts = tomllib.loads((paths.find_root() / "tools" / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["film-facts"] == "filmtools.factcheck:main"


# --- the matching rules, on a small sheet ---

FACTS = {
    "verbatim": [{"text": "tool diff a b\nsecond line", "source": "docs/x.md:1-2"}],
    "copy": [{"text": f"{MINUS} no history", "source": "brief"},
             {"text": f"it{RSQ}s a {LDQ}quote{RDQ}", "source": "brief"}],
    "illustrative": [{"text": "cosine 0.8127"}],
    "illustrative_patterns": [{"pattern": r"^#\d{3}$", "why": "a pattern for these tests"}],
}
SMALL_VO = {"lines": [{"id": "L1", "text": "Your notes vanish."}, {"id": "L2", "text": "It's not you... it's me."}]}
SMALL_SCRIPT = {"acts": [{"id": "I", "name": "The Start", "scenes": ["open", "middle"]}]}
SMALL = build_allowed(FACTS, SMALL_VO, SMALL_SCRIPT)


@pytest.mark.parametrize("s, kind", [
    ("tool diff a b\nsecond line", "verbatim"),  # equals
    ("diff a", "verbatim"),  # a substring
    ("a b\nsecond", "verbatim"),  # a substring across a line break
    (f"{MINUS} no history", "copy"),
    ("no history", "copy"),  # a substring of whole words
    ("cosine 0.8127", "illustrative"),
    ("0.8127", "illustrative"),  # a whole number
    ("#123", "illustrative"),  # a pattern, matched in full
    ("Your notes vanish.", "vo"),  # a voiceover line
    ("vanish.", "vo"),  # one of its words, as displayed
    ("Your", "vo"),
    ("Your notes", "vo"),  # a phrase of a line: whole words, in order
    ("vanish", "vo"),  # a word without its punctuation
    ("you... it's", "vo"),  # a run that crosses an ellipsis
    ("open", "label"),  # a scene id
    ("The Start", "label"),  # an act name
])
def test_what_passes(s, kind):
    assert classify(s, SMALL) == kind


@pytest.mark.parametrize("s", [
    "tool diff a b c",  # longer than the entry it starts like
    "no hist",  # a word cut short: a substring must start and end on a token boundary
    "0.81",  # a number cut short
    "8127",  # a number's tail: "0." before it continues the number
    "cosine 0",  # a number's head: ".8127" after it continues the number
    "Tool diff a b",  # the sheet is case sensitive
    "cosine 0.8128",
    "#12", "#1234", "x#123", "#123\n",  # off the pattern: a pattern has to match the whole string
    "#١٢٣",  # \d in a pattern is an ASCII digit
    "Your vanish",  # not contiguous
    "notes Your",  # not in the line's order
    "note",  # not whole words
    "ope",  # scene ids and act names are matched whole
    "The",
    "I",  # an act's numeral is not an act name
    "tool log --blame",
])
def test_what_fails(s):
    assert classify(s, SMALL) is None


def test_typographic_punctuation_matches_the_typed_forms():
    assert norm(f"it{RSQ}s {LDQ}x{RDQ} {LSQ}y{RSQ} wait{ELLIPSIS}") == "it's \"x\" 'y' wait..."
    assert classify(f"It{RSQ}s not you{ELLIPSIS} it{RSQ}s me.", SMALL) == "vo"
    assert classify(f"you{ELLIPSIS}", SMALL) == "vo"
    assert classify(f"{LDQ}Your notes{RDQ}", SMALL) == "vo"
    assert classify(f"not you{ELLIPSIS} it{RSQ}s", SMALL) == "vo"
    assert classify("it's a \"quote\"", SMALL) == "copy"  # typed input against typographic copy
    assert classify(f"{LDQ}quote{RDQ}", SMALL) == "copy"


# --- phrases of the voiceover: a contiguous run of a line's whole words, punctuation aside ---


def words_only():
    """The film's lines and scenes on a sheet with nothing on it: only voiceover words and labels can pass."""
    return build_allowed({"verbatim": [], "copy": [], "illustrative": []}, VO, SCRIPT)


@pytest.mark.parametrize("s, kind", [
    ("survives the night.", "vo"),
    ("tool you trusted", "vo"),
    ("the nigh", None),  # not whole words
    ("night survives", None),  # not contiguous
])
def test_a_phrase_of_a_line_passes_if_it_is_whole_words_in_order(s, kind):
    assert classify(s, words_only()) == kind


@pytest.mark.parametrize("s", [
    f"Nothing you said{ELLIPSIS} survives the night.",  # a whole line, typographic
    "  survives the night  ",  # whitespace at the ends
    "— survives the night —",  # and punctuation
    f"{LDQ}tool you trusted{RDQ}",
    f"{ELLIPSIS}I say so.",  # L4 begins with its ellipsis
    "survives the\nnight",  # broken over two lines
    "said",  # a word without its punctuation
    "Forty-four",  # a hyphen inside a word stays
])
def test_punctuation_and_whitespace_at_the_ends_do_not_count(s):
    assert classify(s, words_only()) == "vo"


@pytest.mark.parametrize("s", [
    "", " ", "...", "—",  # no words at all is not a run of the voiceover
    "Survives the night",  # case sensitive
    "survives · the night",  # a mark standing between words is not a word
    "same. Nothing you said",  # a run stays inside one line
    "survives the night please",
])
def test_what_is_not_a_phrase_of_the_voiceover(s):
    assert classify(s, words_only()) is None


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


# --- the film's whole sheet ---


@pytest.fixture
def real(sheet_film):
    return load_allowed()


def test_the_sheet_sorts_strings_into_the_right_kinds(real):
    assert classify("$ tool sync notes/today.md 8b21e04 3f9a1c2", real) == "verbatim"
    assert classify(f"{MINUS} no history", real) == "copy"
    assert classify("hotel", real) == "illustrative"
    assert classify("0.5512", real) == "illustrative"  # a float numeral, by its pattern
    assert classify("morning", real) == "vo"
    assert classify("The Turn", real) == "label"
    assert classify("proof", real) == "label"
    assert classify(f"{LDQ}candidates{RDQ}: 2", real) == "copy"
    assert classify(f"It{RSQ}s not you{ELLIPSIS} it{RSQ}s the tool you trusted.", real) == "vo"


@pytest.mark.parametrize("s, passes", [
    (f"{MINUS}0.0931", True),  # a float numeral
    ("0.2143", True),
    ("user-0042", True),  # a namespace row
    ("a41c9d0", True),  # an illustrative commit hash
    ("0.21435", False),  # five decimals
    ("user-42", False),  # two digits
])
def test_the_patterns_let_invented_values_through(real, s, passes):
    assert (classify(s, real) is not None) == passes


@pytest.mark.parametrize("s", [
    "0.551", "12.5512", ".5512", "0,5512", "0.5512 ", "0.5512\n", "x0.5512", "--0.5512",  # not a four decimal numeral
    "user-00042", "User-0042", "user_0042", "user-0042\n", "user-٤٢٠٠",  # not a namespace row
    "b7e3a1", "b7e3a19f", "B7E3A19", "g7e3a19", "b7e3a1\n",  # not seven lowercase hex digits
    "1234567", "defaced", "acceded",  # seven digits, or a word spelt in a-f, is not a commit hash
])
def test_a_value_off_its_pattern_fails(real, s):
    assert classify(s, real) is None


def test_truncated_numbers_and_words_of_the_sheet_fail(real):
    for s in ["56/499", "456/49", "preference 10", "Storage is fre"]:
        assert classify(s, real) is None, s
    for s in ["456/499", "preference 100", "Storage is free"]:
        assert classify(s, real) is not None, s  # the whole tokens still pass


def test_cut_off_words_of_the_voiceover_fail(real):
    for s in ["the nigh", "t's not yo", "the tool you truste", "very morning"]:
        assert classify(s, real) is None, s


def test_the_patterns_are_well_formed():
    for e in SHEET["illustrative_patterns"]:
        re.compile(e["pattern"], re.ASCII)
