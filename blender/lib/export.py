"""What a Blender render hands the engine: plates (EXR + PNG proxy per frame), look stills, and tracked anchors.

A shot numbers its Blender frames as film frames (render.py sets frame_start to the shot's first film frame f0).
Per rendered film frame f, with #### = f - f0 (the plate's index, as app/src/engine/plates.ts reads it):
  out/plates/<shot>/####.exr           linear half-float RGBA (ZIP), Blender's premultiplied alpha: the plate
  app/public/plates/<shot>/proxy/####.png  8-bit sRGB, 960x540 (half the film's 1920x1080): the preview's stand-in,
                                           encoded from the EXR with the plain sRGB transfer (clipped at 1), so it
                                           decodes to the plate's own linear values, not a second tone map
  out/look/<shot>/<f>.png              look mode only: the render through the scene's view transform (AgX), named by
                                       film frame, for looking at
Tracks: data/track/<shot>.json = {"fps": 30, "f0": f0, "anchors": {name: [[x, y, visible], ...]}}, one sample per
film frame from f0, in the film's logical 1920x1080 px (engine: track.ts).

Every frame is checked as soon as its EXR is written: one that comes out blank (Cycles on Metal has written runs of
black frames, silently, with two renders sharing the GPU) is rendered again, and one that stays blank fails the render
with BlankFrameError (lib/blank.py). SHOT["black_ok"] exempts the frames a shot means to be black.

The path, pixel and PNG helpers are bpy-free (tested under the tools project); the rest imports bpy when called.
"""
from __future__ import annotations

import json
import math
import os
import struct
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import blank

REPO = Path(__file__).resolve().parents[2]
FPS = 30
W, H = 1920, 1080  # the film's logical frame
PROXY_RES = (960, 540)


@dataclass(frozen=True)
class PlatePaths:
    exr: Path
    proxy: Path


def plate_paths(shot: str, index: int, root: Path = REPO) -> PlatePaths:
    """Where frame `index` (film frame - f0) of a shot's plate goes."""
    n = f"{index:04d}"
    return PlatePaths(root / "out" / "plates" / shot / f"{n}.exr", root / "app" / "public" / "plates" / shot / "proxy" / f"{n}.png")


def look_path(shot: str, film_frame: int, root: Path = REPO) -> Path:
    return root / "out" / "look" / shot / f"{film_frame:04d}.png"


def track_path(shot: str, root: Path = REPO) -> Path:
    return root / "data" / "track" / f"{shot}.json"


def to_logical(co) -> tuple[float, float, int]:
    """A world_to_camera_view result (x, y across the frame from its bottom-left, z the depth in front of the camera)
    as the film's logical px from the top-left, and 1 if the point is in front of the camera and inside the frame."""
    x, y, z = co[0], co[1], co[2]
    visible = 1 if z > 0 and 0 <= x <= 1 and 0 <= y <= 1 else 0
    return float(x * W), float(H - y * H), visible


def track_doc(f0: int, anchors: dict) -> dict:
    """The track file's content: px to a thousandth, visibility as 0/1."""
    return {"fps": FPS, "f0": f0,
            "anchors": {k: [[round(x, 3), round(y, 3), int(v)] for x, y, v in s] for k, s in anchors.items()}}


def _area_weights(n_in: int, n_out: int) -> np.ndarray:
    """(n_out, n_in): the share of each input pixel in each output pixel's footprint (rows sum to 1)."""
    scale = n_in / n_out
    w = np.zeros((n_out, n_in), np.float32)
    for i in range(n_out):
        a, b = i * scale, (i + 1) * scale
        for j in range(int(math.floor(a)), min(int(math.ceil(b)), n_in)):
            w[i, j] = max(0.0, min(b, j + 1) - max(a, j))
    return w / scale


def resample_area(img: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """Area-average an (h, w, c) image to (out_h, out_w, c): each output pixel is the mean of the input it covers."""
    h, w, c = img.shape
    wy, wx = _area_weights(h, out_h), _area_weights(w, out_w)
    tmp = (wy @ img.astype(np.float32).reshape(h, w * c)).reshape(out_h, w, c)
    return np.einsum("ywc,xw->yxc", tmp, wx, optimize=True)


def srgb8(lin: np.ndarray) -> np.ndarray:
    """Linear light to 8-bit sRGB (the IEC 61966-2-1 transfer), clipped to [0, 1]."""
    x = np.clip(np.asarray(lin, np.float64), 0.0, 1.0)
    s = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)
    return np.round(s * 255).astype(np.uint8)


def write_png(path: Path, rgba: np.ndarray) -> None:
    """An 8-bit RGBA PNG from an (h, w, 4) uint8 array, top row first."""
    h, w, c = rgba.shape
    if c != 4 or rgba.dtype != np.uint8:
        raise ValueError("write_png takes (h, w, 4) uint8")
    raw = np.hstack([np.zeros((h, 1), np.uint8), rgba.reshape(h, w * 4)]).tobytes()  # filter 0 on every row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def read_png(path: Path) -> np.ndarray:
    """An 8-bit RGB or RGBA PNG as an (h, w, 3 or 4) uint8 array, top row first, exactly as its bytes say: no colour
    management. It reads what `write_png` writes (not interlaced, filter 0 on every row); any other PNG, and any
    damaged file (truncated, a failed CRC, the wrong amount of data), raises ValueError."""
    path = Path(path)
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    header, idat, pos, ended = None, [], 8, False
    while pos < len(data) and not ended:
        if pos + 8 > len(data):
            raise ValueError(f"{path} is truncated")
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body, crc = data[pos + 8:pos + 8 + n], data[pos + 8 + n:pos + 12 + n]
        if len(body) != n or len(crc) != 4:
            raise ValueError(f"{path} is truncated")
        if struct.unpack(">I", crc)[0] != zlib.crc32(tag + body) & 0xFFFFFFFF:
            raise ValueError(f"{path}: the {tag.decode('latin-1')} chunk fails its CRC (the file is damaged)")
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        ended = tag == b"IEND"
        pos += 12 + n
    if header is None or not idat or not ended:
        raise ValueError(f"{path} is truncated (no header, image data or end)")
    w, h, depth, color, _compression, _filter_method, interlace = header
    channels = {2: 3, 6: 4}.get(color)
    if depth != 8 or channels is None or interlace:
        raise ValueError(f"{path}: read_png reads 8-bit RGB and RGBA PNGs that are not interlaced "
                         f"(this is depth {depth}, colour type {color}, interlace {interlace})")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as e:
        raise ValueError(f"{path}: the image data does not decompress ({e})") from e
    if len(raw) != h * (1 + w * channels):
        raise ValueError(f"{path}: {len(raw)} bytes of image data, not the {h * (1 + w * channels)} a "
                         f"{w}x{h} image takes")
    rows = np.frombuffer(raw, np.uint8).reshape(h, 1 + w * channels)
    if rows[:, 0].any():
        raise ValueError(f"{path}: rows use PNG filter {int(rows[:, 0].max())}; read_png reads filter 0, which is "
                         "what write_png writes")
    return rows[:, 1:].reshape(h, w, channels).copy()


def proxy_from_linear(px: np.ndarray, res=PROXY_RES) -> np.ndarray:
    """A plate's premultiplied linear RGBA (h, w, 4), top row first, as the proxy's 8-bit straight-alpha sRGB."""
    if (px.shape[1], px.shape[0]) != tuple(res):
        px = resample_area(px, res[0], res[1])
    a = np.clip(px[..., 3:4], 0.0, 1.0)
    rgb = np.where(a > 1e-6, px[..., :3] / np.maximum(a, 1e-6), 0.0)
    return np.concatenate([srgb8(rgb), np.round(a * 255).astype(np.uint8)], axis=2)


# ---------------------------------------------------------------------------------------------------- Blender side

def _settings(scene, fmt: str, *, depth: str, mode: str):
    ims = scene.render.image_settings
    if hasattr(ims, "media_type"):
        ims.media_type = "IMAGE"
    ims.file_format = fmt
    ims.color_mode = mode
    ims.color_depth = depth
    if fmt == "OPEN_EXR":
        ims.exr_codec = "ZIP"
    ims.color_management = "FOLLOW_SCENE"


def save_exr(image, scene, path: Path) -> None:
    """The render as linear half-float RGBA EXR (the scene's linear working space; no view transform)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _settings(scene, "OPEN_EXR", depth="16", mode="RGBA")
    image.save_render(str(path), scene=scene)


def save_view_png(image, scene, path: Path) -> None:
    """The render through the scene's view transform (AgX), as the eye sees it in Blender."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _settings(scene, "PNG", depth="8", mode="RGB")
    image.save_render(str(path), scene=scene)


def read_linear(path: Path) -> np.ndarray:
    """An EXR's pixels as (h, w, 4) float32, top row first."""
    import bpy

    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        if w == 0 or h == 0:  # a truncated or damaged file: Blender logs why and hands back an empty image
            raise ValueError(f"{path}: Blender could not read any pixels from it (a truncated or damaged file?)")
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]  # Blender stores rows bottom-up


def write_proxy(exr: Path, png: Path, res=PROXY_RES) -> None:
    write_png(png, proxy_from_linear(read_linear(exr), res))


@contextmanager
def _film_off(scene):
    """The test hook: Cycles' film exposure at 0 for the render inside, so a real render comes out black, lights, world
    and emissive materials alike (Task 11 found that toggling hide_render per frame crashes Cycles 5.2.2 with motion
    blur, so nothing is hidden)."""
    if scene.render.engine != "CYCLES":
        raise RuntimeError(f"{blank.FORCE_ENV} renders black through Cycles' film exposure, and the engine is "
                           f"{scene.render.engine}")
    cycles = scene.cycles
    keep = cycles.film_exposure
    cycles.film_exposure = 0.0
    try:
        yield
    finally:
        cycles.film_exposure = keep


def render_frame(scene, film_frame: int, shot: str, f0: int, look: bool = False, black_ok: bool = False) -> list[Path]:
    """Render one film frame and write its plate (EXR and proxy), plus its look still. Returns what it wrote.

    The frame is checked once its EXR is written (lib/blank.py): a blank one is rendered again, up to twice, each
    attempt logged, and one that stays blank raises BlankFrameError with its plate left where it was written.
    `black_ok`, for a frame the shot declares black, skips the check. The test hook GITLOOM_FORCE_BLANK ("F" or "F:N",
    comma-separated) makes film frame F render black on its first N attempts (default 1) to prove the retry; unset, it
    does nothing."""
    import bpy

    p = plate_paths(shot, film_frame - f0)
    lp = look_path(shot, film_frame) if look else None
    forced = blank.parse_force_blank(os.environ.get(blank.FORCE_ENV)).get(film_frame, 0)

    def once(attempt: int) -> np.ndarray:
        scene.frame_set(film_frame)
        if attempt <= forced:
            print(f"[{shot}] film frame {film_frame}: attempt {attempt} rendered black on purpose ({blank.FORCE_ENV})",
                  flush=True)
            with _film_off(scene):
                bpy.ops.render.render()
        else:
            bpy.ops.render.render()
        rr = bpy.data.images["Render Result"]
        save_exr(rr, scene, p.exr)
        px = read_linear(p.exr)  # what was written: the check and the proxy both come from the file
        write_png(p.proxy, proxy_from_linear(px))
        if lp is not None:
            save_view_png(rr, scene, lp)
        return px

    blank.render_checked(once, shot=shot, film_frame=film_frame, path=p.exr, black_ok=black_ok)
    return [p.exr, p.proxy] + ([lp] if lp is not None else [])


def track(names, cam, f0: int, f1: int, shot: str | None = None, root: Path = REPO) -> Path:
    """Project the objects `names` (empties, usually) through `cam` at every film frame in [f0, f1) and write
    data/track/<shot>.json (shot: the scene's 'shot' property, which render.py sets). Positions are taken at each
    frame's own time, the middle of the motion-blur shutter, where the plate's motion blur is centred."""
    import bpy
    from bpy_extras.object_utils import world_to_camera_view

    scene = bpy.context.scene
    shot = shot or scene.get("shot")
    if not shot:
        raise ValueError("track() needs a shot name")
    missing = [n for n in names if n not in bpy.data.objects]
    if missing:
        raise KeyError(f"no objects named {missing} to track")
    anchors: dict[str, list] = {n: [] for n in names}
    keep = scene.frame_current
    for f in range(f0, f1):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        cam_ev = cam.evaluated_get(dg)
        for n in names:
            ob = bpy.data.objects[n].evaluated_get(dg)
            anchors[n].append(to_logical(world_to_camera_view(scene, cam_ev, ob.matrix_world.translation)))
    scene.frame_set(keep)
    path = track_path(shot, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(track_doc(f0, anchors), separators=(",", ":")) + "\n")
    return path
