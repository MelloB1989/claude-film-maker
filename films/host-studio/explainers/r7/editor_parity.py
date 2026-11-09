"""agent-06 (r7, the orchestrator's editor_offline_parity_cm rule): editor-vs-reference parity (cm), offline frame, over the dump's frames: mean/max |hand_r|, |hand_l| and the max over
every wrist + finger bone (editor_offline_parity_cm). python3 x/diag_res.py DUMP REF [REF2...]"""
import json, math, sys
def load(p):
    d = json.load(open(p)); return {f["f"]: f["p"] for f in d["frames"]}
FING = ("thumb", "index", "middle", "ring", "pinky")
D = load(sys.argv[1])
for r in sys.argv[2:]:
    try: R = load(r)
    except Exception as e: print(r, "unreadable", e); continue
    com = [f for f in D if f in R]; n = sys.argv[1].split('/')[-1] + " vs " + r.split('/')[-1]
    for b in ("hand_r", "hand_l"):
        ds = [math.dist(D[f][b], R[f][b]) for f in com]
        print(f"{n}: {b} mean {sum(ds)/len(ds):.2f} cm, max {max(ds):.2f} (n {len(ds)})")
    bs = [b for b in D[com[0]] if b in R[com[0]] and (b.startswith("hand_") or b.startswith(FING))]
    w = max((math.dist(D[f][b], R[f][b]), f, b) for f in com for b in bs)
    print(f"{n}: editor_offline_parity_cm {w[0]:.2f} (worst {w[2]} f{w[1]}, {len(bs)} wrist+finger bones) {'PASS' if w[0] <= 1.0 else 'FAIL'} (<= 1.0)")
