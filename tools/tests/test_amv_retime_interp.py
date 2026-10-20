"""Interpolators: optical flow places a moving square half-way within 1 px; the RIFE network runs and keeps its shape."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")


def square(x, size=(180, 320), side=48, y=70):
    img = np.full((*size, 3), 0.15, np.float32)
    rng = np.random.default_rng(1)
    bg = (rng.random((*size, 3)) * 0.1).astype(np.float32)           # texture for the flow to lock onto
    img += cv2.GaussianBlur(bg, (0, 0), 2) * 2
    patt = (rng.random((side, side, 3)) * 0.4 + 0.5).astype(np.float32)
    img[y:y + side, x:x + side] = patt
    return img


def centroid_x(img, thr=0.45):
    m = img.mean(-1) > thr
    return np.nonzero(m)[1].mean()


def test_flow_halfway_square_within_a_pixel():
    from filmtools.amv.interp.flow import FlowInterpolator
    a, b = square(60), square(84)
    mid = FlowInterpolator(work_width=320).between(a, b, [0.5])[0]
    assert abs(centroid_x(mid) - (centroid_x(a) + centroid_x(b)) / 2) < 1.0
    # sharp, not a ghosted double square: the square's pixels are bright and cover its full area
    assert (mid.mean(-1) > 0.45).sum() == pytest.approx(48 * 48, rel=0.08)


def test_flow_quarter_time():
    from filmtools.amv.interp.flow import FlowInterpolator
    a, b = square(60), square(84)
    q = FlowInterpolator(work_width=320).between(a, b, [0.25])[0]
    assert abs(centroid_x(q) - (centroid_x(a) * 0.75 + centroid_x(b) * 0.25)) < 1.5


def test_flow_identical_frames_returns_the_frame():
    from filmtools.amv.interp.flow import FlowInterpolator
    a = square(60)
    out = FlowInterpolator(work_width=320).between(a, a.copy(), [0.3])[0]
    assert np.abs(out - a).max() < 0.02


def test_rife_architecture_runs_with_random_weights():
    torch = pytest.importorskip("torch")
    from filmtools.amv.interp import rife
    net = rife.IFNet().eval()
    x = torch.rand(2, 3, 64, 64)
    with torch.no_grad():
        y = net(x, torch.rand(2, 3, 64, 64), torch.tensor([0.25, 0.75]).view(-1, 1, 1, 1))
    assert y.shape == x.shape and torch.isfinite(y).all()


def test_rife_weights_pin():
    pytest.importorskip("torch")
    from filmtools.amv.interp import rife
    assert len(rife.WEIGHTS_SHA256) == 64 and rife.WEIGHTS_URL.endswith("flownet.pkl")


def test_rife_pretrained_is_a_midpoint_if_cached():
    torch = pytest.importorskip("torch")
    from filmtools.amv.interp import rife
    p = rife.cache_dir() / "flownet.pkl"
    if not (p.is_file() and rife._sha256(p) == rife.WEIGHTS_SHA256):
        pytest.skip("RIFE weights not in the cache (python -m filmtools.amv.interp.rife --fetch)")
    a, b = square(60), square(84)
    mid = rife.RifeInterpolator(device="cpu").between(a, b, [0.5])[0]
    assert abs(centroid_x(mid) - (centroid_x(a) + centroid_x(b)) / 2) < 2.0
