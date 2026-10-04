// 07 `cite`: "Ask me why I believe something… I'll show you the line." The question types in as the cut lands; the
// pointer clicks why?; the citation's label slides open; the thread is pulled out of the citation and, landing on the
// file's face, lays its seam down the margin (the thread-pull, not the old needle: C4-1); each cited line lights with a
// small clink as the seam passes it; on "line." the blame tab slides out.
import { typedCount } from '../../engine/panels';
import { cue, event, typing, type Cue, type SceneCues } from '../cue';
import { timesOf } from '../../scenes/cite-time';
import { TAB_LAND, askLine, citedLit } from '../../scenes/cite';

const cite: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const ask = askLine(T);
  const out: Cue[] = [];
  // the question is typing as the cut lands: its keys from the scene's first frame
  out.push(...typing('cite:ask', (t) => typedCount(ask, t), Math.max(s.start, T.question.at), T.question.end, 'cite.ask'));
  out.push(cue('fold_click', event(c, 'click', T.click)));
  // the citation's label springs open out of the chip; its slide ends as the citation starts streaming in
  out.push(cue('gutter_slide', event(c, 'label', T.cite.at), { gain: -2 }));
  // the thread-pull: drawn out of the citation's underline, then laid down the margin from its landing on the downbeat
  out.push(cue('stitch_pull', event(c, 'draw', T.draw.at), { gain: -2 }));
  out.push(cue('stitch_pull', event(c, 'strike', T.strike), { gain: -5 }));
  citedLit(T).forEach((t, i) => out.push(cue('glass_clink', event(c, `lit${i}`, t), { gain: -6 - i, pan: -0.1 })));
  // "line.": the blame tab slides out of the file and lands beside the lines
  out.push(cue('gutter_slide', event(c, 'blame-tab', T.pull + TAB_LAND), { pan: -0.3 }));
  return out;
};
export default cite;
