"""Make a labelled strip of consecutive frames: python strip.py <frames_dir> <f0> <f1> <out.jpg> [--w 450] [--cols 8]"""
import os
import sys

import cv2
import numpy as np


def main():
    src, f0, f1, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    w = int(sys.argv[sys.argv.index("--w") + 1]) if "--w" in sys.argv else 450
    cols = int(sys.argv[sys.argv.index("--cols") + 1]) if "--cols" in sys.argv else 8
    tiles = []
    for f in range(f0, f1 + 1):
        im = cv2.imread(os.path.join(src, f"f_{f:04d}.jpg"))
        if im is None:
            continue
        im = cv2.resize(im, (w, int(im.shape[0] * w / im.shape[1])), interpolation=cv2.INTER_AREA)
        cv2.putText(im, str(f), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(im, str(f), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
        tiles.append(im)
    blank = np.zeros_like(tiles[0])
    while len(tiles) % cols:
        tiles.append(blank)
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


if __name__ == "__main__":
    main()
