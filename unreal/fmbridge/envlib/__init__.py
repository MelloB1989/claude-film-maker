"""envlib: the environment & lighting maths and planning behind the `env.*` and `light.*` ops, in plain Python.

Nothing here imports `unreal`, so all of it runs (and is unit-tested) outside the editor, on the operator's side as well
as inside the bridge:

- `sun`: where the sun is for a place, a date and a time (NOAA), named times of day, and the sun light it gives.
- `photometry`: EV100, luminance, illuminance, light units, Unreal's exposure, colour temperature.
- `rig`: lighting rigs placed relative to a subject (key/fill/rim/...), with intensities from target lux and ratios.
- `grade`: colour/post presets (white balance, LUT, bloom, grain, vignette, film curve) as PostProcessSettings fields.
- `quality`: Lumen / virtual shadow maps / hardware ray tracing presets as console variables and post settings.
- `stats`: luminance statistics of linear pixels and checks against targets (exposure, clipping, colour cast).
- `spec`: the ENVIRONMENT SPEC: schema, validation with actionable errors, moods, presets, and the plan (desired state)
  that `env.apply` converges the level to.
"""
