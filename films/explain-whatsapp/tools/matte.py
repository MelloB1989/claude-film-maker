#!/usr/bin/env python3
"""Pull an alpha panel out of a black-matte and a grey-matte render of the same frames.

The engine composites a scene's 2D layer over its background in display space ("over" as Canvas2D blends), so with
the panel drawn over black (K) and over mid grey g = 128/255 (G), per pixel in display units:
    K = a*C,   G = a*C + (1 - a)*g   =>   a = 1 - (G - K)/g,   C = K/a   (straight colour)
Grain, vignette and fringe are off in the matte film (they would differ between the passes). Glow added as light
shows in both passes alike, so it lands in C at the alpha of what it sits on, or as faint alpha where it spills.

    python3 matte.py K.mov G.mov OUT_BASE [--png]
writes OUT_BASE.mov (ProRes 4444 with alpha, 10-bit) and, with --png, OUT_BASE_png/%04d.png (RGBA, straight).
"""
import os
import subprocess
import sys

import numpy as np

G = 128 / 255


def frames(path, w, h):
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgb48le', '-'], stdout=subprocess.PIPE)
    n = w * h * 3 * 2
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint16).reshape(h, w, 3).astype(np.float32) / 65535
    p.stdout.close()
    p.terminate()


def probe(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                   'stream=width,height,r_frame_rate', '-of', 'csv=p=0', path]).decode().split(',')
    return int(out[0]), int(out[1]), out[2].strip()


def main():
    k_path, g_path, base = sys.argv[1:4]
    png = '--png' in sys.argv
    w, h, rate = probe(k_path)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba64le', '-s', f'{w}x{h}', '-r', rate,
                            '-i', '-', '-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16',
                            '-vendor', 'apl0', base + '.mov'], stdin=subprocess.PIPE)
    if png:
        os.makedirs(base + '_png', exist_ok=True)
        from PIL import Image
    n = 0
    for K, Gp in zip(frames(k_path, w, h), frames(g_path, w, h)):
        a = 1 - (Gp - K).mean(axis=2) / G
        a = np.clip(a, 0, 1)
        a[a < 2 / 255] = 0
        C = np.where(a[..., None] > 1e-3, K / np.maximum(a[..., None], 1e-3), 0)
        C = np.clip(C, 0, 1)
        rgba = np.concatenate([C, a[..., None]], axis=2)
        q = (rgba * 65535 + 0.5).astype(np.uint16)
        enc.stdin.write(q.tobytes())
        if png:
            Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), 'RGBA').save(f'{base}_png/{n:04d}.png', compress_level=3)
        n += 1
    enc.stdin.close()
    enc.wait()
    print(f'{base}.mov: {n} frames')


if __name__ == '__main__':
    main()
