# The thumbnail's picture, in the reference's thumbnail format: the keeper big on white, worried, holding up a lit
# lantern; the handwritten hook and arrow are added over it (scripts/thumbnail.py).
DRAW = {"fps": 0, "res": [2560, 1440]}


def build(ctx):
    from lib.toon import Person, D2R
    from mathutils import Vector
    t = ctx.toon
    t.world("#ffffff")
    t.group("people")
    k = Person(t, t.cast["keeper"], "keeper", loc=(-0.2, 0, 0), rot=(0, 0, D2R(-18)), hands=("grip", "rest"),
               expression="worried")
    k.head_pose(turn=-6, tilt=-5)
    # the lantern held up by its ring, out to his side: the fist high, the lantern hanging straight down from it
    k.reach(-1, (-1.12, -0.45, 2.15), palm=(0.2, -1, 0), fingers=(-0.55, -0.1, 0.83))
    pivot = t.empty("lantern pivot", (0, 0, 0))
    k.hold(-1, pivot, at="grip")
    a = k.arms[-1]
    q = a["shoulder"].rotation_quaternion @ a["elbow"].rotation_quaternion @ a["wrist"].rotation_quaternion
    pivot.rotation_mode = "QUATERNION"
    pivot.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(q.inverted() @ Vector((0, 0, -1)))
    lamp = t.empty("lantern", (0, 0, -0.14), pivot)
    t.torus("lantern ring", (0, 0, 0.07), 0.07, 0.016, "iron", parent=lamp, rot=(D2R(90), 0, 0), seg=32)
    t.cyl("lantern top", (0, 0, 0.0), 0.06, 0.08, "iron", parent=lamp, r2=0.03)
    t.cyl("lantern cap", (0, 0, -0.09), 0.13, 0.08, "iron", parent=lamp, r2=0.06)
    t.cyl("lantern glass", (0, 0, -0.28), 0.12, 0.3, "glass_lit", parent=lamp, r2=0.12)
    t.cyl("lantern base", (0, 0, -0.47), 0.14, 0.08, "iron", parent=lamp)
    t.blob("lantern flame", (0, -0.13, -0.28), (0.04, 0.01, 0.08), "flame", c=t.face, parent=lamp)
    t.update()
    p = lamp.matrix_world @ Vector((0, 0, -0.28))
    t.blob("lantern glow", (p.x, p.y + 0.9, p.z), (0.75, 0.02, 0.75), "glow", c=t.plain, alpha=0.6)
    t.camera("cam", (0.5, -8.6, 1.75), (0.5, 0, 1.55), lens=60)
