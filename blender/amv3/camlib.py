"""Timeless v3 stage: card-space camera maths (pure Python, no bpy; also used by gate.py and tests).

Card space (EDIT.md "Card space and camera state"): a card is the 1.92 x 1.08 m picture plane of a shot, 1 px = 1 mm.
A camera State on a card is the 2D picture transform v2 used:
  s      picture scale, 1.0 = the card exactly fills the frame (camera at FILL_DIST / s in front of the card)
  cx, cy the card pixel at frame centre (x right, y down, 0..1920 / 0..1080)
  r      roll in degrees, + = the picture turns clockwise on screen
  ds, dcx, dcy, dr  rates per frame (ds in d ln s / frame, dc in px / frame, dr in deg / frame)
Card local axes: +X = picture right, +Y = picture up, +Z = towards the viewer (the card's normal). A camera with identity
rotation looks down -Z with +Y up, so pose() is a translation along +Z plus a roll about Z.
"""
import math
from dataclasses import dataclass, replace

LENS_MM = 35.0
SENSOR_MM = 36.0
CARD_W = 1.92
CARD_H = 1.08
W_PX, H_PX = 1920, 1080
FILL_DIST = CARD_W * LENS_MM / SENSOR_MM  # 1.8667 m: the camera distance at which the card exactly fills the frame


@dataclass
class State:
    s: float = 1.0
    cx: float = 960.0
    cy: float = 540.0
    r: float = 0.0
    ds: float = 0.0
    dcx: float = 0.0
    dcy: float = 0.0
    dr: float = 0.0

    def vec(self):
        return [math.log(self.s), self.cx, self.cy, self.r]

    def rates(self):
        return [self.ds, self.dcx, self.dcy, self.dr]

    @staticmethod
    def from_vec(v, d=(0.0, 0.0, 0.0, 0.0)):
        return State(math.exp(v[0]), v[1], v[2], v[3], d[0], d[1], d[2], d[3])

    def at(self, dt):
        """Linear extrapolation by dt frames along the rates (ln s, c, r are all linear in card space)."""
        return State(self.s * math.exp(self.ds * dt), self.cx + self.dcx * dt, self.cy + self.dcy * dt,
                     self.r + self.dr * dt, self.ds, self.dcx, self.dcy, self.dr)

    def with_(self, **kw):
        return replace(self, **kw)

    def as_dict(self):
        return dict(s=self.s, cx=self.cx, cy=self.cy, r=self.r, ds=self.ds, dcx=self.dcx, dcy=self.dcy, dr=self.dr)


# ---- card <-> local camera position ----------------------------------------------------------------------------------
def px_to_local(px, py):
    """Card pixel -> card-local metres (x right, y up, origin at the card centre)."""
    return ((px - W_PX / 2) / 1000.0, (H_PX / 2 - py) / 1000.0)


def local_to_px(x, y):
    return (x * 1000.0 + W_PX / 2, H_PX / 2 - y * 1000.0)


def local_pose(st):
    """Camera pose in card-local space for a State: (location xyz, roll radians about local Z).
    Camera rotation = Rz(roll); + roll of the camera turns the picture clockwise on screen."""
    x, y = px_to_local(st.cx, st.cy)
    return (x, y, FILL_DIST / st.s), math.radians(st.r)


def state_from_local(loc, roll_rad):
    cx, cy = local_to_px(loc[0], loc[1])
    return State(FILL_DIST / loc[2], cx, cy, math.degrees(roll_rad))


# ---- coverage: the frame must stay inside the card ----------------------------------------------------------------------
def frame_corners_px(st, margin=0.0):
    """Card pixels seen at the four frame corners for a State."""
    hw, hh = (W_PX / 2) / st.s * (1 + margin), (H_PX / 2) / st.s * (1 + margin)
    a = math.radians(st.r)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for ux, uy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        # picture turned clockwise by r on screen = the frame turned counter-clockwise over the card
        out.append((st.cx + ux * ca + uy * sa, st.cy - ux * sa + uy * ca))
    return out


def covers(st, margin=0.0):
    return all(0 <= x <= W_PX and 0 <= y <= H_PX for x, y in frame_corners_px(st, margin))


def min_scale(cx, cy, r, margin=0.0):
    """Smallest s at which the frame (rolled by r, centred on card pixel cx, cy) stays inside the card."""
    a = math.radians(r)
    ca, sa = abs(math.cos(a)), abs(math.sin(a))
    hx = (W_PX / 2 * ca + H_PX / 2 * sa) * (1 + margin)  # half extents of the rotated frame in card px at s = 1
    hy = (W_PX / 2 * sa + H_PX / 2 * ca) * (1 + margin)
    room_x = min(cx, W_PX - cx)
    room_y = min(cy, H_PX - cy)
    if room_x <= 0 or room_y <= 0:
        return 1e9
    return max(hx / room_x, hy / room_y, 1e-6)


def clamp_center(s, cx, cy, r, margin=0.0):
    """Move the frame centre towards the card centre just enough that the frame stays on the card at scale s."""
    a = math.radians(r)
    ca, sa = abs(math.cos(a)), abs(math.sin(a))
    hx = (W_PX / 2 * ca + H_PX / 2 * sa) * (1 + margin) / s
    hy = (W_PX / 2 * sa + H_PX / 2 * ca) * (1 + margin) / s
    cx = min(max(cx, hx), W_PX - hx) if hx < W_PX / 2 else W_PX / 2
    cy = min(max(cy, hy), H_PX - hy) if hy < H_PX / 2 else H_PX / 2
    return cx, cy


def cover(st, w=0.012):
    """Keep the frame on the card: a soft floor on the scale for the current roll and centre (softplus, so the curve
    stays smooth), then pull the centre in just enough. Returns st (modified)."""
    smin = max(min_scale(960.0, 540.0, st.r, 0.006), 1.0)
    L, Lm = math.log(st.s), math.log(smin)
    x = (Lm - L) / w
    L += w * (x + math.log1p(math.exp(-x))) if x > 0 else w * math.log1p(math.exp(x))
    st.s = math.exp(L)
    st.cx, st.cy = clamp_center(st.s, st.cx, st.cy, st.r, 0.004)
    return st


# ---- eases ---------------------------------------------------------------------------------------------------------------
def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_in_expo(u):
    u = clamp01(u)
    return 0.0 if u == 0 else 2 ** (10 * u - 10)


def ease_out_expo(u):
    u = clamp01(u)
    return 1.0 if u == 1 else 1 - 2 ** (-10 * u)


def ease_in_out_cubic(u):
    u = clamp01(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def smoothstep(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def smootherstep(u):
    u = clamp01(u)
    return u ** 3 * (u * (6 * u - 15) + 10)


def expo_in(u, k):
    """Normalised exponential ease-in: E(0) = 0, E'(0) = 0, E(1) = 1; the end slope E'(1) grows with k (about k for big k)."""
    u = clamp01(u)
    if k < 1e-4:
        return u * u
    return (math.exp(k * u) - 1 - k * u) / (math.exp(k) - 1 - k)


def expo_in_d(u, k):
    """dE/du of expo_in."""
    u = clamp01(u)
    if k < 1e-4:
        return 2 * u
    return k * (math.exp(k * u) - 1) / (math.exp(k) - 1 - k)


def expo_k_for_slope(slope, lo=0.05, hi=60.0):
    """The k for which expo_in has end slope E'(1) = slope (slope >= 2; clamps)."""
    if slope <= 2.0001:
        return lo
    for _ in range(60):
        mid = (lo + hi) / 2
        if expo_in_d(1.0, mid) < slope:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hermite(p0, m0, p1, m1, u):
    """Cubic Hermite on [0, 1] with end tangents m0, m1 (already scaled by the interval length)."""
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m1)


def hermite_d(p0, m0, p1, m1, u):
    """d/du of hermite()."""
    u2 = u * u
    return ((6 * u2 - 6 * u) * p0 + (3 * u2 - 4 * u + 1) * m0 + (-6 * u2 + 6 * u) * p1 + (3 * u2 - 2 * u) * m1)


def hermite_state(A, B, t0, t1, t):
    """C1 curve in (ln s, cx, cy, r) from State A at t0 to State B at t1, matching both states' rates. Returns a State with rates."""
    T = float(t1 - t0)
    u = (t - t0) / T
    va, vb, da, db = A.vec(), B.vec(), A.rates(), B.rates()
    v = [hermite(va[i], da[i] * T, vb[i], db[i] * T, u) for i in range(4)]
    d = [hermite_d(va[i], da[i] * T, vb[i], db[i] * T, u) / T for i in range(4)]
    return State.from_vec(v, d)


def lerp(a, b, u):
    return a + (b - a) * u


def blend_state(A, B, w, dw=0.0):
    """Mix two States in (ln s, c, r) with weight w (0 = A, 1 = B). dw = dw/dt for the rates."""
    va, vb, da, db = A.vec(), B.vec(), A.rates(), B.rates()
    v = [lerp(va[i], vb[i], w) for i in range(4)]
    d = [lerp(da[i], db[i], w) + (vb[i] - va[i]) * dw for i in range(4)]
    return State.from_vec(v, d)


# ---- hits (added on top of the camera path) ---------------------------------------------------------------------------------
def punch_curve(dt, amount=0.07, attack=2.0, settle=6.0):
    """Extra ln-scale of a punch dt frames after its frame: +amount in `attack` frames, back to 0 over `settle` (C1)."""
    if dt <= 0 or dt >= attack + settle:
        return 0.0
    a = math.log(1 + amount)
    if dt < attack:
        return a * smoothstep(dt / attack)
    return a * (1 - smoothstep((dt - attack) / settle))


def shake_offsets(dt, seed=1, frames=8.0, amp_deg=1.1, amp_m=0.012):
    """Decaying 3D shake dt frames after its frame -> (pitch, yaw, roll) degrees and (x, y, z) metres in camera space.
    Smooth (sum of sines with incommensurate rates) so motion blur shows real smears, not jitter noise."""
    if dt <= 0 or dt >= frames + 4:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    env = math.exp(-3.2 * dt / frames) * smoothstep(dt / 0.75)  # fast rise (0.75 f) then exponential decay
    if dt > frames:
        env *= 1 - smoothstep((dt - frames) / 4.0)

    def osc(i, f):
        ph = (seed * 12.9898 + i * 78.233) % (2 * math.pi)
        return math.sin(2 * math.pi * f * dt / 30.0 * 4.0 + ph)
    rot = (amp_deg * env * osc(1, 2.3), amp_deg * env * osc(2, 2.9), 0.6 * amp_deg * env * osc(3, 1.7))
    loc = (amp_m * env * osc(4, 2.1), amp_m * env * osc(5, 2.6), 0.5 * amp_m * env * osc(6, 1.9))
    return rot, loc


# ---- depth of field (rack defocus) ---------------------------------------------------------------------------------------
FSTOP_SHARP = 128.0  # the camera's f-stop outside rack pulls: a pinhole, no visible defocus anywhere


def focus_for_blur(d, blur_px, fstop=1.4, lens=LENS_MM, w_px=W_PX):
    """Focus distance (m) in front of a card at distance d (m) that blurs the card by a circle of blur_px (at w_px wide).
    Thin lens: c = (f / N) * f * (d - fd) / (d * (fd - f))  ->  fd = d (f^2/N + c f) / (c d + f^2/N)  (mm)."""
    c = blur_px * SENSOR_MM / w_px
    f = lens
    dm = d * 1000.0
    k = f * f / fstop
    return dm * (k + c * f) / (c * dm + k) / 1000.0


# ---- screen projection (gate) -----------------------------------------------------------------------------------------------
def pixel_ray(u, v, w=W_PX, h=H_PX):
    """Camera-space ray direction for screen pixel (u, v) (sensor fit horizontal, 35 mm on 36 mm)."""
    sx = SENSOR_MM
    sy = SENSOR_MM * h / w
    return ((u / w - 0.5) * sx / LENS_MM, (0.5 - v / h) * sy / LENS_MM, -1.0)


def project_cam(p_cam, w=W_PX, h=H_PX):
    """Camera-space point -> screen pixel (None behind the camera)."""
    x, y, z = p_cam
    if z >= -1e-6:
        return None
    sx = SENSOR_MM
    sy = SENSOR_MM * h / w
    u = (x / -z * LENS_MM / sx + 0.5) * w
    v = (0.5 - y / -z * LENS_MM / sy) * h
    return (u, v)
