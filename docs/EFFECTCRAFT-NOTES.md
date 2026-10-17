
## special (rift, drop portal, triptych/shatter) — agent-04, EffectCraft 0.10.0

Bugs and workarounds found while building `tools/filmtools/amv2/ec/special.jsx`:

- **`File.exists` is always `false`**, even for existing files. Probe a file by `importFile` inside try/catch instead (a missing file
  throws `I/O error ... No such file or directory`). `importOk()` in special.jsx does this.
- **Posterize Time freezes more than the picture**: with it on a layer, the layer's *masks* are evaluated at the frozen time too
  (a mask animated over the freeze never moved). Freeze with a **time-remap hold** on a second layer of the shot precomp instead.
- **Time remap**: `setValuesAtTimes` on a fresh remap leaves the default keys (2 values gave 3 keys), so remove keys by value
  afterwards. A layer's in/out cannot pass the source duration until its time remap is enabled and you set `outPoint` **before**
  `inPoint` (setting `inPoint` first clamps it to the old out point).
- **Shape layers**: path vertices are relative to the layer position, so `position = [0,0]` makes them comp pixels. The **first**
  added vector group is drawn on top (the reverse of After Effects). `moveBefore(x)` puts the layer **above** x, `moveAfter` below.
- **Text layers**: `position` is the baseline centre. For Anton the caps centre sits `0.44 * fontSize` above the position.
- **Twirl** `Twirl Radius` clamps to 100. **Polar Coordinates** `Type of Conversion = 2` is the one that turns noise into a vortex.
  Fractal Noise `Scale`/`Offset Turbulence` live under its `Transform` group. Tritone + Turbulent Displace give a good liquid look.
- **Shatter** (`ec.sim.shatter`) rendered flat grey/black with its default View/Render settings; not used. Own shards instead:
  a polygon mask per shard of a still. **Cutting 35 shards out of the live triptych comp costs ~80 s per frame** (each shard
  re-renders the whole nested comp: precomps are not cached between layers), so special_spec.py pre-renders one still of the
  triptych at the shatter frame and the shards cut that (about 5 s per frame).
- Useful and working: `ec.vr.chromaticaberrations` (per-channel Aberration (Red/Green/Blue) = the red/blue split), `ADBE Ripple`
  (shockwave), `ec.sim.ccballaction` (halftone-like dots), `ec.blur.ccradialfast` (zoom streaks), Bevel Alpha (shard rim).
- `effectcraft-cli` is not on PATH in the agent container (use the full path); it is on the VM's PATH.
