import sys, os, bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _fx3d as fx
from mathutils import Vector
ob = fx.poly_curve("t", [[(Vector((0, 0, 0)), 1.0), (Vector((1, 0, 0)), 1.0)]], 0.001, None)
bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
me = ob.evaluated_get(dg).to_mesh()
ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print("PROBE dims", ob.dimensions[:], "y", min(ys), max(ys), "z", min(zs), max(zs), "bevel", ob.data.bevel_depth, "mode", ob.data.bevel_mode, ob.data.fill_mode)
