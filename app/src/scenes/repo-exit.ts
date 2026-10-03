// The string's exit (the match cut repo → loom, transitions/repo-loom.ts): repo's last shot is framed so its bead string
// lies on the screen line of loom's first fell, where the shuttle's thread is beaten in (B05's track, fell_l/fell_r at
// loom's first frame). On the cut the string's light runs out into it and becomes the weft. Pure: no three.js, so bun
// tests it.

export interface Px {
  x: number;
  y: number;
}

/** A screen line: its angle (rad, y down) and its height at x. */
export interface ScreenLine {
  angle: number;
  at(x: number): number;
}

/** The line through two points. */
export function lineThrough(a: Px, b: Px): ScreenLine {
  const s = (b.y - a.y) / (b.x - a.x);
  return { angle: Math.atan(s), at: (x) => a.y + s * (x - a.x) };
}

/** The least-squares line y = c + s·x through points (at least two, not all on one x). */
export function fitLine(pts: readonly Px[]): ScreenLine {
  const n = pts.length;
  if (n < 2) throw new Error(`fitLine: ${n} point${n === 1 ? '' : 's'}`);
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const p of pts) (sx += p.x), (sy += p.y), (sxx += p.x * p.x), (sxy += p.x * p.y);
  const d = n * sxx - sx * sx;
  if (Math.abs(d) < 1e-9) throw new Error('fitLine: the points are all on one x');
  const s = (n * sxy - sx * sy) / d, c = (sy - s * sx) / n;
  return { angle: Math.atan(s), at: (x) => c + s * x };
}

/**
 * Solves f(p) = 0 for two unknowns by Newton's method with a forward-difference Jacobian (steps h), from p0. Returns
 * the solution, or throws when it has not converged to |f| ≤ tol (per component) in `iters` steps.
 */
export function solve2(
  f: (p: [number, number]) => [number, number],
  p0: [number, number],
  h: [number, number],
  tol: [number, number],
  iters = 8,
): [number, number] {
  let p: [number, number] = [...p0];
  for (let k = 0; k <= iters; k++) {
    const e = f(p);
    if (Math.abs(e[0]) <= tol[0] && Math.abs(e[1]) <= tol[1]) return p;
    if (k === iters) break;
    const e0 = f([p[0] + h[0], p[1]]), e1 = f([p[0], p[1] + h[1]]);
    const a = (e0[0] - e[0]) / h[0], b = (e1[0] - e[0]) / h[1], c = (e0[1] - e[1]) / h[0], d = (e1[1] - e[1]) / h[1];
    const det = a * d - b * c;
    if (Math.abs(det) < 1e-12) throw new Error('solve2: the Jacobian is singular');
    p = [p[0] - (d * e[0] - b * e[1]) / det, p[1] - (-c * e[0] + a * e[1]) / det];
  }
  throw new Error(`solve2: no convergence from [${p0.join(', ')}] in ${iters} steps`);
}

/**
 * Where the exit puts the string, against the fell: the angle between them (rad) and how far the string is from the
 * fell (px, + below it) at x, the middle of the fell's stretch on screen.
 */
export function exitError(string: ScreenLine, fell: ScreenLine, x: number): [number, number] {
  return [string.angle - fell.angle, string.at(x) - fell.at(x)];
}
