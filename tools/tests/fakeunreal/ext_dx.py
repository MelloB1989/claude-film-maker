"""WP11's additions to the fake engine:

- the engine's basic shapes (/Engine/BasicShapes/*), which every editor has and level.spawn(shape=...) loads;
- `obj.get_class().get_name()` as in the engine (a UClass has get_name/get_path_name): the fake's get_class returns
  the Python class, on which Object.get_name was an unbound method, so level.actors failed. (For the lead to fold
  into core.py; harmless if core does it too.)"""


class _ClassOrInstance:
    """A method that also answers on the class: Cls.get_name() -> "Cls", like a UClass."""

    def __init__(self, fn, on_class):
        self.fn, self.on_class = fn, on_class

    def __get__(self, obj, cls):
        if obj is None:
            return lambda: self.on_class(cls)
        return self.fn.__get__(obj, cls)


def install(fake):
    for n in ("Cube", "Sphere", "Cylinder", "Cone", "Plane"):
        path = f"/Engine/BasicShapes/{n}"
        if path not in fake.assets:
            fake.add_asset(path, "StaticMesh")
    obj = fake.Object
    if not isinstance(obj.__dict__.get("get_name"), _ClassOrInstance):
        obj.get_name = _ClassOrInstance(obj.__dict__["get_name"], lambda c: c.__name__)
        obj.get_path_name = _ClassOrInstance(obj.__dict__["get_path_name"], lambda c: f"/Script/Engine.{c.__name__}")
