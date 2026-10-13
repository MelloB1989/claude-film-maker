// stakes: a macro over a real handwritten page, shallow depth of field with a slow rack, the paper going down into the
// dark as the line arrives: "And behind every page," / "a student's *future*." (serif italic on future).
// Voice: the words land on `stakes`' spoken words when data/vo.json exists, else on fixed times.
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import type { PostOverrides } from '@engine/scene';
import { W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { ease, lerp, prog, smoothstep } from '@engine/util';
import { arrive, brandGradient, dropImg, freeCanvas, loadImg, offscreen, spoken, wordAt } from './common';

// Source rect (px of hires_38189_p01, 2396x3521): the last lines of the first answer, "The rank of the matrix = 3".
const FROM = { cx: 1050, cy: 2150, w: 1900 };
const TO = { cx: 880, cy: 2200, w: 1180 };

export default class Stakes extends Scene2D {
  private img: HTMLImageElement | null = null;
  private sharp: HTMLCanvasElement | null = offscreen(W, H);

  override async init() {
    this.img = await loadImg('assets/sheets/hires_38189_p01.jpg');
  }

  draw(c: CanvasRenderingContext2D, f: Frame): PostOverrides {
    const img = this.img!, u = this.u, lt = f.lt, p = f.p;
    const words = spoken(this.ctx);
    const e = 0.5 - 0.5 * Math.cos(Math.PI * p);
    const cx = lerp(FROM.cx, TO.cx, e), cy = lerp(FROM.cy, TO.cy, e), sw = lerp(FROM.w, TO.w, e);
    const sh = (sw * H) / W;
    // (always inside the page)
    const src = [Math.max(0, Math.min(img.naturalWidth - sw, cx - sw / 2)), Math.max(0, Math.min(img.naturalHeight - sh, cy - sh / 2)), sw, sh] as const;

    // the picture, soft everywhere...
    c.save();
    c.filter = `blur(${(16 * u).toFixed(1)}px)`;
    c.drawImage(img, ...src, -40, -40, W + 80, H + 80);
    c.restore();
    // ...and sharp on the plane of focus, which drifts slowly across the page (a rack)
    const s = this.sharp!.getContext('2d')!;
    s.clearRect(0, 0, W, H);
    s.globalCompositeOperation = 'source-over';
    s.drawImage(img, ...src, 0, 0, W, H);
    const fx = W * lerp(0.3, 0.62, e), fy = H * lerp(0.58, 0.5, e);
    const g = s.createRadialGradient(fx, fy, H * 0.12, fx, fy, H * 0.78);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(0.55, 'rgba(0,0,0,0.55)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    s.globalCompositeOperation = 'destination-in';
    s.fillStyle = g;
    s.fillRect(0, 0, W, H);
    c.drawImage(this.sharp!, 0, 0, W, H);

    // light on the paper: warm from the upper left, falling off
    const l = c.createRadialGradient(W * 0.3, H * 0.2, 0, W * 0.3, H * 0.2, W * 0.9);
    l.addColorStop(0, 'rgba(255,236,205,0.16)');
    l.addColorStop(1, 'rgba(0,0,0,0)');
    c.globalCompositeOperation = 'screen';
    c.fillStyle = l;
    c.fillRect(0, 0, W, H);
    c.globalCompositeOperation = 'source-over';

    // the paper goes down into the dark as the line arrives
    const dim = 0.84 * ease.inOutCubic(prog(lt, 0.7, 2.1));
    c.fillStyle = rgba('bg', dim);
    c.fillRect(0, 0, W, H);
    const v = c.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.95);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, rgba('bg', lerp(0.25, 0.78, ease.inOutCubic(prog(lt, 0.7, 2.1)))));
    c.fillStyle = v;
    c.fillRect(0, 0, W, H);

    // the type
    const l1 = ['And', 'behind', 'every', 'page,'];
    const t1 = l1.map((w, i) => wordAt(words, w, this.ctx.start + 1.5 + i * 0.3));
    const tFuture = wordAt(words, 'future', this.ctx.start + 4.1);
    const t2 = [wordAt(words, 'a', this.ctx.start + 3.3), wordAt(words, "student's", this.ctx.start + 3.55)];
    const x0 = W * 0.095;
    const size1 = 84 * u, size2 = 150 * u;
    c.textBaseline = 'alphabetic';
    c.shadowColor = 'rgba(0,0,0,0.5)';
    c.shadowBlur = 28 * u;
    c.font = font(F.display(87.5, 500), size1);
    let x = x0;
    l1.forEach((w, i) => {
      const k = arrive(f.t, t1[i]!, 0.9);
      if (k > 0) {
        c.save();
        c.globalAlpha = k;
        c.filter = `blur(${((1 - k) * 12 * u).toFixed(1)}px)`;
        c.fillStyle = rgba('fg');
        c.fillText(w, x, H * 0.4 + (1 - k) * 22 * u);
        c.restore();
      }
      x += c.measureText(w + ' ').width;
    });
    // line two: "a student's" in the display face, "future." in the serif italic
    const serif = F.role('serif', 400, true);
    const y2 = H * 0.64;
    const first = [["a", t2[0]!], ["student's", t2[1]!]] as const;
    c.font = font(F.display(87.5, 300), size2 * 0.82);
    x = x0;
    for (const [w, at] of first) {
      const k = arrive(f.t, at, 0.9);
      if (k > 0) {
        c.save();
        c.globalAlpha = k;
        c.filter = `blur(${((1 - k) * 14 * u).toFixed(1)}px)`;
        c.fillStyle = rgba('fg');
        c.fillText(w, x, y2 + (1 - k) * 26 * u);
        c.restore();
      }
      x += c.measureText(w + ' ').width;
    }
    const kf = arrive(f.t, tFuture, 1.3);
    if (kf > 0) {
      c.font = font(serif, size2);
      c.save();
      c.globalAlpha = kf;
      c.filter = `blur(${((1 - kf) * 18 * u).toFixed(1)}px)`;
      c.fillStyle = rgba('fg');
      c.fillText('future.', x, y2 + (1 - kf) * 30 * u);
      c.restore();
      // a breath of accent light round the word, and a hairline under it
      const gl = this.glow, wd = c.measureText('future.').width;
      gl.font = font(serif, size2);
      gl.fillStyle = glowInk('accent', 0.2 * smoothstep(0, 1, kf));
      gl.fillText('future.', x, y2);
      const k2 = ease.outExpo(prog(f.t, tFuture + 0.5, tFuture + 1.6));
      gl.fillStyle = brandGradient(gl, x, x + wd);
      gl.globalAlpha = 0.85;
      gl.fillRect(x, y2 + 26 * u, wd * k2, 2 * u);
    }
    c.shadowBlur = 0;
    // the paper is lit for the match cut from `open` and settles into the film's exposure as it goes down
    return { exposure: lerp(1.45, 1, ease.outCubic(prog(lt, 0, 2.2))), tint: 0, warmth: 0.1 };
  }

  override dispose() {
    dropImg(this.img);
    this.img = null;
    freeCanvas(this.sharp);
    this.sharp = null;
    super.dispose();
  }
}
