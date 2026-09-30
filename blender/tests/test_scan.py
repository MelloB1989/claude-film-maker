"""Scanning a shot's existing plates (lib/scan.py), with the EXR reader faked: no Blender needed.

A plate's index is its film frame minus the shot's f0; the film frames are what the report names. The shot's window
[f0, f1) says which plates there must be.
"""
import numpy as np
import pytest

from lib import blank, export, scan

F0 = 100


def lit(peak=0.8):
    px = np.zeros((2, 2, 4), np.float32)
    px[0, 0] = (peak, peak / 2, peak / 4, 1.0)
    return px


def black():
    return np.zeros((2, 2, 4), np.float32)


def lit_at(w, h):
    """A lit plate w x h px."""
    px = np.zeros((h, w, 4), np.float32)
    px[..., :3] = 0.006
    px[0, 0] = (0.8, 0.4, 0.2, 1.0)
    return px


def png(peak):
    """A 2 x 2 RGBA proxy whose brightest RGB code value is `peak`."""
    px = np.zeros((2, 2, 4), np.uint8)
    px[..., 3] = 255
    px[0, 0, 0] = peak
    return px


class Plates:
    """A plate tree under tmp_path for one shot. EXR files are placeholders: the reader answers from `exr_px`."""

    def __init__(self, root, shot="b07_test"):
        self.root, self.shot = root, shot
        self.exr_px, self.exr_reads, self.png_reads, self.indices = {}, [], [], set()

    def exr(self, index, px):
        p = export.plate_paths(self.shot, index, self.root).exr
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"placeholder: the fake reader answers")
        self.exr_px[p] = px
        self.indices.add(index)
        return p

    def proxy(self, index, rgba):
        p = export.plate_paths(self.shot, index, self.root).proxy
        export.write_png(p, rgba)
        self.indices.add(index)
        return p

    def read_exr(self, path):
        self.exr_reads.append(path)
        v = self.exr_px[path]
        if isinstance(v, Exception):
            raise v
        return v

    def read_png(self, path):
        self.png_reads.append(path)
        return export.read_png(path)

    def scan(self, exempt=lambda f: False, f0=F0, f1=None, **kw):
        """Scan the plates; the shot's window defaults to the plates written: up to the last one, gaps and all."""
        f1 = f0 + max(self.indices, default=-1) + 1 if f1 is None else f1
        return scan.scan_plates(self.shot, f0, f1, exempt, root=self.root, read_exr=self.read_exr,
                                read_png=self.read_png, **kw)


def test_a_clean_shot_scans_clean_and_reports_its_dimmest_frame(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit(0.5))
    t.exr(1, lit(0.004))
    t.exr(2, lit(2.0))
    res = t.scan()
    assert res.plates == 3 and res.from_proxy == 0
    assert res.blank == [] and res.unreadable == [] and res.exempt == []
    assert res.clean is True
    peak, film_frame = res.dimmest
    assert peak == pytest.approx(0.004) and film_frame == F0 + 1
    text = "\n".join(scan.report(res))
    for part in ("b07_test", "3 plates", "0000-0002", "all lit", "film frame 101", "0.004"):
        assert part in text


def test_a_blank_exr_is_listed_with_its_film_frame_and_path(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit())
    bad = t.exr(1, black())
    t.exr(2, lit())
    res = t.scan()
    assert res.clean is False
    (f,) = res.blank
    assert (f.film_frame, f.index, f.path) == (F0 + 1, 1, bad)
    text = "\n".join(scan.report(res))
    assert "BLANK" in text and f"film frame {F0 + 1}" in text and str(bad) in text and "all lit" not in text


def test_blank_plates_are_listed_in_frame_order_whatever_order_the_disk_gives(tmp_path):
    t = Plates(tmp_path)
    for i in (5, 1, 3, 2):
        t.exr(i, black() if i in (5, 1, 3) else lit())
    assert [f.index for f in t.scan().blank] == [1, 3, 5]


def test_a_plate_with_only_a_proxy_is_judged_by_the_proxy(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit(5.0))
    t.proxy(0, png(200))
    blank_proxy = t.proxy(1, png(0))
    t.proxy(2, png(1))  # one code value: still blank
    t.proxy(3, png(2))  # two: a dark frame, but lit
    res = t.scan()
    assert res.plates == 4 and res.from_exr == 1 and res.from_proxy == 3
    assert res.dimmest == (5.0, F0)  # the proxies' 8-bit codes are another unit: only EXR plates count
    assert [(f.film_frame, f.path) for f in res.blank] == [(F0 + 1, blank_proxy),
                                                          (F0 + 2, export.plate_paths("b07_test", 2, tmp_path).proxy)]


def test_the_exr_decides_when_a_plate_has_both_and_the_proxy_is_not_read(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit(0.0004))  # its proxy is 0-1 codes (blank by the proxy's rule), but the EXR is lit
    t.proxy(0, png(0))
    res = t.scan()
    assert res.clean and res.from_proxy == 0
    assert t.png_reads == []


def test_declared_black_frames_are_not_judged_blank_but_are_still_bad_with_nans(tmp_path):
    # black_ok lets a frame be black, not hold NaNs: those would bloom into a block in the film all the same
    t = Plates(tmp_path)
    t.exr(0, black())
    nan_black = black()
    nan_black[0, 1, 2] = np.nan
    t.exr(1, nan_black)
    t.exr(2, lit())
    res = t.scan(exempt=lambda f: f in (F0, F0 + 1))
    assert res.blank == [] and res.exempt == [F0, F0 + 1]
    assert [f.film_frame for f in res.bad] == [F0 + 1] and res.clean is False
    assert "2 declared black_ok" in "\n".join(scan.report(res))


def test_an_unreadable_plate_is_reported_and_the_scan_goes_on(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit())
    t.exr(1, RuntimeError("truncated file"))
    t.exr(2, black())
    res = t.scan()
    assert res.clean is False
    (u,) = res.unreadable
    assert (u.film_frame, u.index) == (F0 + 1, 1) and "truncated file" in u.detail
    assert [f.index for f in res.blank] == [2]  # it went on past the unreadable one
    text = "\n".join(scan.report(res))
    assert "UNREADABLE" in text and "truncated file" in text
    assert str(u.path) in text


def test_an_unreadable_plate_whose_error_names_the_file_is_not_named_twice(tmp_path):
    t = Plates(tmp_path)
    p = t.exr(0, black())
    t.exr_px[p] = ValueError(f"{p}: Blender could not read any pixels from it")
    (line,) = scan.report(t.scan())[1:]
    assert line.count(str(p)) == 1


def test_a_plate_with_nans_or_infs_is_listed_as_bad(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit())
    px = lit()
    px[1, 1, 0] = np.nan
    px[1, 0, 1] = np.inf
    bad = t.exr(1, px)
    res = t.scan()
    assert res.clean is False and res.blank == []
    (f,) = res.bad
    assert (f.film_frame, f.index, f.path) == (F0 + 1, 1, bad)
    assert "not finite" in f.detail and "1 NaN" in f.detail and "1 inf" in f.detail
    text = "\n".join(scan.report(res))
    assert "1 BAD" in text and f"BAD film frame {F0 + 1}" in text and str(bad) in text and "all lit" not in text


def test_a_plate_with_a_black_tile_is_listed_as_blank(tmp_path):
    # a final rendered in tiles that lost one: lit elsewhere, so its brightest value alone passes
    t = Plates(tmp_path)
    px = np.full((6, 10, 4), 0.006, np.float32)
    px[2:6, 4:8, :3] = 0.0
    t.exr(0, px)
    res = t.scan(tile=4)
    (f,) = res.blank
    assert "black tile" in f.detail and "x 4-8, y 2-6" in f.detail
    assert t.scan().clean  # at Cycles' 2048-px tile this 10 x 6 plate is one tile, and it is lit


def test_scan_reports_missing_indices_and_mixed_sizes(tmp_path):
    # a final that stopped part way (plates 0, 1 and 3 at its size), look frames rendered over it afterwards (plate 4,
    # another size), and plates 2 and 5 never written; the shot is [F0, F0 + 6)
    t = Plates(tmp_path)
    for i in (0, 1, 3):
        t.exr(i, lit_at(32, 18))
    t.exr(4, lit_at(16, 9))
    res = t.scan(f1=F0 + 6)
    assert res.clean is False
    assert res.missing == [2, 5] and res.extra == []
    assert res.sizes == {(32, 18): [F0, F0 + 1, F0 + 3], (16, 9): [F0 + 4]}
    assert res.blank == [] and res.bad == [] and res.unreadable == []
    text = "\n".join(scan.report(res))
    for part in ("4 of 6 plates", "2 MISSING", f"MISSING film frames {F0 + 2},{F0 + 5}", "MIXED SIZES",
                 f"32x18: film frames {F0}-{F0 + 1},{F0 + 3}", f"16x9: film frame {F0 + 4}"):
        assert part in text, part
    assert "all lit" not in text


def test_plates_outside_the_shots_window_are_extra_and_not_judged(tmp_path):
    # the shot's window moved (weave now starts a frame later), so its old plate set runs one past the end
    t = Plates(tmp_path)
    for i in range(3):
        t.exr(i, lit())
    over = t.exr(3, black())
    res = t.scan(f1=F0 + 3)
    assert res.extra == [3] and res.missing == [] and res.blank == []
    assert over not in t.exr_reads and res.clean is False
    text = "\n".join(scan.report(res))
    assert "1 EXTRA" in text and f"EXTRA plate 0003 (film frame {F0 + 3})" in text and f"[{F0}, {F0 + 3})" in text


def test_expect_res_fails_every_plate_of_another_size(tmp_path):
    t = Plates(tmp_path)
    for i in range(3):
        t.exr(i, lit_at(16, 9))
    assert t.scan().clean  # one size throughout: fine when no size is asked for
    assert t.scan(expect_res=(16, 9)).clean
    res = t.scan(expect_res=(32, 18))
    assert res.clean is False
    text = "\n".join(scan.report(res))
    assert "WRONG SIZE" in text and "not 32x18" in text and f"16x9: film frames {F0}-{F0 + 2}" in text


def test_files_that_are_not_plates_are_ignored(tmp_path):
    t = Plates(tmp_path)
    t.exr(0, lit())
    d = export.plate_paths("b07_test", 0, tmp_path).exr.parent
    (d / "0003.npy").write_bytes(b"not a plate")
    (d / "notes.txt").write_text("x")
    (d / "preview.exr").write_bytes(b"not numbered")
    res = t.scan()
    assert res.plates == 1 and res.clean


def test_a_shot_with_no_plates_is_an_error_not_a_clean_scan(tmp_path):
    with pytest.raises(FileNotFoundError, match="b07_test"):
        Plates(tmp_path).scan()
