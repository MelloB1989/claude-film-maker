
## v2-prep (agent-08): 240 fps footage
- **yuv444p h264 decodes wrong**: a 240 fps `-pix_fmt yuv444p` file imports (fps 240, right size) but `render-frame` gives a wrong picture (mean abs diff 165/255 against the 60 fps original). Use `yuv420p`.
- 240 fps h264 imports as `frameRate 240`, duration correct; layer time remap at a 30 fps comp lands on the same picture as the 60 fps original (mean diff ~0.9/255, the re-encode).
- Random access: `-g 8 -keyint_min 8 -bf 0` (crf 12) renders a remapped 1080p frame in ~0.6-1.5 s, the same or faster than the 60 fps original (~1.8-2.7 s; shared, noisy box). All-intra (`-g 1`) was not faster and 2.6x bigger (60 MB vs 23 MB for 1.35 s of footage).
