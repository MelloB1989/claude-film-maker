// `readui`: see lib/ui.ts (the machinery) and lib/params.ts (this scene's data).
import { UiScene } from './lib/ui';
import { readui } from './lib/params';
import type { Cfg } from './lib/geometry';

export default class Scene extends UiScene {
  protected readonly cfg: Cfg = readui;
}
