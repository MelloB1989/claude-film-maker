"""Desktop input and screen grabs for the few things only the editor's UI can do (Fab, some dialogs). The editor runs in
the logged-in desktop session, so input it sends lands on that desktop. Runs on the bridge's HTTP thread (never the
game thread: the editor must keep pumping messages while a click lands).

Actions (a list, run in order); x, y are pixels on a screenshot `ref` = [w, h] wide (default: the real screen):
    {"click": [x, y]}  {"dclick": [x, y]}  {"rclick": [x, y]}  {"move": [x, y]}
    {"drag": [x1, y1, x2, y2]}  {"scroll": [x, y, notches]}  (notches < 0 scroll down)
    {"type": "text"}  {"key": "enter" | "ctrl+s" | "esc" ...}  {"wait": ms}
"""
from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import tempfile
import time
import zlib
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSE = {"move": 0x0001, "ldown": 0x0002, "lup": 0x0004, "rdown": 0x0008, "rup": 0x0010, "wheel": 0x0800, "abs": 0x8000}
KEYUP, UNICODE = 0x0002, 0x0004
VK = {"enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
      "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23, "f2": 0x71,
      "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, **{chr(c): c for c in range(0x30, 0x3A)},
      **{chr(c).lower(): c for c in range(0x41, 0x5B)}}


class _MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", _MI), ("ki", _KI), ("pad", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(*inputs):
    arr = (_INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))


def _mouse(flags, data=0, x=0, y=0):
    i = _INPUT(type=INPUT_MOUSE)
    i.u.mi = _MI(x, y, data & 0xFFFFFFFF, flags, 0, 0)
    return i


def _key(vk=0, scan=0, flags=0):
    i = _INPUT(type=INPUT_KEYBOARD)
    i.u.ki = _KI(vk, scan, flags, 0, 0)
    return i


def screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _xy(x, y, ref):
    w, h = screen_size()
    if ref:
        x, y = x * w / ref[0], y * h / ref[1]
    return int(round(x)), int(round(y))


def _move(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.05)


def _click(x, y, down="ldown", up="lup", times=1):
    _move(x, y)
    for _ in range(times):
        _send(_mouse(MOUSE[down]), _mouse(MOUSE[up]))
        time.sleep(0.07)


def _type(text: str):
    for ch in text:
        code = ord(ch)
        _send(_key(scan=code, flags=UNICODE), _key(scan=code, flags=UNICODE | KEYUP))
        time.sleep(0.008)


def _chord(spec: str):
    keys = [VK[k.strip().lower()] for k in spec.split("+")]
    _send(*[_key(vk=k) for k in keys])
    _send(*[_key(vk=k, flags=KEYUP) for k in reversed(keys)])


def run(actions: list[dict]) -> list:
    done = []
    for a in actions:
        ref = a.get("ref")
        if "click" in a:
            _click(*_xy(*a["click"], ref))
        elif "dclick" in a:
            _click(*_xy(*a["dclick"], ref), times=2)
        elif "rclick" in a:
            _click(*_xy(*a["rclick"], ref), "rdown", "rup")
        elif "move" in a:
            _move(*_xy(*a["move"], ref))
        elif "drag" in a:
            x1, y1, x2, y2 = a["drag"]
            p1, p2 = _xy(x1, y1, ref), _xy(x2, y2, ref)
            _move(*p1)
            _send(_mouse(MOUSE["ldown"]))
            for k in range(1, 21):
                t = k / 20
                user32.SetCursorPos(int(p1[0] + (p2[0] - p1[0]) * t), int(p1[1] + (p2[1] - p1[1]) * t))
                time.sleep(0.015)
            _send(_mouse(MOUSE["lup"]))
        elif "scroll" in a:
            x, y, n = a["scroll"]
            _move(*_xy(x, y, ref))
            _send(_mouse(MOUSE["wheel"], int(n) * 120))
        elif "type" in a:
            _type(a["type"])
        elif "key" in a:
            _chord(a["key"])
        elif "wait" in a:
            time.sleep(a["wait"] / 1000)
        done.append(next(iter(a)))
        time.sleep(a.get("pause", 120) / 1000)
    return done


# --------------------------------------------------------------------------------------------------------- screen

def _png(w: int, h: int, rgb: bytes) -> bytes:
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b"")


def screenshot_png() -> bytes:
    """The desktop as PNG: through NICE DCV's own grabber when it is there, else a GDI copy of the screen."""
    dcv = r"C:\Program Files\NICE\DCV\Server\bin\dcv.exe"
    if os.path.exists(dcv):
        out = os.path.join(tempfile.gettempdir(), "fmbridge_screen.png")
        r = subprocess.run([dcv, "get-screenshot", "--max-width", "4096", "--format", "png", "--output", out, "console"],
                           capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode == 0 and os.path.exists(out):
            with open(out, "rb") as f:
                return f.read()
    w, h = screen_size()
    hdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    hdr = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.c_char_p(hdr), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)
    bgra = buf.raw
    rgb = bytearray(w * h * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    return _png(w, h, bytes(rgb))


def log_tail(logs: str, lines: int = 200) -> str:
    files = sorted((os.path.join(logs, f) for f in os.listdir(logs) if f.endswith(".log")), key=os.path.getmtime)
    if not files:
        return ""
    with open(files[-1], "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400 * lines))
        return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-lines:])
