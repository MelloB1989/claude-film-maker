"""Spring letters (T_spring): per-letter bouncing red condensed italic with a sub line."""
import sys
from pathlib import Path

if __name__ == "__main__":      # blender -b --factory-startup -P sub.py -- --plan ... (see basic.cli)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from amv.titles import basic


def render(spec, out_dir, opts=None):
    """Render the title's frames k = 0..dur-1 to out_dir/<k:04d>.png (RGBA, straight alpha)."""
    from amv.titles import bl
    spec = basic.unwrap(spec)
    bl.render_frames(basic.spring_frame, spec, basic.frame_list(spec, opts), out_dir, **bl.run_params(opts))


if __name__ == "__main__":
    basic.cli()
