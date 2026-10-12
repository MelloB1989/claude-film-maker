"""The Blender plate pipeline's library, shared by every film (docs/PIPELINE-BLENDER.md). Nothing here names a film.

  film      which film, its film.json (format, fps, theme) and where its shots, tracks and plates live
  theme     the film's palette by role, in linear light
  timing    film frames, scene windows, voiceover words, beats
  cli       render.py's arguments, shot contract, render sizes, GPU backends, exit codes
  setup     a clean render scene; lights, materials, rig: studio lighting, themed materials, the engine's camera
  export    plates, proxies, look stills, tracks; blank, handlers, scan: the guards around a render
  thread, bead, braid, weave   hero motifs: threads and ropes, an engraved glass bead, a plait, a loom

film, theme, timing, cli, blank, handlers, scan, rig and the motifs' geometry are bpy-free (blender/tests runs them
under plain pytest); the rest runs in Blender.
"""
