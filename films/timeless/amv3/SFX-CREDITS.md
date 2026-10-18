# Timeless v3: SFX sources and licences

Every sound in the v3 mix is either the song, the voice lines (both unchanged from v2), or synthesized. No third-party
samples, no rips.

| source | what | licence |
|---|---|---|
| `tools/filmtools/amv3/sfx3.py` | all v3 transition layers (swells, swishes, pass-bys, riser, shockwave, thumps, impacts, slaps, metal slam, glass, tinkle, crackle, thunder, sparks, magic whoosh, goo, tunnel, thwips, rip), synthesized with numpy/scipy from seeded noise and sinusoids | this repository's own code |
| `handover/amv_handover/project/sfx/` (`sfx_kit.json`) | v2's kept cues: `hit`, `impact_boom`, `sub_drop` (in-shot hits, the drops at 480/656/819, the outro hits) | v2 kit, synthesized for the project (as the v2 brief) |

Rendering is deterministic: each layer's seed is `"<cut id>:<layer>:<frame>"` (crc32), so the same EDL gives the
same mix, sample for sample.
