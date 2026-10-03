// 01 `thread`: the cold open. The thread hums under the heartbeat from the moment its light comes up; it frays on
// "forgets"; on "zero" it snaps, and the sound cuts to near-silence for two frames (the music ducks out, the hum is
// gone with the thread) before the freed fibres' breath plays the recoil out.
import { cue, event, word, type SceneCues } from '../cue';
import { threadTimes } from '../../scenes/thread-time';

const FRAME = 1 / 30;
/** The near-silence after the snap (spec §4 01): two frames. */
const HUSH = 2 * FRAME;

const thread: SceneCues = (c) => {
  // (her word first: a cue whose word was edited away names it, before the scene's own clock does)
  const forgets = word(c, 'L01', 'forgets');
  const s = c.scene, T = threadTimes(c.vo, c.audio, s.start, s.end);
  const on = event(c, 'light-on', T.lightOn), snap = event(c, 'snap', T.snap);
  return [
    cue('thread_hum', on, { dur: T.snap - T.lightOn }),
    cue('fray_crackle', forgets),
    cue('thread_snap', snap),
    // the music (and only the music: the snap's own crack must carry) drops to near-silence for two frames
    { kind: 'duck', t: T.snap, dur: HUSH, depth: -30, fade: 0.005, bus: 'music', anchor: snap.anchor },
    cue('fibre_whoosh', event(c, 'snap+2f', T.snap + HUSH), { gain: -3 }),
  ];
};
export default thread;
