"""What the reel's light timeline (light.py) needs beyond studio.py's day build. It only *adds*, at values that change
nothing in the day level (the stills keep working), and re-running it is harmless:

- the night's four recessed downlights (DownCredenza, DownSlats, DownOlive, DownShelves), as studio.py's night places
  them, at intensity 0: light.py pops them on in bar 14;
- the night garden: a second outside card (OutsideNight, T_OutsideNight) 1 cm in front of the day one, additive
  (look.material kind Glow) at intensity 0, so light.py can crossfade day -> night by two intensities;
- the halo's wipe: SignHalo's material becomes MI_K_HaloWipe (kind GlowWipe: the same texture, colour and intensity
  as studio.py's MI_K_Halo, with Reveal 1 = fully lit, i.e. the day level looks the same); light.py keys Reveal.

The cameras (Reel_S01 ... S18) are R3's (reel/build.py). studio.py rebuilds the level from scratch, so run this again
after every studio.py:

    cd tools && uv run python ../films/host-studio/reel/rig.py

It needs the bridge with look.material's GlowWipe kind installed (`film-ue install` from a checkout with it).
"""
from __future__ import annotations

import sys
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from light import DOWN, HALO_CARD  # noqa: E402
from shots import WALL  # noqa: E402

M = "/Game/Studio/Materials"
T = "/Game/Studio/Textures"
OUTSIDE = (WALL - 140, 205, 150)  # studio.py's Outside card: 520 x 900 cm
NIGHT_OUTSIDE = 3.0               # studio.py night's Outside intensity (light.py fades OutsideNight up to it)


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def exists(path: str) -> bool:
    return ok(client.exec_code(f"import unreal\nresult = unreal.EditorAssetLibrary.does_asset_exist({path!r})"))


def where(label: str):
    """An actor's location, or None when the level has no such actor."""
    code = ("from fmbridge.ops import level as L\ntry:\n    p = L.actor({0!r}).get_actor_location()\n"
            "    result = [p.x, p.y, p.z]\nexcept ValueError:\n    result = None").format(label)
    return ok(client.exec_code(code))


def main() -> None:
    done = []
    # the downlights, as studio.py's night places them, dark
    for label, loc, at, _, _ in DOWN:
        ok(client.op("look.light", label=label, kind="spot", loc=list(loc), look_at=list(at), intensity=0.0,
                     temperature=2700, cone=32, radius=600, volumetric=0.4, shadows=label != "DownSlats"))
        done.append(label)
    # the night garden in front of the day one, additive, dark
    tex = f"{T}/T_OutsideNight"
    if not exists(tex):
        raise SystemExit(f"{tex} is missing (studio.py's night texture; textures.py imports it)")
    mat = ok(client.op("look.material", name="MI_K_OutsideNight", color=[1.0, 1.0, 1.0], kind="Glow", texture=tex,
                       intensity=0.0, folder=M))
    ok(client.op("look.card", label="OutsideNight", loc=[OUTSIDE[0] + 1.0, OUTSIDE[1], OUTSIDE[2]], width=520,
                 height=900, material=mat))
    done.append("OutsideNight")
    # the halo's wipe material, identical to MI_K_Halo when fully revealed
    if where("SignHalo") is None:
        raise SystemExit("no SignHalo in the level: run studio.py first (it needs karma_halo.json)")
    halo = f"{T}/T_KarmaHalo"  # as studio.py: the plain colour while the texture is missing
    wipe = ok(client.op("look.material", name="MI_K_HaloWipe", color=[1.0, 0.62, 0.32], kind="GlowWipe",
                        texture=halo if exists(halo) else "", intensity=HALO_CARD, scalars={"Reveal": 1.0, "Softness": 0.03},
                        folder=M))
    ok(client.op("look.apply", label="SignHalo", material=wipe))
    done.append("SignHalo <- MI_K_HaloWipe")
    ok(client.op("level.save"))
    print("\n".join(done))


if __name__ == "__main__":
    main()
