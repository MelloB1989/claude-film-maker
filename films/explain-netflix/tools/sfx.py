"""The v3 SFX hit list for agent-11's mix (docs/STYLE_V3.md §8): data/sfx_v3.json from data/edl.json.

    python3 films/explain-netflix/tools/sfx.py

Each cue is placed where its scene (films/explain-netflix/v3/*.ts) puts the event: on the VO word that drives it (the
word's frame on the shot's clock, words[].f, plus the scene's lag), so a VO retime moves the hits with the graphics.
f is the frame on the shot's clock and stays below the shot's EDL frame count (the 12 tail frames are cut).
whoosh_in and riser land their PEAK on f; data_stream runs f..f_end; every other cue starts on f.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
edl = json.loads((HERE / 'data/edl.json').read_text())
GAIN = {'whoosh_in': -14, 'swoosh_fast': -14, 'hit_sub': -10, 'pop': -18, 'tick': -24, 'data_stream': -24, 'riser': -14, 'glitch': -12, 'chime': -16}


def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum() or ch == "'")


cues = []
for shot in edl['shots']:
    gfx = shot.get('gfx')
    if not gfx:
        continue
    n = shot['frames']
    words = shot.get('words', [])

    def w(word, fb, nth=0, lag=2):
        hits = [x for x in words if norm(x['w']) == norm(word)]
        return (hits[nth]['f'] if len(hits) > nth else fb) + lag

    def add(f, sfx, note, f_end=None, gain=None):
        f = int(round(f))
        if f < 0 or f >= n:
            return
        c = {'shot': gfx, 'f': f, 'sfx': sfx, 'gain': GAIN[sfx] if gain is None else gain, 'note': note}
        if f_end is not None:
            c['f_end'] = int(min(n - 1, round(f_end)))
        cues.append(c)

    add(6, 'whoosh_in', 'camera arrive (the cut lands in motion)')
    if gfx == 'title':
        snap = w('but', 8, lag=4)
        add(0, 'data_stream', 'packets racing round the spinner ring', f_end=snap)
        add(3, 'tick', 'kicker types on')
        add(snap, 'pop', 'spinner resolves, play mark slams in')
        add(w('video', 14, lag=1), 'hit_sub', "'300+' slams")
        add(w('video', 14, lag=5), 'pop', "'million members' rises")
        add(w('come', 26, lag=0), 'pop', "'without buffering.' rises")
    elif gfx == 'oca':
        add(w('internet', 3, lag=0), 'pop', 'provider platform opens')
        for i in range(4):
            add(w('providers', 14, lag=0) + i * 2, 'pop', f'home {i + 1} lands')
        add(w('providers', 14, lag=4), 'tick', "'YOUR INTERNET PROVIDER' types on")
        add(2, 'data_stream', 'slow long-haul packets from the far library', f_end=w('inside', 55, lag=7), gain=-28)
        add(w('get', 28), 'swoosh_fast', 'the appliance drops in')
        add(w('get', 28, lag=9), 'pop', 'the appliance lands (a small bounce)')
        add(w('free', 39), 'hit_sub', "'FREE' slams")
        add(w('inside', 55), 'data_stream', 'dense red streams from the box to every home', f_end=n - 1)
        add(w('networks', 78), 'chime', 'platform rim pulses: inside their own network')
    elif gfx == 'prefill':
        add(w('every', 9, lag=-6), 'riser', 'the moon rises', gain=-20)
        add(w('night', 17), 'pop', "'night' drops in")
        add(w('night', 17, lag=8), 'tick', "'OFF-PEAK FILL WINDOW' types on")
        for i in range(8):
            add(w('predicts', 42) + i * 2, 'pop', f'title card {i + 1} flips up')
        add(w('area', 66), 'chime', "your area's picks light red")
        add(w('copies', 108), 'swoosh_fast', 'picked cards fly into the box')
        add(w('copies', 108), 'data_stream', 'packet stream library -> box', f_end=n - 1)
        add(w('box', 124), 'pop', 'fill gauge pulses')
        add(w('near', 132), 'chime', "'the box near you'")
    elif gfx == 'ladder':
        add(w('cartoon', 7, lag=-2), 'pop', 'cartoon screen pops up')
        for i in range(5):
            add(w('cartoon', 7, lag=5) + i * 2, 'pop', f'cartoon rung {i + 1} shoots out')
        add(w('fewer', 31, lag=4), 'tick', "'fewer bits'")
        add(w('action', 53, lag=-6), 'swoosh_fast', 'camera whips to the action film')
        for i in range(5):
            add(w('action', 53, lag=5) + i * 2, 'pop', f'action rung {i + 1} shoots out')
        add(w('action', 53, lag=2), 'data_stream', 'a torrent of bits into the action ladder', f_end=w('so', 81))
        add(w('film', 63, lag=4), 'tick', "'more bits'")
        add(w('ladder', 117), 'riser', "pull back into 'Its own ladder'")
        add(w('ladder', 117, lag=3), 'hit_sub', "'ladder' lands, rungs flash")
    elif gfx == 'abr':
        add(w('video', 13, lag=-6), 'data_stream', 'light running along the video bar', f_end=w('cut', 24, lag=-2))
        add(w('cut', 24, lag=1), 'swoosh_fast', 'the laser sweeps the bar')
        add(w('chunks', 35), 'hit_sub', "'CHUNKS' slams")
        add(w('few', 52), 'tick', "'a few seconds each' types on")
        add(w('your', 81, lag=2), 'whoosh_in', 'camera swings back to the ladder')
        add(w('player', 87), 'pop', 'ladder shelves come up')
        for i in range(12):
            add(w('picks', 102) + i * 4 + 7, 'pop', f'chunk {i + 1} lands on its rung')
        add(w('every', 140), 'chime', "'every chunk' glows")
    elif gfx == 'buffer':
        add(0, 'data_stream', 'network stream onto the buffer', f_end=n - 1)
        add(w('dips', 17), 'glitch', "'dips?': the stream stutters")
        add(w('chunk', 43, lag=0), 'pop', 'the softer 720p chunk lands')
        add(w('softer', 63), 'chime', "'a little softer'")
        add(w('softer', 63, lag=8), 'tick', "'no stall' types on")
    elif gfx == 'planes':
        add(w('play', 11, lag=2), 'pop', 'play button pressed')
        add(w('play', 11, lag=3), 'swoosh_fast', 'request flies up to AWS')
        add(w('aws', 28, lag=0), 'hit_sub', "'AWS' slams", gain=-12)
        add(w('points', 43), 'swoosh_fast', 'AWS points its beam at the box')
        add(w('box', 63), 'chime', "'use this box'")
        add(w('it', 78), 'data_stream', 'the box streams the video to the screen', f_end=n - 1)
        add(w('streams', 83), 'pop', 'the screen comes alive')
    elif gfx == 'end':
        add(2, 'pop', 'play ring returns')
        add(10, 'hit_sub', "'The box next door delivers.' slams")
        add(17, 'tick', 'series tag types on')

cues.sort(key=lambda c: ([s.get('gfx') for s in edl['shots']].index(c['shot']), c['f']))
out = HERE / 'data/sfx_v3.json'
out.write_text(json.dumps(cues, indent=1) + '\n')
print(f'{len(cues)} cues -> {out}')
