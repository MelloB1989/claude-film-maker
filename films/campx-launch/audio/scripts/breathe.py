"""Lengthen chosen pauses of a take: insert silence at the quietest point of the gap after given words.
Usage: breathe.py <takes dir> <line> <src take> <dst take> <word index>=<target gap s> ..."""
import json, sys
from pathlib import Path
import numpy as np
from filmtools.wav import read_wav, write_wav
root, line, src, dst = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
targets = {int(k): float(v) for k, v in (a.split('=') for a in sys.argv[5:])}
m = json.loads((root/line/f'{src}.json').read_text()); x, sr = read_wav(root/line/f'{src}.wav')
w = [dict(d) for d in m['words']]
inserts = []  # (sample index, n samples)
for i, tgt in sorted(targets.items()):
    a, b = w[i]['end'], w[i+1]['start']; gap = b - a
    add = tgt - gap
    assert add > 0, (w[i]['w'], gap, tgt)
    # quietest 10 ms window inside the middle of the gap
    ia, ib = int((a + 0.25*gap)*sr), int((b - 0.25*gap)*sr); h = int(0.01*sr)
    e = [np.sum(x[j:j+h]**2) for j in range(ia, max(ia+1, ib-h), h//2)]
    at = ia + int(np.argmin(e))*(h//2) + h//2
    inserts.append((at, int(round(add*sr)), w[i]['w'], round(gap, 3), tgt))
out, prev, shift = [], 0, 0.0
f = int(0.004*sr); ramp = np.linspace(1, 0, f)
for at, n, *_ in inserts:
    seg = x[prev:at].copy(); seg[-f:] *= ramp; out += [seg, np.zeros(n, dtype=x.dtype)]
    nxt_start = at; prev = at
    x = x.copy(); x[at:at+f] *= ramp[::-1]
out.append(x[prev:]); y = np.concatenate(out)
for d in w:
    t = sum(n for at, n, *_ in inserts if at/sr <= d['start'])/sr
    d['start'] = round(d['start'] + t, 4); d['end'] = round(d['end'] + t, 4)
write_wav(root/line/f'{dst}.wav', y, sr)
meta = {**m, 'take': dst, 'duration': round(len(y)/sr, 4), 'words': w, 'derived_from': src,
        'edit': [f"gap after {wd!r} {g:.2f}s -> {t:.2f}s" for _, _, wd, g, t in inserts]}
(root/line/f'{dst}.json').write_text(json.dumps(meta, indent=1))
print(line, dst, meta['edit'], meta['duration'])
