// What a media block draws: an image, or a clip's frames. openSource(src) opens either.
// - 'frames/<name>' opens a rendered sequence from out/<film>/media/<name>/meta.json (no clip in assets/); meta.json's
//   optional "ext" ("png" for lossless line art; default "jpg") names the frame files, and count 1 is a still. A
//   missing meta.json fails an export, naming the path; the player warns and draws nothing.
// - An image (png, jpg, webp, svg) decodes once at init.
// - A clip plays from its extracted frames (paths.ts: scripts/media.ts writes them to out/<film>/media/<name>/), loaded
//   through prepare(t) into a small LRU, as plates are (plates.ts): export awaits them, so every frame is exact, and
//   a frame that was not prepared fails the export. Without extracted frames, the player (not an export) falls back to
//   an HTMLVideoElement seeked to the clip time, best effort; an export fails naming the command that extracts them.
import { FPS, filmUrl, outUrl } from '../../engine/config';
import { LRU } from '../../engine/plates';
import { clipFrame, framePath, framesName, isFrames, isVideo, mediaName } from './paths';

/** A drawable frame and its size in px. */
export interface Picture { el: CanvasImageSource; width: number; height: number }

export interface MediaSource {
  /** The media's size in px. */
  readonly width: number;
  readonly height: number;
  /** Load what frame(t) needs. */
  prepare(t: number): Promise<void>;
  /** The picture at film time t (null while a clip's frame is still loading in the player). */
  frame(t: number): Picture | null;
  dispose(): void;
}

export interface ClipOpts {
  /** The shot's id (for errors) and its start (film s): the clip's `offset` plays then. */
  id: string;
  start: number;
  rate?: number;
  offset?: number;
  loop?: boolean;
}

const pageHas = (k: string) => typeof location !== 'undefined' && new URLSearchParams(location.search).has(k);

async function loadImage(url: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.decoding = 'async';
  img.src = url;
  await img.decode();
  return img;
}

class ImageSource implements MediaSource {
  constructor(private img: HTMLImageElement | null) {}
  get width() { return this.img?.naturalWidth ?? 1; }
  get height() { return this.img?.naturalHeight ?? 1; }
  async prepare() {}
  frame(): Picture | null {
    return this.img ? { el: this.img, width: this.img.naturalWidth, height: this.img.naturalHeight } : null;
  }
  dispose() {
    if (this.img) this.img.src = '';
    this.img = null;
  }
}

interface Meta { fps: number; count: number; width: number; height: number; ext?: string }

class FrameSource implements MediaSource {
  private cache = new LRU<number, HTMLImageElement>(pageHas('export') ? 4 : 12, (img) => { img.src = ''; });
  private pending = new Map<number, Promise<HTMLImageElement>>();
  private disposed = false;
  private readonly exporting = pageHas('export');

  constructor(private name: string, private meta: Meta, private o: ClipOpts) {}
  get width() { return this.meta.width; }
  get height() { return this.meta.height; }

  index(t: number) {
    return clipFrame(t, { start: this.o.start, offset: this.o.offset, rate: this.o.rate, loop: this.o.loop, fps: this.meta.fps, count: this.meta.count, filmFps: FPS });
  }

  async prepare(t: number) {
    const i = this.index(t);
    const own = this.fetch(i);
    if (!this.exporting) for (let k = 1; k <= 3; k++) this.fetch((i + k) % this.meta.count).catch(() => {});
    await own;
  }

  frame(t: number): Picture | null {
    const i = this.index(t);
    let img = this.cache.get(i);
    if (!img) {
      if (this.exporting) throw new Error(`shot ${this.o.id}: clip ${this.name} frame ${i} was not prepared (the block awaits it in prepare(t))`);
      // the player: the nearest frame it has
      let best: number | undefined;
      for (const k of this.cache.keys()) if (best === undefined || Math.abs(k - i) < Math.abs(best - i)) best = k;
      img = best === undefined ? undefined : this.cache.get(best);
      if (!img) return null;
    }
    return { el: img, width: this.meta.width, height: this.meta.height };
  }

  private fetch(i: number): Promise<HTMLImageElement> {
    const have = this.cache.get(i);
    if (have) return Promise.resolve(have);
    let p = this.pending.get(i);
    if (!p) {
      const url = outUrl(framePath(this.name, i, this.meta.ext));
      p = loadImage(url).then(
        (img) => {
          this.pending.delete(i);
          if (this.disposed) img.src = '';
          else this.cache.set(i, img);
          return img;
        },
        (err) => {
          this.pending.delete(i);
          throw new Error(`shot ${this.o.id}: clip frame ${url} did not load (${(err as Error)?.message ?? err})`);
        },
      );
      this.pending.set(i, p);
    }
    return p;
  }

  dispose() {
    this.disposed = true;
    this.cache.clear();
  }
}

/** The player's fallback for a clip with no extracted frames: an HTMLVideoElement seeked to the clip time. */
class VideoElementSource implements MediaSource {
  constructor(private v: HTMLVideoElement | null, private o: ClipOpts) {}
  get width() { return this.v?.videoWidth || 1; }
  get height() { return this.v?.videoHeight || 1; }
  async prepare() {}
  frame(t: number): Picture | null {
    const v = this.v;
    if (!v) return null;
    const d = v.duration || 1;
    let ct = (this.o.offset ?? 0) + (t - this.o.start) * (this.o.rate ?? 1);
    ct = this.o.loop ?? true ? ((ct % d) + d) % d : Math.max(0, Math.min(d - 0.001, ct));
    if (!v.seeking && Math.abs(v.currentTime - ct) > 0.5 / FPS) v.currentTime = ct;
    return v.readyState >= 2 ? { el: v, width: v.videoWidth, height: v.videoHeight } : null;
  }
  dispose() {
    if (this.v) {
      this.v.removeAttribute('src');
      this.v.load();
    }
    this.v = null;
  }
}

/** Open a block's `src` (a path in the film's folder, a URL, or 'frames/<name>'): an image, or a clip's frames. */
export async function openSource(src: string, o: ClipOpts): Promise<MediaSource> {
  if (isFrames(src)) {
    const name = framesName(src);
    const metaUrl = outUrl(`media/${name}/meta.json`);
    const meta: Meta | null = await fetch(metaUrl).then((r) => (r.ok ? r.json() : null), () => null);
    if (meta && meta.count > 0) return new FrameSource(name, meta, o);
    if (pageHas('export')) throw new Error(`shot ${o.id}: frames ${src} has no ${metaUrl} (render the sequence into out/<film>/media/${name}/ with a meta.json)`);
    console.warn(`shot ${o.id}: frames ${src} has no ${metaUrl}; drawing nothing`);
    return new ImageSource(null);
  }
  if (!isVideo(src)) {
    try {
      return new ImageSource(await loadImage(filmUrl(src)));
    } catch {
      throw new Error(`shot ${o.id}: image ${filmUrl(src)} did not load`);
    }
  }
  const name = mediaName(src);
  const metaUrl = outUrl(`media/${name}/meta.json`);
  const meta: Meta | null = await fetch(metaUrl).then((r) => (r.ok ? r.json() : null), () => null);
  if (meta && meta.count > 0) return new FrameSource(name, meta, o);
  const how = `extract its frames: cd app && bun scripts/media.ts --film <id> (writes ${metaUrl})`;
  if (pageHas('export')) throw new Error(`shot ${o.id}: clip ${src} has no extracted frames; ${how}`);
  console.warn(`shot ${o.id}: clip ${src} has no extracted frames, playing it through a <video> (best effort); ${how}`);
  const v = document.createElement('video');
  v.muted = true;
  v.playsInline = true;
  v.preload = 'auto';
  v.crossOrigin = 'anonymous';
  v.src = filmUrl(src);
  await new Promise<void>((res) => {
    v.addEventListener('loadeddata', () => res(), { once: true });
    v.addEventListener('error', () => res(), { once: true });
  });
  return new VideoElementSource(v, o);
}
