# blender/amv3: the Timeless v3 3D stage

One Blender scene for the whole edit: every shot is a card, one camera (CAM) moves continuously with real Cycles motion
blur, and the stage renders three passes. `films/timeless/amv3/EDIT.md` is the creative spec and `REFS.md` holds the
measured targets.

    blender -b --factory-startup -P blender/amv3/stage.py -- --edl films/timeless/amv3/edl.json --data $AMV3_DATA \
        --frames 0-260 --res 0.25 --samples 32 --out out/stage/t1 [--passes plate,text,light] [--only C01,C02] \
        [--gate-only] [--strict] [--save x.blend] [--device OPTIX] [--identity S03@100] [--filter GAUSSIAN:0.3]

Outputs: `<out>/<pass>/f_NNNNN.png` (comp frame numbers), `<out>/gate.csv` + the gate report in the log,
`<out>/keys.json` (camera keys, teleports, every window's bounds) and `<out>/camdump.json`.
Judge smears at >= 32 spp: at 8 spp the noise looks "sharp" to motion_metrics.py.
GPU: `blender/amv3/pod_stage.sh <ip> <port> --name final --samples 64 --procs 3` (run it from the VM).

## Files
- `stage.py` holds the core: StageContext (the contract), scene/passes, hold intents, the solver, hits, camera
  fcurves, the shutter, the camera dump and render.
- `camlib.py` is pure Python: State, card space, coverage (`cover`, `min_scale`, `clamp_center`), eases, Hermite,
  punch/shake, DOF (`focus_for_blur`) and projection.
- `cards.py` covers card meshes (mirror-tiled 3x3 option), the card/holdout/emission materials, the act void
  environments and image sequences (a symlink folder per shot, so the end frames hold).
- `flow.py` has the core transitions: `open`, `zt` (push/pull, keeps the zoom sign), `whip`, `cube`, `flip`, `slam`.
- `gate.py` is the smoothness gate on the keyed camera (screen motion at 13 points, REFS targets). The official gate is
  `tools/filmtools/amv3/motion_metrics.py`, run on the rendered plate pass.
- `xfx/<type>.py` holds the signature transition modules. `text3d.py` holds the 3D titles (built after the camera is
  keyed).

## Build order
shots -> home cards -> hold intents -> every cut's `bounds()` -> touching windows resolved right to left -> every
cut's `build()` (camera keys go into the key store) -> holds -> hits -> CAM fcurves (+ lens, DOF) + shutter keys ->
`build_over()` overlays -> `text3d.build(E, ctx)` -> camera dump + gate -> render.
A missing or failing module becomes a push zt (logged, skipped by the gate).

## Module contract (xfx/<type>.py)
- `bounds(T, ctx) -> {"A": State at w0, "B": State at w1}` with rates. Start from `ctx.entry_state(T)` /
  `ctx.exit_state(T)` (the shots' hold intents). If you change A's rates, call `ctx.settle_entry(T, A)`: it re-places A
  so the hold before the window is the gentlest curve. When two windows touch (w1 == next w0), the LATER window's
  "A" becomes the earlier window's "B".
- `build(T, ctx)` keys the camera on [w0, w1). The easiest way is `ctx.key_path(fn, w0, w1, 0.25)` with
  `fn(t) -> (loc, quat[, lens])`. Register set changes first with `ctx.teleport(f_half)`; key_path then keys
  t_h - 0.02 / t_h + 0.02 and your fn must return the right side. The entry and exit poses must equal
  `ctx.pose(card, state)` at w0 / w1 with matching rates.
- `build_over(T, ctx)` adds objects only (it runs after the camera is written; read it with `ctx.cam_matrix(f)`).
- `T` is the CUTS entry with `a` / `b` replaced by the shot dicts. Never import `stage` (it runs as `__main__`).

## ctx
| call | what |
|---|---|
| `ctx.E, fps, data, res, out, log(msg)` | EDL dict, 30, $AMV3_DATA, render scale, output dir, logger |
| `ctx.shot(id)`, `ctx.act_at(f)`, `ctx.act_of(id)`, `ctx.palette(act)` | shot dict, act ids, {key, rim, leak, fog} RGB |
| `ctx.track(id, f)` | tracked focus [x, y] (plate px) or None |
| `ctx.card(id)`, `ctx.home(id)` | home card (3x3 mirror-tiled; picture fades into the act haze outside the real card), origin |
| `ctx.new_set(name)` | a fresh world origin for a private set (sets are 100 m apart; camera clip 90 m) |
| `ctx.make_card(id, name, matrix=None, alpha="none"/"matte", depth=0, hole=None, collection="plate", frames=None, backface=None, tile=1)` | a card playing the plate in comp time. matrix may carry a uniform scale; returns a mesh object (modifiers OK); hole = dict(center, radius=[(f, px)], feather) |
| `ctx.matte_card(id, matrix=None, frames=None)` | holdout card for the text/light passes, exactly in the card plane |
| `ctx.pose(card, state)`, `ctx.pose_matrix(card, state)` | camera (loc, quat) / matrix showing `state` on `card` (honours card scale) |
| `ctx.intent(id, f)`, `ctx.hold_state(id, f)` | the shot's hold intent / solved hold State |
| `ctx.key_cam(f, loc, rot, lens=None)`, `ctx.key_path(fn, t0, t1, step)` | camera keys (LINEAR) |
| `ctx.teleport(f_half)`, `ctx.teleports` | set changes |
| `ctx.key_dof(f, focus_m, fstop)` | lens defocus (rack focus). Outside keyed spans the f-stop is 128 (pinhole). `camlib.focus_for_blur(d, px)` |
| `ctx.cam_matrix(f)`, `ctx.cam_lens(f)` | the final camera (after hits), from the key store |
| `ctx.coll("plate"/"text"/"light"/"holdout")` | collections; `light` is emissive FX (also in the plate pass) |
| `ctx.env(origin, act, frames=None)` | the act's void around a set (fog sphere, bokeh, strands, haze), never black |
| `ctx.show(ob, f0, f1)` | render visibility [f0, f1) (calling again widens it) |
| `ctx.transparent_from(f=None)` | alpha 0 from this frame (default 819; honours scene["amv3_transparent_from"]) |

## Passes
- `plate` = plate + light collections (text and holdout excluded). Pixel filter Gaussian 0.3 (a hold frame reproduces
  the plate: 99.4 % of pixels within +-2 levels).
- `text` = text + holdout. `light` = light + holdout. Blackman-Harris 1.5. Film transparent everywhere; the act voids
  stop at `transparent_from`.

## Motion model (REFS numbers)
Holds drift 2.2 / 2.8 / 3.3 %/f zoom (Tobey / Andrew / Tom) plus pan <= 6.5 px/f and roll ~0.15 deg/f. Every component
is quadratic between the window bounds, and a hold with no room to pull out turns round instead (>= 6 f). The zt
attack is a pure exponential (x1.2-1.75/f) from a solved entry speed (the hold accelerates into it). B lands at the
same speed (A one frame before / B one frame after <= 2.2, A's peak gives way first) and decays x1.22/f. B's first
4-5 frames are rack-defocused (real DOF). Roll keeps its sign through the cut. Shutter 0.75 in holds, up to 1.0 at
cuts, <= 0.95 next to a teleport.
