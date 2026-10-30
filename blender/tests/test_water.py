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
    for (c, rate, w, appear, near, far), (c1, *_rest) in zip(puddle, river):
        assert c == pytest.approx(c1 * 0.3) and near >= 1.0 and far > near > appear
    # finer layers fade closer than broader ones, and the finest ring right under the lens
    assert all(a[5] <= b[5] and a[3] <= b[3] for a, b in zip(river, river[1:])) and river[0][3] == 0.0


def test_wake_shape_opens_from_the_bow_and_trails_the_stern():
    v, quads, out, side = water.wake_shape(5.0, arm=8.0, spread=20.0, trail=4.0, n=8)
    assert len(v) == 3 * 3 * 9 and len(quads) == 3 * 8 * 2 and max(max(q) for q in quads) == len(v) - 1
    assert out.min() == 0.0 and out.max() == 1.0 and set(side) == {0.0, 1.0}
    mid = v[side == 0.0]
    assert mid[:, 0].max() == pytest.approx(2.5)                     # starts at the bow
    assert mid[:, 0].min() < -2.5                                     # and runs back behind the boat
    # the arms open symmetrically either side of the track
    assert np.allclose(np.sort(v[:, 1]), np.sort(-v[:, 1]))
