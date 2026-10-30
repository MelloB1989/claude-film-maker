import math

import numpy as np
import pytest

from lib import water


def _cylinder(r=0.1, n=12, z0=-1.0, z1=1.0, at=(2.0, 3.0)):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ring = np.c_[at[0] + r * np.cos(a), at[1] + r * np.sin(a)]
    verts = np.r_[np.c_[ring, np.full(n, z0)], np.c_[ring, np.full(n, z1)]]
    edges = [(i, i + n) for i in range(n)] + [(i, (i + 1) % n) for i in range(n)] + \
        [(n + i, n + (i + 1) % n) for i in range(n)]
    return verts, edges


def test_waterline_is_where_the_upright_edges_cross_the_level():
    v, e = _cylinder()
    pts = water.waterline(v, e, 0.25)
    assert pts.shape == (12, 2)                         # only the 12 uprights cross it
    assert np.allclose(np.hypot(pts[:, 0] - 2.0, pts[:, 1] - 3.0), 0.1)
    assert len(water.waterline(v, e, 2.0)) == 0          # above it all: nothing
    assert water.waterline(v, [], 0.0).shape == (0, 2)


def test_collar_ring_hugs_the_outline_from_outside():
    v, e = _cylinder(r=0.2)
    verts, quads, out = water.collar_ring(water.waterline(v, e, 0.0), 0.3, n=16, pad=0.01)
    assert verts.shape == (32, 2) and len(quads) == 16 and max(max(q) for q in quads) == 31
    r = np.hypot(verts[:, 0] - 2.0, verts[:, 1] - 3.0)
    assert np.all(r[:16] >= 0.2 - 0.01) and np.all(r[:16] <= 0.22)       # inner: just outside the post
    assert np.allclose(r[16:] - r[:16], 0.3)                               # outer: `width` beyond
    assert list(out) == [0.0] * 16 + [1.0] * 16


def test_ring_layers_scale_cells_and_fades_for_a_puddle():
    river = water.ring_layers(1.0)
    puddle = water.ring_layers(0.3)
    assert river == list(water.RING_LAYERS)
    for (c, rate, w, near, far), (c1, *_rest) in zip(puddle, river):
        assert c == pytest.approx(c1 * 0.3) and near >= 1.0 and far > near
    # finer layers fade closer than broader ones
    assert all(a[4] <= b[4] for a, b in zip(river, river[1:]))
