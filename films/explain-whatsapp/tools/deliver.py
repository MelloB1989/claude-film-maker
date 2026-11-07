#!/usr/bin/env python3
"""Cut the film's two renders into the per-scene deliverables (GFX.md):

    python3 deliver.py FULL.mov PANEL_MATTES.mov OUTDIR [--png]

FULL.mov is `explain-whatsapp` rendered whole (every graphics beat full frame, back to back); PANEL_MATTES.mov is
`explain-whatsapp-panel` rendered whole (the panel beats over black, then the same over grey). Writes
OUTDIR/<scene>_full.mov (ProRes 422 HQ) for every beat and OUTDIR/<scene>_panel.mov (ProRes 4444 with alpha, from
alpha.ts) for the panel beats: each the EDL's frame count plus the TAIL frames that hold the end state.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAIL = 12


def cut(src, f0, n, dst):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vf', f'trim=start_frame={f0}:end_frame={f0 + n},setpts=PTS-STARTPTS',
                    '-an', '-c:v', 'prores_ks', '-profile:v', '3', '-pix_fmt', 'yuv422p10le', '-vendor', 'apl0', dst], check=True)
    got = int(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                                       'stream=nb_read_frames', '-of', 'csv=p=0', dst]).decode().strip())
    if got != n:
        raise SystemExit(f'{dst}: {got} frames, wanted {n}')


def main():
    full, mattes, out = sys.argv[1:4]
    png = ['--png'] if '--png' in sys.argv else []
    os.makedirs(out, exist_ok=True)
    edl = json.load(open(os.path.join(HERE, '..', 'data', 'edl.json')))
    f = 0
    for s in edl['shots']:
        n = s['frames'] + TAIL
        cut(full, f, n, os.path.join(out, f"{s['gfx']}_full.mov"))
        print(f"{s['gfx']}_full.mov  frames {f}-{f + n - 1} ({n})", flush=True)
        f += n
    panels = [s for s in edl['shots'] if s['kind'] == 'panel']
    half = sum(s['frames'] + TAIL for s in panels)
    f = 0
    for s in panels:
        n = s['frames'] + TAIL
        k, g = os.path.join(out, f"_{s['gfx']}_k.mov"), os.path.join(out, f"_{s['gfx']}_g.mov")
        cut(mattes, f, n, k)
        cut(mattes, half + f, n, g)
        # straight alpha from the pair (alpha.ts: bun + ffmpeg, no numpy), ProRes 4444 (+ RGBA PNGs with --png)
        extra = []
        if png:
            d = os.path.join(out, f"{s['gfx']}_panel_png")
            os.makedirs(d, exist_ok=True)
            extra = ['--png', d]
        subprocess.run(['bun', os.path.join(HERE, 'alpha.ts'), k, g, os.path.join(out, f"{s['gfx']}_panel.mov"), '--grey', '128', *extra], check=True)
        os.remove(k)
        os.remove(g)
        f += n


if __name__ == '__main__':
    main()
