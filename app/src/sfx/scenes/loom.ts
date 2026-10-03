// 05 `loom`: the four tiers, woven. The shuttle clacks into its box on every beat (the tracked shuttle's landings, each
// held to its beat) and swishes through the shed mid-flight; the incidents fray and the gc stamp lands on "let go"; the
// rules warps creak tight as she names them and jolt on "break"; the skills lane lights with a shimmer when the shuttle
// first reaches it.
import { cue, event, onBeat, word, type Cue, type SceneCues } from '../cue';
import { loomTimes, reachTime, shuttlePasses } from '../../scenes/loom-time';

const SHOT = 'b05_loom';
const FRAME = 1 / 30;

const loom: SceneCues = (c) => {
  const s = c.scene, T = loomTimes(c.vo, c.audio, s.start, s.end), track = c.track(SHOT);
  const out: Cue[] = [];
  const passes = shuttlePasses(track);
  passes.forEach(({ depart, land, dir }, k) => {
    // each landing is on a beat (the plate's clock): the clack goes on the beat itself, within a frame of the picture's
    const beat = c.audio.beats.reduce((best, b) => (Math.abs(b - land) < Math.abs(best - land) ? b : best), Infinity);
    if (!(Math.abs(beat - land) <= FRAME + 1e-9)) throw new Error(`loom: the shuttle lands at ${land.toFixed(3)}, off the beat by more than a frame`);
    // the swish through the shed, mid-flight
    if (depart !== null) out.push(cue('weave_swish', event(c, `pick${k}`, (depart + land) / 2), { gain: -4, pan: 0.15 * dir }));
    out.push(cue('shuttle_clack', onBeat(c, beat), { pan: 0.3 * dir }));
  });
  // "Incidents… I let go.": the oldest rows fray and let go, and the gc stamp lands as the first does
  out.push(cue('fray_crackle', event(c, 'release', T.release[0]!), { gain: -2 }));
  out.push(cue('stamp', event(c, 'gc', T.release[0]!), { gain: -3, pan: 0.2 }));
  // "Rules": the slack warps pulled tight; "break": the jolt that rings through them
  out.push(cue('rope_creak', word(c, 'L13', 'rules')));
  out.push(cue('rope_creak', word(c, 'L13', 'break'), { gain: -8 }));
  // the skills warps light as the shuttle first flies into their lane
  out.push(cue('heal_shimmer', event(c, 'skills-reach', reachTime(track, T.tier.skills))));
  return out;
};
export default loom;
