#!/usr/bin/env python3
"""Write data/sfx_v3.json, the v3 graphics' SFX hit list for agent-11's mix (docs/STYLE_V3.md section 8).

    python3 films/explain-whatsapp/tools/sfx_v3.py

Every cue is on its shot's clock (frame 0 = the shot's first frame) and inside the EDL's frame count (the 12 tail frames
are cut). Word-tied cues use the EDL's word frames plus the same 2-frame lag the scenes land on (MotionScene.cue), so
they follow the picture if the VO moves. Gains are dB against the voice: pops -18, whooshes -14, hits -10, loops -24.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.dirname(HERE)
LAG = 2


def main():
    edl = json.load(open(os.path.join(FILM, 'data', 'edl.json')))
    fps = edl['fps']
    out = []
    for s in edl['shots']:
        shot, n = s['gfx'], s['frames']
        words = s['words']

        def w(word, nth=0, fb=0):
            hits = [x['f'] for x in words if x['w'].lower().strip(".,?!") == word]
            return (hits[nth] if nth < len(hits) else fb) + LAG

        def sec(x):
            return round(x * fps)

        cues = []

        def c(f, sfx, gain, note, **kw):
            f = int(round(f))
            if 0 <= f < n:
                cues.append(dict(shot=shot, f=f, sfx=sfx, gain=gain, note=note, **kw))

        def stream(f0, f1, note, gain=-24):
            f0, f1 = max(0, int(f0)), min(n - 1, int(f1))
            if f1 > f0:
                cues.append(dict(shot=shot, f=f0, f_end=f1, sfx='data_stream', gain=gain, note=note))

        c(8, 'whoosh_in', -14, 'camera arrive settles')
        if shot == 'title':
            stream(0, n - 1, 'the river of messages through the server')
            c(3, 'pop', -18, '100+ billion rises')
            c(w('stay'), 'hit_sub', -10, 'the 0 slams on the server')
            c(w('servers'), 'pop', -18, '"delivered, then deleted"')
        elif shot == 'connect':
            c(w('open'), 'pop', -18, 'phone screen wakes')
            c(w('connection') - 4, 'swoosh_fast', -14, 'the connection beam draws to the server')
            c(w('one'), 'pop', -18, '"One connection,"')
            stream(w('connection') + 7, n - 1, 'heartbeats both ways', gain=-26)
            c(w('open', 1), 'pop', -18, '"always open"')
            c(w('whatsapp'), 'pop', -20, '"server" label')
        elif shot == 'erlang':
            c(w('server'), 'pop', -18, 'ONE SERVER, the cube lights')
            stream(w('each'), w('tiny'), 'six phones beam in, orbs light')
            for i in range(0, 6, 2):
                c(w('each') + sec(0.32) + i * 2, 'pop', -20, f'process orb {i + 1} lights')
            c(w('tiny') - 2, 'swoosh_fast', -14, 'camera dives onto one orb')
            c(w('erlang'), 'pop', -18, '"1 Erlang process"')
            c(w('process'), 'tick', -22, 'A FEW KB · OWN MAILBOX')
            c(w('two'), 'riser', -16, 'riser peaks as the field explodes', )
            c(w('two') + 1, 'hit_sub', -10, '2,000,000 slams; the pull back')
            c(w('million'), 'pop', -18, 'CONNECTIONS · ONE SERVER (2012)')
        elif shot == 'store':
            c(w('straight') - 5, 'swoosh_fast', -14, 'message shoots through')
            c(w('straight') + sec(0.62) - LAG, 'chime', -16, 'delivered to the online friend')
            c(w('if') + 2, 'pop', -18, 'friend drops OFFLINE')
            c(w('if') + sec(0.5), 'pop', -20, 'message parks in the slot')
            for k in range(3):
                c(w('waits') + k * 6, 'tick', -24, 'clock ring (WAITS)')
            c(w('delivered') - 4, 'swoosh_fast', -14, 'friend back: the message shoots across')
            c(w('delivered') + sec(0.28), 'chime', -16, 'delivered (two ticks)')
            c(w('deleted'), 'hit_sub', -10, 'the server copy shatters; "then deleted"')
        elif shot == 'ticks':
            c(w('ticks'), 'pop', -18, 'the bubble swings in')
            c(w('one'), 'pop', -14, 'tick 1 slams')
            c(w('server'), 'pop', -20, '"the server has it"')
            c(w('two'), 'pop', -14, 'tick 2 slams')
            c(w('reached'), 'pop', -20, '"it reached their phone"')
            c(w('blue'), 'chime', -14, 'ticks turn blue')
            c(w('read'), 'pop', -20, '"they\'ve read it"')
        elif shot == 'group':
            for i in range(4):
                c(w('group') - 4 + i * 2, 'pop', -20, f'group phones pop up ({i + 1})')
            c(w('encrypts') + 3, 'pop', -14, 'the lock snaps shut')
            c(w('once'), 'swoosh_fast', -14, 'one sealed copy flies to the server')
            c(w('fans') + 2, 'hit_sub', -10, 'the fan-out burst')
            stream(w('fans') + 4, n - 1, 'streams to every member')
            c(w('everyone'), 'pop', -18, 'GROUPS UP TO 1,024 MEMBERS')
        elif shot == 'e2e':
            stream(0, n - 1, 'ciphertext stream through the server', gain=-26)
            c(w('signal'), 'pop', -18, '"Signal"')
            c(w('protocol'), 'pop', -18, '"protocol", tag')
            c(w('keys') - 6, 'swoosh_fast', -16, 'keys drop')
            c(w('keys') + 5, 'pop', -14, 'keys dock on the phones')
            c(w('phones'), 'chime', -18, 'keys pulse')
        elif shot == 'media':
            c(w('photos'), 'pop', -18, 'the photo lifts off')
            c(w('go'), 'swoosh_fast', -16, 'the photo arcs to the store')
            c(w('blob'), 'pop', -20, '"blob store"')
            c(w('encrypted') + 2, 'pop', -14, 'scramble + the lock snaps')
            c(w('encrypted') + sec(0.55), 'pop', -18, 'drops into the store')
            c(w('only') - 1, 'swoosh_fast', -16, 'the key rides the message')
            c(w('key'), 'pop', -18, 'KEY + LINK')
            c(w('message') - 1, 'chime', -16, 'key arrives')
            stream(w('message'), n - 1, 'the friend pulls the blob (via CDN)')
        elif shot == 'end':
            cues = [x for x in cues if x['sfx'] != 'whoosh_in']
            c(1, 'riser', -16, 'riser peaks into the slam (it starts in the presenter shot before)')
            c(3, 'hit_sub', -10, '100+ billion slams')
            for i in range(3):
                c(11 + i * 2, 'pop', -20, f'answer {i + 1}')
        out += cues
    json.dump(out, open(os.path.join(FILM, 'data', 'sfx_v3.json'), 'w'), indent=1)
    print(f'{len(out)} cues')


if __name__ == '__main__':
    main()
