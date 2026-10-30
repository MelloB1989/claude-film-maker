// Where a clip's extracted frames live, and which frame shows when: pure, shared by the Video block and
// scripts/media.ts (the extractor), and tested by bun.
//
// The media workflow: a clip in a film's folder (films/<id>/assets/clip.mp4) is extracted once, at the film's frame
// rate, by `cd app && bun scripts/media.ts --film <id>` into out/<id>/media/<name>/####.jpg (frame 0 first) with a
// meta.json { fps, count, width, height, src }; out/ is never committed. The block loads the frames it needs through
// prepare(t), so every exported frame shows exactly its clip frame, whatever the browser can decode.
//
// A sequence rendered straight into out/<id>/media/<name>/ (Blender, say) needs no clip: a block `src` of 'frames/<name>'
// (no extension) opens it from that folder's meta.json. Its frames may be lossless PNG: meta.json then carries
// "ext": "png" (absent: "jpg", as the extractor writes). One frame is a still.

/** The extensions taken for clips (anything else is an image). */
export const VIDEO_EXT = /\.(mp4|m4v|mov|webm|mkv)$/i;

export const isVideo = (src: string) => VIDEO_EXT.test(src);

/** A `src` naming a rendered image sequence, not a file: 'frames/<name>' (no extension). */
export const FRAMES_SRC = /^frames\/[^/\\.]+$/;

export const isFrames = (src: string) => FRAMES_SRC.test(src);

/** The frames folder name of a 'frames/<name>' src. */
export const framesName = (src: string) => src.slice('frames/'.length);

/** A clip's frames folder name: its path in the film's folder without `assets/` and its extension, `/` as `__`. */
export function mediaName(src: string): string {
  return src.replace(/^\.\//, '').replace(/^assets\//, '').replace(/\.[^./]+$/, '').replace(/[/\\]+/g, '__');
}

/** A clip frame's path under out/<film>/ (outUrl takes it): media/<name>/0042.jpg (`ext` from meta.json, default jpg). */
export const framePath = (name: string, i: number, ext = 'jpg') => `media/${name}/${String(i).padStart(4, '0')}.${ext}`;

/**
 * The clip frame on screen at film time t: the clip runs from `offset` s of itself at the shot's `start`, at `rate`,
 * looping or holding its last frame. Read on the film's frame grid (`filmFps`): every motion-blur sub-frame of a film
 * frame shows the same clip frame, as a plate does (plates.ts).
 */
export function clipFrame(t: number, o: { start: number; offset?: number; rate?: number; loop?: boolean; fps: number; count: number; filmFps: number }): number {
  const tf = Math.round(t * o.filmFps) / o.filmFps;
  const ct = (o.offset ?? 0) + (tf - o.start) * (o.rate ?? 1);
  const n = Math.round(ct * o.fps + 1e-6);
  if (o.count <= 0) return 0;
  if (o.loop ?? true) return ((n % o.count) + o.count) % o.count;
  return Math.max(0, Math.min(o.count - 1, n));
}
