import bpy
ob = bpy.data.objects.new("e", None)
print("PROBE cycles attrs", [a for a in dir(ob.cycles) if "blur" in a or "motion" in a], [a for a in dir(ob) if "motion" in a or "blur" in a])
