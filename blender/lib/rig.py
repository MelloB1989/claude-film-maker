"""The engine's camera rig (app/src/engine/stage.ts CameraRig) in Python, so a Blender shot and the scene that composites
its plate see through one camera: keys with a time, a position, a target, a vertical fov and a roll; between keys the
position and the target follow a centripetal Catmull-Rom through all of them, the fov and the roll interpolate, each
segment timed by the ease of the key it heads to (default inOutCubic); before the first key and after the last it holds
them. Poses are in the engine's coordinates (metres, y up, the camera looking down -z); `ENGINE_TO_BLENDER` turns them
into Blender's (z up), a proper rotation, so handedness and cross products carry over.

The lens is the engine's DoF camera: a 36 mm gate shooting 16:9, the picture 20.25 mm tall (dof.ts DOF_SENSOR_H), so a
vertical fov is a focal length (`lens_mm`). B03 (b03_reform.py) has its own copy of this port; this is the shared one.

numpy only (tested under the tools project); `place_camera` sets a Blender camera from a pose.
"""
from __future__ import annotations

import math

import numpy as np

ENGINE_TO_BLENDER = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
SENSOR_H_MM = 20.25  # the engine's DoF camera: a 36 mm gate shooting 16:9
SENSOR_W_MM = 36.0


def to_blender(v) -> np.ndarray:
    """Engine coordinates (y up) to Blender's (z up): (x, y, z) -> (x, -z, y). Works on (3,) and (n, 3)."""
    v = np.asarray(v, float)
    return v @ ENGINE_TO_BLENDER.T


def lens_mm(fov_deg: float) -> float:
    """The focal length (mm) that gives a vertical fov on the engine's 20.25 mm-tall gate."""
    return SENSOR_H_MM / 2 / math.tan(math.radians(fov_deg) / 2)


def _in_out_cubic(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


EASE = {  # util.ts ease, the ones a camera key uses (each one the engine has: test_rig.py)
    "linear": lambda x: x,
    "inQuad": lambda x: x * x,
    "outQuad": lambda x: 1 - (1 - x) ** 2,
    "inOutQuad": lambda x: 2 * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 2 / 2,
    "inCubic": lambda x: x ** 3,
    "outCubic": lambda x: 1 - (1 - x) ** 3,
    "inOutCubic": _in_out_cubic,
    "outQuart": lambda x: 1 - (1 - x) ** 4,
    "inOutQuart": lambda x: 8 * x ** 4 if x < 0.5 else 1 - (-2 * x + 2) ** 4 / 2,
    "outExpo": lambda x: 1.0 if x >= 1 else 1 - 2 ** (-10 * x),
}


def catmull_rom(p0, p1, p2, p3, u: float) -> np.ndarray:
    """stage.ts catmullRom: centripetal (Barry-Goldman) between p1 and p2 at u in [0, 1]; a missing or coincident
    neighbour is mirrored from the other side."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    d12 = float(np.linalg.norm(p1 - p2))
    if d12 < 1e-9:
        return p1.copy()
    if p0 is None or np.linalg.norm(np.asarray(p0, float) - p1) < 1e-9:
        p0 = 2 * p1 - p2
    if p3 is None or np.linalg.norm(p2 - np.asarray(p3, float)) < 1e-9:
        p3 = 2 * p2 - p1
    p0, p3 = np.asarray(p0, float), np.asarray(p3, float)
    t1 = math.sqrt(np.linalg.norm(p0 - p1))
    t2 = t1 + math.sqrt(d12)
    t3 = t2 + math.sqrt(np.linalg.norm(p2 - p3))
    t = t1 + u * (t2 - t1)
    a1 = ((t1 - t) * p0 + t * p1) / t1
    a2 = ((t2 - t) * p1 + (t - t1) * p2) / (t2 - t1)
    a3 = ((t3 - t) * p2 + (t - t2) * p3) / (t3 - t2)
    b1 = ((t2 - t) * a1 + t * a2) / t2
    b2 = ((t3 - t) * a2 + (t - t1) * a3) / (t3 - t1)
    return ((t2 - t) * b1 + (t - t1) * b2) / (t2 - t1)


class Pose:
    """A camera in engine coordinates: position, target, vertical fov and roll (degrees)."""

    def __init__(self, pos, target, fov: float, roll: float = 0.0):
        self.pos, self.target = np.asarray(pos, float), np.asarray(target, float)
        self.fov, self.roll = float(fov), float(roll)

    def basis(self) -> np.ndarray:
        """The camera's axes (columns x, y, z; it looks down -z) as three's lookAt (up y) then rotateZ(roll) set them."""
        z = self.pos - self.target
        z = z / np.linalg.norm(z) if np.linalg.norm(z) > 0 else np.array([0.0, 0.0, 1.0])
        up = np.array([0.0, 1.0, 0.0])
        x = np.cross(up, z)
        if np.linalg.norm(x) < 1e-12:  # looking straight up or down: three nudges z
            z = z + np.array([1e-4, 0.0, 0.0])
            z /= np.linalg.norm(z)
            x = np.cross(up, z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        r = math.radians(self.roll)
        c, s = math.cos(r), math.sin(r)
        return np.column_stack([x, y, z]) @ np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])

    def depth(self, p) -> float:
        """A point's depth along the view axis (stage.ts depthOf: what a focus distance is measured in)."""
        return float(-(self.basis()[:, 2] @ (np.asarray(p, float) - self.pos)))

    def project(self, p, aspect: float = 16 / 9) -> tuple[float, float]:
        """A point's place on the film's logical 1920x1080 frame (px from the top left)."""
        v = self.basis().T @ (np.asarray(p, float) - self.pos)
        ty = math.tan(math.radians(self.fov) / 2)
        x, y = v[0] / (-v[2] * ty * aspect), v[1] / (-v[2] * ty)
        return 960 * (1 + x), 540 * (1 - y)

    def project_many(self, P, aspect: float = 16 / 9) -> np.ndarray:
        """project() for points (n, 3): (n, 2) px, and NaN where a point is behind the camera."""
        v = (np.asarray(P, float) - self.pos) @ self.basis()
        ty = math.tan(math.radians(self.fov) / 2)
        with np.errstate(divide="ignore", invalid="ignore"):
            x = v[:, 0] / (-v[:, 2] * ty * aspect)
            y = v[:, 1] / (-v[:, 2] * ty)
        out = np.column_stack([960 * (1 + x), 540 * (1 - y)])
        out[v[:, 2] >= 0] = np.nan
        return out

    def blender_matrix(self) -> list[list[float]]:
        """The camera's world matrix in Blender (rows), its axes the engine camera's turned into Blender's frame."""
        rot = ENGINE_TO_BLENDER @ self.basis()
        p = to_blender(self.pos)
        return [[*rot[0], p[0]], [*rot[1], p[1]], [*rot[2], p[2]], [0.0, 0.0, 0.0, 1.0]]


class Rig:
    """stage.ts CameraRig. keys: [{t, pos, target, fov?, roll?, ease?}] (engine coordinates; the first key needs a fov,
    a key without one carries the previous key's, as a roll does; ease is a name in EASE, default inOutCubic)."""

    def __init__(self, keys: list[dict]):
        if not keys:
            raise ValueError("a Rig needs at least one key")
        ks = sorted(keys, key=lambda k: k["t"])
        if ks[0].get("fov") is None:
            raise ValueError("the first camera key needs a fov")
        fov, roll = None, 0.0
        self.keys = []
        for k in ks:
            fov = k.get("fov", fov)
            roll = k.get("roll", roll)
            name = k.get("ease", "inOutCubic")
            if name not in EASE:
                raise KeyError(f"no ease {name!r} (have {', '.join(EASE)})")
            self.keys.append({"t": float(k["t"]), "pos": np.asarray(k["pos"], float), "target": np.asarray(k["target"], float),
                              "fov": float(fov), "roll": float(roll), "ease": EASE[name]})

    def at(self, t: float) -> Pose:
        ks, n = self.keys, len(self.keys)
        i = 0
        while i < n and ks[i]["t"] <= t:
            i += 1
        if i == 0 or i == n or ks[i - 1]["t"] == t:
            k = ks[max(0, i - 1)]
            return Pose(k["pos"].copy(), k["target"].copy(), k["fov"], k["roll"])
        a, b = ks[i - 1], ks[i]
        e = b["ease"]((t - a["t"]) / (b["t"] - a["t"]))
        nb = lambda j: ks[j]["pos"] if 0 <= j < n else None  # noqa: E731
        nt = lambda j: ks[j]["target"] if 0 <= j < n else None  # noqa: E731
        return Pose(catmull_rom(nb(i - 2), a["pos"], b["pos"], nb(i + 1), e),
                    catmull_rom(nt(i - 2), a["target"], b["target"], nt(i + 1), e),
                    a["fov"] + (b["fov"] - a["fov"]) * e, a["roll"] + (b["roll"] - a["roll"]) * e)


def place_camera(cam, pose: Pose, focus: float | None = None) -> None:
    """Set a Blender camera object to an engine pose: its world matrix, its lens for the pose's fov on the engine's gate
    (the camera's sensor must be the 36 x 20.25 mm one, fit vertically), and its focus distance (metres) if given."""
    from mathutils import Matrix

    cam.matrix_world = Matrix(pose.blender_matrix())
    cam.data.lens = lens_mm(pose.fov)
    if focus is not None:
        cam.data.dof.focus_distance = float(focus)


def engine_camera(name: str = "camera", fstop: float = 4.0, collection=None):
    """A Blender camera on the engine's gate (36 x 20.25 mm, fit vertically) with depth of field at `fstop`."""
    import bpy

    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = SENSOR_H_MM
    cam.data.sensor_width = SENSOR_W_MM
    cam.data.clip_start, cam.data.clip_end = 0.005, 60.0
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = fstop
    cam.data.dof.aperture_blades = 0
    (collection or bpy.context.scene.collection).objects.link(cam)
    return cam
