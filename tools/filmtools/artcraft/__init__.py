"""Integration with ArtCraft's free open-source apps (getartcraft.com): FilmCraft (video editor, Premiere-like),
EffectCraft (motion graphics, After Effects-like), LightCraft (raw developer, Lightroom-like) and PhotoCraft (image
editor, Photoshop-like). See docs/ARTCRAFT.md.

    install.py      find / install the release binaries (no sudo): `python -m filmtools.artcraft install|status`
    effectcraft.py  shared EffectCraft CLI helpers (find, run a script, render preview frames)
    filmcraft.py    a film's edit as a FilmCraft project (.fcproj + OTIO / EDL / FCPXML), headless
    lightcraft.py   LightCraft CLI helpers: develop steps, sky mask, radial spots, full-size export
    photocraft.py   PhotoCraft CLI helpers: crop + Lanczos resize, glow, light leak, sharpening, convert
    photo.py        graded stills (posters, thumbnails, social cuts, film assets) in named looks, with a detail check
"""
