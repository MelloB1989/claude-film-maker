// Control plane vs data plane: everything before the video (login, profiles, recommendations, the licence, which box
// to use) runs on AWS; press play, AWS points you to the box nearby, and the box streams the video.
// params: kick, title
import { NfScene, rev, land, text, kicker, heading, card, link, server, pill, screen, packet, bez, rgba, glowInk, lerp, clamp, ease, TAU, type Frame } from './lib';

export default class Planes extends NfScene {
  protected nominal = 5.33;
  protected override panelTitle = 'Control plane vs data plane';

  protected scene(c: CanvasRenderingContext2D, g: CanvasRenderingContext2D, t: number, f: Frame) {
    const tPlay = this.cue('play', 0.55), tAws = this.cue('aws', 1.25), tPoints = this.cue('points', 1.9);
    const tBox = this.cue('box', 2.7), tStreams = this.cue('streams', 3.55), tVideo = this.cue('video', 4.1);
    heading(c, this.p('kick', 'Two halves'), this.p('title', 'Press play: AWS points, the box streams'), t);

    // ——— control plane: AWS ———
    const kA = rev(t, 0.05, 0.4);
    const ax = 120, ay = 270, aw = 760, ah = 470;
    const hotA = rev(t, tAws, 0.3) * (1 - rev(t, tStreams, 0.6));
    card(c, ax, ay + (1 - kA) * 24, aw, ah, { a: kA, r: 22, edge: hotA > 0 ? rgba('accent2', 0.3 + 0.5 * hotA) : undefined });
    if (hotA > 0) { g.save(); g.globalAlpha *= hotA * 0.35; g.strokeStyle = glowInk('accent2'); g.lineWidth = 4; g.beginPath(); g.roundRect(ax, ay, aw, ah, 22); g.stroke(); g.restore(); }
    kicker(c, 'Control plane', ax + 36, ay + 56, kA, 'accent2');
    text(c, 'AWS', ax + aw - 36, ay + 58, { size: 40, weight: 800, face: 'display', width: 87.5, align: 'right', alpha: kA });
    const chips = ['Login', 'Profiles', 'Recommendations', 'Search', 'Licence', 'Which box?'];
    chips.forEach((s, i) => {
      const cx = ax + 40 + (i % 2) * 350, cy = ay + 120 + Math.floor(i / 2) * 100;
      const k = rev(t, 0.1 + i * 0.05, 0.35);
      const hot = i === 5 ? rev(t, tAws + 0.1, 0.3) : 0;
      c.save(); c.globalAlpha *= k;
      c.fillStyle = hot > 0 ? rgba('accent2', 0.12 + 0.2 * hot) : 'rgba(242,236,228,0.05)';
      c.beginPath(); c.roundRect(cx, cy, 330, 72, 12); c.fill();
      c.strokeStyle = hot > 0 ? rgba('accent2', 0.8) : '#3b3129'; c.lineWidth = 1.5; c.stroke();
      // a tiny service glyph: three stacked bars
      for (let b = 0; b < 3; b++) { c.fillStyle = rgba(hot > 0 ? 'accent2Bright' : 'fgFaint'); c.fillRect(cx + 22, cy + 22 + b * 11, 22, 6); }
      text(c, s, cx + 62, cy + 46, { size: 26, weight: 600 });
      c.restore();
    });

    // ——— data plane: the boxes ———
    const kD = rev(t, 0.12, 0.4);
    const dx = 1040, dy = 270, dw = 760, dh = 470;
    const hotD = rev(t, tBox, 0.3);
    card(c, dx, dy + (1 - kD) * 24, dw, dh, { a: kD, r: 22, edge: hotD > 0 ? rgba('accent', 0.3 + 0.5 * hotD) : undefined });
    kicker(c, 'Data plane', dx + 36, dy + 56, kD, 'accent');
    text(c, 'Open Connect', dx + dw - 36, dy + 58, { size: 36, weight: 800, face: 'display', width: 87.5, align: 'right', alpha: kD });
    const boxes = [[1180, 470], [1420, 420], [1660, 470]] as const;
    const chosen = 1;
    boxes.forEach(([bx, by], i) => {
      const isC = i === chosen;
      server(c, g, bx, by, 0.95, f.t + i, { a: kD * (isC ? 1 : 1 - 0.55 * hotD), busy: isC ? 0.3 + 0.6 * rev(t, tStreams, 0.3) : 0.3 });
      if (isC && hotD > 0) {
        const r = 112 + 6 * Math.sin(t * 6);
        c.strokeStyle = rgba('accentBright', 0.8 * hotD); c.lineWidth = 3; c.beginPath(); c.ellipse(bx + 8, by + 4, r, r * 0.62, 0, 0, TAU); c.stroke();
        g.strokeStyle = glowInk('accent', 0.6 * hotD); g.lineWidth = 6; g.beginPath(); g.ellipse(bx + 8, by + 4, r, r * 0.62, 0, 0, TAU); g.stroke();
        text(c, 'the box near you', bx + 50, by + 118, { size: 24, weight: 600, align: 'left', color: 'accentBright', alpha: hotD });
      }
    });

    // ——— you ———
    const ux = 960, uy = 826;
    const kU = rev(t, 0.15, 0.4);
    screen(c, g, ux, uy, 'tv', 1.2, { a: kU, on: 0.25 + 0.75 * rev(t, tStreams + 0.3, 0.4) });
    // the play mark, pressed on "play"
    const press = rev(t, tPlay - 0.1, 0.15) * (1 - rev(t, tPlay + 0.25, 0.2));
    const kPl = 1 - rev(t, tStreams + 0.2, 0.3);
    if (kPl > 0) {
      c.save(); c.globalAlpha *= kU * kPl; c.translate(ux, uy); c.scale(1 - 0.15 * press, 1 - 0.15 * press);
      c.fillStyle = rgba('fg'); c.beginPath(); c.moveTo(-12, -16); c.lineTo(18, 0); c.lineTo(-12, 16); c.closePath(); c.fill();
      c.restore();
    }
    const rip = clamp((t - tPlay) / 0.6);
    if (rip > 0 && rip < 1) { c.strokeStyle = rgba('fg', 0.6 * (1 - rip)); c.lineWidth = 2; c.beginPath(); c.arc(ux, uy, 30 + rip * 45, 0, TAU); c.stroke(); }

    // request: you → AWS (amber), answer: AWS → you, pointing at the box
    const req = clamp((t - tPlay) / Math.max(0.3, tAws - tPlay));
    const P0 = [ux - 60, uy - 30], P3 = [ax + aw / 2 + 150, ay + ah];
    if (req > 0 && req < 1) {
      const [x, y] = bez(P0, [P0[0]! - 40, P0[1]! - 80], [P3[0]!, P3[1]! + 90], P3, ease.inOutCubic(req));
      packet(c, g, x, y, 'accent2', 1, 8);
    }
    const ans = clamp((t - tPoints) / 0.55);
    if (ans > 0 && ans < 1) {
      const [x, y] = bez(P3, [P3[0]!, P3[1]! + 90], [P0[0]! - 40, P0[1]! - 80], P0, ease.inOutCubic(ans));
      packet(c, g, x, y, 'accent2', 1, 8);
    }
    // the pointer: AWS → that box (an arc over the top)
    const kp = rev(t, tPoints + 0.2, 0.6, ease.inOutCubic) * (1 - rev(t, tStreams + 0.5, 0.4));
    if (kp > 0) {
      link(c, g, [ax + aw - 120, ay + 6], [boxes[chosen][0], boxes[chosen][1] - 60], kp, { color: 'accent2', width: 3, dash: true, vertical: true, bend: -0.6, glow: 0.8 });
      pill(c, g, 'use this box', 960, 236, { a: clamp(kp * 2 - 1), color: 'accent2', size: 24 });
    }
    // the stream: that box → you (red, heavy, many packets)
    const ks = rev(t, tStreams, 0.45, ease.inOutCubic);
    if (ks > 0) {
      const from: [number, number] = [boxes[chosen][0] - 20, boxes[chosen][1] + 60], to: [number, number] = [ux + 70, uy - 30];
      link(c, g, from, to, ks, { color: 'accent', width: 6, packets: 7, t, speed: 1.4, glow: 1.4, vertical: true });
    }
    pill(c, g, 'AWS decides · the box delivers', 1560, 150, { a: rev(t, tVideo + 0.1, 0.35), color: 'accent', filled: true, size: 24 });
    void land; void lerp;
  }
}
