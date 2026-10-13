"""Write data/edit.json so each line's first word lands on its target time (the film's fixed placement)."""
import json, sys
from pathlib import Path
film = Path(sys.argv[1])
TARGET = {'L01': 2.0, 'L02': 10.0, 'L03': 15.5, 'L04': 21.5, 'L05': 35.5, 'L06': 49.5, 'L07': 62.5, 'L08': 78.5, 'L09': 85.5}
sel = json.loads((film / 'audio/vo/selects.json').read_text())
ov, prev, lead = {}, None, None
for lid, t in TARGET.items():
    m = json.loads((film / f'audio/vo/paced/{lid}/{sel[lid]["take"]}.json').read_text())
    w0 = m['words'][0]
    start = t - (w0['onset'] if w0.get('onset') is not None else w0['start'])
    if prev is None:
        lead = round(start, 4)
    else:
        ov[lid] = {'gap_before': round(start - prev, 4)}
    prev = start + m['duration']
edit = {"lead_in": lead, "tail": round(90.0 - prev, 4), "gap": {"line": 0.35, "scene": 0.8, "act": 1.4},
        "scene_lead": 0.3, "overrides": ov, "optional": {}}
(film / 'data/edit.json').write_text(json.dumps(edit, indent=1) + '\n')
print('edit.json written; tail', edit['tail'])
