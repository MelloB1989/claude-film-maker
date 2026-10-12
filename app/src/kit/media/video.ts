// Video: a clip from the film's folder, framed and moved exactly as Image is (frame.ts), playing frame-exact in export.
//
// The workflow: put the clip in films/<id>/assets/ and extract it once at the film's frame rate:
//   cd app && bun scripts/media.ts --film <id>          (every clip in assets/; --src assets/x.mp4 for one)
// which writes out/<id>/media/<name>/####.jpg and meta.json (out/ is never committed). The block loads the frames a
// frame needs in prepare(t), as plates are loaded, so an export shows exactly the clip frame for each film frame
// (a frame missing fails it). Without extracted frames the player falls back to a <video> element (best effort) and
// an export fails, naming the command.
//
// Params: every Image param (src 'assets/clip.mp4', fit, from/to (default no push for a clip), radius, shadow,
// border, entry, drift...), and
//   clipStart 0       the clip's time (s) at the shot's start
//   rate 1            playback speed (0.5: half speed)
//   loop true         loop the clip (false: hold its last frame)
import { Image } from './image';

export class Video extends Image {
  protected override defaults: Record<string, unknown> = { to: { zoom: 1 } };
}

export default Video;
