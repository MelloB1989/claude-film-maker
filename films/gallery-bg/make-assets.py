#!/usr/bin/env python3
"""The gallery's sample media, drawn with ffmpeg (lavfi drawbox/drawtext): a dashboard screenshot, a tall phone feed and
a short clip. Original, made here; rerun to remake them:  python3 films/gallery-bg/make-assets.py"""
import os
import random
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'assets')
ROOT = os.path.dirname(os.path.dirname(HERE))
FONT_SRC = os.path.join(ROOT, 'fonts', 'src', 'Geist[wght].ttf')
MONO_SRC = os.path.join(ROOT, 'fonts', 'src', 'JetBrainsMono[wght].ttf')

tmp = tempfile.mkdtemp()
FONT = os.path.join(tmp, 'ui.ttf')
MONO = os.path.join(tmp, 'mono.ttf')
shutil.copy(FONT_SRC, FONT)
shutil.copy(MONO_SRC, MONO)


def box(x, y, w, h, c):
    return f"drawbox=x={x}:y={y}:w={w}:h={h}:color={c}:t=fill"


def text(s, x, y, size, c, mono=False):
    s = s.replace(':', r'\:').replace("'", '')
    return f"drawtext=fontfile={MONO if mono else FONT}:text='{s}':x={x}:y={y}:fontsize={size}:fontcolor={c}:expansion=none"


def render(w, h, filters, out, q=4):
    graph = ','.join(filters)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'color=c=0x0b1020:s={w}x{h}:d=1', '-vf', graph,
                    '-frames:v', '1', '-q:v', str(q), out], check=True)


def dashboard():
    W, H = 1600, 1000
    f = [box(0, 0, 250, H, '0x0e1530'), box(0, 0, W, 1, '0x1c2540')]
    f += [box(28, 34, 26, 26, '0x3d7bff'), text('Orbit', 66, 34, 26, '0xe8edf7')]
    for i, (name, on) in enumerate([('Overview', True), ('Analytics', False), ('Deploys', False), ('Customers', False), ('Settings', False)]):
        y = 110 + i * 52
        if on:
            f.append(box(16, y - 10, 218, 42, '0x18213d'))
            f.append(box(16, y - 10, 3, 42, '0x3d7bff'))
        f.append(box(36, y + 2, 14, 14, '0x3d7bff' if on else '0x2c3a60'))
        f.append(text(name, 64, y, 19, '0xe8edf7' if on else '0x9aa6c0'))
    f += [text('Overview', 290, 36, 34, '0xe8edf7'), text('Last 30 days', 292, 82, 17, '0x9aa6c0')]
    f += [box(1390, 38, 170, 40, '0x3d7bff'), text('New deploy', 1420, 48, 18, '0xffffff')]
    stats = [('Active users', '48,210', '+12.4%'), ('Deploys', '1,284', '+8.1%'), ('p50 latency', '82 ms', '-14%'), ('Uptime', '99.98%', '+0.02')]
    for i, (lab, val, d) in enumerate(stats):
        x = 290 + i * 320
        f += [box(x, 130, 300, 140, '0x111830'), box(x, 130, 300, 1, '0x2c3a60')]
        f += [text(lab, x + 22, 152, 17, '0x9aa6c0'), text(val, x + 22, 186, 40, '0xe8edf7'), text(d, x + 22, 238, 16, '0x2fd6a3')]
    # the chart card
    f += [box(290, 300, 880, 420, '0x111830'), text('Requests', 312, 322, 20, '0xe8edf7'), text('per day', 410, 325, 16, '0x5c6886')]
    for k in range(5):
        f.append(box(312, 380 + k * 64, 836, 1, '0x1c2540'))
    rnd = random.Random(7)
    v = 0.35
    for k in range(30):
        v = min(0.95, max(0.15, v + rnd.uniform(-0.12, 0.16)))
        bh = int(v * 300)
        f.append(box(320 + k * 27, 680 - bh, 17, bh, '0x3d7bff' if k < 29 else '0x2fd6a3'))
    # the side card
    f += [box(1190, 300, 370, 420, '0x111830'), text('Recent deploys', 1212, 322, 20, '0xe8edf7')]
    for k, (name, t, ok) in enumerate([('api-gateway', '2m ago', True), ('web', '14m ago', True), ('billing', '1h ago', False), ('search', '3h ago', True), ('auth', '5h ago', True)]):
        y = 372 + k * 66
        f += [box(1212, y, 10, 10, '0x2fd6a3' if ok else '0x3d7bff'), text(name, 1236, y - 6, 18, '0xe8edf7', mono=True), text(t, 1470, y - 4, 15, '0x5c6886')]
        f.append(box(1212, y + 36, 326, 1, '0x1c2540'))
    # the table
    f += [box(290, 740, 1270, 230, '0x111830'), text('Top endpoints', 312, 760, 20, '0xe8edf7')]
    for k, (ep, rq, lat) in enumerate([('GET /v1/projects', '1.2M', '41 ms'), ('POST /v1/deploys', '284k', '96 ms'), ('GET /v1/metrics', '198k', '58 ms')]):
        y = 810 + k * 50
        f += [text(ep, 312, y, 18, '0x9aa6c0', mono=True), text(rq, 960, y, 18, '0xe8edf7'), text(lat, 1200, y, 18, '0xe8edf7')]
        f.append(box(312, y + 36, 1226, 1, '0x1c2540'))
    render(W, H, f, os.path.join(OUT, 'dashboard.jpg'), q=5)


def feed():
    W, H = 720, 2200
    f = [text('9:41', 48, 22, 26, '0xe8edf7'), text('Orbit', 48, 96, 44, '0xe8edf7'), text('Your week in review', 50, 154, 22, '0x9aa6c0')]
    rnd = random.Random(3)
    y = 220
    for k in range(7):
        h = 300 if k % 2 == 0 else 230
        f += [box(32, y, W - 64, h, '0x111830'), box(32, y, W - 64, 1, '0x2c3a60')]
        f += [box(56, y + 28, 52, 52, '0x3d7bff' if k % 3 else '0x2fd6a3'), text(['Deploy shipped', 'Latency down 14%', 'New teammate', 'Weekly report', 'Uptime 99.98%', 'Search reindexed', 'Billing updated'][k], 128, y + 30, 26, '0xe8edf7')]
        f.append(text(['api-gateway v4.2', 'p50 82 ms', 'Mara joined Platform', '48,210 active users', 'all regions', '3.1M documents', 'invoice #2041'][k], 130, y + 64, 19, '0x9aa6c0'))
        if h == 300:
            v = 0.4
            for b in range(16):
                v = min(0.95, max(0.15, v + rnd.uniform(-0.15, 0.18)))
                bh = int(v * 150)
                f.append(box(58 + b * 38, y + h - 28 - bh, 26, bh, '0x24479a' if b < 15 else '0x3d7bff'))
        else:
            for li in range(3):
                f.append(box(58, y + 112 + li * 34, [520, 440, 300][li], 14, '0x18213d'))
        y += h + 24
    render(W, H, f, os.path.join(OUT, 'feed.jpg'), q=6)


def clip():
    # 3 s at 30 fps: a slow zoom into the Mandelbrot set, in a cold blue
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'mandelbrot=s=960x540:rate=30:start_scale=1.4:end_scale=0.6:inner=black',
                    '-t', '3', '-vf', 'format=gray,eq=contrast=1.25:brightness=-0.06,format=rgb24,colorchannelmixer=rr=0.22:gg=0.5:bb=1.0', '-c:v', 'libx264', '-preset', 'slow', '-crf', '28',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', os.path.join(OUT, 'clip.mp4')], check=True)


os.makedirs(OUT, exist_ok=True)
dashboard()
feed()
clip()
shutil.rmtree(tmp)
for n in ['dashboard.jpg', 'feed.jpg', 'clip.mp4']:
    print(n, os.path.getsize(os.path.join(OUT, n)) // 1024, 'KiB')
