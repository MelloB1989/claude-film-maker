"""WP7's fakes: cine cameras with the engine's defaults and clamps, skeletons with bones, camera rigs.

- CineCameraComponent starts as the engine's default camera (filmback "16:9 Digital Film", lens "Universal Zoom"
  4-1000 mm f/1.2-22, focal 35, f/2.8, manual focus) and clamps current_focal_length / current_aperture to its
  lens settings as CineCameraComponent.cpp:528-529 does.
- SkeletalMeshComponent answers does_socket_exist / get_socket_location from a bone table set with
  `fake.pose(actor, {bone: [x, y, z]})` (world cm); without one it answers as core does.
- CameraRig_Rail (a spline you can set points on) and CameraRig_Crane.
"""
from . import core


class CameraFilmbackSettings(core.Object):
    pass


class CameraLensSettings(core.Object):
    pass


class CameraFocusSettings(core.Object):
    pass


class CameraTrackingFocusSettings(core.Object):
    pass


class CineCameraComponent(core.CineCameraComponent):
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
        p.setdefault("current_aperture", 2.8)

    def set_editor_property(self, name, value, notify_mode=None):
        ls = self._props.get("lens_settings")
        if name == "current_focal_length" and ls is not None:
            value = min(max(float(value), ls._props["min_focal_length"]), ls._props["max_focal_length"])
        if name == "current_aperture" and ls is not None:
            value = min(max(float(value), ls._props["min_f_stop"]), ls._props["max_f_stop"])
        super().set_editor_property(name, value, notify_mode)

    def set_custom_near_clipping_plane(self, v):
        self._props["custom_near_clipping_plane"] = float(v)


class CineCameraActor(core.CameraActor):
    COMPONENTS = (("scene_component", core.SceneComponent), ("camera_component", CineCameraComponent))

    def get_cine_camera_component(self):
        return self._props["camera_component"]


def _does_socket_exist(self, name) -> bool:
    return str(name) in self._props.get("bones", {})


def _get_socket_location(self, name, _orig=core.SceneComponent.get_socket_location):
    b = self._props.get("bones", {})
    if str(name) in b:
        return core.Vector(*b[str(name)])
    return _orig(self, name)


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

    def pose(actor, bones: dict):
        """Give an actor's skeletal mesh a pose: {bone: [x, y, z]} in world cm."""
        a = fake.actor(actor) if isinstance(actor, str) else actor
        comp = a.get_components_by_class(core.SkeletalMeshComponent)[0]
        comp._props["bones"] = {k: list(v) for k, v in bones.items()}
        return a
    fake.pose = pose
    # bones on every skeletal mesh (a superset of core's: without a bone table it answers as before)
    # bones on skeletal meshes: core.SkinnedMeshComponent's table (shared with WP10's fakes)
