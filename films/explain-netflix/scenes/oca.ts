// Open Connect: without it, every stream crosses the open internet from far away; with it, a Netflix appliance sits
// inside your ISP's network and serves the stream from next door.
// params: kick, title
import { NfScene, rev, land, text, kicker, heading, card, cloud, link, server, home, pill, rgba, glowInk, W, H, TAU, clamp, ease, type Frame } from './lib';

export default class Oca extends NfScene {
  protected nominal = 4.7;
  protected override panelTitle = 'Open Connect';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    heading(c, this.p('kick', 'Step 1 · Get close'), this.p('title', 'A Netflix box inside your ISP'), t);

    // the far side: the library, then the open internet
    const kL = rev(t, 0.0, 0.35);
    const lib = { x: 230, y: 600 };
    card(c, lib.x - 95, lib.y - 70, 190, 140, { a: kL, r: 16 });
    // a film-strip glyph
    c.save(); c.globalAlpha *= kL;
    c.fillStyle = rgba('accent', 0.9); c.fillRect(lib.x - 50, lib.y - 34, 100, 50);
    c.fillStyle = 'rgba(0,0,0,0.55)';
    for (let i = 0; i < 6; i++) { c.fillRect(lib.x - 46 + i * 17, lib.y - 31, 9, 6); c.fillRect(lib.x - 46 + i * 17, lib.y + 9, 9, 6); }
    c.restore();
    text(c, 'Netflix library', lib.x, lib.y + 48, { size: 22, color: 'fgDim', align: 'center', alpha: kL });

    const kC = rev(t, 0.05, 0.4);
    cloud(c, 640, 600, 440, 240, { a: kC, fill: 'rgba(110,86,70,0.38)' });
    cloud(c, 640, 600, 400, 210, { a: kC, fill: 'rgba(150,120,98,0.18)' });
    text(c, 'the open internet', 640, 612, { size: 34, weight: 600, color: 'fgDim', align: 'center', alpha: kC });

    // the ISP's network
    const kI = rev(t, this.cue('providers', 0.55) - 0.1, 0.45);
    const ix = 1060, iy = 300, iw = 760, ih = 650;
    c.save(); c.translate(0, (1 - kI) * 30);
    card(c, ix, iy, iw, ih, { a: kI, r: 28, fill: ['rgba(40,30,26,0.75)', 'rgba(22,16,13,0.85)'], edge: 'rgba(242,180,76,0.28)' });
    kicker(c, 'Your internet provider', ix + 36, iy + 52, kI, 'accent2');
    c.restore();

    // homes
    const homes = [1170, 1340, 1510, 1680].map((x, i) => ({ x, y: 840, at: 0.3 + i * 0.06 }));
    // the long way round (before the appliance), fading once it lands
    const longK = rev(t, 0.15, 0.6, ease.inOutCubic);
    const longFade = 1 - rev(t, this.cue('inside', 2.3), 0.6);
    const slow = 0.18;
    for (const [i, h] of homes.entries()) {
      link(c, g, [lib.x + 95, lib.y], [h.x, h.y - 50], longK, { color: 'fgDim', width: 2, dash: true, packets: 2, t: t + i * 0.7, speed: slow, alpha: 0.75 * longFade, bend: 0.55 });
    }
    if (longK > 0.5 && longFade > 0) {
      const a = clamp((longK - 0.5) * 2) * longFade;
      pill(c, g, 'far away · congested · slow to start', 640, 760, { color: 'fgDim', a, size: 22 });
    }

    // the appliance lands
    const kS = land(t, this.cue('get', 1.2), 0.6);
    const sx = 1440, sy = 520;
    if (kS > 0) {
      // a pool of light under it
      const pg = c.createRadialGradient(sx, sy + 40, 0, sx, sy + 40, 260);
      pg.addColorStop(0, `rgba(229,36,44,${0.16 * kS})`); pg.addColorStop(1, 'rgba(229,36,44,0)');
      c.fillStyle = pg; c.fillRect(sx - 280, sy - 220, 560, 520);
      server(c, g, sx, sy - (1 - kS) * 120, 1.25, f.t, { a: clamp(kS * 1.4), busy: 0.6 * rev(t, this.cue('inside', 2.3), 0.4) });
      text(c, 'Open Connect Appliance', sx, sy + 92, { size: 28, weight: 600, align: 'center', alpha: rev(t, this.cue('get', 1.2) + 0.2, 0.4) });
    }
    // short, fast links to the homes
    const kN = rev(t, this.cue('inside', 2.3), 0.5, ease.inOutCubic);
    for (const [i, h] of homes.entries()) {
      link(c, g, [sx, sy + 150], [h.x, h.y - 52], kN, { color: 'accent', width: 3, packets: 3, t: t + i * 0.3, speed: 1.2, glow: 1, vertical: true });
    }
    for (const h of homes) home(c, g, h.x, h.y, 1, { a: rev(t, h.at, 0.5), tv: rev(t, this.cue('their', 2.8) + (h.x % 7) * 0.04, 0.35) });

    // takeaways
    const tags = [['Free for the ISP', this.cue('free', 1.65)], ['Inside their own network', this.cue('inside', 2.3) + 0.2], ['Streams from next door', this.cue('networks', 3.3) + 0.1]] as const;
    tags.forEach(([s, at], i) => pill(c, g, s, 120, 300 + i * 70, { a: rev(t, at, 0.35), color: i === 2 ? 'accent' : 'accent2', filled: i === 2, align: 'left', size: 24 }));
    void W; void TAU; void glowInk;
  }
}
