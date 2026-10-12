// end: the CampX logo rising out of the dark with a light sweep over it, "Medha AI · Evaluate smarter. Decide faster.",
// campx.in, and a slow fade to black.
import { Scene2D, type Frame } from '@kit/scene2d';
import type { PostOverrides } from '@engine/scene';
import { W, H } from '@engine/gl';
import { HEX, rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, lerp, prog } from '@engine/util';
import { arrive, brandGradient, dropImg, freeCanvas, loadImg, offscreen, spoken, wordAt } from './common';

export default class End extends Scene2D {
  private logo: HTMLImageElement | null = null;
  private mask: HTMLCanvasElement | null = offscreen(W, H);

  override async init() {
    this.logo = await loadImg('assets/brand/campx-logo-white.png');
  }

  draw(c: CanvasRenderingContext2D, f: Frame): PostOverrides {
    const u = this.u, t = f.t, st = this.ctx.start;
    const words = spoken(this.ctx.vo, this.ctx.id);
    const tTag = wordAt(words, 'evaluate', st + 2.1);

    const bg = c.createRadialGradient(W / 2, H * 0.42, 0, W / 2, H * 0.42, W * 0.6);
    bg.addColorStop(0, rgba('surface2', 0.8));
    bg.addColorStop(0.6, rgba('bg2', 0.6));
    bg.addColorStop(1, rgba('bg', 0));
    c.fillStyle = bg;
    c.fillRect(0, 0, W, H);

    // the logo
    const lw = W * 0.3, lh = lw * (this.logo!.naturalHeight / this.logo!.naturalWidth);
    const lx = (W - lw) / 2, ly = H * 0.4 - lh / 2;
    const k = arrive(t, st + 0.35, 1.5);
    const push = 1 + 0.02 * f.p;
    c.save();
    c.translate(W / 2, H / 2);
    c.scale(push, push);
    c.translate(-W / 2, -H / 2);
    if (k > 0) {
      c.save();
      c.globalAlpha = k;
      c.filter = `blur(${((1 - k) * 16 * u).toFixed(1)}px)`;
      c.drawImage(this.logo!, lx, ly + (1 - k) * 36 * u, lw, lh);
      c.restore();
      // a light sweep once it has settled: the gradient passing through the mark
      const ks = prog(t, st + 1.2, st + 2.4);
      if (ks > 0 && ks < 1) {
        const m = this.mask!.getContext('2d')!;
        m.globalCompositeOperation = 'source-over';
        m.clearRect(0, 0, W, H);
        m.drawImage(this.logo!, lx, ly, lw, lh);
        m.globalCompositeOperation = 'source-in';
        const sx = lerp(lx - 200 * u, lx + lw + 200 * u, ease.inOutCubic(ks));
        const g = m.createLinearGradient(sx - 160 * u, 0, sx + 160 * u, 0);
        g.addColorStop(0, 'rgba(0,0,0,0)');
        g.addColorStop(0.5, HEX.accentBright);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        m.fillStyle = g;
        m.fillRect(0, 0, W, H);
        const gl = this.glow;
        gl.globalAlpha = 0.85 * Math.sin(Math.PI * ks);
        gl.drawImage(this.mask!, 0, 0, W, H);
      }
    }
    c.restore();

    // Medha AI · Evaluate smarter. Decide faster.
    const kt = arrive(t, tTag, 1.0);
    if (kt > 0) {
      const sz = 44 * u, y = H * 0.62;
      c.save();
      c.globalAlpha = kt;
      c.filter = `blur(${((1 - kt) * 8 * u).toFixed(1)}px)`;
      c.textBaseline = 'alphabetic';
      const med = 'Medha AI', sep = '  ·  ', rest = 'Evaluate smarter. Decide faster.';
      c.font = font(F.display(87.5, 800), sz);
      const wm = c.measureText(med).width;
      c.font = font(F.display(87.5, 300), sz);
      const ws = c.measureText(sep).width, wr = c.measureText(rest).width;
      const x = (W - (wm + ws + wr)) / 2, dy = (1 - kt) * 14 * u;
      c.font = font(F.display(87.5, 800), sz);
      c.fillStyle = brandGradient(c, x, x + wm);
      c.fillText(med, x, y + dy);
      c.font = font(F.display(87.5, 300), sz);
      c.fillStyle = rgba('fgDim');
      c.fillText(sep, x + wm, y + dy);
      c.fillStyle = rgba('fg');
      c.fillText(rest, x + wm + ws, y + dy);
      c.restore();
    }
    // campx.in
    const ku = arrive(t, tTag + 0.9, 1.0);
    if (ku > 0) {
      c.save();
      c.globalAlpha = ku * 0.9;
      c.textAlign = 'center';
      c.font = font(F.display(87.5, 500), 30 * u);
      c.letterSpacing = `${(6 * u).toFixed(1)}px`;
      c.fillStyle = rgba('fgDim');
      c.fillText('campx.in', W / 2 + 3 * u, H * 0.74 + (1 - ku) * 10 * u);
      c.restore();
    }
    // to black
    const fade = ease.inOutCubic(prog(t, this.ctx.end - 0.9, this.ctx.end - 0.05));
    return { fade };
  }

  override dispose() {
    dropImg(this.logo);
    this.logo = null;
    freeCanvas(this.mask);
    this.mask = null;
    super.dispose();
  }
}
