"""Fabric presets for Chaos cloth on a presenter's garment: the solver config, and the max distance per zone.

Units: mass density kg/m2 (Chaos `Density`, "MassMode: Density"), stiffness 0..1 (Chaos weighted values: `low` where
the map is 0, `high` where it is 1), damping 0..1, distances cm, velocity scales 0..1. The values are starting points
from Epic's defaults and fabric weights (cotton jersey ~150 g/m2, light shirting/twill ~180-220 g/m2, chino ~280 g/m2),
tuned for a presenter (slow, close to the body, no wind): stiff enough not to swim, soft enough to fold. The research
doc (docs/unreal/research/cloth-physics.md) gives the reasons and the sources; change values there and here together.

A preset's `zones` say where the cloth hangs free. Each zone takes the vertices nearest to its bones (rest pose) and
ramps the max distance from `from_cm` at its anchor end to `to_cm` at its free end: down the torso (height), or out
along the limb (along). 0 cm = skinned (the cloth follows the body exactly there: collar, shoulder seam, waistband).
"""
from __future__ import annotations

import copy

# Chaos cloth config (UChaosClothConfig / UChaosClothSharedSimConfig properties, snake_case as Python names them).
# Only what a preset changes from the engine defaults is listed; `ops.cloth` writes each one and reads it back.
BASE_CONFIG = {
    "mass_mode": "DENSITY",          # EClothMassMode: kg/m2 x the garment's area: the same fabric reads the same on any mesh
    "density": 0.15,                 # kg/m2
    "min_per_particle_mass": 0.0001,
    "edge_stiffness": 1.0,           # stretch along edges (XPBD, 0..1): keep 1, let tethers do the rest
    "bending_stiffness": 0.1,        # folds: low = soft jersey, high = card
    "area_stiffness": 1.0,
    "tether_stiffness": 1.0,         # long range attachment: stops the hem stretching away from the anchors
    "tether_scale": 1.0,             # 1.0 = no stretch beyond rest length along the tethers
    "use_geodesic_distance": True,   # tethers measured over the cloth, not through the body (shirts round a torso)
    "collision_thickness": 0.5,      # cm kept off the physics asset's shapes
    "friction_coefficient": 0.6,
    "use_self_collisions": False,
    "self_collision_thickness": 0.5,
    "damping": 0.05,                 # 0.01 default: presenters want calm cloth, not buzz
    "linear_velocity_scale": 0.75,   # how much of the actor's motion the cloth feels (Epic default 0.75)
    "angular_velocity_scale": 0.75,
    "fictitious_angular_scale": 0.5,  # centrifugal kick on turns: half, or a quick head turn flings the hem
    "gravity_scale": 1.0,
    "anim_drive_stiffness": 0.0,     # pull toward the skinned pose everywhere: 0 = free within the max distance
    "drag_coefficient": 0.035,
    "lift_coefficient": 0.035,
    # shared (one per mesh)
    "iteration_count": 2,
    "max_iteration_count": 6,
    "subdivision_count": 2,          # substeps: 2 at 24 fps (and MRQ's temporal samples shorten the step further)
}

# component settings (USkeletalMeshComponent) every cloth garment gets
COMPONENT = {
    "teleport_distance_threshold": 30.0,   # cm the root may jump in a frame before the cloth teleports (0 = never)
    "teleport_rotation_threshold": 30.0,   # degrees likewise: a cut that re-places a presenter must not fling the cloth
    "reset_after_teleport": True,          # bResetAfterTeleport: back to the skinned pose, then settle (needs pre-roll)
    "allow_cloth_actors": True,            # bAllowClothActors
    "disable_cloth_simulation": False,
    "collide_with_environment": False,     # the garment collides with ITS body's physics asset, not the room
    "cloth_max_distance_scale": 1.0,
}

PRESETS = {
    "cotton_tee": {
        "about": "a fitted cotton jersey T-shirt over a presenter's torso: anchored at the collar and shoulder seams, "
                 "free toward the hem and the sleeve ends; soft folds, no swing",
        "config": {"density": 0.15, "bending_stiffness": 0.08, "damping": 0.06, "tether_scale": 1.03,
                   "collision_thickness": 0.4, "friction_coefficient": 0.6},
        "zones": [
            {"name": "collar", "bones": ["neck_01", "neck_02", "head"], "ramp": "fixed", "from_cm": 0.0, "to_cm": 0.0},
            {"name": "shoulder", "bones": ["clavicle_l", "clavicle_r"], "ramp": "fixed", "from_cm": 0.0,
             "to_cm": 0.0},
            {"name": "torso", "bones": ["spine_05", "spine_04", "spine_03", "spine_02", "spine_01", "pelvis"],
             "ramp": "height", "from_cm": 0.0, "to_cm": 3.0, "gamma": 1.6},
            {"name": "sleeve", "bones": ["upperarm_l", "upperarm_r", "upperarm_twist_01_l", "upperarm_twist_01_r",
                                         "upperarm_twist_02_l", "upperarm_twist_02_r"],
             "ramp": "along", "from_cm": 0.0, "to_cm": 2.0, "gamma": 1.4},
        ],
        "free": ["torso", "sleeve"],          # zones that must visibly move (qa.cloth "alive")
        "pinned": ["collar", "shoulder"],     # zones that must stay put (qa.cloth "anchored")
        "hem_band_cm": 6.0,                   # the bottom of a free zone counted as its hem in qa.cloth
        "settle_s": 1.0,                      # time for the hem to come to rest from the skinned pose (pre-roll)
    },
    "overshirt_light": {
        "about": "a light open overshirt (shirting/twill) over a top: anchored at the collar and the shoulders, its "
                 "open front and hem hang free and swing a little on a turn",
        "config": {"density": 0.2, "bending_stiffness": 0.25, "damping": 0.06, "tether_scale": 1.02,
                   "collision_thickness": 0.6, "friction_coefficient": 0.5, "use_self_collisions": False},
        "zones": [
            {"name": "collar", "bones": ["neck_01", "neck_02", "head"], "ramp": "fixed", "from_cm": 0.0, "to_cm": 0.0},
            {"name": "shoulder", "bones": ["clavicle_l", "clavicle_r"], "ramp": "fixed", "from_cm": 0.0,
             "to_cm": 0.0},
            {"name": "torso", "bones": ["spine_05", "spine_04", "spine_03", "spine_02", "spine_01", "pelvis"],
             "ramp": "height", "from_cm": 0.3, "to_cm": 6.0, "gamma": 1.5},
            {"name": "sleeve", "bones": ["upperarm_l", "upperarm_r", "upperarm_twist_01_l", "upperarm_twist_01_r",
                                         "upperarm_twist_02_l", "upperarm_twist_02_r", "lowerarm_l", "lowerarm_r",
                                         "lowerarm_twist_01_l", "lowerarm_twist_01_r", "lowerarm_twist_02_l",
                                         "lowerarm_twist_02_r"],
             "ramp": "along", "from_cm": 0.0, "to_cm": 3.0, "gamma": 1.3},
        ],
        "free": ["torso", "sleeve"],
        "pinned": ["collar", "shoulder"],
        "hem_band_cm": 8.0,
        "settle_s": 1.5,
    },
    "trousers": {
        "about": "chino-weight trousers: anchored at the waistband and the seat, free below the knee toward the hem",
        "config": {"density": 0.28, "bending_stiffness": 0.4, "damping": 0.08, "tether_scale": 1.02,
                   "collision_thickness": 0.6, "friction_coefficient": 0.7, "fictitious_angular_scale": 0.3},
        "zones": [
            {"name": "waist", "bones": ["pelvis", "spine_01"], "ramp": "fixed", "from_cm": 0.0, "to_cm": 0.0},
            {"name": "thigh", "bones": ["thigh_l", "thigh_r", "thigh_twist_01_l", "thigh_twist_01_r",
                                        "thigh_twist_02_l", "thigh_twist_02_r"],
             "ramp": "along", "from_cm": 0.0, "to_cm": 1.0, "gamma": 2.0},
            {"name": "leg", "bones": ["calf_l", "calf_r", "calf_twist_01_l", "calf_twist_01_r", "calf_twist_02_l",
                                      "calf_twist_02_r", "foot_l", "foot_r"],
             "ramp": "along", "from_cm": 1.0, "to_cm": 3.0, "gamma": 1.0},
        ],
        "free": ["leg"],
        "pinned": ["waist"],
        "hem_band_cm": 6.0,
        "settle_s": 1.0,
    },
}

RAMPS = ("fixed", "height", "along")


def names() -> list:
    return sorted(PRESETS)


def get(name: str, overrides: dict | None = None) -> dict:
    """A preset by name, with its config merged over BASE_CONFIG and `overrides` ({"config": {...}, "zones":
    {zone: {"to_cm": ...}}, "settle_s": ...}) applied. Raises KeyError (with the names) for an unknown preset or key,
    so a typo cannot silently do nothing."""
    if name not in PRESETS:
        raise KeyError(f"no cloth preset {name!r}: one of {', '.join(names())}")
    p = copy.deepcopy(PRESETS[name])
    p["name"] = name
    p["config"] = {**BASE_CONFIG, **p["config"]}
    for k, v in (overrides or {}).items():
        if k == "config":
            for ck, cv in v.items():
                if ck not in BASE_CONFIG:
                    raise KeyError(f"no cloth config key {ck!r}: one of {', '.join(sorted(BASE_CONFIG))}")
                p["config"][ck] = cv
        elif k == "zones":
            by = {z["name"]: z for z in p["zones"]}
            for zn, zv in v.items():
                if zn not in by:
                    raise KeyError(f"preset {name} has no zone {zn!r}: one of {', '.join(by)}")
                for zk, val in zv.items():
                    if zk not in ("from_cm", "to_cm", "gamma", "bones", "ramp"):
                        raise KeyError(f"zone key {zk!r}: one of from_cm, to_cm, gamma, bones, ramp")
                    by[zn][zk] = val
        elif k in ("settle_s", "hem_band_cm", "free", "pinned"):
            p[k] = v
        else:
            raise KeyError(f"no preset key {k!r}: one of config, zones, settle_s, hem_band_cm, free, pinned")
    for z in p["zones"]:
        if z["ramp"] not in RAMPS:
            raise KeyError(f"zone {z['name']}: ramp {z['ramp']!r}: one of {', '.join(RAMPS)}")
    return p


def max_cm(preset: dict) -> float:
    """The largest max distance a preset paints (cm)."""
    return max([max(z["from_cm"], z["to_cm"]) for z in preset["zones"]] or [0.0])
