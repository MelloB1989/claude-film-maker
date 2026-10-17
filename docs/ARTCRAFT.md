# ArtCraft integration (FilmCraft + EffectCraft)

[ArtCraft](https://getartcraft.com/apps) publishes free, open-source (MIT OR Apache-2.0, pure Rust) clean-room alternatives to
Adobe's tools; the releases live under github.com/storytold. Two matter here, and both ship a **headless CLI**:

| app | stands in for | version used | project file | headless |
|---|---|---|---|---|
| [FilmCraft](https://github.com/storytold/filmcraft) | Premiere Pro | **0.8.0** (alpha) | `.fcproj`, JSON, `schema_version` 13 | `filmcraft-cli`: `run` (JSONL of engine commands), `exec`, `inspect`, `import`, `export`, `render`, `probe`, `mcp` (700 commands) |
| [EffectCraft](https://github.com/storytold/effectcraft) | After Effects | **0.10.0** | `.ecproj`, JSON, schema 2 | `effectcraft-cli`: `script` (AE object model in JS), `render-frame`, `render`, `props`, `get`/`set`, `mcp` |

FilmCraft reads and writes **FCP7 XML (xmeml), FCPXML 1.9-1.11, OpenTimelineIO, CMX 3600 EDL, AAF and OMF**; it cannot open
Premiere `.prproj` (the top blocker on its own roadmap). Its export formats include H.264/AAC mp4, ProRes, DNxHR, MXF, PNG
sequences and WAV. EffectCraft round-trips Lottie and cannot open After Effects projects. Both are young: expect schema bumps,
which is why nothing in this repo writes their project files by hand.

## Install (no sudo)

```
cd tools
python -m filmtools.artcraft install [filmcraft|effectcraft|all] [--version v0.8.0]
python -m filmtools.artcraft status
```

Downloads the Linux tarball of the release, checks it against the release's `SHA256SUMS.txt`, unpacks it to
`$ARTCRAFT_HOME`, else `film-making/bin/artcraft/` (the shared path every machine sees), else `~/.local/share/artcraft`.
Binaries are found via `--cli`, `$FILMCRAFT_CLI` / `$EFFECTCRAFT_CLI`, PATH, then the newest install there. Installed now:
`film-making/bin/artcraft/{filmcraft-0.8.0,effectcraft-0.10.0}-linux-x86_64/bin/*-cli`.

## FilmCraft exporter (`tools/filmtools/artcraft/filmcraft.py`)

```
PYTHONPATH=tools python -m filmtools.artcraft.filmcraft --film films/<id> --variant final|layers|scenes \
    [--video out/<id>/...mp4] [--mix PATH] [--layers DIR] [--out out/<id>/artcraft] \
    [--interchange otio,edl,fcpxml,xml,aaf] [--preview 1.5,10] [--no-verify] [--emit-only]
```

Output: `out/<id>/artcraft/<id>-<variant>.fcproj` (plus the interchange files, `script.jsonl` of the engine commands).

How it works: the edit is plain data (`Timeline`: media, clips on tracks, Motion keyframes) -> FilmCraft engine commands
(`file.import`, `file.newSequence`, `timeline.place`, `effects.setParam`, `file.saveAs`, `file.exportInterchange`) -> run by
`filmcraft-cli run`, which builds and saves the project, so it is valid by construction. The first pass places everything to
learn the clip ids the engine hands out; the second adds the keyframes and saves (ids must match or the build fails).

| variant | for | content |
|---|---|---|
| `final` | AMV and three.js films | the rendered mp4 on V1 (its own sound dropped), the mix on A1. The AMV mp4 defaults to `out/<id>/amv/<id>.mp4`, a three.js film's to `out/<id>/<id>.mp4` |
| `layers` | AMV | the bake stage's RGBA layer sequences, one clip per shot at the plan's cuts, with the plan's Motion keys (position, scale, rotation, opacity), the mix on A1. A layer that runs on past its cut sits one track above the next shot, as the layer stack does |
| `scenes` | three.js films | `data/timeline.json` scene windows as one clip per scene (source offset into the full mp4, so each can be trimmed and moved), the mix on A1 |

AMV frame rate and size come from the plan (30 fps, 1920x1080); three.js films from `film.json` / `timeline.json`. Image
sequences use FilmCraft's *indeterminate media timebase*; the exporter sets it to the film's fps before importing (otherwise
60 frames would last 2.002 s).

### What works (verified)

- Built and **reopened headless** with FilmCraft 0.8.0: `verify()` reads the saved `.fcproj` back through `filmcraft-cli
  inspect` and compares every clip's track, start frame, length, source offset and keyframe count with the edit (pytest does
  this for all three variants; the CLI does it unless `--no-verify`).
- The real `films/timeless` plan (33 shots, stand-in 192x108 layer PNGs, 30 s sine mix): 34 clips on 2 video tracks, 351 KB,
  ~2.7 s end to end; `filmcraft-cli export` rendered it to a 30.0 s h264+aac mp4 in 20 s at quarter size; `render --seconds`
  produced frames; OTIO, EDL, FCPXML and FCP7 XML were written by the engine from the same project.
- `--preview s1,s2` renders those program frames with FilmCraft's own renderer.
- `python -m filmtools.amv.effectcraft` is unchanged for users; its CLI discovery moved into `artcraft/effectcraft.py`.

### What does not (yet)

- **Not opened in the FilmCraft GUI**: this container has no display; the check is the engine's own loader/renderer, the same
  code the GUI uses, but a visual check in the app is still manual: *File > Open Project > `<id>-<variant>.fcproj`*, scrub the
  timeline, compare with the final mp4.
- Real layer frames were not available here (the bake stage output is not on this machine), so `layers` was exercised with
  synthetic frames of the right names and counts. Motion keys use FilmCraft's Linear interpolation between the plan's
  compressed key spans; whether position / scale match After Effects frame for frame on real bakes is unchecked.
- `layers` carries only the shots. The Blender compositor's flash, strobes, grade, bloom, letterbox, accents, titles and
  outro are not FilmCraft clips; use `final` for the finished look, `layers` to re-cut.
- `scenes` cuts the finished render; it does not export the three.js scene graph (there is no equivalent in an editor).
- Media is referenced by absolute path, like `.fcproj` itself; move the film and use FilmCraft's Link Media / Project Manager.
- FilmCraft scales nothing by default: a render that is not the sequence size sits at native size.
- Premiere `.prproj`, After Effects `.aep` and Resolve projects are out of scope (neither app opens them); the OTIO / EDL /
  FCPXML / XML files are the way into other editors.

## EffectCraft

`amv/effectcraft.py` (see `docs/PIPELINE-AMV.md`) builds the AMV as an `.ecproj` through `effectcraft-cli script`; the shared
CLI helpers now live in `artcraft/effectcraft.py`. An EffectCraft comp (titles, motion graphics) can be rendered with
`effectcraft-cli render --format h264|prores|png ...` and brought into FilmCraft as media; that hand-off is manual, not
automated here.

## Tests

`tools/tests/test_artcraft.py`: plain-data tests always (ticks, track assignment, key clamping, install selection and
checksum refusal, AMV layer timeline); engine tests (build, reopen, verify, render a frame, tamper detection, interchange files)
when `filmcraft-cli` and ffmpeg are installed, else skipped.
