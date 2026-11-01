"""Does her garments' leader pose survive into a play world (Movie Render Queue renders in one, PIE)? Begins Simulate in
the editor, reads each of her skeletal mesh components' leader there, and the Top's pelvis against the Body's (a posed
garment sits on the body's bones), then ends play. Nothing saved. Run from tools/ on the operator's Mac through run.sh:
    uv run python ../films/host-studio/props/her_outfit_ue/pie_check.py
"""
import json
import time

from filmtools.unreal import client

START = '''
import unreal
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_play_simulate()
result = True
'''
READ = '''
import unreal
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
out = {"world": w.get_name() if w else None}
if w:
    for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Actor):
        comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}
        if "Body" not in comps or "Top" not in comps:
            continue
        for n, c in comps.items():
            lead = c.get_editor_property("leader_pose_component")
            out[n] = lead.get_name() if lead else None
        def v(p):
            return [round(p.x, 1), round(p.y, 1), round(p.z, 1)]
        out["pelvis"] = {n: v(comps[n].get_socket_location("pelvis")) for n in ("Body", "Top", "Trousers") if n in comps}
        out["hand_l"] = {n: v(comps[n].get_socket_location("hand_l")) for n in ("Body", "Top") if n in comps}
result = out
'''
STOP = '''
import unreal
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
result = True
'''


def main():
    out = {}
    try:
        out["start"] = client.exec_code(START).get("ok")
        for _ in range(10):
            time.sleep(2)
            r = client.exec_code(READ)
            out["read"] = r.get("result") or r.get("error")
            if isinstance(out["read"], dict) and out["read"].get("world"):
                break
    finally:
        out["stop"] = client.exec_code(STOP).get("ok")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
