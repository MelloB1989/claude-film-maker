"""Is a garment section simulatable as Chaos cloth? Pure topology on triangles (no `unreal`).

Round 5: her overshirt (a finished render mesh: solidified into an outer and an inner layer, with collar, plackets,
buttons and a pocket as separate pieces, ~108k vertices) was simulated as one cloth and collapsed into a crumpled,
shredded mass. Legacy skeletal-mesh cloth simulates the render section itself, so that section must be a cloth:
- open: a single-layer garment has borders (hem, neck, cuffs). A CLOSED shell (zero border edges) is a solidified
  garment, outer and inner layers joined at the rims: the two layers crush into each other;
- one piece: separate islands (buttons, pockets, a loose neckband) fall or fly in the free zones;
- light: tens of thousands of particles are slow and unstable (Epic's "clothes explode" reports ran ~50k).
The fix for a thick render garment is a separate single-layer proxy SIM section driving it (mesh-to-mesh), not this.

    st = analyze(triangles, material_ids)       # per material id
    problems = judge(st[mid])                   # [] when simulatable
"""
from __future__ import annotations

MAX_VERTS = 40000
MAX_SMALL_ISLAND_FRAC = 0.01   # pieces besides the main one may hold at most this share of the vertices


def _find(parent: dict, a: int) -> int:
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def analyze(triangles: list, material_ids: list | None = None) -> dict:
    """Per material id: {"verts", "tris", "border_edges", "islands", "main_frac"}. `triangles`: [(a, b, c)] vertex
    indices (welded: one index per position); `material_ids`: per triangle (default all 0)."""
    groups: dict = {}
    for i, t in enumerate(triangles):
        mid = material_ids[i] if material_ids else 0
        groups.setdefault(mid, []).append(t)
    out = {}
    for mid, tris in groups.items():
        edges: dict = {}
        parent: dict = {}
        for a, b, c in tris:
            for v in (a, b, c):
                parent.setdefault(v, v)
            for u, w in ((a, b), (b, c), (c, a)):
                e = (u, w) if u < w else (w, u)
                edges[e] = edges.get(e, 0) + 1
                ru, rw = _find(parent, u), _find(parent, w)
                if ru != rw:
                    parent[ru] = rw
        sizes: dict = {}
        for v in parent:
            r = _find(parent, v)
            sizes[r] = sizes.get(r, 0) + 1
        nverts = len(parent)
        out[mid] = {"verts": nverts, "tris": len(tris), "border_edges": sum(1 for n in edges.values() if n == 1),
                    "islands": len(sizes), "main_frac": round(max(sizes.values()) / float(nverts), 4) if nverts else 0}
    return out


def judge(st: dict, max_verts: int = MAX_VERTS) -> list:
    """Why a section cannot be simulated as cloth, as sentences (empty when it can)."""
    out = []
    if st["verts"] and st["border_edges"] == 0:
        out.append("it is a CLOSED shell (no border edges): a solidified garment, outer and inner layers joined at the "
                   "rims; simulated as cloth the layers crush into each other (round 5: her overshirt)")
    if st["islands"] > 1 and (1.0 - st["main_frac"]) > MAX_SMALL_ISLAND_FRAC:
        out.append(f"it is {st['islands']} separate pieces ({1 - st['main_frac']:.0%} of the vertices outside the main "
                   "one: buttons, pockets, a loose band?); loose pieces fall or fly in the free zones")
    if st["verts"] > max_verts:
        out.append(f"{st['verts']} vertices is too many to simulate (limit {max_verts}): slow and unstable")
    return out
