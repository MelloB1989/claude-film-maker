// Small drawn marks (list bullets, feature icons, separators): vector strokes that draw on with progress k (0..1), so
// they write themselves in instead of popping, crisp at any size and in any colour (no font has to carry them).
export type MarkKind = 'check' | 'dot' | 'arrow' | 'plus' | 'dash' | 'star' | 'x' | 'spark';
export const MARKS: readonly MarkKind[] = ['check', 'dot', 'arrow', 'plus', 'dash', 'star', 'x', 'spark'];

/** Polylines of a mark in a unit box (-0.5..0.5, y down). */
const PATHS: Record<Exclude<MarkKind, 'dot' | 'star' | 'spark'>, [number, number][][]> = {
  check: [[[-0.36, 0.02], [-0.1, 0.28], [0.38, -0.28]]],
  arrow: [[[-0.4, 0], [0.38, 0]], [[0.08, -0.3], [0.38, 0], [0.08, 0.3]]],
  plus: [[[0, -0.38], [0, 0.38]], [[-0.38, 0], [0.38, 0]]],
  dash: [[[-0.34, 0], [0.34, 0]]],
  x: [[[-0.3, -0.3], [0.3, 0.3]], [[0.3, -0.3], [-0.3, 0.3]]],
};

/** A four-pointed star (a separator, a spark) as a filled path in the unit box, its waist `w`. */
function star(c: CanvasRenderingContext2D, x: number, y: number, s: number, w = 0.12) {
  c.beginPath();
  c.moveTo(x, y - 0.5 * s);
  c.quadraticCurveTo(x + w * s, y - w * s, x + 0.5 * s, y);
  c.quadraticCurveTo(x + w * s, y + w * s, x, y + 0.5 * s);
  c.quadraticCurveTo(x - w * s, y + w * s, x - 0.5 * s, y);
  c.quadraticCurveTo(x - w * s, y - w * s, x, y - 0.5 * s);
  c.closePath();
}

/**
 * Draw a mark centred at (x, y), `s` px across, written on to `k` (0..1): strokes trace from their start, filled marks
 * grow. `color` is a CSS colour; `weight` the stroke width as a fraction of s.
 */
export function drawMark(c: CanvasRenderingContext2D, kind: MarkKind, x: number, y: number, s: number, k: number, color: string, weight = 0.11) {
  if (k <= 0) return;
  c.save();
  c.fillStyle = color;
  c.strokeStyle = color;
  if (kind === 'dot') {
    c.beginPath();
    c.arc(x, y, 0.2 * s * Math.min(1, k * 1.1), 0, Math.PI * 2);
    c.fill();
  } else if (kind === 'star' || kind === 'spark') {
    const g = Math.min(1, k);
    star(c, x, y, s * g * (kind === 'spark' ? 1 : 0.85), kind === 'spark' ? 0.08 : 0.14);
    c.fill();
  } else {
    const paths = PATHS[kind];
    const lens = paths.map((p) => p.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - p[i]![0], q[1] - p[i]![1]), 0));
    const total = lens.reduce((a, b) => a + b, 0);
    let left = Math.min(1, k) * total;
    c.lineWidth = weight * s;
    c.lineCap = 'round';
    c.lineJoin = 'round';
    c.beginPath();
    paths.forEach((p) => {
      if (left <= 0) return;
      c.moveTo(x + p[0]![0] * s, y + p[0]![1] * s);
      for (let i = 1; i < p.length && left > 0; i++) {
        const a = p[i - 1]!, b = p[i]!, l = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const f = Math.min(1, left / l);
        c.lineTo(x + (a[0] + (b[0] - a[0]) * f) * s, y + (a[1] + (b[1] - a[1]) * f) * s);
        left -= l;
      }
    });
    c.stroke();
  }
  c.restore();
}
