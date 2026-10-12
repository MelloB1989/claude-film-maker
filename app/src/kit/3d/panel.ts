// Panel3D: floating UI panels in the studio. One or more panels (engine/panels.ts: a terminal, an editor, a JSON
// response, a chat, a card) stand in 3D in a layout, rise in one after another, their lines typing in on time; the
// camera pushes in under a slow drift and focus pulls to the panel that is active (the one whose line started last); a
// highlighted line gets a blade of accent light under it, a lit bar in the margin and a wash over its row.
//
// Params (all optional but the panels):
//   panels | panel     PanelInput(s) (engine/panels.ts): { kind 'terminal' | 'editor' | 'json' | 'chat' | 'card', title,
//                      w (panel px; default by layout: single 1100, pair 820, stack 980, fan 760), h or rows, lang,
//                      gutter, size (code px, default 30), lines }; each
//                      line { text, kind?, at? (TimeRef from the shot's start), cps?, spans?, highlight? }
//                      a panel's `type` (TimeRef): its lines without an `at` type in one after another from then
//                      (cmd and code lines at `cps`, default 42; output lines whole, 0.12 s apart)
//                      a panel's `enter` (TimeRef, default 0.08 s + 0.22 s per panel): when it rises in
//   layout             'single' | 'pair' | 'stack' | 'fan' (default by count: 1 single, 2 pair, more fan); tilt 14 (deg)
//   span               the share of the frame's width the layout's box at rest fills (single 0.64, pair 0.78 (about 0.85
//                      in perspective), stack 0.68, fan 0.8;
//                      0.84 in a tall frame), never taller than 0.8 of the frame
//   highlight          { panel 0, line, at (TimeRef), color 'accent' | 'accent2' } or a list: the line lit
//   camera 'push', az -4, el 3, fov 30, fstop 2.4, and every Scene3D param
import * as THREE from 'three';
import { Panel, lineEnd, type PanelInput, type PanelLine } from '../../engine/panels';
import { Bar, Blade, Wash } from '../../engine/panel-light';
import { slam } from '../../engine/motion';
import { W, H } from '../../engine/gl';
import { clamp, ease, prog, pulse } from '../../engine/util';
import type { TimeRef } from '../text/fx';
import { isTall } from '../scene2d';
import { Scene3D, type Frame } from './scene3d';
import { boundsOf, panelPlacements, type PanelLayout } from './layout3d';

/** A line as a film gives it: `at` a TimeRef from the shot's start. */
export type PanelLineParam = Omit<PanelLine, 'at'> & { at?: TimeRef };
/** A panel as a film gives it. */
export type PanelParam = Omit<PanelInput, 'lines' | 'w'> & { w?: number; lines: PanelLineParam[]; type?: TimeRef; cps?: number; enter?: TimeRef };
export interface HighlightParam { panel?: number; line: number; at?: TimeRef; color?: 'accent' | 'accent2' }

/** A panel's default width (panel px) by layout, and how much of the frame's width the layout fills. */
const PANEL_W: Record<PanelLayout, number> = { single: 1100, pair: 820, stack: 980, fan: 760 };
// (set against the box at rest: turned panels' near edges grow in perspective, so a pair at 0.78 spans about 0.85)
const FILL: Record<PanelLayout, number> = { single: 0.64, pair: 0.78, stack: 0.68, fan: 0.8 };

interface Lit { panel: number; line: number; at: number; bar: Bar; blade: Blade; wash: Wash }

export class Panel3D extends Scene3D {
  protected override defaults: Record<string, unknown> = { camera: 'push', az: -4, el: 3, fov: 30, fstop: 2.4 };
  private panels: { panel: Panel; group: THREE.Group; home: THREE.Vector3; rot: THREE.Euler; enter: number; starts: number[] }[] = [];
  private lit: Lit[] = [];

  /** Song-time lines for a panel: `at` resolved, untimed lines chained from `type`. */
  protected linesOf(pp: PanelParam): PanelLine[] {
    let cursor = pp.type !== undefined ? this.at(pp.type) : null;
    const cps = pp.cps ?? 42;
    return pp.lines.map((l) => {
      const out: PanelLine = { ...l, at: l.at !== undefined ? this.at(l.at) : undefined };
      if (out.at === undefined && cursor !== null) {
        const typed = l.kind === 'cmd' || (l.kind === undefined && pp.kind !== 'terminal' && pp.kind !== 'chat');
        out.at = cursor;
        if (typed && out.cps === undefined) out.cps = cps;
      }
      if (out.at !== undefined && cursor !== null) cursor = Math.max(cursor, lineEnd(out)) + 0.12;
      return out;
    });
  }

  protected build() {
    const raw = this.p<PanelParam[] | undefined>('panels', undefined) ?? (this.ctx.params.panel ? [this.ctx.params.panel as PanelParam] : []);
    if (!raw.length) throw new Error(`shot ${this.ctx.id}: Panel3D needs \`panels\` (or \`panel\`)`);
    const sizes: { w: number; h: number }[] = [];
    const layout = this.p<PanelLayout>('layout', raw.length === 1 ? 'single' : raw.length === 2 ? 'pair' : 'fan');
    raw.forEach((pp, i) => {
      const { type: _t, cps: _c, enter, ...spec } = pp;
      const panel = this.own(new Panel({ ...spec, w: pp.w ?? PANEL_W[layout], size: pp.size ?? 30, lines: this.linesOf(pp) }));
      const group = new THREE.Group();
      group.add(panel.mesh);
      this.stage.scene.add(group);
      const starts = panel.spec.lines.map((l) => l.at ?? -Infinity);
      this.panels.push({ panel, group, home: new THREE.Vector3(), rot: new THREE.Euler(), enter: this.at(enter ?? 0.08 + 0.22 * i), starts });
      sizes.push({ w: panel.spec.w / 1000, h: panel.spec.h / 1000 });
    });
    const places = panelPlacements(layout, sizes, { aspect: W / H, tilt: this.p('tilt', 14) });
    places.forEach((pl, i) => {
      const P = this.panels[i]!;
      P.home.set(...pl.pos);
      P.rot.set(...pl.rot);
    });
    // highlights: a blade under the line, a bar in its margin, a wash over its row
    const hs = this.p<HighlightParam | HighlightParam[] | undefined>('highlight', undefined);
    for (const h of hs === undefined ? [] : Array.isArray(hs) ? hs : [hs]) {
      const P = this.panels[h.panel ?? 0];
      if (!P) throw new Error(`shot ${this.ctx.id}: highlight names panel ${h.panel}, there are ${this.panels.length}`);
      const size = { w: P.panel.spec.w, h: P.panel.spec.h }, key = h.color ?? 'accent';
      const g = P.panel.layout;
      const lit: Lit = {
        panel: h.panel ?? 0, line: h.line, at: h.at !== undefined ? this.at(h.at) : Math.max(this.ctx.start, lineEnd(P.panel.spec.lines[h.line]!) + 0.1),
        bar: this.own(new Bar(size, key)), blade: this.own(new Blade(size, Math.max(1, 0.06 * g.size), 0.5 * g.lineH, key)), wash: this.own(new Wash(size)),
      };
      P.group.add(lit.bar.mesh, lit.blade.mesh, lit.wash.mesh);
      this.lit.push(lit);
    }
    // framing: the layout fills `fill` of the frame's width (FILL), never more than 0.8 of its
    // height; turned panels reach toward the lens, so their box is taken a little wide
    const b = boundsOf(places, sizes);
    const fill = this.p('span', isTall() ? 0.84 : FILL[layout]);
    this.frame({ centre: b.centre, w: b.w * 1.04, h: b.h, margin: [(1 - fill) / 2, 0.1] });
  }

  /** Where focus is at t: on each panel as it enters or a line of it starts, pulled over 0.35 s (a pure function of t). */
  private focusAt(t: number): THREE.Vector3 {
    const ev: { t: number; i: number }[] = [];
    this.panels.forEach((P, i) => {
      ev.push({ t: P.enter, i });
      for (const s of P.starts) if (Number.isFinite(s)) ev.push({ t: s, i });
    });
    ev.sort((a, b) => a.t - b.t || a.i - b.i);
    const at = (i: number) => this.panels[i]!.group.getWorldPosition(new THREE.Vector3());
    const c = at(ev[0]?.i ?? 0);
    let cur = ev[0]?.i ?? 0;
    for (const e of ev) {
      if (e.t > t) break;
      if (e.i === cur) continue;
      c.lerp(at(e.i), prog(t, e.t, e.t + 0.35, ease.inOutCubic));
      cur = e.i;
    }
    return c;
  }

  protected update(f: Frame): THREE.Vector3 {
    const t = f.t;
    for (const P of this.panels) {
      // rising in: from below and turned back, on a 4 Hz spring that lands at `enter` + its rise
      const k = slam(t, P.enter + 0.3, { freq: 3.5, damping: 0.75 });
      P.group.visible = k > 0;
      P.panel.opacity = clamp(k * 1.6);
      P.group.position.set(P.home.x, P.home.y - (1 - k) * 0.35, P.home.z - (1 - k) * 0.25);
      P.group.rotation.set(P.rot.x + (1 - k) * 0.35, P.rot.y, P.rot.z);
      P.panel.draw(t);
    }
    for (const L of this.lit) {
      const P = this.panels[L.panel]!, pn = P.panel, g = pn.layout;
      const n = Array.from(pn.spec.lines[L.line]!.text).length;
      const o = pn.textOrigin(L.line, t), top = pn.rowTop(L.line, t);
      const draw = prog(t, L.at, L.at + 0.45, ease.outCubic);
      const heat = t < L.at ? 0 : pulse(t, L.at + 0.45, 0.35);
      const on = draw > 0 ? 1 : 0;
      L.blade.set(o.x, o.x + n * g.adv * draw, o.baseline + 0.32 * g.size, heat, 1.15 * on * (this.glowLevel / 3));
      L.bar.set(g.padX * 0.45, top + 4, top + g.lineH - 4, on * (this.glowLevel / 3) * (1.2 + 1.5 * heat));
      L.wash.set(0, top, pn.spec.w, top + g.lineH, 0.045 * draw, 0);
    }
    return this.focusAt(t);
  }
}

export default Panel3D;
