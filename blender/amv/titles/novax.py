"""Novax: the house hero title (Nikovax's text tutorial), rebuilt as real 3D type in Blender.

AE spec (novax_lib.jsx / reference 04 §0, scaled by S/385): an italic distressed grotesk (Chinese Rocks) whose
tracking springs open -26 -> +48 over 29 f (expo-out), a stroke-only copy in the palette's stroke colour, a fill that
is white at the top and the palette colour at the bottom (52 % until f9, then 15 % at f28), a slanted white light bar
sweeping left -> right f0-19, a wide bloom that ignites f0 -> f10 -> f22, a rough black dry-brush bar under the baseline
carrying the wide-tracked tag, an optional thin sub word across the middle; the layer breathes 104 -> 96 % and exits
with a fast 112 % fade over the last 5 f (T_novax in text_lib.jsx).

Better than AE (same timing, same layout): the fill is bevelled extruded glass-metal lit by a studio HDRI so the edges
catch real highlights, the stroke is a round emissive tube, and the bloom is the compositor's true Bloom glare.
"""
from __future__ import annotations

from pathlib import Path

from . import common as C
from .common import Glow, Mat, TitleOpts, TitleScene, Word, lin, lin_keys


def render(spec: dict, out_dir: Path, opts: TitleOpts) -> None:
    pal = C.NOVAX_PALETTES[spec.get("palette") or "icy_blue"]
    S = float(spec.get("size") or 290)
    k_s = S / 385.0
    P = tuple(spec.get("pos") or (C.W / 2, C.H / 2))
    dur = int(spec["dur"])
    text = spec["text"].upper()
    ital = 0.2

    sc = TitleScene(opts)
    sc.set_environment(hdri=C.hdri_path("studio_small_08"), strength=1.1)

    # layer pivot at the title position: scale/opacity of the whole layer
    layer = sc.empty("layer")

    # ---- fill: bevelled extruded letters, white-to-colour vertical gradient, sweep, chrome sheen ---------------------
    fm = Mat("fill")
    word_fill = Word(sc, text, "chinese_rocks", S, -26, name="fill", extrude_px=9 * k_s, bevel_px=1.6 * k_s, material=fm.mat)
    cap = word_fill.cap_px
    x, y, _ = fm.object_xyz(word_fill.root)
    t = fm.math("MULTIPLY_ADD", y, 1.0 / (cap / C.PX), 0.5, clamp=True)            # 0 baseline .. 1 cap line
    col = fm.ramp(t, [(0.0, pal["fill"]), (0.5, pal["fill"]), (0.82, "#FFFFFF"), (1.0, "#FFFFFF")])
    lean = 0.4 * cap / C.PX
    sw_pos = fm.value("sweep_x", -5.0)
    sw_w = 0.26 * cap / C.PX
    d = fm.math("ABSOLUTE", fm.math("SUBTRACT", fm.math("ADD", x, fm.math("MULTIPLY", y, -lean / (cap / C.PX) * 0 - 0.4)), sw_pos))
    sweep = fm.math("SUBTRACT", 1.0, fm.math("DIVIDE", d, sw_w * 0.5), clamp=True)
    em_col = fm.mix(col, (1, 1, 1, 1), sweep)
    b = fm.bsdf
    fm.link(col, b.inputs["Base Color"])
    b.inputs["Metallic"].default_value = 0.55
    b.inputs["Roughness"].default_value = 0.22
    fm.link(em_col, b.inputs["Emission Color"])
    fm.link(fm.math("ADD", fm.value("em0", 0.5), fm.math("MULTIPLY", sweep, 4.0)), b.inputs["Emission Strength"])
    fm.link(fm.value("alpha", 0.52), b.inputs["Alpha"])

    # ---- stroke: round emissive tube along the glyph outlines -------------------------------------------------------
    sm = Mat("stroke")
    sm.nt.nodes.remove(sm.bsdf)
    st_a = sm.value("alpha", 1.0)
    st_e = sm.value("e", 2.5)
    sm.emission_only(sm.mix(lin(pal["stroke"]), (1, 1, 1, 1), 0.35), st_e, alpha=st_a)
    word_stroke = Word(sc, text, "chinese_rocks", S, -26, name="stroke", outline_px=max(3.0, 4.0 * k_s), material=sm.mat)

    # ---- tag on the rough bar ---------------------------------------------------------------------------------------
    tag = spec.get("tag")
    bar = tagw = tm = bm = None
    if tag:
        capA = 0.64 * S
        bar_dy = 0.32 * S + 0.19 * capA + 0.0
        bar_w = 1.1 * word_fill.width_px(48) * 0.62
        bar, bm = C.brush_bar(sc, bar_w, 0.17 * capA * 1.5, name="bar", seed=3.0)
        tm = Mat("tag")
        tm.nt.nodes.remove(tm.bsdf)
        ta = tm.value("alpha", 1.0)
        tm.emission_only((1, 1, 1, 1), 1.0, alpha=ta)
        tagw = Word(sc, tag.upper(), "montserrat_light", 59 * k_s, 0, name="tag", material=tm.mat)
        tag_dy = bar_dy + 0.0
    subw = sm_sub = None
    if spec.get("sub"):
        sm_sub = Mat("sub")
        sm_sub.nt.nodes.remove(sm_sub.bsdf)
        sa = sm_sub.value("alpha", 1.0)
        sm_sub.emission_only((1, 1, 1, 1), 1.0, alpha=sa)
        subw = Word(sc, spec["sub"].upper(), "montserrat_light", S * 0.33, -67, name="sub", material=sm_sub.mat)
    for w in (word_fill, word_stroke, tagw, subw):
        if w is not None:
            w.root.parent = layer
    if bar is not None:
        bar.parent = layer

    glows = [Glow(0.55, 0.62, 0.30, pal["glowB"]), Glow(0.7, 0.22, 0.45, pal["glowA"]), Glow(0.5, 0.85, 0.0, pal["glowA"])]
    comp = sc.build_compositor(glows=glows, shadow={"opacity": 0.5, "dist": 5 * k_s, "soft": 8 * k_s})

    sweep_range = (-0.62 * word_fill.width_px(48) / C.PX - sw_w, 0.62 * word_fill.width_px(48) / C.PX + sw_w)

    def pose(k):
        tr = -26 + 74 * C.expo(k / 29.0)
        for w in (word_fill, word_stroke):
            w.layout(tr)
        s = lin_keys([[0, 104], [dur - 6, 96], [dur - 1, 112]], k) / 100.0
        a_out = lin_keys([[dur - 5, 1.0], [dur - 1, 0.0]], k)
        wx, wy = C.ae_to_world(*P)
        layer.matrix_basis = _mu().Matrix.Translation((wx, wy, 0)) @ _mu().Matrix.Diagonal((s, s, 1.0, 1.0))
        word_fill.pose((C.W / 2, C.H / 2), shear=ital)
        word_stroke.pose((C.W / 2, C.H / 2), shear=ital, z=0.09 * k_s + 0.0)
        fo = lin_keys([[0, 0.52], [9, 0.52], [28, 0.15]], k)
        fm.set("alpha", fo * a_out)
        fm.set("em0", 0.5 * a_out)
        u = clamp01_(k / 19.0)
        fm.set("sweep_x", sweep_range[0] + (sweep_range[1] - sweep_range[0]) * u if k <= 19 else 99.0)
        sm.set("alpha", a_out)
        sm.set("e", 2.5)
        ignite = lin_keys([[0, 0.0], [10, 1.0], [22, 0.0]], k)
        comp.set_glow(0, strength=0.30 * a_out)
        comp.set_glow(1, strength=0.45 * a_out)
        comp.set_glow(2, strength=0.9 * ignite * a_out)
        comp.set_shadow_opacity(0.5 * a_out)
        if tag:
            trt = 0 + 32 * C.expo(k / 29.0)
            tagw.layout(trt)
            tagw.pose((C.W / 2, C.H / 2 + tag_dy), shear=0.0)
            bar.matrix_basis = _mu().Matrix.Translation((0, -bar_dy / C.PX + 0.0, -0.02))
            tm.set("alpha", a_out)
            bm.set("alpha", a_out)
        if subw is not None:
            subw.layout(-67 + 117 * C.expo(k / 29.0))
            subw.pose((C.W / 2, C.H / 2 + 0.33 * 0.32 * S - 0.0))
            sm_sub.set("alpha", a_out)

    C.render_sequence(sc, spec, out_dir, opts, pose)


def _mu():
    import mathutils
    return mathutils


def clamp01_(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u
