"""Host_Op look round 5: apply the orchestrator's picks to the character and put the new Host_Op on the level, in
the order the round-3 gotchas need (r3/HANDOFF.md "Box gotchas", ROUND3 "Handoff: note 2"):

    operator_mh.py STAGE='look' (grooms, skin, iris; the body with --body)
    -> mh.rig (only after a body change: the rig fits the head and neck to the body)
    -> mh.textures (a skin or body change discards them) -> mh.build force=true (retried while a cloud request runs)
    -> host_swap.py HOST='op' (L.spawn replace=True + seq.rebind: a fresh actor, no TRASH_)
    -> groom.set label=Host melanin/redness (colours live on the placed actor) -> STAGE='measure' (heights for agent-11)

Mutating: agent-06 runs it, from the kali tree's tools dir. It prints only names, timings and numbers:

    cd tools && uv run python ../films/host-studio/reel/r4/look_apply.py --checkout /srv/ue/r3tree \\
        --hair WI_Hair_M_SideSweptFringe --brows WI_Eyebrows_M_FlatThick --mustache WI_Mustache_S_PencilThin \\
        --beard WI_Goatee_M_Soulpatch --skin 0.55:0.50 --iris 0.92:0.12 --body slim

Then the dressing in r3/DRESS.md's order (agent-02), level.save, and agent-02's neck_probe.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from look_sheet import BODY_NOW, BODY_SLIM, BODY_SLIMMER, CHAR, THIN  # noqa: E402

BODIES = {"now": BODY_NOW, "slim": BODY_SLIM, "slimmer": BODY_SLIMMER}


def main() -> None:
    from filmtools.unreal import client
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkout", required=True, help="the box tree (the editor reads the stage scripts from it)")
    ap.add_argument("--hair", required=True)
    ap.add_argument("--brows", required=True)
    ap.add_argument("--mustache", default="none")
    ap.add_argument("--beard", default="none")
    ap.add_argument("--skin", default="", help="u:v (default: unchanged)")
    ap.add_argument("--iris", required=True, help="u:v")
    ap.add_argument("--body", default="", help="now|slim|slimmer or a JSON of measurements (default: unchanged)")
    ap.add_argument("--melanin", type=float, default=1.0)
    ap.add_argument("--redness", type=float, default=0.08)
    ap.add_argument("--beard-thin", type=float, default=0.0, help="the beard's strand width x this on the placed Host "
                    "(per instance, saved with the level; look_sheet's 'thin')")
    ap.add_argument("--lips", default="", help="r,g,b linear: lips makeup 'Natural' in this colour (before the build)")
    ap.add_argument("--rerig", action="store_true", help="re-rig on the body as it is (agent-02: the face's neck seam "
                    "fitted to the final body; round 3's record has chest 104 against bodies.py's 100)")
    ap.add_argument("--skip-build", action="store_true", help="only the character stage (a dry look)")
    a = ap.parse_args()
    rep = {}

    def ok(res, what):
        if not res.get("ok"):
            print(json.dumps({**rep, "failed": what, "error": res.get("error"),
                              "stdout": (res.get("stdout") or "")[-1500:]}, indent=1))
            raise SystemExit(1)
        return res.get("result")

    g = {"STAGE": "look", "HAIR": a.hair, "BROWS": a.brows, "MUSTACHE": a.mustache, "BEARD": a.beard,
         "IRIS_UV": tuple(float(x) for x in a.iris.split(":"))}
    if a.skin:
        g["SKIN_UV"] = tuple(float(x) for x in a.skin.split(":"))
    else:  # unchanged: the character's own values (the stage would otherwise set its default)
        cur = ok(client.op("mh.settings_fields", path=CHAR, which="skin"), "skin read")
        g["SKIN_UV"] = (cur["skin"]["u"], cur["skin"]["v"])
    body = BODIES.get(a.body) or (json.loads(a.body) if a.body else None)
    if body:
        g["BODY_SET"] = body
    if a.lips:
        rep["lips"] = ok(client.op("mh.makeup", path=CHAR, settings={"lips": {"type": "Natural", "color": [
            float(x) for x in a.lips.split(",")]}}), "mh.makeup")
    stage = os.path.join(a.checkout, "films/host-studio/unreal/operator_mh.py")
    code = "".join(f"{k} = {v!r}\n" for k, v in g.items()) + f"exec(open({stage!r}).read())"
    t0 = time.time()
    rep["look"] = ok(client.exec_code(code, timeout=1800), "STAGE look")
    rep["look_s"] = round(time.time() - t0)
    if a.skip_build:
        print(json.dumps(rep, indent=1))
        return
    steps = ([("mh.rig", {"character": CHAR})] if body or a.rerig else []) + [
        ("mh.textures", {"character": CHAR}), ("mh.build", {"character": CHAR, "name": "Host_Op", "force": True})]
    for step, args in steps:
        t0 = time.time()
        for _ in range(18):  # the build is refused for a few ticks right after the textures (round 3)
            res = client.op(step, timeout=3600, **args)
            why = (res.get("error", "") or "") + (res.get("stdout", "") or "")
            if res.get("ok") or "cloud request is still running" not in why:
                break
            time.sleep(10)
        rep[step] = {"result": ok(res, step), "s": round(time.time() - t0)}
        print(json.dumps({step: rep[step]}), file=sys.stderr)
    swap = os.path.join(a.checkout, "films/host-studio/unreal/host_swap.py")
    t0 = time.time()
    res = client.exec_code(f"HOST = 'op'\nCHECKOUT = {a.checkout!r}\nexec(open({swap!r}).read())", timeout=1800)
    rep["host_swap"] = {"ok": res.get("ok"), "s": round(time.time() - t0),
                        "stdout": (res.get("stdout") or "")[-1500:]}
    ok(res, "host_swap")
    rep["groom"] = ok(client.op("groom.set", label="Host", melanin=a.melanin, redness=a.redness), "groom.set")["changed"]
    if a.beard_thin:  # THIN reads the actor from mh.build's _PREVIEWS: point it at the placed Host
        put = ("import importlib, unreal\n_b = importlib.import_module('fmbridge.ops.mh.build')\n"
               "_b._PREVIEWS['Host'] = [x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem)"
               ".get_all_level_actors() if x.get_actor_label() == 'Host'][0]\n")
        rep["beard_thin"] = ok(client.exec_code(put + f"LABEL = 'Host'\nF = {{'Beard': {a.beard_thin}}}\n" + THIN
                                                + "\n_b._PREVIEWS.pop('Host', None)"), "beard thin")
    trash = "import unreal\nh = [x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if x.get_actor_label() == 'Host'][0]\nresult = [c.get_name() for c in h.get_components_by_class(unreal.ActorComponent) if c.get_name().startswith('TRASH_')]"
    rep["trash"] = ok(client.exec_code(trash), "TRASH_ check")
    rep["measure"] = ok(client.exec_code(f"STAGE = 'measure'\nexec(open({stage!r}).read())"), "measure")
    print(json.dumps(rep, indent=1))
    print("next: the dressing in r3/DRESS.md's order, level.save, agent-02's neck_probe.py; heights to agent-11 "
          "if eye/top moved (round 3: eye 168.7, top 181.7)")


if __name__ == "__main__":
    main()
