// 03 `her`: "Not me." After the hard cut, one silent beat (the music ducks out); the two ends swell back together and
// click shut on "Not"; the camera whips onto the bead, which lands on the downbeat after "me."; the hard cut to the
// headline strikes its − line; the + lines type in with her, their hero words slamming in; on "blame" the gutter slides
// in.
import { cue, event, onBeat, onDownbeat, typing, word, type Cue, type Duck, type SceneCues } from '../cue';
import { BLAME_GUTTER, HEROES, PLUS_WORDS, STRIKE, flatShown, plusTimes, timesOf } from '../../scenes/her-time';

const her: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const out: (Cue | Duck)[] = [];
  // ex → her (spec §4 03): a hard cut to black on the downbeat, then one silent beat
  const cut = onBeat(c, s.start), i = Number(cut.anchor.slice(5));
  out.push({ kind: 'duck', t: s.start, dur: c.audio.beats[i + 1]! - s.start, depth: -24, fade: 0.03, bus: 'music', anchor: 'cut:ex-her' });
  // the re-form: the swell ends as the ends click shut on "Not"
  out.push(cue('reform_swell', word(c, 'L06', 'not')));
  // the whip along the thread onto the bead, centred on the downbeat after "me.", where the bead lands
  const down = onDownbeat(c, T.down);
  out.push(cue('whoosh_whip', down, { gain: -2 }));
  out.push(cue('commit_thock', down));
  // the hard cut to the headline on the next beat: the strike runs through the − line
  out.push(cue('pen_strike', event(c, 'strike', T.beatAfterDown + STRIKE.at), { gain: -6, pan: -0.2 }));
  // the + lines: the flat words type in with her (a letter a frame), the hero words slam in on her onsets
  plusTimes(T).forEach((ats, li) => {
    PLUS_WORDS[li]!.forEach((w, wi) => {
      if (HEROES.includes(wi)) return;
      const n = Array.from(w).length, at = ats[wi]!;
      out.push(...typing(`her:plus${li + 1}.${wi}`, (t) => flatShown(t, at, n), at, at + n / 30, `her.plus${li + 1}.${wi}`).map((k) => ({ ...k, gain: (k.gain ?? 0) - 6 })));
    });
  });
  out.push(cue('type_slam', word(c, 'L07', 'memory'), { gain: -4 }));
  out.push(cue('type_slam', word(c, 'L07', 'commit')));
  out.push(cue('type_slam', word(c, 'L08', 'fact'), { gain: -4 }));
  out.push(cue('type_slam', word(c, 'L08', 'blame')));
  // the blame gutter slides in over the slide's own length: its click lands as it comes to rest
  out.push(cue('gutter_slide', event(c, 'blame-gutter', T.blame + BLAME_GUTTER.end), { pan: -0.35 }));
  return out;
};
export default her;
