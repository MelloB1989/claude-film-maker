
## outro (agent-06): Blender 5.2 notes (no EffectCraft use)
- The outro is a self-contained Blender script (`blender/amv2/outro.py`); output is opaque RGB PNG, black at 899.
- Blender 5.2: `scene.compositing_node_group` (not use_nodes), Glare/Translate take sockets (`inputs["Type"]`), actions are layered
  (`all_fcurves` helper). Poly-spline point keys disable motion blur for that object ("Topology differs"): strands are unblurred.
- Additive flash cards lift blacks visibly under AgX: keep flash amplitude <= 0.2 linear.
- Euler order matters for cards stood up with rotation X 90 degrees: use rotation_mode ZYX to spin about the card's own normal.
