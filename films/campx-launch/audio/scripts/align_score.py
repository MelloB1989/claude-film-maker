"""Shift a score so its tracked downbeats land on the plan's bar lines: trim `trim` s from the head, pad the tail."""
import json, sys
from pathlib import Path
import numpy as np
from filmtools.wav import read_wav, write_wav
src, dst, trim = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3])
x, sr = read_wav(src, mono=False)
n = int(round(trim * sr)); y = np.concatenate([x[n:], np.zeros((n,) + x.shape[1:], dtype=x.dtype)])
f = int(0.01 * sr); y[:f] *= np.linspace(0, 1, f)[:, None] if y.ndim > 1 else np.linspace(0, 1, f)
write_wav(dst, y, sr)
side = json.loads(src.with_suffix('.plan.json').read_text())
side['aligned'] = {'source': src.name, 'trim_s': trim, 'why': 'the tracked downbeats sat this late against the plan; trimmed so beats fall on whole and half seconds'}
dst.with_suffix('.plan.json').write_text(json.dumps(side, indent=1))
print(dst, len(y) / sr)
