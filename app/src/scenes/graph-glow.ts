// Light along a thread on screen, for scene `graph`: at the constellation's distance a diff thread's blood or moss
// strand is about a pixel wide, too thin for its own light to carry (honest's finding), so the colour a link carries
// (the dangling link's blood dashes, the heal's moss, the walk, an edge landing) is also drawn as a soft run of light
// along the thread's projected centreline on a low-res glow layer, which the scene adds as blood or moss light
// (look.ts glow). The thread's own strand light rides under it, and takes over in the close-ups.
type Ctx = CanvasRenderingContext2D;

export interface P2 { x: number; y: number }

/** The light's two strokes: a soft halo and a fine core (logical px wide), and their strengths. */
export const GLOW_STROKE = { halo: 9, haloGain: 0.2, core: 2.2, coreGain: 0.9 };

/**
 * Light along `pts` (logical px, even along the thread's length, its first at arc fraction 0 and its last at 1),
 * `level(u)` strong at arc fraction u (0..1), in white: the layer's composite tints it. Each step is its own stroke at
 * its own strength, with butt ends so steps don't double up where they meet. `scale` maps logical px to the layer's.
 */
export function glowAlong(c: Ctx, pts: readonly P2[], level: (u: number) => number, gain = 1, stroke = GLOW_STROKE, blur?: (u: number) => number) {
  const n = pts.length - 1;
  if (n < 1) return;
  c.save();
  c.lineCap = 'butt';
  for (const [width, g] of [[stroke.halo, stroke.haloGain], [stroke.core, stroke.coreGain]] as const) {
    for (let i = 0; i < n; i++) {
      const u = (i + 0.5) / n;
      // out of focus the light spreads as the lens spreads the thread: wider, and fainter for it
      const b = blur ? 0.7 * blur(u) : 0;
      c.lineWidth = width + b;
      const k = level(u) * g * gain * (width / (width + b));
      if (k <= 0.004) continue;
      const p = pts[i]!, q = pts[i + 1]!;
      // a hair past each end, so a step meets the next without a seam
      const dx = q.x - p.x, dy = q.y - p.y, L = Math.hypot(dx, dy) || 1, ex = (dx / L) * 0.35, ey = (dy / L) * 0.35;
      c.strokeStyle = `rgba(255,255,255,${Math.min(1, k).toFixed(4)})`;
      c.beginPath();
      c.moveTo(p.x - ex, p.y - ey);
      c.lineTo(q.x + ex, q.y + ey);
      c.stroke();
    }
  }
  c.restore();
}

/** A soft round light at (x, y): a pearl lighting, seen through its glass (logical px radius, strength). */
export function glowDot(c: Ctx, x: number, y: number, r: number, k: number) {
  if (k <= 0.004 || r <= 0) return;
  c.save();
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(255,255,255,${Math.min(1, k).toFixed(4)})`);
  g.addColorStop(0.35, `rgba(255,255,255,${Math.min(1, 0.45 * k).toFixed(4)})`);
  g.addColorStop(1, 'rgba(255,255,255,0)');
  c.fillStyle = g;
  c.fillRect(x - r, y - r, 2 * r, 2 * r);
  c.restore();
}

/**
 * A dashed ring of light at (x, y), radius r (logical px): where a link points at a memory that doesn't exist yet, the
 * place it would be. `dashes` dashes round it, `phase` (turns) turning them, strength k.
 */
export function glowRing(c: Ctx, x: number, y: number, r: number, k: number, phase = 0, dashes = 14) {
  if (k <= 0.004 || r <= 0.5) return;
  c.save();
  c.lineCap = 'round';
  const step = (Math.PI * 2) / dashes, on = step * 0.42;
  for (const [w, g] of [[7, 0.18], [1.8, 0.85]] as const) {
    c.lineWidth = w;
    c.strokeStyle = `rgba(255,255,255,${Math.min(1, k * g).toFixed(4)})`;
    for (let i = 0; i < dashes; i++) {
      const a = i * step + phase * Math.PI * 2;
      c.beginPath();
      c.arc(x, y, r, a, a + on);
      c.stroke();
    }
  }
  c.restore();
}
