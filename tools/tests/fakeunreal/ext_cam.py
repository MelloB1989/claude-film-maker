"""WP7's fakes: cine cameras with the engine's defaults and clamps, skeletons with bones, camera rigs.

- CineCameraComponent starts as the engine's default camera (filmback "16:9 Digital Film", lens "Universal Zoom"
  4-1000 mm f/1.2-22, focal 35, f/2.8, manual focus) and clamps current_focal_length / current_aperture to its
  lens settings as CineCameraComponent.cpp:528-529 does.
- Skeletons: core's bone table (`fake.pose(actor, {bone: [x, y, z]})`).
- CameraRig_Rail (a spline you can set points on) and CameraRig_Crane.
- The camera's float UPROPERTYs (filmback, lens limits, focus distance, focal length, aperture) are 32-bit floats in
  the engine (CineCameraSettings.h, CineCameraComponent.h), so a value read back is the float32 nearest the one
  written, never the Python double: compare with a tolerance (day 1: exact compares reported every re-run changed).
- A camera's actor rotation reads back from its transform (USceneComponent::GetComponentRotation, from the quat),
  so yaw -180 reads 180, and so on: compare rotations by direction, not by the numbers written.
"""
import math
import struct

from . import core


def f32(v) -> float:
    """The float32 nearest `v`, as a C++ float UPROPERTY stores it."""
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


class _F32(core.Object):
    """A struct (or component) whose FLOATS properties are C++ floats."""
    FLOATS: tuple = ()

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **{k: f32(v) if k in self.FLOATS else v for k, v in props.items()})

    def set_editor_property(self, name, value, notify_mode=None):
        super().set_editor_property(name, f32(value) if name in self.FLOATS else value, notify_mode)


class CameraFilmbackSettings(_F32):
    FLOATS = ("sensor_width", "sensor_height", "sensor_horizontal_offset", "sensor_vertical_offset")


class CameraLensSettings(_F32):
    FLOATS = ("min_focal_length", "max_focal_length", "min_f_stop", "max_f_stop", "minimum_focus_distance",
              "squeeze_factor")


class CameraFocusSettings(_F32):
    FLOATS = ("manual_focus_distance", "focus_smoothing_interp_speed", "focus_offset")


class CameraTrackingFocusSettings(core.Object):
    pass


class CineCameraComponent(core.CineCameraComponent):
    FLOATS = ("current_focal_length", "current_aperture")

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        p = self._props
        p.setdefault("filmback", CameraFilmbackSettings(sensor_width=23.76, sensor_height=13.365))
        p.setdefault("lens_settings", CameraLensSettings(min_focal_length=4.0, max_focal_length=1000.0, min_f_stop=1.2,
                                                         max_f_stop=22.0, diaphragm_blade_count=7))
        p.setdefault("focus_settings", CameraFocusSettings(
            focus_method="MANUAL", manual_focus_distance=100000.0, smooth_focus_changes=False,
            focus_smoothing_interp_speed=8.0,
            tracking_focus_settings=CameraTrackingFocusSettings(actor_to_track=None,
                                                                relative_offset=core.Vector(0, 0, 0))))
        p.setdefault("current_focal_length", 35.0)
        p.setdefault("current_aperture", f32(2.8))

    def set_editor_property(self, name, value, notify_mode=None):
        ls = self._props.get("lens_settings")
        if name == "current_focal_length" and ls is not None:
            value = min(max(float(value), ls._props["min_focal_length"]), ls._props["max_focal_length"])
        if name == "current_aperture" and ls is not None:
            value = min(max(float(value), ls._props["min_f_stop"]), ls._props["max_f_stop"])
        super().set_editor_property(name, f32(value) if name in self.FLOATS else value, notify_mode)

    def get_horizontal_field_of_view(self):
        """CineCameraComponent.cpp:286-301 with no crop, squeeze 1, no overscan."""
        import math
        w = self._props["filmback"]._props["sensor_width"]
        return math.degrees(2 * math.atan(w / (2 * self._props["current_focal_length"])))

    def get_vertical_field_of_view(self):
        import math
        h = self._props["filmback"]._props["sensor_height"]
        return math.degrees(2 * math.atan(h / (2 * self._props["current_focal_length"])))

    def set_custom_near_clipping_plane(self, v):
        self._props["custom_near_clipping_plane"] = float(v)


class CineCameraActor(core.CameraActor):
    COMPONENTS = (("scene_component", core.SceneComponent), ("camera_component", CineCameraComponent))

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        # the engine's subobject names (CameraActor.cpp:19,25; CineCameraActor.cpp:16): Sequencer binds by them
        object.__setattr__(self._props["scene_component"], "_name", "SceneComponent")
        object.__setattr__(self._props["camera_component"], "_name", "CameraComponent")

    def get_cine_camera_component(self):
        return self._props["camera_component"]

    def get_actor_rotation(self):
        """The rotation as the engine reads it back: from the transform's axes (FMatrix::Rotator), not as written."""
        x, y, z = self._xf.rotation._axes()
        pitch = math.degrees(math.atan2(x.z, math.hypot(x.x, x.y)))
        yaw = math.degrees(math.atan2(x.y, x.x))
        # roll: the up axis against the one of (pitch, yaw, 0)
        sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
        sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
        y0 = core.Vector(-sy, cy, 0.0)
        z0 = core.Vector(-sp * cy, -sp * sy, cp)
        roll = math.degrees(math.atan2(z.x * y0.x + z.y * y0.y + z.z * y0.z, z.x * z0.x + z.y * z0.y + z.z * z0.z))
        return core.Rotator(roll=roll, pitch=pitch, yaw=yaw)


class SplineComponent(core.SceneComponent):
    def set_spline_points(self, points, coordinate_space=None, update_spline=True):
        self._props["points"] = [core.Vector(p.x, p.y, p.z) for p in points]


class CameraRig_Rail(core.Actor):
    COMPONENTS = (("transform_component", core.SceneComponent), ("rail_spline_component", SplineComponent))

    def get_rail_spline_component(self):
        return self._props["rail_spline_component"]


class CameraRig_Crane(core.Actor):
    COMPONENTS = (("transform_component", core.SceneComponent),)


def install(fake):
    for cls in (CameraFilmbackSettings, CameraLensSettings, CameraFocusSettings, CameraTrackingFocusSettings,
                CineCameraComponent, CineCameraActor, SplineComponent, CameraRig_Rail, CameraRig_Crane):
        fake._classes[cls.__name__] = cls
        setattr(fake, cls.__name__, cls)
    # bones on skeletal meshes: core's table, set with fake.pose(actor, {bone: [x, y, z]}) (shared with WP10)
