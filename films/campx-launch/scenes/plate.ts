// A Blender plate scene (open, ingest3d, read3d, mark3d): composites out/<film>/plates/<shot>/ when its frames exist,
// else shows a placeholder, a real answer sheet on a slow push, so the cut is watchable before the plates land.
// Engine overlays that belong to the scene are drawn here, over the plate (mark3d: the "Suggested · 7 / 8" mark).
//
// params: shot (default the scene id), variant ('rise' | 'push' | 'scan'), sheet (asset), overlay ('mark')
import type { THREE } from '@engine/three';
import { Scene, disposeLayer, type Frame } from '@engine/scene';
import { Layer2D, W, H, clearRT } from '@engine/gl';
import { FPS, FILM_ID, outUrl } from '@engine/config';
import { LIN, HEX, rgba } from '@engine/palette';
import { Plate, plateUrl } from '@engine/plates';
import { F, font } from '@engine/type';
import { spring } from '@engine/motion';
import { ease, lerp, prog } from '@engine/util';
import { dropImg, loadImg, spoken, wordAt } from './common';

const inExport = () => typeof location !== 'undefined' && new URLSearchParams(location.search).has('export');

async function hasPlate(shot: string, count: number): Promise<boolean> {
  // a spread of the shot's frame files, EXR in an export and the proxy in the player (a plate still rendering has
  // the first, not the last, and is not used yet); the dev server answers a missing path with its page, which is HTML
  const has = async (i: number) => {
    try {
      const r = await fetch(plateUrl(shot, i, inExport() ? 'exr' : 'proxy'), { method: 'HEAD' });
      return r.ok && !(r.headers.get('content-type') ?? '').includes('text/html');
    } catch {
      return false;
    }
  };
  // (sampled across the shot: look renders write a few frames of it, not all)
  const probe = [0, 1, count >> 2, count >> 1, (3 * count) >> 2, count - 2, count - 1];
  return (await Promise.all(probe.map(has))).every(Boolean);
}

export default class PlateScene extends Scene {
  private plate: Plate | null = null;
  private sheet: HTMLImageElement | null = null;
  private layer = new Layer2D();
  private glowLayer = new Layer2D();

  private get shot() {
    return (this.ctx.params.shot as string | undefined) ?? this.ctx.id;
  }

  override async init() {
    const f0 = Math.round(this.ctx.start * FPS), count = Math.round((this.ctx.end - this.ctx.start) * FPS);
    if (await hasPlate(this.shot, count)) {
      this.plate = new Plate(this.shot, f0, { count });
    } else {
      console.warn(`[${FILM_ID}] no plate for ${this.shot} (${outUrl('plates/' + this.shot)}): showing the placeholder`);
      this.sheet = await loadImg((this.ctx.params.sheet as string | undefined) ?? 'assets/sheets/hires_38189_p02.jpg');
    }
  }

  override async prepare(t: number) {
    await this.plate?.prepare(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp } = this.ctx;
    clearRT(renderer, out, LIN.bg);
    const L = this.layer, c = L.ctx, G = this.glowLayer, g = G.ctx;
    L.clear();
    G.clear();
    if (this.plate) this.plate.draw(renderer, comp, out, f.t);
    else this.placeholder(c, f);
    if (this.ctx.params.overlay === 'mark') this.markOverlay(c, g, f);
    comp.draw(renderer, L.upload(), out);
    comp.draw(renderer, G.upload(), out, { mode: 'add', tint: [2.5, 2.5, 2.5] });
  }

  /** The sheet in a pool of warm light, on a slow push: rises from the dark ('rise'), or just pushes. */
  private placeholder(c: CanvasRenderingContext2D, f: Frame) {
    const img = this.sheet!, p = f.p, variant = (this.ctx.params.variant as string | undefined) ?? 'push';
    const u = Math.min(W, H) / 1080;
    const light = c.createRadialGradient(W / 2, H * 0.55, 0, W / 2, H * 0.55, H * 0.95);
    light.addColorStop(0, rgba('surface2', 0.95));
    light.addColorStop(1, rgba('bg', 0));
    c.fillStyle = light;
    c.fillRect(0, 0, W, H);
    const rise = variant === 'rise' ? 1 - ease.outCubic(prog(f.lt, 0.5, 5)) : 0;
    const h = H * lerp(0.86, 0.95, p) * (1 + 0.0), w = h * (img.naturalWidth / img.naturalHeight);
    const x = (W - w) / 2, y = (H - h) / 2 + rise * H * 0.22;
    c.save();
    c.shadowColor = 'rgba(0,0,0,0.6)';
    c.shadowBlur = 60 * u;
    c.shadowOffsetY = 24 * u;
    c.globalAlpha = variant === 'rise' ? ease.outCubic(prog(f.lt, 0, 2.2)) : 1;
    c.drawImage(img, x, y, w, h);
    c.restore();
    if (variant === 'scan') {
      const sy = y + h * ease.inOutCubic(prog(f.lt, 0.6, f.end - f.start - 0.6));
      const gr = c.createLinearGradient(0, sy - 60 * u, 0, sy + 4 * u);
      gr.addColorStop(0, 'rgba(0,0,0,0)');
      gr.addColorStop(1, rgba('accentBright', 0.35));
      c.fillStyle = gr;
      c.fillRect(x, sy - 60 * u, w, 64 * u);
      c.fillStyle = rgba('accentBright', 0.9);
      c.fillRect(x, sy, w, 2 * u);
    }
    // the light over it all
    const v = c.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, rgba('bg', 0.8));
    c.fillStyle = v;
    c.fillRect(0, 0, W, H);
    // fade up from black
    c.fillStyle = rgba('bg', 1 - ease.outCubic(prog(f.lt, 0, 1.2)));
    c.fillRect(0, 0, W, H);
  }

  /** "Suggested · 7 / 8": the engine's mark, springing in on "suggests" so it has settled by "a mark" (params.markAt, in scene seconds, overrides). */
  private markOverlay(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, f: Frame) {
    const u = Math.min(W, H) / 1080;
    const at = (this.ctx.params.markAt as number | undefined)
      ?? wordAt(spoken(this.ctx), 'suggests', this.ctx.start + 5.1) + 0.15 - this.ctx.start;
    const lt = f.lt - at;
    if (lt < 0) return;
    const k = Math.min(1.15, spring(lt, 3, 0.7)), a = Math.min(1, lt * 5);
    const cx = W * 0.73, cy = H * 0.13;
    const label = 'Suggested', val = '7 / 8';
    c.save();
    c.translate(cx, cy);
    c.scale(0.86 + 0.14 * k, 0.86 + 0.14 * k);
    c.globalAlpha = a;
    c.font = font(F.display(87.5, 500), 30 * u);
    c.letterSpacing = `${(2 * u).toFixed(1)}px`;
    const wl = c.measureText(label).width;
    c.font = font(F.display(87.5, 800), 64 * u);
    c.letterSpacing = '0px';
    const wv = c.measureText(val).width;
    const gap = 26 * u, padX = 34 * u, h = 104 * u, dot = 12 * u;
    const w = padX * 2 + dot + 18 * u + wl + gap + wv;
    // the pill: glass over the plate, a hairline in the accent
    c.beginPath();
    c.roundRect(-w / 2, -h / 2, w, h, h / 2);
    c.fillStyle = rgba('surface', 0.82);
    c.fill();
    c.lineWidth = 1.5 * u;
    c.strokeStyle = rgba('accentBright', 0.75);
    c.stroke();
    let x = -w / 2 + padX;
    c.beginPath();
    c.arc(x + dot / 2, 0, dot / 2, 0, Math.PI * 2);
    c.fillStyle = rgba('accentBright');
    c.fill();
    x += dot + 18 * u;
    c.textBaseline = 'middle';
    c.font = font(F.display(87.5, 500), 30 * u);
    c.letterSpacing = `${(2 * u).toFixed(1)}px`;
    c.fillStyle = rgba('fgDim');
    c.fillText(label, x, 2 * u);
    c.letterSpacing = '0px';
    c.font = font(F.display(87.5, 800), 64 * u);
    c.fillStyle = rgba('fg');
    c.fillText(val, x + wl + gap, 2 * u);
    c.restore();
    // its light
    g.save();
    g.translate(cx, cy);
    g.globalAlpha = a * 0.5;
    g.beginPath();
    g.arc(-w / 2 + padX + dot / 2, 0, dot / 2, 0, Math.PI * 2);
    g.fillStyle = HEX.accentBright;
    g.shadowColor = HEX.accentBright;
    g.shadowBlur = 30 * u;
    g.fill();
    g.restore();
  }

  override dispose() {
    this.plate?.dispose();
    dropImg(this.sheet);
    disposeLayer(this.layer);
    disposeLayer(this.glowLayer);
  }
}
