import shutil
import struct
import subprocess
import zlib

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


def test_read_png_gives_back_what_write_png_wrote(tmp_path):
    rgba = np.array([[[255, 0, 0, 255], [0, 255, 0, 128], [0, 0, 255, 0]],
                     [[17, 34, 51, 255], [237, 231, 234, 255], [1, 2, 3, 4]]], dtype=np.uint8)
    path = tmp_path / "x.png"
    export.write_png(path, rgba)
    out = export.read_png(path)
    assert out.dtype == np.uint8 and out.shape == (2, 3, 4)  # 2 rows of 3 px, top row first
    assert out.tolist() == rgba.tolist()


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _png(w: int, h: int, raw: bytes, color_type: int = 6, depth: int = 8, interlace: int = 0) -> bytes:
    """A PNG built by hand: `raw` is the filtered scanlines (a filter byte, then the row's bytes, per row)."""
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, color_type, 0, 0, interlace))
            + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))


def test_read_png_reads_rgb_too(tmp_path):
    path = tmp_path / "rgb.png"
    path.write_bytes(_png(2, 1, bytes([0, 1, 2, 3, 4, 5, 6]), color_type=2))  # one row: filter 0, then (1,2,3), (4,5,6)
    assert export.read_png(path).tolist() == [[[1, 2, 3], [4, 5, 6]]]


def test_read_png_refuses_what_it_cannot_decode_exactly(tmp_path):
    cases = {
        "not a png": b"GIF89a not a png at all",
        "filtered": _png(2, 1, bytes([1, 1, 2, 3, 4, 5, 6, 7, 8])),  # filter 1 (Sub): write_png never writes it
        "16 bit": _png(1, 1, bytes([0]) + bytes(8), depth=16),
        "greyscale": _png(2, 1, bytes([0, 9, 9]), color_type=0),
        "interlaced": _png(1, 1, bytes([0, 1, 2, 3, 4]), interlace=1),
    }
    for name, data in cases.items():
        path = tmp_path / f"{name.replace(' ', '_')}.png"
        path.write_bytes(data)
        with pytest.raises(ValueError):
            export.read_png(path)


def test_read_png_notices_a_file_cut_off_anywhere(tmp_path):
    rgba = np.random.default_rng(3).integers(0, 256, (16, 16, 4), dtype=np.uint8)  # noise: a chunk of real length
    good = tmp_path / "good.png"
    export.write_png(good, rgba)
    data = good.read_bytes()
    assert export.read_png(good).tolist() == rgba.tolist()
    cut = tmp_path / "cut.png"
    for n in range(len(data)):  # every shorter prefix: in the signature, or a chunk's header, body or CRC
        cut.write_bytes(data[:n])
        with pytest.raises(ValueError):
            export.read_png(cut)


def test_read_png_notices_a_failed_crc_a_missing_chunk_and_the_wrong_amount_of_data(tmp_path):
    good = tmp_path / "good.png"
    export.write_png(good, np.full((8, 8, 4), 200, np.uint8))
    data = good.read_bytes()
    i = data.index(b"IDAT")
    crc_at = i + 4 + struct.unpack(">I", data[i - 4:i])[0]  # the IDAT chunk's CRC: the data itself is untouched
    signature, header = data[:8], data[8:8 + 25]  # the signature and the IHDR chunk (13 bytes of data in 25)
    cases = {
        "crc": (data[:crc_at] + bytes([data[crc_at] ^ 0xFF]) + data[crc_at + 1:], "CRC"),
        "no_end": (data[:-12], "truncated"),  # the IEND chunk is 12 bytes
        "no_data": (signature + header + _chunk(b"IEND", b""), "truncated"),
        "short": (_png(2, 2, bytes([0]) + bytes(8)), "bytes of image data"),  # one row of the two the header says
        "long": (_png(1, 1, bytes([0]) + bytes(8)), "bytes of image data"),
    }
    for name, (content, message) in cases.items():
        path = tmp_path / f"{name}.png"
        path.write_bytes(content)
        with pytest.raises(ValueError, match=message):
            export.read_png(path)
