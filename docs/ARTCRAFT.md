# ArtCraft integration (FilmCraft, EffectCraft, LightCraft, PhotoCraft)

[ArtCraft](https://getartcraft.com/apps) publishes free, open-source (MIT OR Apache-2.0, pure Rust) clean-room alternatives to
Adobe's tools; the releases live under github.com/storytold. Four matter here, and all ship a **headless CLI**:

| app | stands in for | version used | project file | headless |
|---|---|---|---|---|
| [FilmCraft](https://github.com/storytold/filmcraft) | Premiere Pro | **0.8.0** (alpha) | `.fcproj`, JSON, `schema_version` 13 | `filmcraft-cli`: `run` (JSONL of engine commands), `exec`, `inspect`, `import`, `export`, `render`, `probe`, `mcp` (700 commands) |
| [EffectCraft](https://github.com/storytold/effectcraft) | After Effects | **0.10.0** | `.ecproj`, JSON, schema 2 | `effectcraft-cli`: `script` (AE object model in JS), `render-frame`, `render`, `props`, `get`/`set`, `mcp` |
| [LightCraft](https://github.com/storytold/lightcraft) | Lightroom | **0.9.1** | a library + XMP sidecars | `lightcraft-cli`: `run` (engine commands, JSON lines), `render`, `controls`, `commands`, `snapshot`, `mcp` |
| [PhotoCraft](https://github.com/storytold/photocraft) | Photoshop | **0.10.0**, 0.11.1 | `.pcraft`, PSD / PSB | `photocraft-cli`: `run`, `batch` (action lists, `.atn`), `convert`, `info`, `serve`, `mcp` (900+ commands) |

FilmCraft reads and writes **FCP7 XML (xmeml), FCPXML 1.9-1.11, OpenTimelineIO, CMX 3600 EDL, AAF and OMF**; it cannot open
Premiere `.prproj` (the top blocker on its own roadmap). Its export formats include H.264/AAC mp4, ProRes, DNxHR, MXF, PNG
sequences and WAV. EffectCraft round-trips Lottie and cannot open After Effects projects. Both are young: expect schema bumps,
which is why nothing in this repo writes their project files by hand.

## Install (no sudo)

```
cd tools
python -m filmtools.artcraft install [filmcraft|effectcraft|lightcraft|photocraft|all] [--version v0.8.0]
python -m filmtools.artcraft status
```

Downloads the Linux tarball of the release, checks it against the release's `SHA256SUMS.txt`, unpacks it to
`$ARTCRAFT_HOME`, else `film-making/bin/artcraft/` (the shared path every machine sees), else `~/.local/share/artcraft`.
Binaries are found via `--cli`, `$FILMCRAFT_CLI` / `$EFFECTCRAFT_CLI` / `$LIGHTCRAFT_CLI` / `$PHOTOCRAFT_CLI`, PATH, then
the newest install there. Installed now:
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

## Stills: LightCraft + PhotoCraft (`tools/filmtools/artcraft/photo.py`)

Graded photos for a film (images for `films/<id>/assets/`, posters, thumbnails, social cuts) in a named look, cropped to
an exact size, with a check that the result is as sharp as a plain resize of the original.

```
cd tools
uv run python -m filmtools.artcraft.photo looks
uv run python -m filmtools.artcraft.photo grade IMG_1161.HEIC --look fresh,golden-hour --target instagram-portrait \
    --crop 0.21,0.14,0.83 --sky --spot 0.52,0.42,0.11,0.17 --face 0.52,0.345,0.035 --film showcase --check --sheet
uv run python -m filmtools.artcraft.photo spec photos.json [--look ...] [--only 01-hero] [--out DIR | --film ID] [--check] [--sheet]
```

Output: `<out>/<look>/<name>.jpg` and `<out>/<look>/grade.json` (crop, sizes, detail ratio per photo), `<out>/sheet.jpg`
with `--sheet`. `--film` writes to `out/<id>/stills/` and makes `--target film` the film's frame size.

```
photo (HEIC / JPEG / PNG / TIFF / raw)
  ──► LightCraft: the look's develop values + the photo's own, sky mask, radial spots on people and faces
      exported whole: uncropped, native size, 16-bit TIFF
  ──► PhotoCraft: crop to the target's aspect + Lanczos resize, glow, light leak, flatten, output sharpening ──► JPEG
  └─► check: fine-over-mid spectral detail of the result / that of the ungraded photo, cropped the same, Lanczos-resized
```

| look | |
|---|---|
| `clean` | true colour, highlights held, shadows lifted, crisp: the baseline |
| `fresh` | true-to-life and punchy: slightly cool, deep blacks, vivid sky, true greens; no glow, leak or grain |
| `golden-hour` | warm skin and light, olive greens, gold highlights over teal shadows, soft-light bloom, warm leak from the top-left, fine grain |

Targets: `instagram-portrait` 1440x1800, `instagram-square` 1440x1440, `instagram-landscape` 1440x754, `story` 1080x1920,
`youtube-thumb` 1920x1080, `poster` 2000x3000, `landscape` / `vertical` / `square` (the film formats), `film`, `WxH`, or
`W:H@L` (aspect, long edge). A crop that is smaller than the target is enlarged, with a warning.

A spec (`spec photos.json`) holds the photos and anything per photo: `crop` (`[x0, y0, x1]`: the height follows from the
aspect) or `focus` + `zoom`, `sky`, `spots` (`{"kind": "person" | "face" | "custom", "at": [x, y], "r": r | [rx, ry],
"values"?}`), `develop` (any LightCraft control, every look), `soften` (skin smoothing on faces, 0..1), and `looks`
(per-look `develop` / `sky` / `person` / `face` / `finish` overrides). Its own `looks` can define new looks on a `base`
look. Coordinates are 0..1 of the photo as shown (orientation applied). The full format is in the module docstring.

### What works (verified)

- iPhone HEIC straight from the camera roll (12 and 24 MP, no conversion), LightCraft 0.9.1 with PhotoCraft 0.10.0 and
  0.11.1: three photos in two looks to 1440x1800 in 44 s on a 12-core machine with no GPU (about 7 s per photo and
  look, the check included). Every result scored 1.18-1.25 of a plain Lanczos resize.
- The measurements the pipeline is built on:
  - LightCraft's uncropped export is the original to within 1% at every spatial frequency. Its crop path keeps ~60% of
    the finest detail and its downscale is softer than Lanczos: a crop + resize there scored 0.53-0.87 on the same
    photos, hence the crop in PhotoCraft and the 0.95 floor in the check.
  - LightCraft's `sky` mask works without a model. `subject` / `object` / `prompt` masks need Meta's SAM 3 weights,
    a gated download (`segment.model.download` after the user accepts the licence with their own Hugging Face token);
    without them `subject` is a centred blob, so people are lit with radial spots placed by hand.
  - A brightening spot on a person against the sky lights a ring of sky round them; intersecting it with luminance
    up to 0.55 (the default when `sky` is set) keeps it on the person.
  - `effects.dehaze` crushes dark hair to solid black at 15; the looks keep it at 4 or less (raise it per photo on
    landscapes).
  - Contrast + clarity + texture + LightCraft sharpening + output sharpening stack into crunchy, red faces: the looks
    sharpen lightly in LightCraft and once more in PhotoCraft, after the resize.
  - PhotoCraft's linear gradient puts its `from` colour opposite the direction of `angle`: -45 is the top-left corner.

### What does not (yet)

- AI masks: SAM 3 is not installed here; spots are coordinates you pick.
- The installer fetches the Linux tarballs; the macOS CLIs ship as `*-cli-<v>-macos-universal.zip` and are not handled.
- The looks are tuned on daylight phone photos. On raw files LightCraft's white balance is Kelvin, so a look's `wb.*`
  is left out unless the photo sets its own.
- Stills only: grading a frame sequence this way would work but costs seconds a frame; motion grading stays with the
  AMV grade and EffectCraft.

## EffectCraft

`amv/effectcraft.py` (see `docs/PIPELINE-AMV.md`) builds the AMV as an `.ecproj` through `effectcraft-cli script`; the shared
CLI helpers now live in `artcraft/effectcraft.py`. An EffectCraft comp (titles, motion graphics) can be rendered with
`effectcraft-cli render --format h264|prores|png ...` and brought into FilmCraft as media; that hand-off is manual, not
automated here.

## Tests

`tools/tests/test_artcraft.py`: plain-data tests always (ticks, track assignment, key clamping, install selection and
checksum refusal, AMV layer timeline); engine tests (build, reopen, verify, render a frame, tamper detection, interchange files)
when `filmcraft-cli` and ffmpeg are installed, else skipped.

`tools/tests/test_artcraft_photo.py`: targets, crops, look inheritance, the LightCraft / PhotoCraft steps, the detail metric
and the CLI's errors always; when `lightcraft-cli` and `photocraft-cli` are installed, a synthetic photo graded through both
engines in two looks (size, crop, detail check, grade.json, sheet), a spec run, and engine errors naming the step.
