"""WP10's fakes: a scene capture that "renders" actors' bounds as flat boxes (so a still, a framing box and a depth
layer agree), render targets, bones on skeletal components, component bounds, line traces against actor bounds, and
a cine camera's field of view from its lens.

The capture is a z-buffered rasteriser of each visible mesh actor's bounds box (or of each shown component's
`fake_depth` callable for depth tests), through fmbridge.qa.framing's camera model: crude, but positions, sizes and
occlusion are right, so ops can be tested end to end without an engine.

Test knobs (set on objects):
    actor._props["fake_color"] = (r, g, b)          the box's colour in final captures (default by label)
    comp._props["fake_bones"] = {name: [x, y, z]}    world positions; get_bone_index / get_socket_location read them
    comp._props["fake_bounds"] = ([o], [e])          SystemLibrary.get_component_bounds
    comp._props["fake_depth"] = f(u, v) -> cm|None   a component's depth layer (for qa.penetration)
"""
from __future__ import annotations

import math
import os
import struct
import zlib


class FakeRT:
    """A render target: size_x/size_y and the last capture's pixels (list of (r, g, b, a) floats)."""

    def __init__(self, w: int, h: int, fmt):
        self.w, self.h, self.fmt = int(w), int(h), fmt
        self.pixels = [(0.0, 0.0, 0.0, 1.0)] * (self.w * self.h)

    def get_editor_property(self, name):
        return {"size_x": self.w, "size_y": self.h, "render_target_format": self.fmt}[name]

    size_x = property(lambda self: self.w)
    size_y = property(lambda self: self.h)


class _Sample:
    __slots__ = ("r", "g", "b", "a")

    def __init__(self, r, g, b, a):
        self.r, self.g, self.b, self.a = r, g, b, a


def install(fake):
    core = __import__(f"{__package__}.core", fromlist=["core"])
    Vector = fake.Vector

    # --- actors and components -------------------------------------------------------------------------------
    def is_hidden_ed(self):
        return bool(self._props.get("temporarily_hidden", False) or self._props.get("hidden_ed", False))

    core.Actor.is_hidden_ed = is_hidden_ed

    def get_bone_index(self, name):
        bones = self._props.get("fake_bones") or {}
        return list(bones).index(str(name)) if str(name) in bones else -1

    def get_socket_location(self, name):
        bones = self._props.get("fake_bones") or {}
        if str(name) in bones:
            return Vector(*bones[str(name)])
        return self.get_world_location()

    def get_num_bones(self):
        return len(self._props.get("fake_bones") or {})

    def get_skeletal_mesh_asset(self):
        return self._props.get("skeletal_mesh_asset")

    def get_materials(self):
        return list(self._props.get("override_materials", []))

    core.SkeletalMeshComponent.get_skeletal_mesh_asset = get_skeletal_mesh_asset
    core.MeshComponent.get_materials = get_materials

    def hfov(self):
        fb = self._props.get("filmback")
        sw = fb.get_editor_property("sensor_width") if fb is not None else 36.0
        f = self._props.get("current_focal_length", 35.0)
        return math.degrees(2 * math.atan(sw / (2 * f)))

    core.CineCameraComponent.get_horizontal_field_of_view = hfov
    fake.CameraFilmbackSettings = type("CameraFilmbackSettings", (core.Object,), {"__module__": "unreal"})

    # --- SystemLibrary: component bounds, line traces --------------------------------------------------------
    sl = fake.SystemLibrary

    def get_component_bounds(component):
        b = component._props.get("fake_bounds")
        if b:
            o, e = b
        else:
            owner = component.get_owner()
            o, e = owner.get_actor_bounds(False) if owner else (Vector(), Vector(50, 50, 50))
            o, e = list(o), list(e)
        o, e = Vector(*o), Vector(*e)
        return o, e, e.length()

    class FakeHit:
        def __init__(self, distance, location, actor):
            self.distance, self.location, self.actor = distance, location, actor

        def to_tuple(self):
            return (True, self.distance <= 1e-9, 0.0, self.distance, self.location, self.location, Vector(0, 0, 1), Vector(0, 0, 1),
                    None, self.actor, None, "", "", 0, 0, 0, None, None)

    def line_trace_single(world, start, end, trace_channel, trace_complex, actors_to_ignore, draw_debug_type,
                          ignore_self=True, *a, **k):
        """The nearest actor bounds box the segment hits (axis-aligned boxes, as the fake has no meshes)."""
        ign = {id(x) for x in actors_to_ignore or []}
        best = None
        s, e = Vector(*start), Vector(*end)
        d = e - s
        length = d.length()
        for act in fake.world.actors():
            if id(act) in ign or act.get_actor_label() == "FMQA_Capture" or not act.get_components_by_class(core.PrimitiveComponent):
                continue
            o, ext = act.get_actor_bounds(False)
            t = _ray_box(s, d, o, ext)
            if t is not None and (best is None or t < best[0]):
                best = (t, act)
        if best is None:
            return None
        t, act = best
        return FakeHit(t * length, s + d * t, act)

    sl.get_component_bounds = staticmethod(get_component_bounds)
    sl.line_trace_single = staticmethod(line_trace_single)

    # --- render targets and scene captures -------------------------------------------------------------------
    class RenderingLibrary(core.Object):
        @staticmethod
        def create_render_target2d(world, width=256, height=256, format=None, clear_color=None, auto_mips=False,  # noqa: A002
                                   uav=False):
            fake.calls.append(("RenderingLibrary.create_render_target2d", (width, height, format), {}))
            return FakeRT(width, height, format)

        @staticmethod
        def export_render_target(world, rt, file_path, file_name):
            fake.calls.append(("RenderingLibrary.export_render_target", (file_path, file_name), {}))
            _write_png(os.path.join(file_path, file_name), rt)

        @staticmethod
        def read_render_target_raw(world, rt, normalize=True):
            return [_Sample(*p) for p in rt.pixels]

    fake.RenderingLibrary = RenderingLibrary
    fake._classes["RenderingLibrary"] = RenderingLibrary

    class SceneCaptureComponent2D(core.SceneComponent):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name, outer, **props)
            self._props.setdefault("show_only_actors", [])
            self._props.setdefault("hidden_actors", [])
            object.__setattr__(self, "_show_only", [])
            object.__setattr__(self, "captures", 0)

        def clear_show_only_components(self):
            self._show_only.clear()

        def show_only_component(self, c):
            self._show_only.append(c)

        def show_only_actor_components(self, actor, include_children=False):
            self._show_only.extend(actor.get_components_by_class(core.PrimitiveComponent))

        def capture_scene(self):
            object.__setattr__(self, "captures", self.captures + 1)
            fake.calls.append(("SceneCaptureComponent2D.capture_scene", (), {}))
            _render(fake, core, self)

    class SceneCapture2D(core.Actor):
        COMPONENTS = (("capture_component2d", SceneCaptureComponent2D),)

    fake.SceneCaptureComponent2D = SceneCaptureComponent2D
    fake.SceneCapture2D = SceneCapture2D
    fake._classes["SceneCaptureComponent2D"] = SceneCaptureComponent2D
    fake._classes["SceneCapture2D"] = SceneCapture2D


def _ray_box(s, d, o, e):
    """Entry t in [0, 1] of the segment s + t d into the box o +- e, or None."""
    t0, t1 = 0.0, 1.0
    for k in "xyz":
        sk, dk = getattr(s, k), getattr(d, k)
        lo, hi = getattr(o, k) - getattr(e, k), getattr(o, k) + getattr(e, k)
        if abs(dk) < 1e-12:
            if sk < lo or sk > hi:
                return None
            continue
        a, b = (lo - sk) / dk, (hi - sk) / dk
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return None
    return t0


def _color_for(label: str) -> tuple:
    h = sum(ord(c) * (i + 1) for i, c in enumerate(label)) % 360
    r, g, b = [max(0.0, min(1.0, abs(((h / 60 + k) % 6) - 3) - 1)) for k in (0, 4, 2)]
    return 60 + 180 * r, 60 + 180 * g, 60 + 180 * b


def _render(fake, core, comp):
    """Rasterise the scene into comp's texture target: each visible mesh actor's bounds box (8 corners -> screen
    box, depth = its nearest corner), z-buffered; components with a `fake_depth` function draw that instead."""
    from fmbridge.qa import framing
    rt = comp._props.get("texture_target")
    if rt is None:
        return
    owner = comp.get_owner()
    rot = owner.get_actor_rotation()
    cam = framing.Camera(list(owner.get_actor_location()), {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
                         fov=float(comp._props.get("fov_angle", 90.0)), aspect=rt.w / rt.h)
    source = str(getattr(comp._props.get("capture_source"), "name", comp._props.get("capture_source")))
    depth_mode = "DEPTH" in source
    mode = str(getattr(comp._props.get("primitive_render_mode"), "name", comp._props.get("primitive_render_mode")))
    show_only = comp._show_only if "SHOW_ONLY" in mode else None
    hidden = {id(a) for a in comp._props.get("hidden_actors") or []}
    far = 3.0e38
    zb = [far] * (rt.w * rt.h)
    col = [(40.0, 40.0, 48.0)] * (rt.w * rt.h) if not depth_mode else None
    if col is not None:  # a floor-to-sky gradient so a frame is never flat
        col = [(30.0 + 50.0 * (y / rt.h), 30.0 + 40.0 * (y / rt.h), 50.0 + 30.0 * (1 - y / rt.h))
               for y in range(rt.h) for _ in range(rt.w)]
    for act in fake.world.actors():
        if act is owner or id(act) in hidden or act.is_hidden_ed():
            continue
        prims = act.get_components_by_class(core.PrimitiveComponent)
        if not prims:
            continue
        if show_only is not None:
            prims = [p for p in prims if any(p is s for s in show_only)]
            if not prims:
                continue
        fns = [p._props.get("fake_depth") for p in prims if p._props.get("fake_depth")]
        if fns:
            for i in range(rt.w * rt.h):
                y, x = divmod(i, rt.w)
                for fn in fns:
                    d = fn((x + 0.5) / rt.w, (y + 0.5) / rt.h)
                    if d is not None and d < zb[i]:
                        zb[i] = d
                        if col is not None:
                            col[i] = act._props.get("fake_color") or _color_for(act.get_actor_label())
            continue
        o, e = act.get_actor_bounds(False)
        sb = framing.screen_box(cam, framing.bounds_corners(list(o), list(e)))
        if not sb["box"] or sb["behind"]:
            continue
        x0, y0, x1, y1 = sb["box"]
        dist = min(cam.project(p)[2] for p in framing.bounds_corners(list(o), list(e)))
        c = act._props.get("fake_color") or _color_for(act.get_actor_label())
        for y in range(int(y0 * rt.h), min(rt.h, int(math.ceil(y1 * rt.h)))):
            for x in range(int(x0 * rt.w), min(rt.w, int(math.ceil(x1 * rt.w)))):
                i = y * rt.w + x
                if dist < zb[i]:
                    zb[i] = dist
                    if col is not None:
                        col[i] = c
    if depth_mode:
        rt.pixels = [(z, z, z, 1.0) for z in zb]
    else:
        rt.pixels = [(float(round(r)), float(round(g)), float(round(b)), 255.0) for r, g, b in col]


def _write_png(path: str, rt: FakeRT):
    raw = bytearray()
    for y in range(rt.h):
        raw.append(0)
        for r, g, b, _ in rt.pixels[y * rt.w:(y + 1) * rt.w]:
            raw += bytes((int(r) & 255, int(g) & 255, int(b) & 255))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", rt.w, rt.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
