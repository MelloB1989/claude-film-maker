"""The anime pipeline: generated key art made into shots the engine animates (docs/PIPELINE-ANIME.md).

- `assets`: generated pictures and clips fetched into the film's folder, each with its provenance (data/gen.json);
- `cutout`: a character cut out of a keyframe (RGBA), and the plate behind it filled;
- `depth`: a depth map of a plate, for the engine's 2.5D parallax;
- `clips`: generated clips conformed to the film (frame rate, size, trims, a still held as a clip);
- `dialogue`: a cast of voices speaking a script, placed on the timeline, with the subtitle cues;
- `synth`, `score`, `foley`: a score and sound effects synthesised from scratch, cued to the picture;
- `mix`: dialogue, score and effects mixed and mastered to the film's mix.
"""
