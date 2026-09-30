import pytest

from gitloom_film.align import words_from_alignment, words_to_dicts


def al(text, dt=0.1):
    starts = [i * dt for i in range(len(text))]
    return {"characters": list(text), "character_start_times_seconds": starts,
            "character_end_times_seconds": [s + dt for s in starts]}


def test_words_carry_punctuation_and_letter_times():
    ws = words_from_alignment(al("Every conversation... back to zero."))
    assert [w.w for w in ws] == ["Every", "conversation...", "back", "to", "zero."]
    assert ws[1].start == pytest.approx(0.6)  # 'c' is character 6
    assert ws[1].end == pytest.approx(1.8)  # its last letter 'n' is character 17


def test_leading_ellipsis_attaches_to_first_word():
    ws = words_from_alignment(al("...I say so."))
    assert ws[0].w == "...I" and ws[0].start == pytest.approx(0.3)


def test_hyphen_and_apostrophe_words():
    ws = words_from_alignment(al("It's Forty-four..."))
    assert [w.w for w in ws] == ["It's", "Forty-four..."]
    assert ws[1].start == pytest.approx(0.5) and ws[1].end == pytest.approx(1.5)


def test_detached_punctuation_joins_previous_word():
    ws = words_from_alignment(al("Go ahead ... Blame me."))
    assert [w.w for w in ws] == ["Go", "ahead...", "Blame", "me."]


def test_mismatched_arrays_raise():
    a = al("Hi.")
    a["character_end_times_seconds"].pop()
    with pytest.raises(ValueError, match="differ in length"):
        words_from_alignment(a)


def test_to_dicts_rounds():
    assert words_to_dicts(words_from_alignment(al("Hi."))) == [{"w": "Hi.", "start": 0.0, "end": 0.2}]
