"""Hand-written cue sheet for films/campx-launch: cues anchored to scene cuts and voiceover word onsets (data/vo.json),
resolved against data/sfx_palette.json into data/sfx.json (the shape app/scripts/cues.ts writes)."""
import json, sys
from pathlib import Path
film = Path(sys.argv[1])
vo = json.loads((film / 'data/vo.json').read_text()); tl = json.loads((film / 'data/timeline.json').read_text())
pal = json.loads((film / 'data/sfx_palette.json').read_text())['sounds']
cut = {s['id']: float(s['start']) for s in tl['scenes']}
def word(line, w):
    l = next(x for x in vo['lines'] if x['id'] == line)
    i = next(i for i, x in enumerate(l['words']) if x['w'].strip('.,').lower() == w.lower())
    return l['words'][i]['start'], f'word:{line}:{i}'
def at_cut(scene, off=0.0):
    return cut[scene] + off, f'cut:{scene}' + (f'{off:+.2f}s' if off else '')
C = []  # (scene, sound, (t, anchor), gain, pan, dur)
def add(scene, sound, ta, gain=0.0, pan=0.0, dur=None): C.append((scene, sound, ta, gain, pan, dur))
# open: the hall of scripts in the dark; one page rises into the light; match cut at 9
add('open', 'paper_rustle', at_cut('open', 1.0), -4, -0.3)
add('open', 'paper_flutter', at_cut('open', 5.0), 0, 0.1)
add('open', 'whoosh_soft', at_cut('stakes'), -3)
# stakes -> title: a riser that ends on the title reveal, the title impact on the cut
add('stakes', 'riser_title', at_cut('title'), -2)
add('title', 'impact_title', at_cut('title'), 2)
add('title', 'whoosh_zoom', at_cut('ingest3d'), 0)
# ingest3d: scan gate, cover dissolves, pages fan
add('ingest3d', 'scanner_hum', at_cut('ingest3d', 0.4), -2, 0, 7.2)
add('ingest3d', 'scan_sweep', word('L04', 'ZIP'), 0)
add('ingest3d', 'paper_rustle', word('L04', 'splits'), 0, 0.2)
add('ingest3d', 'dissolve_shimmer', word('L04', 'removes'), 0)
# ingestui callouts (split, anonymised, tamper-checked) ride the line
add('ingestui', 'digital_tick_2', word('L04', 'checks'), -2, -0.15)
add('ingestui', 'digital_tick_4', word('L04', 'tampering'), -2, 0.15)
# read3d: scan line reads the page; typeset lines lift off
add('read3d', 'whoosh_soft', at_cut('read3d'), -5)
add('read3d', 'scan_sweep', word('L05', 'reads'), -1)
for k, w in enumerate(['line', 'of', 'handwriting', 'is', 'transcribed', 'corrected']):
    add('read3d', f'digital_tick_{k + 1}', word('L05', w), -4, -0.2 if k % 2 else 0.2)
add('read3d', 'digital_tick_3', word('L05', 'mapped'), -3)
add('read3d', 'digital_tick_5', word('L05', 'question'), -3)
# mark3d: answer threads to key points that light up
add('mark3d', 'whoosh_soft', at_cut('mark3d'), -5)
add('mark3d', 'glass_chime', word('L06', 'key'), -3, -0.3)
t, a = word('L06', 'point'); add('mark3d', 'glass_chime', (t, a), -2, 0.0)
l6 = next(x for x in vo['lines'] if x['id'] == 'L06'); i = [k for k, x in enumerate(l6['words']) if x['w'].startswith('point')][1]
add('mark3d', 'glass_chime', (l6['words'][i]['start'], f'word:L06:{i}'), -1, 0.3)
add('markui', 'ui_click', word('L06', 'mark'), -3)
# control: whip in; accept / adjust / override; flagged for review
add('control', 'whoosh_whip', at_cut('control'), -2)
add('control', 'ui_click', word('L07', 'accept'), -1)
t, a = word('L07', 'accept'); add('control', 'ui_confirm', (t + 0.12, a + '+0.12s'), -1)
add('control', 'ui_click', word('L07', 'adjust'), -3, 0.1)
add('control', 'ui_click', word('L07', 'override'), -3, -0.1)
add('control', 'alert_pulse', word('L07', 'flagged'), 0)
# outcome and end
add('outcome', 'whoosh_soft', at_cut('outcome'), -5)
add('end', 'whoosh_soft', at_cut('end'), -6)
add('end', 'impact_logo', at_cut('end'), -2)
cues, n = [], {}
for scene, sound, (t, anchor), gain, pan, dur in sorted(C, key=lambda c: c[2][0]):
    base = pal.get(sound) or pal[sound.rsplit('_', 1)[0]]
    n[scene] = n.get(scene, 0) + 1
    c = {'sound': sound, 't': round(t, 4), 'anchor': anchor, 'gain': round(base['gain'] + gain, 2)}
    if pan: c['pan'] = pan
    if dur is not None: c['dur'] = dur
    cues.append({**c, 'id': f'{scene}.{n[scene]:04d}', 'scene': scene, 'prompt': base['prompt'], 'duration': base['duration']})
sheet = {'fps': tl['fps'], 'generated_by': 'hand-written (audio producer): scene cuts and voiceover word onsets; '
         'regenerate with app/scripts/cues.ts once the scenes carry cue modules', 'cues': cues, 'ducks': []}
(film / 'data/sfx.json').write_text(json.dumps(sheet, indent=1) + '\n')
print(len(cues), 'cues')
for c in cues: print(f"  {c['t']:7.3f} {c['scene']:9} {c['sound']:16} {c['gain']:6.1f} {c['anchor']}")
