import shutil
import subprocess

import numpy as np
import pytest

from lib import export

# Expected values are derived by hand (the sRGB formula, box averages worked on paper), never with export.py.


def test_plate_paths_are_where_the_engine_reads_them():
    # app/src/engine/plates.ts plateUrl: out/plates/<shot>/####.exr, and plates/<shot>/proxy/####.png under app/public
    p = export.plate_paths("_cube", 7)
    assert p.exr == export.REPO / "out/plates/_cube/0007.exr"
    assert p.proxy == export.REPO / "app/public/plates/_cube/proxy/0007.png"


def test_look_stills_are_named_by_film_frame():
    assert export.look_path("_cube", 47) == export.REPO / "out/look/_cube/0047.png"


def test_to_logical_maps_the_camera_view_onto_the_1920x1080_frame():
    # world_to_camera_view: x, y from 0 to 1 across the frame from its bottom-left corner, z the depth in front
    assert export.to_logical((0.5, 0.5, 3.0)) == (960.0, 540.0, 1)
    assert export.to_logical((0.0, 1.0, 2.0)) == (0.0, 0.0, 1)  # top-left
    assert export.to_logical((1.0, 0.0, 2.0)) == (1920.0, 1080.0, 1)  # bottom-right
    assert export.to_logical((0.25, 0.75, 1.0)) == (480.0, 270.0, 1)


def test_to_logical_hides_anchors_off_frame_or_behind_the_camera_but_keeps_their_place():
    assert export.to_logical((1.25, 0.5, 2.0)) == (2400.0, 540.0, 0)
    assert export.to_logical((0.5, -0.1, 2.0)) == (960.0, 1188.0, 0)
    assert export.to_logical((0.5, 0.5, -1.0))[2] == 0
    assert export.to_logical((0.5, 0.5, 0.0))[2] == 0


def test_track_doc_is_the_engine_format_with_rounded_px():
    doc = export.track_doc(40, {"corner": [(100.123456, 200.5, 1), (130.0004, 180.9996, 0)]})
    assert doc == {"fps": 30, "f0": 40, "anchors": {"corner": [[100.123, 200.5, 1], [130.0, 181.0, 0]]}}


def test_resample_area_averages_whole_pixels():
    img = np.array([[[0.0], [2.0], [4.0], [6.0]],
                    [[1.0], [3.0], [5.0], [7.0]]])  # 2 rows x 4 columns, 1 channel
    out = export.resample_area(img, 2, 1)
    assert out.shape == (1, 2, 1)
    np.testing.assert_allclose(out[..., 0], [[1.5, 5.5]])


def test_resample_area_splits_pixels_at_fractional_scales():
    # 3 px -> 2 px: each output pixel covers 1.5 input pixels, the middle one shared half and half
    img = np.array([[[0.0], [3.0], [6.0]]])
    out = export.resample_area(img, 2, 1)
    np.testing.assert_allclose(out[..., 0], [[1.0, 5.0]])  # (0 + 1.5) / 1.5, (1.5 + 6) / 1.5


def test_srgb8_is_the_srgb_transfer_clipped_to_8_bits():
    lin = np.array([0.0, 0.001, 0.5, 0.846873, 1.0, 2.0, -1.0])
    assert export.srgb8(lin).tolist() == [0, 3, 188, 237, 255, 255, 0]  # 3.29, 187.52, bone's 237


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg to decode the PNG")
def test_write_png_writes_what_a_decoder_reads_back(tmp_path):
    rgba = np.array([[[255, 0, 0, 255], [0, 255, 0, 128], [0, 0, 255, 0]],
                     [[17, 34, 51, 255], [237, 231, 234, 255], [1, 2, 3, 4]]], dtype=np.uint8)
    path = tmp_path / "x.png"
    export.write_png(path, rgba)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                         check=True, capture_output=True).stdout
    assert raw == rgba.tobytes()
