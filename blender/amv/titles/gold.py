"""Gold 3D with a floor reflection (2rsf0 / qLnk look): a heavy italic word in real gold on a deep extrusion.

AE spec (T_gold): Barlow Condensed Black Italic (Anton fallback), tracking 30, nine dark-bronze copies stepping (1.2, 1.8)
px, a gold gradient face with a CC Light Sweep f3 -> f20 across +-800 px and a gold bloom, a flipped copy under the word
at 35 % (blurred 6 px, fading out downwards), entry = rise 160 px from below while scale-y goes 40 -> 100 % over 8 f
(ease-out), opacity 0 -> 100 over f0-3, slow growth to 104 %, fade over the last 5 f, a sub line above (T_subline, f8).

Here: real gold (metallic, roughness 0.2, the palette ramp as reflectance colour) lit by a studio HDRI, with a bevelled
deep body; the reflection is the same geometry mirrored under the word with its own alpha ramp.
"""
from __future__ import annotations

from pathlib import Path

from . import common as C
from .common import Glow, Mat, TitleOpts, TitleScene, Word, lin, lin_keys


def render(spec: dict, out_dir: Path, opts: TitleOpts) -> None:
    pal = C.TPAL[spec.get("palette") or "gold"]
    S = float(spec.get("size") or 300)
    P = tuple(spec.get("pos") or (C.W / 2, C.H / 2 - 40))
    dur = int(spec["dur"])
    text = spec["text"]
    role = "barlow_black_italic"
    TR = 30

    sc = TitleScene(opts)
    sc.set_environment(hdri=C.hdri_path("studio_small_09"), strength=1.0, tint="#FFE9C0", rotation=(90.0, 0.0, 180.0))
    layer = sc.empty("layer")
    refl = sc.empty("reflection")
    depth = 20.0

    def build(tag, height_fade=None):
        body_m = Mat("body" + tag)
        body_m.bsdf.inputs["Base Color"].default_value = lin(pal["ext"])
        body_m.bsdf.inputs["Metallic"].default_value = 0.9
        body_m.bsdf.inputs["Roughness"].default_value = 0.38
        body_m.link(body_m.value("alpha", 1.0), body_m.bsdf.inputs["Alpha"])
        body = Word(sc, text, role, S, TR, name="body" + tag, extrude_px=depth, bevel_px=2.0, material=body_m.mat)
        face = Word(sc, text, role, S, TR, name="face" + tag, extrude_px=5.0, bevel_px=3.2, bevel_res=4)
        fm = C.metal_material("face" + tag, face.root, face.cap_px,
                              [(0.0, pal["bot"]), (0.5, pal["mid"]), (1.0, pal["top"])], metallic=1.0, roughness=0.2,
                              emission=0.15, sweep_w_px=0.34 * face.cap_px, lean=0.35, sweep_strength=5.0,
                              sweep_color="#FFF3CF", height_fade=height_fade)
        face.set_material(fm.mat)
        return body, body_m, face, fm

    body, body_m, face, fm = build("")
    rbody, rbody_m, rface, rfm = build("_r", height_fade=(1.0, -1.5))   # dies out ~60 % down the mirrored word, clear of the letterbox
    for w in (body, face):
        w.attach(layer)
    for w in (rbody, rface):
        w.attach(refl)
    sub = C.SubLine(sc, spec["sub"], layer, (0, -S * 0.62), 8, dur) if spec.get("sub") else None

    comp = sc.build_compositor(glows=[Glow(0.6, 0.55, 0.5, pal["glow"]), Glow(0.8, 0.2, 0.3, "#FFFFFF")])
    gap = face.cap_px * 1.0 + 34

    def pose(k):
        rise = lin_keys([[0, 160.0], [8, 0.0]], k)
        rise = 160.0 * (1 - C.ease_out_expo(k / 8.0)) if k < 8 else 0.0
        sy = lin_keys([[0, 40.0], [8, 100.0], [dur - 1, 104.0]], k) / 100.0
        sx = lin_keys([[0, 100.0], [8, 100.0], [dur - 1, 104.0]], k) / 100.0
        a = lin_keys([[0, 0.4], [3, 1.0], [dur - 5, 1.0], [dur - 1, 0.0]], k)     # visible from k = 0 (AE pops on f_in)
        C.set_layer(layer, (P[0], P[1] + rise), scale_xy=(sx, sy))
        c = (C.W / 2, C.H / 2)
        body.pose(c, oblique=(10.8, 16.2))
        face.pose(c, z=(depth / 2 + 2.5) / C.PX)
        for m in (body_m, fm):
            m.set("alpha", a)
        fm.set("sweep_x", (-800 + 1600 * min(max((k - 3) / 17.0, 0.0), 1.0)) / C.PX if 3 <= k <= 20 else 99.0)
        # reflection: the same word mirrored about the floor line, fading downwards
        C.set_layer(refl, (P[0], P[1] + gap + rise), scale_xy=(sx, -sy))
        rbody.pose(c, oblique=(10.8, 16.2))
        rface.pose(c, z=(depth / 2 + 2.5) / C.PX)
        ra = 0.35 * lin_keys([[0, 0.4], [8, 1.0], [dur - 5, 1.0], [dur - 1, 0.0]], k)
        for m in (rbody_m, rfm):
            m.set("alpha", ra)
        rfm.set("sweep_x", fm.values["sweep_x"].outputs[0].default_value)
        comp.set_glow(0, strength=0.5 * a)
        comp.set_glow(1, strength=0.3 * a)
        if sub:
            sub.update(k, a)

    C.render_sequence(sc, spec, out_dir, opts, pose)
