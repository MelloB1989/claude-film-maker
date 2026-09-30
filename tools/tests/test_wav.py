import numpy as np

from gitloom_film.wav import SR, pcm16_to_float, read_wav, write_wav


def test_pcm16_to_float_scales():
    b = np.array([0, 16384, -32768, 32767], dtype="<i2").tobytes()
    assert np.allclose(pcm16_to_float(b), [0, 0.5, -1, 32767 / 32768])


def test_pcm16_stereo_deinterleaves():
    x = pcm16_to_float(np.array([1, -1, 2, -2], dtype="<i2").tobytes(), channels=2)
    assert x.shape == (2, 2) and x[1, 1] == -2 / 32768


def test_wav_roundtrip_24bit(tmp_path):
    x = (np.sin(np.linspace(0, 100, SR)) * 0.5).astype(np.float32)
    write_wav(tmp_path / "a.wav", x)
    y, sr = read_wav(tmp_path / "a.wav")
    assert sr == SR and np.max(np.abs(x - y)) < 1e-6


def test_read_wav_downmixes_unless_asked(tmp_path):
    st = (np.stack([np.ones(100), -np.ones(100) * 0.5], axis=1) * 0.5).astype(np.float32)
    write_wav(tmp_path / "s.wav", st)
    y, _ = read_wav(tmp_path / "s.wav")
    assert np.allclose(y, 0.125, atol=1e-6)
    z, _ = read_wav(tmp_path / "s.wav", mono=False)
    assert z.shape == (100, 2)
