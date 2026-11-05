"""film-anime-cutout: cut the characters out of a keyframe, and fill the plate behind them.

A 2.5D shot moves its layers at different depths, so a keyframe is split in two: the foreground (the characters,
RGBA with a soft matte) and the plate behind them, its hole filled so the parallax never shows a gap. The matte is
the anime segmentation model (skytnt/anime-seg's ISNet, ONNX, on the CPU), cleaned and feathered; the hole (the
matte grown a little past its edge) is filled by push-pull, a smooth fill that reads as out-of-focus background, which
holds for the few pixels a camera move uncovers (a big move wants a plate generated on its own).

    uv run film-anime-cutout --film <id> --src assets/gen/key-standoff.png [--out assets/layers/standoff]
        [--grow 12] [--feather 1.5] [--keep-largest 0]

writes <out>/fg.png (premultiplied-safe straight-alpha RGBA), <out>/plate.png (RGB, filled) and <out>/matte.png
(8-bit). --boxes x0,y0,x1,y1;... keeps only matte inside those boxes (fractions of the frame): when the model picks up
a post or a boat as well as a person. --parts x0,y0,x1,y1;... segments each box on its own (a small figure fills the
model's input, so it is found where the whole frame missed it) and writes each as its own full-frame layer,
<out>/part1.png, part2.png, ..., for figures at different depths; fg.png and the plate then hold all of them.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import cli, paths


MODEL_URL = "https://huggingface.co/skytnt/anime-seg/resolve/main/isnetis.onnx"
MODEL_SIZE = 1024


def model_path() -> Path:
    """The anime segmentation model (skytnt/anime-seg ISNet, Apache-2.0), fetched once to ~/.cache/film-tools."""
    import urllib.request

    p = Path.home() / ".cache" / "film-tools" / "isnetis.onnx"
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        print(f"fetching {MODEL_URL} (176 MB, once)")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(p)
    return p


def matte(rgb: np.ndarray, size: int = MODEL_SIZE) -> np.ndarray:
    """The foreground (character) matte of an RGB uint8 image, float32 0..1: the image letterboxed into a size x
    size square, segmented, and the matte cropped back and resized to the image."""
    import cv2
    import onnxruntime as ort

    sess = ort.InferenceSession(str(model_path()), providers=["CPUExecutionProvider"])
    h0, w0 = rgb.shape[:2]
    h, w = (size, int(size * w0 / h0)) if h0 > w0 else (int(size * h0 / w0), size)
    ph, pw = size - h, size - w
    x = np.zeros((size, size, 3), np.float32)
    x[ph // 2:ph // 2 + h, pw // 2:pw // 2 + w] = cv2.resize(rgb.astype(np.float32) / 255.0, (w, h), interpolation=cv2.INTER_AREA)
    m = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    m = m[ph // 2:ph // 2 + h, pw // 2:pw // 2 + w]
    return np.clip(cv2.resize(m, (w0, h0), interpolation=cv2.INTER_CUBIC), 0, 1).astype(np.float32)


def refine(m: np.ndarray, feather: float = 1.5, boxes: list[tuple[float, float, float, float]] | None = None,
           keep_largest: int = 0) -> np.ndarray:
    """Clean a matte: drop specks, keep only `boxes` (fractions) if given, keep the `keep_largest` biggest blobs
    (0: all), then soften the edge by `feather` px."""
    import cv2

    h, w = m.shape
    if boxes:
        keep = np.zeros_like(m)
        for x0, y0, x1, y1 in boxes:
            keep[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1
        m = m * keep
    hard = (m > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hard, 8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(-areas) + 1
    min_area = 0.0005 * h * w
    keep_ids = [i for i in order if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if keep_largest:
        keep_ids = keep_ids[:keep_largest]
    blob = np.isin(lab, keep_ids).astype(np.float32)
    # the soft matte inside the kept blobs (grown a touch, so their soft edges stay)
    near = cv2.dilate(blob, np.ones((5, 5), np.uint8))
    out = m * near
    if feather > 0:
        out = cv2.GaussianBlur(out, (0, 0), feather)
    return np.clip(out, 0, 1)


def pushpull(rgb: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Fill the pixels where `known` is 0 from the ones where it is 1 by push-pull: average down a pyramid weighting
    by what is known (the coarsest level knows everything), then fill each level's unknown pixels from the level
    below it on the way back up. Smooth, with no streaks: it reads as soft out-of-focus background."""
    import cv2

    c = rgb.astype(np.float32) * known[..., None]
    w = known.astype(np.float32)
    levels = []
    # down until every cell of the coarsest level knows something (a hole as wide as a coarse cell would stay empty)
    while min(w.shape) > 1 and (min(w.shape) > 4 or (w <= 1e-6).any()):
        levels.append((c, w))
        c = cv2.resize(c, (max(1, c.shape[1] // 2), max(1, c.shape[0] // 2)), interpolation=cv2.INTER_AREA)
        w = cv2.resize(w, (c.shape[1], c.shape[0]), interpolation=cv2.INTER_AREA)
        if c.ndim == 2:
            c = c[..., None]
    col = c / np.maximum(w, 1e-6)[..., None]
    if (w <= 1e-6).any():  # still a cell with nothing known: the mean of all that is
        col[w <= 1e-6] = c.reshape(-1, c.shape[-1]).sum(0) / max(float(w.sum()), 1e-6)
    for c_l, w_l in reversed(levels):
        up = cv2.resize(col, (c_l.shape[1], c_l.shape[0]), interpolation=cv2.INTER_LINEAR)
        own = c_l / np.maximum(w_l, 1e-6)[..., None]
        k = np.clip(w_l, 0, 1)[..., None]
        col = own * k + up * (1 - k)
    return col


def fill_plate(rgb: np.ndarray, m: np.ndarray, grow: int = 12, method: str = "pushpull") -> np.ndarray:
    """The plate behind the matte: the matte grown by `grow` px and filled ('pushpull': soft and smooth, right for
    mist and out-of-focus backgrounds; 'telea': OpenCV inpainting, which keeps edges but streaks in a wide hole),
    blended in over a soft edge."""
    import cv2

    hole = (m > 0.02).astype(np.uint8)
    if grow > 0:
        hole = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    if method == "telea":
        small = cv2.resize(rgb, (rgb.shape[1] // 2, rgb.shape[0] // 2), interpolation=cv2.INTER_AREA)
        hs = cv2.resize(hole, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        fill = cv2.inpaint(small, hs, 9, cv2.INPAINT_TELEA)
        fill = cv2.resize(cv2.GaussianBlur(fill, (0, 0), 3), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    elif method == "pushpull":
        fill = pushpull(rgb, 1.0 - hole.astype(np.float32))
    else:
        raise SystemExit(f"--fill is 'pushpull' or 'telea', got {method!r}")
    k = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), max(1.0, grow / 3))[..., None]
    return np.clip(rgb * (1 - k) + fill * k, 0, 255).astype(np.uint8)


def part_matte(rgb: np.ndarray, box: tuple[float, float, float, float], feather: float) -> np.ndarray:
    """The matte of the largest figure inside `box` (fractions), segmented on the crop alone, on a full-frame canvas."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    m = np.zeros((h, w), np.float32)
    m[y0:y1, x0:x1] = refine(matte(rgb[y0:y1, x0:x1]), feather, None, 1)
    return m


def cutout(src: Path, out: Path, *, grow: int = 12, feather: float = 1.5, fill: str = "pushpull",
           boxes: list[tuple[float, float, float, float]] | None = None, keep_largest: int = 0,
           parts: list[tuple[float, float, float, float]] | None = None) -> dict[str, Path]:
    from PIL import Image

    rgb = np.asarray(Image.open(src).convert("RGB"))
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    if parts:
        ms = [part_matte(rgb, b, feather) for b in parts]
        for i, pm in enumerate(ms, 1):
            Image.fromarray(np.dstack([rgb, (pm * 255 + 0.5).astype(np.uint8)])).save(out / f"part{i}.png")
            written[f"part{i}"] = out / f"part{i}.png"
        m = np.maximum.reduce(ms)
    else:
        m = refine(matte(rgb), feather, boxes, keep_largest)
    a = (m * 255 + 0.5).astype(np.uint8)
    Image.fromarray(np.dstack([rgb, a])).save(out / "fg.png")
    Image.fromarray(fill_plate(rgb, m, grow, fill)).save(out / "plate.png")
    Image.fromarray(a).save(out / "matte.png")
    return {**written, "fg": out / "fg.png", "plate": out / "plate.png", "matte": out / "matte.png"}


def parse_boxes(s: str | None) -> list[tuple[float, float, float, float]] | None:
    if not s:
        return None
    boxes = []
    for b in s.split(";"):
        v = [float(x) for x in b.split(",")]
        if len(v) != 4:
            raise SystemExit(f"a box is x0,y0,x1,y1 (fractions), got {b!r}")
        boxes.append((v[0], v[1], v[2], v[3]))
    return boxes


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Cut the characters out of a keyframe and fill the plate behind them.")
    ap.add_argument("--src", required=True, help="the keyframe, relative to the film folder")
    ap.add_argument("--out", help="the layer folder, relative to the film (default assets/layers/<src stem>)")
    ap.add_argument("--grow", type=int, default=12)
    ap.add_argument("--feather", type=float, default=1.5)
    ap.add_argument("--fill", default="pushpull", help="how the plate's hole is filled: pushpull (soft) or telea")
    ap.add_argument("--boxes", help="keep only matte inside these boxes: x0,y0,x1,y1;... (fractions of the frame)")
    ap.add_argument("--keep-largest", type=int, default=0)
    ap.add_argument("--parts", help="segment each box on its own, one layer each: x0,y0,x1,y1;... (fractions)")
    a = cli.parse(ap, argv)
    f = paths.current()
    src = f.path(a.src)
    out = f.path(a.out) if a.out else f.dir / "assets" / "layers" / src.stem.removeprefix("key-")
    for k, p in cutout(src, out, grow=a.grow, feather=a.feather, fill=a.fill, boxes=parse_boxes(a.boxes),
                       keep_largest=a.keep_largest, parts=parse_boxes(a.parts)).items():
        print(f"{k}: {f.rel(p)}")
