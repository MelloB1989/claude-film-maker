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
- `flow.py` has the core transitions: `open`, `zt` (push/pull, keeps the zoom sign; now only the fallback for missing
  modules), `whip`, `cube`, `flip`, `slam`.
- `nest.py` is the v3.1 nested zoom (type `nest`, every zoom-in / zoom-out cut): one static world layout per window,
  the rig flies through a feathered region of the front clip into the next clip (see "Nest" below).
- `regions.py` prepares the region masks (eye / lens from `$AMV3_DATA/regions/<shot>/<kind>/`, bg = 1 - matte; an
  ellipse around the track stands in when a mask is missing): blurred 16-bit masks the card shader thresholds, so the
  feather is animatable.
- `gate.py` is the smoothness gate on the keyed camera (screen motion at 13 points, REFS targets). The official gate is
  `tools/filmtools/amv3/motion_metrics.py`, run on the rendered plate pass.
- `xfx/<type>.py` holds the signature transition modules. `text3d.py` holds the 3D titles (built after the camera is
  keyed).

## Camera rig
`RIG_DOLLY` (world location) -> `RIG_ORBIT` (quaternion pan / tilt) -> `RIG_ROLL` (rotation z = roll about the view
axis) -> `RIG_SHAKE` (camera-local offsets: shake hits + module offsets) -> `CAM` (lens, DOF; identity local transform).
Modules still key the camera's world pose (`key_path` / `key_cam`); the core decomposes each pose into the nulls
(swing-twist: orbit = the pose without its twist about the view axis, roll = that twist, unwrapped) and writes
**Bezier keys whose handles come from the path's own derivative** (key_path samples t + h on the right side of any
teleport). Holds key every channel every 3 f, staggered (dolly +0, orbit +1, roll +2: overlapping keys, the motion never
stops). Windows key every 0.25 f. `punch@F` rides on the lens, `shake@F` on RIG_SHAKE (a few smooth bumps at
0.10-0.18 cycles/f, the first the largest). After the camera is written, `ctx.cam_matrix(f)` evaluates the rig fcurves
(hits and offsets included).

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
| `ctx.key_cam(f, loc, rot, lens=None, ahead=None)`, `ctx.key_path(fn, t0, t1, step)` | camera world pose keys -> rig Bezier keys (ahead = (loc, rot, lens, h) sets the handles; key_path does it for you) |
| `ctx.key_rig(f, channel, value, slope=None)` | explicit Bezier key on a rig null: "dolly" (Vector), "orbit" (Quaternion), "roll" (deg), "lens" (mm); inside the window being built it replaces the core's keys of that channel |
| `ctx.key_offset(f, loc=(x, y, z), rot=(pitch, yaw, roll))` | additive camera-local offset on RIG_SHAKE (m / deg), smooth between keys; key 0 at both ends |
| `ctx.rig`, `ctx.rig_pose(f)` | the rig objects {dolly, orbit, roll, shake, cam}; CAM's world (loc, quat) |
| `ctx.nest_bounds(T, **p)`, `ctx.nest(T, **p)`, `ctx.nest_layout(cut_id)` | a nested zoom for a module's window (see Nest); nest_layout works after the builds (text3d, overlays) |
| `ctx.plate_image(sid)` | the shot's plate sequence in comp time (set the node's image_user up with `cards.setup_user`) |
| `ctx.denoise(f0, f1)` | render [f0, f1) with OIDN (glass / volume frames are found automatically) |
| `ctx.teleport(f_half)`, `ctx.teleports` | set changes |
| `ctx.key_dof(f, focus_m, fstop)` | lens defocus (rack focus). Outside keyed spans the f-stop is 128 (pinhole). `camlib.focus_for_blur(d, px)` |
| `ctx.cam_matrix(f)`, `ctx.cam_lens(f)` | the final camera (after hits), from the key store |
| `ctx.coll("plate"/"text"/"light"/"holdout")` | collections; `light` is emissive FX (also in the plate pass) |
| `ctx.env(origin, act, frames=None)` | the act's void around a set (fog sphere, bokeh, strands, haze), never black |
| `ctx.show(ob, f0, f1)` | render visibility [f0, f1) (calling again widens it) |
| `ctx.transparent_from(f=None)` | alpha 0 from this frame (default 819; honours scene["amv3_transparent_from"]) |

## Nest (type `nest`; p = {mode, region, shot, settle, roll, land, at, size, reveal, fill, fstop, grow})
- `push`: the front card is A's home card, B's card is a copy (uniform scale k) D m behind A's region, rolled so the
  camera's roll is continuous. `pull`: the mirror; the front card is a copy of B in front of A's home card and the camera
  pulls back through B's region. Clips never move; only the rig does. After w1 the camera teleports from the copy to
  B's home card with the same relative pose (`ctx.seamless`, invisible; the gate measures through it).
- The camera crosses the front plane at f - 0.5 through the region's point (`at`, else the opening's centre / the
  deepest background point). ln s_K (the back card's apparent scale) is one curve: an exponential attack from the hold
  into the crossing, the natural decay (x1.22 / f) after it, with the same speed on both sides (`land` is solved; a push
  may land deeper than `settle`, up to x1.35, to keep the decay; a pull's A shrinks to 0.55-1.1, faded mirror tiles
  allowed). D comes from the reveal: B framed `fill` x the region (an opening: B grows >= `grow` (3) x before the
  crossing; a background: 1.3 x), capped so the crossing speed fits the landing.
- Reveal: the front card's opacity inside the region ramps 1 -> 0 over `reveal` = [lead, dur] (default [10, 8]) frames
  before the crossing (push) / 0 -> 1 after it (pull); feather 3-12 screen px with the region's size on screen.
- DOF: push focuses on the back plane from the reveal (A defocuses as it nears); pull racks from A to B after the
  crossing. Masks: `$AMV3_DATA/regions/<shot>/<eye|lens>/f_NNNNN.png` (255 inside); bg = 1 - matte.
- Nest object: `front`, `back` (cards), `D`, `k`, `t_x`, `t_r`, `pose(t)`, `z(t)` (camera distance to the front plane),
  `point(card, px, py, dz)`, `state_on("front" | "back", t)`.

## Render cost
Per frame, only the camera's set is visible (`cull_by_set`): Cycles loads the 2-4 sequences that frame can show.
Emission cards need no bounces (diffuse 1, volume 0, clamp direct 3 / indirect 1.5, caustics off). Frames with glass /
volume objects (or `ctx.denoise`) render with OIDN (albedo + normal, accurate prefilter); card holds stay undenoised.

## Passes
- `plate` = plate + light collections (text and holdout excluded). Pixel filter Gaussian 0.3 (a hold frame reproduces
  the plate: 99.4 % of pixels within +-2 levels).
- `text` = text + holdout. `light` = light + holdout. Blackman-Harris 1.5. Film transparent everywhere; the act voids
  stop at `transparent_from`.
- **Comp the light pass as RGB-add, ignoring alpha.** Additive emitters (Emission + Transparent: bolts, sparks, rings,
  the cube glints, whip streaks) come out with alpha 0 but full RGB. Alpha-over makes them vanish. The same applies
  to additive bits in the plate pass after `transparent_from` (comp the plate over the outro with alpha, then add its RGB
  where alpha == 0, or keep those emitters opaque).

## Motion model (REFS numbers)
Holds drift 2.2 / 2.8 / 3.3 %/f zoom (Tobey / Andrew / Tom) plus pan <= 6.5 px/f and roll ~0.15 deg/f. Every component
is quadratic between the window bounds, and a hold with no room to pull out turns round instead (>= 6 f). The zt
attack is a pure exponential (x1.2-1.75/f) from a solved entry speed (the hold accelerates into it). B lands at the
same speed (A one frame before / B one frame after <= 2.2, A's peak gives way first) and decays x1.22/f. B's first
4-5 frames are rack-defocused (real DOF). Roll keeps its sign through the cut. Shutter 0.75 in holds, up to 1.0 at
cuts, <= 0.95 next to a teleport.
