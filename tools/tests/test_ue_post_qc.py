"""B53 delivery QC (filmtools.unreal.post_qc): parsers and checks on canned ffmpeg output, probes mocked."""
import json

from filmtools.unreal import post_cli, post_cut, post_qc as qc

EBUR = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -14.3 LUFS
    Threshold: -24.5 LUFS

  Loudness range:
    LRA:         6.1 LU

  True peak:
    Peak:       -1.4 dBFS
"""
BLACK = "[blackdetect @ 0x2] black_start:0 black_end:0.5 black_duration:0.5\n" \
        "[blackdetect @ 0x2] black_start:2.0 black_end:2.75 black_duration:0.75\n"
FREEZE = "[freezedetect @ 0x3] lavfi.freezedetect.freeze_start: 3.0\n" \
         "[freezedetect @ 0x3] lavfi.freezedetect.freeze_duration: 2.5\n" \
         "[freezedetect @ 0x3] lavfi.freezedetect.freeze_end: 5.5\n"


def probe_json(frames=120, audio=5.0, w=1920, h=1080, streams=("video", "audio")):
    st = []
    if "video" in streams:
        st.append({"codec_type": "video", "codec_name": "h264", "width": w, "height": h, "r_frame_rate": "24/1",
                   "nb_read_frames": str(frames)})
    if "audio" in streams:
        st.append({"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "duration": str(audio)})
    return {"streams": st, "format": {"duration": str(audio)}}


class FakeProbes:
    def __init__(self, info, ebur=EBUR, black="", freeze=""):
        self.info, self.e, self.b, self.f = info, ebur, black, freeze

    def probe(self, path):
        return self.info

    def ebur128(self, path):
        return self.e

    def blackdetect(self, path, min_s):
        return self.b

    def freezedetect(self, path, min_s):
        return self.f


def test_parsers():
    assert qc.parse_ebur128(EBUR) == {"I": -14.3, "TP": -1.4, "LRA": 6.1}
    assert qc.parse_black(BLACK) == [[0.0, 0.5], [2.0, 2.75]]
    assert qc.parse_freeze(FREEZE, 10) == [[3.0, 5.5]]
    assert qc.parse_freeze("freeze_start: 9.0", 10) == [[9.0, 10]]
    srt = "1\n00:00:01,000 --> 00:00:02,500\nHello there.\n\n2\n00:00:03,000 --> 00:00:04,000\nBye.\n"
    assert qc.parse_captions(srt) == [[1.0, 2.5, "Hello there."], [3.0, 4.0, "Bye."]]
    assert qc.parse_captions("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nA\nB\n") == [[1.0, 2.0, "A B"]]


def test_edl_round_trip_from_post_cut(tmp_path):
    spec = post_cut.validate({"kind": "delivery", "version": 1, "name": "d", "fps": 24, "edl": [[12, 24], [40, 60]],
                              "shots": [{"id": "S01", "start": 0, "end": 48, "frames": "a"},
                                        {"id": "S02", "start": 48, "end": 96, "frames": "b"}],
                              "outputs": [{"name": "m", "preset": "h264"}]}, tmp_path)
    e = qc.parse_edl(post_cut.cmx3600(spec), 24)
    assert e["frames"] == 32 and e["cuts"] == [12, 20] and [x["clip"] for x in e["events"]] == ["S01", "S01", "S02"]


def test_clean_delivery_passes(tmp_path):
    (tmp_path / "d.srt").write_text("1\n00:00:01,000 --> 00:00:02,500\nHello there.\n")
    edl = "TITLE: D\nFCM: NON-DROP FRAME\n\n001  AX       V     C        00:00:00:00 00:00:05:00 00:00:00:00 00:00:05:00\n"
    (tmp_path / "d.edl").write_text(edl)
    r = qc.run(tmp_path / "d.mp4", tmp_path / "d.edl", tmp_path / "d.srt", probes=FakeProbes(probe_json(), black=BLACK[:63]))
    assert r["pass"] and r["issues"] == [], r["issues"]  # the 0-0.5 s black is the head allowance
    assert r["metrics"]["loudness"]["I"] == -14.3 and r["metrics"]["edl_frames"] == 120


def test_every_problem_is_reported(tmp_path):
    srt = ("1\n00:00:01,000 --> 00:00:01,300\nThis one is far too fast to read in the time it has on screen\n\n"
           "2\n00:00:01,200 --> 00:00:02,000\nOverlap.\n\n3\n00:00:04,500 --> 00:00:05,600\nAcross the cut.\n")
    (tmp_path / "c.srt").write_text(srt)
    edl = ("001  AX       V     C        00:00:00:00 00:00:05:00 00:00:00:00 00:00:05:00\n"
           "002  AX       V     C        00:00:10:00 00:00:11:00 00:00:05:00 00:00:06:00\n")
    (tmp_path / "c.edl").write_text(edl)
    loud = EBUR.replace("-14.3", "-18.0").replace("-1.4 dBFS", "-0.2 dBFS")
    r = qc.run(tmp_path / "c.mp4", tmp_path / "c.edl", tmp_path / "c.srt",
               probes=FakeProbes(probe_json(frames=130, audio=5.0), ebur=loud, black=BLACK, freeze=FREEZE))
    codes = {i["code"] for i in r["issues"]}
    assert not r["pass"]
    assert {"qc.duration_vs_edl", "qc.duration_audio", "qc.loudness_off_target", "qc.true_peak_over",
            "qc.black_frames", "qc.frozen_frames", "qc.caption_short", "qc.caption_fast", "qc.caption_overlap",
            "qc.caption_across_cut"} <= codes
    black = next(i for i in r["issues"] if i["code"] == "qc.black_frames")
    assert black["frame"] == 48 and black["severity"] == "fail" and "fix" in black
    md = qc.markdown(r)
    assert md.startswith("# Delivery QC: c.mp4") and "**FAIL**" in md and "`qc.true_peak_over`" in md


def test_streams_and_safe_area():
    f = qc.stream_facts(probe_json(streams=("video",), w=1080, h=1920))
    r = qc.report(f, None, [], [], None, [[0.0, 3.0, "This caption is far too long to fit on two lines of a "
                                                    "vertical phone frame at this size, really"]])
    codes = {i["code"] for i in r["issues"]}
    assert codes >= {"qc.streams", "qc.caption_safe_area"}


def test_cli_writes_json_and_md(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qc, "Probes", lambda: FakeProbes(probe_json()))
    rc = post_cli.main(["qc", str(tmp_path / "x.mp4"), "-o", str(tmp_path / "q.json"), "--md", str(tmp_path / "q.md")])
    assert rc == 0 and json.loads((tmp_path / "q.json").read_text())["pass"]
    assert (tmp_path / "q.md").read_text().startswith("# Delivery QC")
