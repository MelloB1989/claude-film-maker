// EndCard: the last frame of a launch film. The product's name lands glyph by glyph on the beat, its tagline comes up
// under it, a call-to-action pill pops in on the next beat (a light sheen crossing it), and the URL types in below. An
// optional logo (an image in the film's assets/) sits above the name, and a soft pool of accent light behind it.
//
// Params:
//   name (required)    the product's name (a KineticText line: size 190, reveal 'rise', unit 'glyph')
//   tagline            under the name (the KineticText sub)
//   cta                the button's label ('Get started'); ctaColor 'accent'; arrow true
//   url                typed in mono under the button
//   logo               an image path in the film's folder ('assets/logo.svg'); logoSize 120 (reference px)
//   aura true          a soft pool of accent light behind the name
//   ...and any KineticText param (delay, sync, size, emphasis, kicker, align...)
import type { Frame } from '../scene2d';
import { glowInk } from '../scene2d';
import { filmUrl } from '../../engine/config';
import { W, H } from '../../engine/gl';
import { LIN, rgba } from '../../engine/palette';
import { font, measure } from '../../engine/type';
import { spring } from '../../engine/motion';
import { clamp, ease, prog } from '../../engine/util';
import * as fx from './fx';
import { KineticText, type KineticParams, type LineSpec } from './kinetic';
import { family, metrics } from './layout';

export class EndCard extends KineticText {
  protected override defaults: Partial<KineticParams> = { size: 190, width: 87.5, weight: 800, reveal: 'rise', unit: 'glyph', stagger: 0.035, push: 0.02, subSize: 44 };
  private logo: HTMLImageElement | null = null;
  private logoBox = { x: 0, y: 0, w: 0, h: 0 };
  private pill = { x: 0, y: 0, w: 0, h: 0, fs: 0, label: '', fam: '' };
  private urlAt = { x: 0, y: 0, fs: 0, fam: '', text: '' };
  private ctaAt = 0;
  private urlStart = 0;

  protected override specs(): LineSpec[] {
    return [{ text: this.need<string>('name') }];
  }

  override async init() {
    const path = this.p<string | null>('logo', null);
    if (path) {
      const img = new Image();
      img.src = filmUrl(path);
      try {
        await img.decode();
      } catch {
        throw new Error(`shot ${this.ctx.id}: logo ${filmUrl(path)} did not load`);
      }
      this.logo = img;
    }
    const tagline = this.p<string | undefined>('tagline', undefined);
    if (tagline !== undefined) this.defaults = { ...this.defaults, sub: tagline };
    this.layoutBlock();
  }

  protected override layoutBlock() {
    super.layoutBlock();
    const u = this.u;
    const { audio } = this.ctx;
    // what stands below the block: the button and the url
    const cta = this.p('cta', ''), url = this.p('url', '');
    const fs = 30 * u, pfam = family({ role: 'ui', weight: 600 });
    const arrow = this.p('arrow', true) ? 1.1 * fs : 0;
    const pw = cta ? measure(cta, pfam, fs) + arrow + 2 * 1.05 * fs : 0, ph = cta ? 2.3 * fs : 0;
    const ufs = 26 * u, ufam = family({ role: 'mono', weight: 500 });
    const gapA = 54 * u, gapB = 34 * u;
    const below = (cta ? gapA + ph : 0) + (url ? (cta ? gapB : gapA) + metrics(ufam).cap * ufs : 0);
    // and above it: the logo
    const lh = this.logo ? this.p('logoSize', 120) * u : 0;
    const lw = this.logo ? (lh * this.logo.naturalWidth) / Math.max(1, this.logo.naturalHeight) : 0;
    const above = this.logo ? lh + 48 * u : 0;
    // centre the whole stack: move the block by half of what it gained below and above
    const dy = (above - below) / 2;
    for (const l of this.setLines) l.y += dy;
    this.box.y0 += dy;
    this.box.y1 += dy;
    const cx = (this.box.x0 + this.box.x1) / 2;
    this.logoBox = { x: cx - lw / 2, y: this.box.y0 - above, w: lw, h: lh };
    let y = this.box.y1;
    if (cta) {
      y += gapA;
      this.pill = { x: cx - pw / 2, y, w: pw, h: ph, fs, label: cta, fam: pfam };
      y += ph;
    }
    if (url) {
      y += (cta ? gapB : gapA) + metrics(ufam).cap * ufs;
      this.urlAt = { x: cx - measure(url, ufam, ufs) / 2, y, fs: ufs, fam: ufam, text: url };
    }
    // the button on the beat after the tagline lands, the url just after it
    const sub = this.setLines.filter((l) => l.kind === 'sub');
    const after = (sub.length ? Math.max(...sub.map((l) => l.last)) + 0.35 : this.lastAt + 0.3);
    this.ctaAt = audio.timeOfBeat(Math.ceil(audio.beatAt(after) - 1e-6));
    this.urlStart = this.ctaAt + (cta ? 0.3 : 0);
  }

  protected override drawBefore(c: CanvasRenderingContext2D, f: Frame, push: number) {
    const t = f.t;
    // the pool of light behind the name
    // (on the main layer, below the bloom's threshold: a pool of colour, not a light source)
    if (this.p('aura', true)) {
      const k = prog(t, this.firstAt - 0.1, this.lastAt + 0.8, ease.outCubic);
      if (k > 0) {
        const cx = (this.box.x0 + this.box.x1) / 2, cy = (this.box.y0 + this.box.y1) / 2;
        const r = 0.75 * Math.max(this.box.x1 - this.box.x0, 0.55 * Math.min(W, H));
        const color = this.p('ctaColor', 'accent'), a = 0.16 * k * this.exitOf(this.setLines[0]!, t).alpha;
        c.save();
        c.translate(cx, cy);
        c.scale(1, 0.62);
        const grad = c.createRadialGradient(0, 0, 0, 0, 0, r);
        // a gaussian-ish falloff: no edge anywhere
        for (const s of [0, 0.2, 0.4, 0.6, 0.8, 1]) grad.addColorStop(s, rgba(color, a * Math.exp(-4.5 * s * s) * (1 - s)));
        c.fillStyle = grad;
        c.fillRect(-r, -r, 2 * r, 2 * r);
        c.restore();
      }
    }
    if (this.logo) {
      const k = spring(t - (this.firstAt - 0.15), 4, 0.75);
      if (k > 0) {
        const b = this.logoBox;
        c.save();
        c.globalAlpha = clamp(k) * this.exitOf(this.setLines[0]!, t).alpha;
        c.translate(b.x + b.w / 2, b.y + b.h / 2 + (1 - k) * 0.2 * b.h);
        c.scale(0.85 + 0.15 * k, 0.85 + 0.15 * k);
        c.drawImage(this.logo, -b.w / 2, -b.h / 2, b.w, b.h);
        c.restore();
      }
    }
  }

  protected override drawAfter(c: CanvasRenderingContext2D, f: Frame, push: number) {
    const t = f.t;
    const ex = this.exitOf(this.setLines[this.setLines.length - 1]!, t).alpha;
    const P = this.pill;
    if (P.w > 0 && t >= this.ctaAt - 0.02) {
      const k = spring(t - (this.ctaAt - 0.02), 5, 0.62);
      const color = this.p('ctaColor', 'accent');
      const [r, gg, b] = LIN[color as 'accent'] ?? LIN.accent;
      const ink = 0.2126 * r + 0.7152 * gg + 0.0722 * b > 0.4 ? 'bg' : 'fg';
      const cx = P.x + P.w / 2, cy = P.y + P.h / 2;
      const s = 0.7 + 0.3 * k;
      for (const ctx of [c, this.glowAt(push)]) {
        if (!ctx) continue;
        const glow = ctx !== c;
        ctx.save();
        ctx.globalAlpha = clamp(k * 2) * ex;
        ctx.translate(cx, cy);
        ctx.scale(s, s);
        ctx.translate(-cx, -cy);
        ctx.fillStyle = glow ? glowInk(color, 0.28) : rgba(color);
        ctx.beginPath();
        ctx.roundRect(P.x, P.y, P.w, P.h, P.h / 2);
        ctx.fill();
        if (!glow) {
          // the sheen: a soft band of light crossing the pill once it has landed
          const u = prog(t, this.ctaAt + 0.25, this.ctaAt + 1.05, ease.inOutCubic);
          if (u > 0 && u < 1) {
            ctx.save();
            ctx.beginPath();
            ctx.roundRect(P.x, P.y, P.w, P.h, P.h / 2);
            ctx.clip();
            const sx = P.x - P.h + (P.w + 2 * P.h) * u;
            const grad = ctx.createLinearGradient(sx - P.h, 0, sx + P.h, 0);
            grad.addColorStop(0, 'rgba(255,255,255,0)');
            grad.addColorStop(0.5, 'rgba(255,255,255,0.32)');
            grad.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = grad;
            ctx.fillRect(P.x, P.y, P.w, P.h);
            ctx.restore();
          }
        }
        // the label and its arrow (on the glow layer: cut out, so they stay crisp on the lit pill)
        if (glow) ctx.globalCompositeOperation = 'destination-out';
        const paint = glow ? '#000' : rgba(ink);
        ctx.fillStyle = paint;
        ctx.font = font(P.fam, P.fs);
        ctx.textBaseline = 'middle';
        const tx = P.x + 1.05 * P.fs;
        ctx.fillText(P.label, tx, cy + 0.04 * P.fs);
        if (this.p('arrow', true)) {
          const ax = tx + measure(P.label, P.fam, P.fs) + 0.45 * P.fs, aw = 0.62 * P.fs;
          const nudge = 0.12 * P.fs * Math.max(0, Math.sin(Math.PI * prog(t, this.ctaAt + 0.9, this.ctaAt + 1.3)));
          ctx.strokeStyle = paint;
          ctx.lineWidth = Math.max(2, 0.085 * P.fs);
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          ctx.beginPath();
          ctx.moveTo(ax + nudge, cy);
          ctx.lineTo(ax + aw + nudge, cy);
          ctx.moveTo(ax + aw * 0.6 + nudge, cy - aw * 0.38);
          ctx.lineTo(ax + aw + nudge, cy);
          ctx.lineTo(ax + aw * 0.6 + nudge, cy + aw * 0.38);
          ctx.stroke();
        }
        ctx.restore();
      }
    }
    const U = this.urlAt;
    if (U.text) {
      const n = fx.typedCount(t, this.urlStart, 34, Array.from(U.text).length);
      if (n > 0) {
        c.save();
        c.globalAlpha = ex;
        c.font = font(U.fam, U.fs);
        c.fillStyle = rgba('fgDim');
        c.fillText(Array.from(U.text).slice(0, n).join(''), U.x, U.y);
        c.restore();
      }
    }
  }
}

export default EndCard;
