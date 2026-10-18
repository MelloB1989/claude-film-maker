# xfx-A harness (eye_tunnel, symbiote, sling_ring, web_wipe)

A small scene that mimics the stage contract's `ctx` so each module can be built and rendered before (and without)
the core stage. Holds outside the window are the module's own `bounds()` carried along their rates; the harness runs
the same entry/exit check as the core's gate and prints per-frame camera speed (`GATE` lines).

| cut | module | window | shots |
|---|---|---|---|
| C04 | `symbiote` | 139-161 (cut 151) | S04 -> S05 |
| C08 | `eye_tunnel` | 236-264 (cut 252) | S08 -> S09 |
| C24 | `sling_ring` | 611-626 (cut 620) | S24 -> S25 |
| C27 | `web_wipe` | 680-692 (cut 686) | S27 -> S28 |

Data: `--data` is a folder with `plates/<id>/` (+ plate.json) and `tracks/<id>.json`, i.e. `$AMV3_DATA` on the VM.
eye_tunnel also reads the plates of S01-S07, S10-S16, S18, S19, S21, S23, S25, S27, S28, S30 for the tunnel cards.

    # build only (gate printout), any machine with Blender 5.2
    blender -b --factory-startup -P blender/amv3/xfx/_harness_a/harness.py -- \
        --edl films/timeless/amv3/edl.json --data $AMV3_DATA --cut C08 --no-render [--save c08.blend]

    # half-res strip on CPU (window +-3 f), plate pass; add light for the glow pass
    blender -b --factory-startup -P blender/amv3/xfx/_harness_a/harness.py -- \
        --edl films/timeless/amv3/edl.json --data $AMV3_DATA --cut C08 --res 0.5 --samples 16 \
        --out out/xa/C08 --passes plate,light

    # RunPod 4090 (operator): full res, 64 samples, OPTIX
    blender -b --factory-startup -P blender/amv3/xfx/_harness_a/harness.py -- \
        --edl films/timeless/amv3/edl.json --data $AMV3_DATA --cut C08 --res 1.0 --samples 64 \
        --device OPTIX --out out/xa/C08_full --passes plate,light

    # contact strip
    blender/amv3/xfx/_harness_a/strip.sh out/xa/C08/plate 234 33 6 c08.jpg 320

In the real stage the modules are called by `blender/amv3/stage.py` (`bounds`/`build` per the contract); nothing in
the modules imports the harness.
