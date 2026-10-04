// Blender plates: a shot's rendered frames, for a scene to composite (blender/render.py writes them).
//
// Each frame of a plate is a file named by its index in the plate, #### = film frame - f0 (the plate's first film
// frame), in two forms (blender/lib/export.py):
//   out/plates/<shot>/####.exr          linear half-float RGBA, premultiplied: the plate itself (served at /out/plates/)
//   public/plates/<shot>/proxy/####.png 8-bit sRGB at 960x540 (half the film's 1920x1080): the preview's stand-in
//
// Frame mapping (Review Focus 4): the plate frame for film time t is round(t * 30) - f0, rounded as the engine rounds
// (frameIdx), so plate frame n is on screen for exactly film frame n. Every motion-blur sub-frame of a frame (a shutter
// of at most one frame) maps to that frame's plate: the plate carries Blender's motion blur already.
//
// Export awaits `prepare(t)` before every frame (Scene.prepare, Engine.prepare), and `texture(t)` is then exactly that
// frame, or it throws: a plate never silently shows a neighbour in a render. It composites the EXR or fails: the
// proxy (8-bit, clipped at 1, so its blood and moss cores stop blooming; upscaled 2x) stands in only when the export
// opts into it (render.ts --proxies, a draft). The player prepares best-effort and shows the nearest frame it has
// while the right one loads.
import * as THREE from 'three';
import { EXRLoader } from 'three/examples/jsm/loaders/EXRLoader.js';
import { PH, PW, type BlendMode, type Compositor } from './gl';
import { frameIdx } from './util';

export type PlateKind = 'exr' | 'proxy';
/** 'export': exact frames or an error, EXR first. 'preview': best effort, proxies. */
export type PlateMode = 'export' | 'preview';

/** The plate frame (file index) for film time t: film frame round(t * 30) minus the plate's first film frame. */
export function plateIndex(t: number, f0: number): number {
  return frameIdx(t) - f0;
}

/** Where frame i of a shot's plate is served (relative to the page, like data/ and audio/). */
export function plateUrl(shot: string, i: number, kind: PlateKind): string {
  const n = String(i).padStart(4, '0');
  return kind === 'exr' ? `out/plates/${shot}/${n}.exr` : `plates/${shot}/proxy/${n}.png`;
}

/** A small least-recently-used map: `get` refreshes an entry, and `set` past the cap evicts the stalest. */
export class LRU<K, V> {
  private m = new Map<K, V>(); // in use order: least recent first

  constructor(readonly cap: number, private onEvict?: (v: V, k: K) => void) {}

  get(k: K): V | undefined {
    const v = this.m.get(k);
    if (v !== undefined) {
      this.m.delete(k);
      this.m.set(k, v);
    }
    return v;
  }

  set(k: K, v: V) {
    this.m.delete(k);
    this.m.set(k, v);
    while (this.m.size > this.cap) {
      const [k0, v0] = this.m.entries().next().value as [K, V];
      this.m.delete(k0);
      this.onEvict?.(v0, k0);
    }
  }

  has(k: K) {
    return this.m.has(k);
  }

  /** Keys from the least to the most recently used. */
  keys(): K[] {
    return [...this.m.keys()];
  }

  clear() {
    for (const [k, v] of this.m) this.onEvict?.(v, k);
    this.m.clear();
  }
}

const exrLoader = new EXRLoader().setDataType(THREE.HalfFloatType);
const pngLoader = new THREE.TextureLoader();

/**
 * Loads one plate file as a texture. The EXR comes out linear, half float and upright (EXRLoader flips its rows), with
 * Blender's premultiplied alpha; the proxy decodes from sRGB when sampled, with straight alpha.
 * `userData.premultiplied` says which.
 */
export async function loadPlateTexture(url: string, kind: PlateKind): Promise<THREE.Texture> {
  if (kind === 'exr') {
    const tex = await exrLoader.loadAsync(url);
    tex.userData.premultiplied = true;
    return tex;
  }
  const tex = await pngLoader.loadAsync(url);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.userData.premultiplied = false;
  return tex;
}

export interface PlateOpts {
  /** Default: 'export' when the page runs with ?export (render.ts), else 'preview'. */
  mode?: PlateMode;
  /** The plate's frame count, when known: times before it hold frame 0 and times after it the last frame. */
  count?: number;
  /**
   * Textures kept, each a decoded frame in CPU and GPU memory (a 2560x1440 EXR: 28 MiB of each). Default 8 in preview;
   * 3 in export, which needs only the frame's own plate frames between its prepare() and its render(): 30·shutter/fps
   * plate frames pass per film frame, so one at 30 fps and up to three at 24 or 25 fps with a shutter over 0.8
   * (engine.test.ts checks fps 24 to 60 with shutters to 1). The scene's dispose() releases them all.
   */
  cap?: number;
  /** Frames loaded ahead of the prepared one in preview (default 2; export loads only what it renders). */
  ahead?: number;
  /**
   * Export: composite a frame's 960x540 proxy where its EXR is missing, warning once (a draft). Default: the page's
   * ?proxies (render.ts --proxies). Otherwise a missing EXR fails the export.
   */
  proxies?: boolean;
  /** The output size in px (default the engine's, PW x PH): export warns once when a plate is smaller (upscaled). */
  output?: [number, number];
  /** Loads one frame file (default loadPlateTexture). */
  load?: (url: string, kind: PlateKind) => Promise<THREE.Texture>;
}

const pageHas = (k: string) => typeof location !== 'undefined' && new URLSearchParams(location.search).has(k);

export class Plate {
  readonly mode: PlateMode;
  private count?: number;
  private ahead: number;
  private proxies: boolean;
  private output: [number, number];
  private load: (url: string, kind: PlateKind) => Promise<THREE.Texture>;
  private cache: LRU<number, THREE.Texture>;
  private pending = new Map<number, Promise<THREE.Texture>>();
  private warned = false;
  private warnedSize = false;
  private disposed = false;

  /** `f0`: the plate's first film frame (the shot's, as blender/render.py rendered it). */
  constructor(readonly shot: string, readonly f0: number, o: PlateOpts = {}) {
    this.mode = o.mode ?? (pageHas('export') ? 'export' : 'preview');
    this.count = o.count;
    this.ahead = o.ahead ?? (this.mode === 'preview' ? 2 : 0);
    this.proxies = o.proxies ?? pageHas('proxies');
    this.output = o.output ?? [PW, PH];
    this.load = o.load ?? loadPlateTexture;
    this.cache = new LRU(o.cap ?? (this.mode === 'export' ? 3 : 8), (tex) => tex.dispose());
  }

  /** The plate frame shown at film time t (clamped into the plate when its count is known, else at 0). */
  index(t: number): number {
    const i = Math.max(0, plateIndex(t, this.f0));
    return this.count === undefined ? i : Math.min(i, this.count - 1);
  }

  /** Load the frame for t (and, in preview, a few ahead). Resolves once texture(t) has it. */
  async prepare(t: number): Promise<void> {
    const i = this.index(t);
    const own = this.fetch(i);
    for (let k = 1; k <= this.ahead; k++) {
      if (this.count === undefined || i + k < this.count) this.fetch(i + k).catch(() => {}); // best effort
    }
    await own;
  }

  /** The frame for t. Export: exactly it, or an error. Preview: it, else the nearest loaded frame (the earlier on a tie), else null. */
  texture(t: number): THREE.Texture | null {
    const i = this.index(t);
    const tex = this.cache.get(i);
    if (tex) return tex;
    if (this.mode === 'export') {
      throw new Error(`plate ${this.shot} frame ${i} (film frame ${this.f0 + i}) not prepared: the scene must await plate.prepare(t) in its prepare()`);
    }
    let best: number | undefined;
    for (const k of this.cache.keys()) {
      const d = Math.abs(k - i), bd = best === undefined ? Infinity : Math.abs(best - i);
      if (d < bd || (d === bd && k < best!)) best = k;
    }
    return best === undefined ? null : this.cache.get(best)!;
  }

  /**
   * Composite the frame for t into `out` (linear light): `replace` (the default) makes the plate the whole picture,
   * `normal` lays it over what is there by its alpha. Returns false when there is nothing to show yet (preview).
   */
  draw(renderer: THREE.WebGLRenderer, comp: Compositor, out: THREE.WebGLRenderTarget, t: number, o: { mode?: BlendMode; opacity?: number } = {}): boolean {
    const tex = this.texture(t);
    if (!tex) return false;
    comp.draw(renderer, tex, out, { mode: o.mode ?? 'replace', opacity: o.opacity ?? 1, premult: !tex.userData.premultiplied, space: 'linear' });
    return true;
  }

  /** Releases every frame it holds; one still loading is released when it lands. */
  dispose() {
    this.disposed = true;
    this.cache.clear();
  }

  private fetch(i: number): Promise<THREE.Texture> {
    const have = this.cache.get(i);
    if (have) return Promise.resolve(have);
    let p = this.pending.get(i);
    if (!p) {
      p = this.loadFrame(i).then(
        (tex) => {
          this.pending.delete(i);
          if (this.disposed) tex.dispose();
          else this.cache.set(i, tex);
          return tex;
        },
        (err) => {
          this.pending.delete(i);
          throw err;
        },
      );
      this.pending.set(i, p);
    }
    return p;
  }

  private async loadFrame(i: number): Promise<THREE.Texture> {
    const png = plateUrl(this.shot, i, 'proxy');
    if (this.mode === 'preview') return this.load(png, 'proxy');
    const exr = plateUrl(this.shot, i, 'exr');
    let tex: THREE.Texture;
    try {
      tex = await this.load(exr, 'exr');
    } catch (err) {
      const at = `plate ${this.shot} frame ${i} (film frame ${this.f0 + i})`;
      if (!this.proxies) {
        throw new Error(`${at}: no ${exr} (${(err as Error)?.message ?? err}); render it (blender/render.py --shot ${this.shot}), or pass --proxies to composite its 960x540 proxy`);
      }
      try {
        tex = await this.load(png, 'proxy');
      } catch {
        throw new Error(`${at} is missing: no ${exr} and no ${png} (render it: blender/render.py --shot ${this.shot})`);
      }
      if (!this.warned) {
        this.warned = true;
        console.warn(`plate ${this.shot}: no EXR for frame ${i} (${exr}), compositing the 960x540 proxy (--proxies)`);
      }
    }
    const img = tex.image as { width?: number; height?: number } | undefined;
    const [ow, oh] = this.output;
    if (!this.warnedSize && img?.width && img.height && (img.width < ow || img.height < oh)) {
      this.warnedSize = true;
      console.warn(`plate ${this.shot} is ${img.width}x${img.height}, smaller than the ${ow}x${oh} output: it is upscaled`);
    }
    return tex;
  }
}
