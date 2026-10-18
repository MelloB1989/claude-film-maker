"""Labelled strip of stage frames (VM python, cv2): python strip.py <pass_dir> <f0> <f1> <out.jpg> [w] [cols]"""
import os
import sys

import cv2
import numpy as np

src, f0, f1, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
w = int(sys.argv[5]) if len(sys.argv) > 5 else 480
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 6
tiles = []
for f in range(f0, f1 + 1):
    im = cv2.imread(os.path.join(src, f"f_{f:05d}.png"), cv2.IMREAD_UNCHANGED)
    if im is None:
        continue
    if im.shape[2] == 4:  # straight alpha over magenta: shows holes / uncovered frame
        a = im[:, :, 3:4].astype(np.float32) / 255
        im = (im[:, :, :3] * a + np.array([255, 0, 255]) * (1 - a)).astype(np.uint8)
    im = cv2.resize(im, (w, int(im.shape[0] * w / im.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.putText(im, str(f), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(im, str(f), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    tiles.append(im)
blank = np.zeros_like(tiles[0])
while len(tiles) % cols:
    tiles.append(blank)
rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(out)
