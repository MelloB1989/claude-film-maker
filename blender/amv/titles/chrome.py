"""Chrome slam: heavy italic word slammed in at 235 % with a horizontal smear, polished chrome face on a dark extrusion.

AE spec (T_chrome): Exo 2 Black Italic (Barlow / Anton fallbacks), tracking 20, six dark copies stepping (1.6, 2.2) px
down-right for the extrusion, an outline echo one 0.78 S below at `echo` %, a white-to-steel gradient face with a
CC Light Sweep f2 -> f16 across +-700 px and a white bloom; scale 235 -> 100 over 5 f then drifting to 92 %, opacity 0 -> 100
over f0-1, horizontal blur 70 -> 30 -> 0 px over f0-4, exit = a fast exposure flash (+1.5 stops) fading out the last 4 f.

Here: the extrusion is a real deep bevelled body slanted so a straight-on camera sees it run (9.6, 13.2) px down-right
(AE's stack), the face is physically based chrome (metal, roughness 0.12) reflecting a studio HDRI, tinted by the
palette ramp so the AE gradient survives; the bloom is Blender's Bloom glare.
"""
from __future__ import annotations

from pathlib import Path

from . import common as C
from .common import Glow, Mat, TitleOpts, TitleScene, Word, lin, lin_keys

SLAM = [[0, 235], [1, 170], [2, 132], [3, 112], [4, 104], [5, 100]]


def render(spec: dict, out_dir: Path, opts: TitleOpts) -> None:
    pal = C.TPAL[spec.get("palette") or "chrome"]
    S = float(spec.get("size") or 250)
    P = tuple(spec.get("pos") or (C.W / 2, C.H / 2))
    dur = int(spec["dur"])
    text = spec["text"]
    echo = float(spec.get("echo") or 40) / 100.0
    slam = SLAM + [[dur - 1, 92]]
    role = "exo2_black_italic"
    TR = 20

    sc = TitleScene(opts)
    sc.set_environment(hdri=C.hdri_path("studio_small_08"), strength=float(opts.extra.get("env_str", 1.0)),
                       rotation=(90.0, 0.0, 180.0))
    layer = sc.empty("layer")

    body_m = Mat("body")
    bb = body_m.bsdf
    bb.inputs["Base Color"].default_value = lin(pal["ext"])
    bb.inputs["Metallic"].default_value = 0.85
    bb.inputs["Roughness"].default_value = 0.34
    body_m.link(body_m.value("alpha", 1.0), bb.inputs["Alpha"])
    depth = 22.0
    body = Word(sc, text, role, S, TR, name="body", extrude_px=depth, bevel_px=2.0, material=body_m.mat)
    face = Word(sc, text, role, S, TR, name="face", extrude_px=5.0, bevel_px=3.4, bevel_res=4)
    fm = C.metal_material("face", face.root, face.cap_px, [(0.0, "#C4C9CF"), (0.4, "#F0F1F1"), (1.0, "#FFFFFF")],
                          metallic=1.0, roughness=0.12, sweep_w_px=0.34 * face.cap_px, lean=0.35, sweep_strength=5.0)
    face.set_material(fm.mat)
    em, echo_m = C.flat_word(sc, text, role, S, TR, name="echo", color=pal["top"], strength=1.5)
    # outline-only echo: replace the flat word by tube outlines
    for ob in em.letters:
        if ob is not None:
            ob.data.fill_mode = "NONE"
            ob.data.bevel_depth = 1.5 / C.PX
            ob.data.bevel_resolution = 2
    for w in (body, face, em):
        w.attach(layer)
    sub = C.SubLine(sc, spec["sub"], layer, (0, S * 0.62), 6, dur) if spec.get("sub") else None

    comp = sc.build_compositor(glows=[Glow(0.5, 0.55, 0.9, pal["glow"]), Glow(0.7, 0.2, 0.5, "#FFFFFF")], hblur=True)
    sweep_x = lambda k: (-700 + 1400 * min(max((k - 2) / 14.0, 0.0), 1.0)) / C.PX if 2 <= k <= 16 else 99.0

    def pose(k):
        s = lin_keys(slam, k) / 100.0
        C.set_layer(layer, P, s)
        # AE keys the opacity on the null parent only, which does not reach the children: the slam is visible from k = 0
        a = lin_keys([[dur - 4, 1.0], [dur - 1, 0.0]], k)
        flash = lin_keys([[dur - 4, 0.0], [dur - 1, 1.5]], k)
        c = (C.W / 2, C.H / 2)
        body.pose(c, oblique=(9.6, 13.2), z=-0.0)
        face.pose(c, z=(depth / 2 + 2.5) / C.PX)
        body_m.set("alpha", a)
        fm.set("alpha", a)
        fm.set("sweep_x", sweep_x(k))
        fm.set("em", 0.25 * 2 ** flash)
        em.pose((C.W / 2, C.H / 2 + 0.78 * S))
        echo_m.set("alpha", echo * a)
        comp.set_hblur(lin_keys([[0, 70], [2, 30], [4, 0]], k))
        comp.set_glow(0, strength=0.4 * a * (1 + flash))
        comp.set_glow(1, strength=0.2 * a * (1 + flash))
        if sub:
            sub.update(k, a)

    C.render_sequence(sc, spec, out_dir, opts, pose)
