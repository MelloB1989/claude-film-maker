// title: "CampX Digital Evaluation" revealed by a light sweep (the brand gradient as light passing over the type), then
// "Powered by Medha AI" with Medha AI in the brand gradient. On the voice when data/vo.json exists.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { HEX, rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, lerp, prog } from '@engine/util';
import { arrive, brandGradient, freeCanvas, offscreen, spoken, wordAt } from './common';

export default class Title extends Scene2D {
  private mask: HTMLCanvasElement | null = offscreen(W, H);

  draw(c: CanvasRenderingContext2D, f: Frame) {
    const u = this.u, t = f.t, st = this.ctx.start;
    const words = spoken(this.ctx.vo, this.ctx.id);
    // the sweep starts on "Introducing" and has passed the whole name by "Evaluation"
    const tName = wordAt(words, 'introducing', st + 0.5) + 0.1;
    const tEnd = Math.max(tName + 1.0, wordAt(words, 'evaluation', tName + 1.5));
    const tPow = wordAt(words, 'powered', st + 3.0);
    const push = 1 + 0.035 * f.p;

    // a deep indigo room, lit from behind the type
    const bg = c.createRadialGradient(W * 0.5, H * 0.46, 0, W * 0.5, H * 0.46, W * 0.7);
    bg.addColorStop(0, rgba('surface2', 0.9));
    bg.addColorStop(0.6, rgba('bg2', 0.8));
    bg.addColorStop(1, rgba('bg', 0));
    c.fillStyle = bg;
    c.fillRect(0, 0, W, H);

    c.save();
    c.translate(W / 2, H / 2);
    c.scale(push, push);
    c.translate(-W / 2, -H / 2);

    // the name: CampX in the heavy cut, Digital Evaluation in the light one
    const sA = 132 * u, sB = 132 * u;
    const fa = font(F.display(87.5, 800), sA), fb = font(F.display(87.5, 300), sB);
    c.font = fa;
    const wa = c.measureText('CampX ').width;
    c.font = fb;
    const wb = c.measureText('Digital Evaluation').width;
    const total = wa + wb, x0 = (W - total) / 2, y = H * 0.5;
    const draw = (cx: CanvasRenderingContext2D, fill: string | CanvasGradient) => {
      cx.textBaseline = 'alphabetic';
      cx.fillStyle = fill;
      cx.font = fa;
      cx.fillText('CampX', x0, y);
      cx.font = fb;
      cx.fillText('Digital Evaluation', x0 + wa, y);
    };

    // the sweep: x of the light's centre, and the type it has passed
    const k = ease.inOutCubic(prog(t, tName, tEnd));
    const band = 340 * u;
    const sx = lerp(x0 - band * 0.3, x0 + total + band, k);
    const m = this.mask!.getContext('2d')!;
    m.clearRect(0, 0, W, H);
    m.globalCompositeOperation = 'source-over';
    draw(m, rgba('fg'));
    m.globalCompositeOperation = 'destination-in'; // keep the type that is behind the sweep, softly
    const reveal = m.createLinearGradient(sx - band * 0.5, 0, sx + band * 0.15, 0);
    reveal.addColorStop(0, 'rgba(0,0,0,1)');
    reveal.addColorStop(1, 'rgba(0,0,0,0)');
    m.fillStyle = reveal;
    m.fillRect(0, 0, W, H);
    c.drawImage(this.mask!, 0, 0, W, H); // fg is crisp; what the sweep has not reached is not there

    // the light riding the leading edge: the brand gradient, only on the type, added as glow
    if (k > 0 && k < 1) {
      const g = this.glow;
      const lm = this.mask!.getContext('2d')!;
      lm.globalCompositeOperation = 'source-over';
      lm.clearRect(0, 0, W, H);
      draw(lm, '#ffffff');
      lm.globalCompositeOperation = 'source-in';
      const lg = lm.createLinearGradient(sx - band * 0.45, 0, sx + band * 0.12, 0);
      lg.addColorStop(0, 'rgba(255,255,255,0)');
      lg.addColorStop(0.55, HEX.accent);
      lg.addColorStop(0.85, HEX.accent2Bright);
      lg.addColorStop(1, 'rgba(255,255,255,0)');
      lm.fillStyle = lg;
      lm.fillRect(0, 0, W, H);
      g.save();
      g.globalAlpha = 0.9 * Math.sin(Math.PI * k);
      g.drawImage(this.mask!, 0, 0, W, H);
      g.restore();
      // and the sweep itself as a soft vertical ellipse of light
      g.save();
      g.translate(sx, y - sA * 0.35);
      g.scale(0.22, 1);
      const bl = g.createRadialGradient(0, 0, 0, 0, 0, sA * 1.5);
      bl.addColorStop(0, glowInk('accentBright', 0.3 * Math.sin(Math.PI * k)));
      bl.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = bl;
      g.fillRect(-sA * 1.6, -sA * 1.6, sA * 3.2, sA * 3.2);
      g.restore();
    }

    // a hairline under the name, drawn out from the centre
    const kr = ease.outExpo(prog(t, tEnd - 0.2, tEnd + 1.1));
    if (kr > 0) {
      const hw = total * 0.5 * kr;
      c.fillStyle = brandGradient(c, W / 2 - total / 2, W / 2 + total / 2);
      c.globalAlpha = 0.85;
      c.fillRect(W / 2 - hw, y + 38 * u, hw * 2, 2 * u);
      c.globalAlpha = 1;
    }

    // Powered by Medha AI
    const kp = arrive(t, tPow, 1.0);
    if (kp > 0) {
      const sP = 38 * u, sM = 64 * u, yp = H * 0.66;
      c.save();
      c.globalAlpha = kp;
      c.filter = `blur(${((1 - kp) * 10 * u).toFixed(1)}px)`;
      c.textBaseline = 'alphabetic';
      c.font = font(F.display(87.5, 500), sP);
      const pre = 'Powered by';
      c.letterSpacing = `${(3 * u).toFixed(1)}px`;
      const wp = c.measureText(pre + '  ').width;
      c.font = font(F.display(87.5, 800), sM);
      c.letterSpacing = '0px';
      const wm = c.measureText('Medha AI').width;
      const xp = (W - (wp + wm)) / 2, dy = (1 - kp) * 20 * u;
      c.font = font(F.display(87.5, 500), sP);
      c.letterSpacing = `${(3 * u).toFixed(1)}px`;
      c.fillStyle = rgba('fgDim');
      c.fillText(pre, xp, yp + dy);
      c.letterSpacing = '0px';
      c.font = font(F.display(87.5, 800), sM);
      c.fillStyle = brandGradient(c, xp + wp, xp + wp + wm);
      c.fillText('Medha AI', xp + wp, yp + dy);
      c.restore();
      const g = this.glow;
      g.font = font(F.display(87.5, 800), sM);
      g.fillStyle = brandGradient(g, xp + wp, xp + wp + wm);
      g.globalAlpha = 0.28 * kp;
      g.fillText('Medha AI', xp + wp, yp + dy);
    }
    c.restore();
  }

  override dispose() {
    freeCanvas(this.mask);
    this.mask = null;
    super.dispose();
  }
}
