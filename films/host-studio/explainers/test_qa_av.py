import math

from qa_av import captions_numbers, exposure_numbers, facts_numbers, parse_ebur128, parse_srt

VO = {"lines": {"W01": {"text": "WhatsApp delivers over a hundred billion messages a day.", "start_s": 1.0, "end_s": 4.0},
                "W02": {"text": "Each phone keeps one connection open.", "start_s": 4.5, "end_s": 6.5}}}
SRT = """1
00:00:01,040 --> 00:00:02,500
WhatsApp delivers over a hundred

2
00:00:02,500 --> 00:00:04,000
billion messages a day.

3
00:00:04,600 --> 00:00:06,500
Each phone keeps one connection open.
"""


def test_captions_match_and_onsets():
    g = captions_numbers(parse_srt(SRT), VO)
    assert g["captions.text_match"]["value"] == 1
    assert g["captions.onset_ms"]["value"] == 100 and "W02" in g["captions.onset_ms"]["where"]


def test_captions_word_change_and_missing_line():
    g = captions_numbers(parse_srt(SRT.replace("open.", "alive.")), VO)
    assert g["captions.text_match"]["value"] == 0 and "open" in g["captions.text_match"]["where"]
    g = captions_numbers(parse_srt(SRT.split("\n\n3")[0]), VO)
    assert g["captions.onset_ms"]["value"] is None and "W02" in g["captions.onset_ms"]["error"]


def test_exposure_jump_and_drift():
    flat = [0.18] * 30
    assert exposure_numbers({"A": flat})["shot.exposure_jump_stops"]["value"] == 0
    pop = flat[:15] + [0.18 * 2 ** 0.3] * 15  # a 0.3-stop step mid-shot
    g = exposure_numbers({"A": flat, "B": pop})
    assert math.isclose(g["shot.exposure_jump_stops"]["value"], 0.3, abs_tol=1e-3) and "B" in g["shot.exposure_jump_stops"]["where"]
    ramp = [0.18 * 2 ** (k / 100) for k in range(48)]  # a slow 0.47-stop drift, no single jump
    g = exposure_numbers({"R": ramp})
    assert g["shot.exposure_jump_stops"]["value"] < 0.02 and g["shot.exposure_drift_stops"]["value"] > 0.3


def test_facts_softened_or_sourced():
    assert facts_numbers(VO, {"claims": []})["facts.sourced"]["value"] == 1  # softened ("over a hundred billion"); "one connection" is no claim
    vo = {"lines": {"N1": {"text": "Netflix has 300 million members.", "start_s": 0, "end_s": 2}}}
    assert facts_numbers(vo, {"claims": []})["facts.sourced"]["value"] == 0
    src = {"claims": [{"said": "300 million members", "source": "https://example.com/q3-letter"}]}
    assert facts_numbers(vo, src)["facts.sourced"]["value"] == 1


def test_ebur128_summary():
    t = "...\nSummary:\n\n  Integrated loudness:\n    I:         -14.2 LUFS\n  True peak:\n    Peak:       -1.3 dBFS\n"
    assert parse_ebur128(t) == (-14.2, -1.3)


def test_format():
    from qa_av import format_numbers
    ok = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "24/1"},
                      {"codec_type": "audio", "sample_rate": "48000"}], "format": {"duration": "61.5"}}
    g = format_numbers(ok)
    assert g["deliver.format_ok"]["value"] == 1 and g["deliver.duration_s"]["value"] == 61.5
    ok["streams"][0].update(width=1080, height=1920)
    assert "16:9" in format_numbers(ok)["deliver.format_ok"]["where"]


def test_agent11_cues_and_spelled_numbers():
    vo = {"lines": [{"id": "N01", "text": "Netflix has over three hundred million paying members.", "start": 0.75, "end": 3.9},
                    {"id": "N02", "text": "Each title gets twelve hundred encodes.", "start": 4.2, "end": 6.0}]}
    g = facts_numbers(vo, {"claims": []})
    assert g["facts.sourced"]["value"] == 0 and "N02" in g["facts.sourced"]["where"] and "N01" not in g["facts.sourced"]["where"]
    srt = "1\n00:00:00,750 --> 00:00:03,900\nNetflix has over three hundred million paying members.\n\n" \
          "2\n00:00:04,200 --> 00:00:06,000\nEach title gets twelve hundred encodes.\n"
    assert captions_numbers(parse_srt(srt), vo)["captions.text_match"]["value"] == 1


def test_onset_uses_the_caption_with_the_lines_first_word_not_one_still_on_screen():
    vo = {"lines": [{"id": "A", "text": "One two three.", "start": 1.0, "end": 2.0},
                    {"id": "B", "text": "Four five.", "start": 2.3, "end": 3.5}]}
    srt = "1\n00:00:00,950 --> 00:00:02,400\nOne two three.\n\n2\n00:00:02,400 --> 00:00:03,500\nFour five.\n"
    g = captions_numbers(parse_srt(srt), vo)
    assert g["captions.onset_ms"]["value"] == 100 and "B" in g["captions.onset_ms"]["where"]
