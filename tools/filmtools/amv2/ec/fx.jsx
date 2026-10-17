// fx.jsx - the EffectCraft FX library for Timeless v2. One global, FX; every helper lives inside it.
//   FX.buildUnder(main, E, ctx)  adjustment layers on the picture (looks, chromatic hits, glitches, shake), under the grade
//   FX.buildOver(main, E, ctx)   overlays above the grade (flashes, ink frames, light sweeps, speed lines, letterbox)
// Everything is planned from edl.json (hits, shot fx tags, transition names) by FX.plan; E.x.fx (fx_spec.py) carries
// measured screen positions for the tags that need one. Effect parameters are addressed by display name.
// Rules of the look (EDIT.md "what was wrong with v1"): high glow thresholds, tight radii, no whole-frame haze, no orange flood.
var FX = {
    ACT_SCALE: { tobey: 0.6, andrew: 0.85, tom: 1.0 },   // hit strength is scaled by the act's temperament
    _c: null,

    // ---------------------------------------------------------------- helpers
    log: function (m) { try { FX._c.log("fx: " + m); } catch (e) { } },
    t: function (f) { return f / FX._c.fps; },
    tryit: function (what, fn) { try { return fn(); } catch (e) { FX.log(what + ": " + e); return null; } },
    parade: function (l) { return l.property("ADBE Effect Parade"); },
    // effect by match name, renamed, returned fresh (references go stale after the next addProperty): set its params at once
    add: function (l, mn, label) {
        var e = FX.parade(l).addProperty(mn);
        if (label) { e.name = label; return FX.parade(l).property(label); }
        return e;
    },
    set: function (fx, name, v) { FX.tryit("set " + name, function () { fx.property(name).setValue(v); }); },
    // keys: [[comp frame, value], ...]; the layers FX makes start at comp time 0, so layer time == comp time
    keys: function (prop, ks) {
        if (!ks || !ks.length) return;
        if (ks.length == 1) { prop.setValue(ks[0][1]); return; }
        var ts = [], vs = [];
        for (var i = 0; i < ks.length; i++) { ts.push(FX.t(ks[i][0])); vs.push(ks[i][1]); }
        prop.setValuesAtTimes(ts, vs);
    },
    tkeys: function (fx, name, ks) { FX.tryit("keys " + name, function () { FX.keys(fx.property(name), ks); }); },
    tr: function (l, n) { return l.property("ADBE Transform Group").property(n); },
    solid: function (main, name, col, w, h, f0, f1) {
        var l = main.layers.addSolid(col, name, w || main.width, h || main.height, 1, main.duration);
        if (f0 !== undefined) { l.inPoint = FX.t(f0); l.outPoint = FX.t(f1); }
        return l;
    },
    adj: function (main, name, f0, f1) {
        var l = FX.solid(main, name, [1, 1, 1], 0, 0, f0, f1);
        l.adjustmentLayer = true;
        return l;
    },
    blend: function (l, mode) { FX.tryit("blend", function () { l.blendingMode = mode; }); },
    rng: function (seed) {   // mulberry32
        var a = seed >>> 0;
        return function () {
            a = (a + 0x6D2B79F5) >>> 0; var t = a;
            t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    },
    clamp: function (v, a, b) { return Math.max(a, Math.min(b, v)); },
    easeOutExpo: function (t) { return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t); },
    easeInCubic: function (t) { return t * t * t; },
    rectMask: function (l, x0, y0, x1, y1, feather) {
        var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        var sh = new Shape(); sh.vertices = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; sh.closed = true;
        m.property("ADBE Mask Shape").setValue(sh);
        if (feather) m.property("ADBE Mask Feather").setValue([feather, feather]);
        return m;
    },
    actOf: function (E, f) {
        var a = E.acts;
        for (var i = 0; i < a.length; i++) if (f >= a[i].f0 && f < a[i].f1) return a[i].id;
        return "outro";
    },
    shotAt: function (E, f) {
        for (var i = 0; i < E.shots.length; i++) if (f >= E.shots[i].a && f < E.shots[i].b) return E.shots[i];
        return null;
    },
    X: function (E) { return (E.x && E.x.fx) || {}; },
    // screen position of a clip-pixel point: the MAIN layer's position/scale/rotation at frame f (the shot's own move)
    toComp: function (id, p, f) {
        var l = FX._c.shot(id);
        if (!l) return p;
        return FX.tryit("toComp", function () {
            var t = FX.t(f), T = l.property("ADBE Transform Group");
            var pos = T.property("ADBE Position").valueAtTime(t, false), sc = T.property("ADBE Scale").valueAtTime(t, false);
            var rot = T.property("ADBE Rotate Z").valueAtTime(t, false), an = T.property("ADBE Anchor Point").valueAtTime(t, false);
            var r = rot * Math.PI / 180, dx = (p[0] - an[0]) * sc[0] / 100, dy = (p[1] - an[1]) * sc[1] / 100;
            return [pos[0] + dx * Math.cos(r) - dy * Math.sin(r), pos[1] + dx * Math.sin(r) + dy * Math.cos(r)];
        }) || p;
    },

    // ---------------------------------------------------------------- planning (pure data from the EDL)
    // tags: "name" or "name@frame" (frames are absolute comp frames)
    tagsOf: function (S, name) {
        var out = [];
        for (var i = 0; i < S.fx.length; i++) {
            var m = String(S.fx[i]).split("@");
            if (m[0] == name) out.push(m.length > 1 ? parseInt(m[1], 10) : null);
        }
        return out;
    },
    plan: function (E) {
        var P = { shakes: [], chromas: [], flashes: [], inks: [], glitches: [], sweeps: [], lines: [], looks: [], boxes: [], glints: [] };
        var strength = {}, i, j, S;
        for (i = 0; i < E.hits.length; i++) strength[E.hits[i][0]] = E.hits[i][1];
        var has = { shake: {}, chroma: {}, flash: {}, ink: {} };
        // explicit tags in the shot fx
        for (i = 0; i < E.shots.length; i++) {
            S = E.shots[i];
            var kinds = [["shake", "shake"], ["chroma", "chroma"], ["flash", "flash"], ["ink_frame", "ink"]];
            for (j = 0; j < kinds.length; j++) {
                var fs = FX.tagsOf(S, kinds[j][0]);
                for (var k = 0; k < fs.length; k++) if (fs[k] !== null) has[kinds[j][1]][fs[k]] = strength[fs[k]] || 2.4;
            }
        }
        var hitFrames = [];
        for (i = 0; i < E.hits.length; i++) hitFrames.push(E.hits[i][0]);
        var outro = E.outro ? E.outro.f0 : 819, tri = E.triptych ? E.triptych.f0 : 777;
        // hit rules; explicit tags always win over the rules at the same frame
        for (i = 0; i < E.hits.length; i++) {
            var f = E.hits[i][0], s = E.hits[i][1];
            if (f >= outro) continue;
            var act = FX.actOf(E, f), k0 = FX.ACT_SCALE[act] || 1;
            if (f >= tri) {   // the triptych panels belong to SPECIAL: a soft white pop on the biggest hits only
                if (s >= 2.5 && !has.flash[f]) has.flash[f] = -s;   // negative strength = soft
                continue;
            }
            if (s >= 2.5) {
                if (!has.flash[f] && !has.ink[f]) has.flash[f] = s * k0;
                if (!has.shake[f]) has.shake[f] = s * k0;
            } else if (s >= 1.8) {
                if (!has.shake[f] && !has.chroma[f]) {
                    if (act == "tom") { has.shake[f] = -s * k0; if (s >= 2.2) has.chroma[f] = s; }   // negative = light
                    else has.chroma[f] = s * k0 + 0.2;
                }
            }
        }
        var m;
        for (m in has.shake) P.shakes.push({ f: +m, s: has.shake[m] });
        for (m in has.chroma) P.chromas.push({ f: +m, s: has.chroma[m] });
        for (m in has.flash) P.flashes.push({ f: +m, s: has.flash[m], len: has.ink[m] ? 1 : 2 });   // flash + ink at one frame: 1 f white, then the ink frame
        for (m in has.ink) P.inks.push({ f: +m + (has.flash[m] ? 1 : 0), s: has.ink[m] });
        // transitions
        for (i = 0; i < E.shots.length; i++) {
            S = E.shots[i];
            if (S.xout.indexOf("glitch_") == 0) P.glitches.push({ f: S.b, kind: S.xout.substr(7), id: S.id });
            if (S.xout == "light_sweep") P.sweeps.push({ f: S.b, kind: "cut", id: S.id });
            if (S.xin == "open_lightsweep") P.sweeps.push({ f: S.a, kind: "open", id: S.id });
            var sl = FX.tagsOf(S, "speed_lines");
            if (sl.length) P.lines.push({ f0: S.a, f1: S.b, id: S.id, grow: true });
            else if (S.xout == "zoom_in" && S.a >= E.acts[1].f0 && S.b < outro) P.lines.push({ f0: S.b - 6, f1: S.b, id: S.id, grow: false });
            if (FX.tagsOf(S, "letterbox").length) P.boxes.push({ f0: S.a, f1: S.b, id: S.id });
            var rs = FX.tagsOf(S, "riser_shake");
            if (rs.length) P.risers = (P.risers || []).concat([{ f0: 468, f1: 480, id: S.id }]);
            for (j = 0; j < S.fx.length; j++) {
                var tg = String(S.fx[j]).split("@");
                if (tg[0] == "lens_glint" || tg[0] == "lens_flare") P.glints.push({ f: parseInt(tg[1], 10), kind: tg[0], id: S.id });
                else if ({ halation: 1, bokeh_bloom: 1, neon_glow: 1, sparks_glow: 1, eye_glow: 1, electric_glow: 1, fire_glow: 1,
                    sun_flare: 1, glass_glint: 1, symbiote_flicker: 1 }[tg[0]]) P.looks.push({ kind: tg[0], id: S.id, a: S.a, b: S.b });
            }
        }
        return P;
    },

    // ---------------------------------------------------------------- shake: Transform effect on an adjustment layer
    // amp in px; decays over len frames (or grows when `grow`). Scale rides the shake so the edges never show.
    shake: function (main, f, len, amp, o) {
        o = o || {};
        var r = FX.rng(f * 7919 + 13), l = FX.adj(main, o.name || ("FX shake " + f), f, f + len);
        var tau = len / 3.2, pk = [], sk = [], rk = [], sg = r() < 0.5 ? 1 : -1;
        for (var i = 0; i < len; i++) {
            var d = o.grow ? Math.pow((i + 1) / len, 1.6) : Math.exp(-i / tau);
            var a = amp * d, s1 = (i % 2 ? -1 : 1) * sg;
            var dx = a * s1 * (0.55 + 0.45 * r()), dy = a * -s1 * (0.35 + 0.5 * r()) * 0.8;
            var th = (o.rot === 0 ? 0 : 0.045 * a * s1 * (0.5 + 0.5 * r())); // degrees
            var sc = 1 + Math.max(Math.abs(dx) / 960, Math.abs(dy) / 540) + Math.abs(th) * 0.0175 * 1.15 + 0.004;
            pk.push([f + i, [960 + dx, 540 + dy]]); sk.push([f + i, sc * 100]); rk.push([f + i, th]);
        }
        var e = FX.add(l, "ADBE Geometry2", "shake");
        FX.tkeys(e, "Position", pk); FX.tkeys(e, "Scale Height", sk); FX.tkeys(e, "Rotation", rk);
        FX.set(e, "Use Composition's Shutter Angle", 0); FX.set(e, "Shutter Angle", 140);
        return l;
    },

    // ---------------------------------------------------------------- chromatic hit: radial RGB split that decays over 5 f
    // VR Chromatic Aberrations is spherical: it warps the frame's top/bottom rows. Shrink to 95 % first (empty border takes
    // the warp), split, and scale back up: clean edges, no visible softening.
    chromaStack: function (l, amps, f0) {
        var e = FX.add(l, "ADBE Geometry2", "pre"); FX.set(e, "Scale Height", 95);
        var rk = [], bk = [];
        for (var i = 0; i < amps.length; i++) { rk.push([f0 + i, amps[i]]); bk.push([f0 + i, -amps[i]]); }
        e = FX.add(l, "ec.vr.chromaticaberrations", "rgb split");
        FX.set(e, "Falloff Distance", 0);
        FX.tkeys(e, "Aberration (Red)", rk); FX.tkeys(e, "Aberration (Blue)", bk);
        e = FX.add(l, "ADBE Geometry2", "post"); FX.set(e, "Scale Height", 100 / 0.95);
    },
    chroma: function (main, f, s) {
        var a = 15 + 9 * (Math.abs(s) - 1.8), prof = [1, 0.62, 0.34, 0.15, 0.04], amps = [];
        for (var i = 0; i < prof.length; i++) amps.push(a * prof[i]);
        var l = FX.adj(main, "FX chroma " + f, f, f + prof.length);
        FX.chromaStack(l, amps, f);
        return l;
    },

    // ---------------------------------------------------------------- flash + ink frame (above the grade)
    flash: function (main, f, s, len) {
        var soft = s < 0, v = soft ? 0.5 : FX.clamp(0.8 + 0.2 * (Math.abs(s) - 2.5), 0.6, 1);
        len = len || 2;
        var l = FX.solid(main, "FX flash " + f, [1, 1, 1], 0, 0, f, f + len);
        if (len > 1) FX.keys(FX.tr(l, "ADBE Opacity"), [[f, 100 * v], [f + 1, 100 * v * 0.38]]);
        else FX.tr(l, "ADBE Opacity").setValue(100 * v);
        return l;
    },
    // a comic frame: frame 1 a hard B&W threshold, frame 2 the same inverted
    ink: function (main, f, E) {
        var lv = (FX.X(E).ink_level || {})[f] || (FX.X(E).ink_level || {})[f - 1] || 128;
        var a = FX.adj(main, "FX ink A " + f, f, f + 1), e;
        e = FX.add(a, "ADBE Gaussian Blur 2", "denoise"); FX.set(e, "Blurriness", 1.6);
        e = FX.add(a, "ADBE Threshold2", "ink"); FX.set(e, "Level", lv);
        var b = FX.adj(main, "FX ink B " + f, f + 1, f + 2);
        e = FX.add(b, "ADBE Gaussian Blur 2", "denoise"); FX.set(e, "Blurriness", 1.6);
        e = FX.add(b, "ADBE Threshold2", "ink"); FX.set(e, "Level", lv);
        FX.add(b, "ADBE Invert", "invert");
        return b;
    },

    // ---------------------------------------------------------------- transitions
    // glitch_dark / glitch_electric: 7 frames around the cut b (3 f exit, 4 f entry), 3 slice bands, RGB split, stutter
    glitch: function (main, g) {
        var b = g.f, f0 = b - 3, n = 7, prof = [0.55, 0.85, 1.0, 0.9, 0.6, 0.32, 0.12], r = FX.rng(b * 31 + 5), i, e;
        var l = FX.adj(main, "FX glitch " + g.kind + " " + b, f0, f0 + n);
        var amps = [];
        for (i = 0; i < n; i++) amps.push(26 * prof[i]);
        FX.chromaStack(l, amps, f0);
        if (g.kind == "dark") {
            e = FX.add(l, "ADBE Exposure2", "dip");
            var ek = []; for (i = 0; i < n; i++) ek.push([f0 + i, -0.7 * prof[i]]);
            FX.tkeys(e.property("Master"), "Exposure", ek);
        } else {
            e = FX.add(l, "ADBE Glo2", "electric glow");
            FX.set(e, "Glow Threshold", 84); FX.set(e, "Glow Radius", 18); FX.set(e, "Glow Colors", 2);
            FX.set(e, "Color A", [0.55, 0.78, 1, 1]); FX.set(e, "Color B", [0.15, 0.3, 1, 1]);
            var gk = []; for (i = 0; i < n; i++) gk.push([f0 + i, 1.0 * prof[i]]);
            FX.tkeys(e, "Glow Intensity", gk);
        }
        // slice displacement: each band is an adjustment layer with a keyed mask and an Offset (wraps: no gaps)
        for (var bnd = 0; bnd < 3; bnd++) {
            var sl = FX.adj(main, "FX glitch slice " + bnd + " " + b, f0, f0 + n), shapes = [], ts = [], ok = [];
            e = FX.add(sl, "ADBE Offset", "slice");
            for (i = 0; i < n; i++) {
                var y0 = r() * 900, hh = 24 + r() * 80, dir = r() < 0.5 ? -1 : 1, dx = dir * (40 + r() * 140) * prof[i];
                var sh = new Shape(); sh.vertices = [[-50, y0], [1970, y0], [1970, y0 + hh], [-50, y0 + hh]]; sh.closed = true;
                shapes.push(sh); ts.push(FX.t(f0 + i)); ok.push([f0 + i, [960 + dx, 540]]);
            }
            FX.tkeys(e, "Shift Center To", ok);
            var m = sl.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            m.property("ADBE Mask Shape").setValuesAtTimes(ts, shapes);
        }
        // 1-frame stutter: the picture holds the previous frame on the frame before the cut
        FX.tryit("stutter", function () {
            var st = FX.adj(main, "FX glitch stutter " + b, b - 1, b);
            FX.set(FX.add(st, "ADBE Posterize Time", "hold"), "Frame Rate", 15);
        });
    },

    // soft anamorphic light sweep: a feathered slanted band + a hot core + a horizontal streak, all additive.
    // x(t): band centre across the frame; peak(t): 0..1 brightness. Returns nothing; layers are named "FX sweep ...".
    sweepLayers: function (main, name, f0, f1, xFrom, xTo, peakF, tint, o) {
        o = o || {};
        var n = f1 - f0, ang = o.angle === undefined ? 14 : o.angle, i, W = main.width, H = main.height;
        function env(f) { var d = (f - peakF) / ((f < peakF ? peakF - f0 : f1 - peakF) + 0.001); return Math.max(0, 1 - d * d); }
        // the band centre crosses the frame and is at mid-frame on the peak frame; it leaves faster than it arrives
        function xAt(f) {
            var cx = W / 2, v = f <= peakF ? (cx - xFrom) / Math.max(1, peakF - f0) : (xTo - cx) / Math.max(1, f1 - 1 - peakF);
            return cx + (f - peakF) * v;
        }
        var defs = [
            { nm: "band", w: o.bw || 760, feather: 300, gain: 0.8, col: tint },
            { nm: "core", w: 150, feather: 90, gain: 0.6, col: [1, 1, 1] }
        ];
        for (var k = 0; k < defs.length; k++) {
            var d = defs[k], l = FX.solid(main, "FX sweep " + d.nm + " " + name, d.col, d.w + 2 * d.feather, 2600, f0, f1);
            FX.rectMask(l, d.feather, 0, d.w + d.feather, 2600, d.feather);
            FX.blend(l, BlendingMode.ADD);
            var pk = [], ok = [];
            for (i = 0; i < n; i++) {
                var f = f0 + i; pk.push([f, [xAt(f), H / 2]]); ok.push([f, 100 * d.gain * env(f) * (o.gain || 1)]);
            }
            FX.keys(FX.tr(l, "ADBE Position"), pk); FX.keys(FX.tr(l, "ADBE Opacity"), ok);
            FX.tr(l, "ADBE Rotate Z").setValue(ang);
        }
        // the streak: a thin bright line across the frame at the band's height, stretching to its peak
        var sx = FX.solid(main, "FX sweep streak " + name, [tint[0] * 0.6 + 0.4, tint[1] * 0.6 + 0.4, 1], W * 1.6, 14, f0, f1);
        FX.rectMask(sx, 0, 3, W * 1.6, 11, 4);
        FX.blend(sx, BlendingMode.ADD);
        var so = [], sp = [];
        for (i = 0; i < n; i++) { so.push([f0 + i, 75 * env(f0 + i) * (o.gain || 1)]); sp.push([f0 + i, [W / 2, H * (o.streakY || 0.6)]]); }
        FX.keys(FX.tr(sx, "ADBE Opacity"), so); FX.keys(FX.tr(sx, "ADBE Position"), sp);
        FX.tryit("streak blur", function () { var gb = FX.add(sx, "ADBE Gaussian Blur 2", "soft"); FX.set(gb, "Blurriness", 6); });
        // a faint wash so the cut sits in a soft bright frame, never a dip to black
        var w = FX.solid(main, "FX sweep wash " + name, tint, 0, 0, f0, f1), wk = [];
        for (i = 0; i < n; i++) wk.push([f0 + i, 22 * env(f0 + i) * (o.gain || 1)]);
        FX.keys(FX.tr(w, "ADBE Opacity"), wk); FX.blend(w, BlendingMode.ADD);
    },
    sweep: function (main, sw, E) {
        if (sw.kind == "cut") {
            var act = FX.actOf(E, sw.f);
            FX.sweepLayers(main, "" + sw.f, sw.f - 3, sw.f + 3, -300, 2220, sw.f, act == "tobey" ? [1, 0.93, 0.78] : [0.9, 0.95, 1]);
        } else {   // open_lightsweep: black -> picture under a lens sweep over 12 f
            var f0 = sw.f, k = FX.solid(main, "FX open black " + sw.f, [0, 0, 0], 0, 0, f0, f0 + 12), ok = [];
            for (var i = 0; i < 12; i++) { var u = i / 11; ok.push([f0 + i, 100 * Math.pow(1 - u, 2.2)]); }
            FX.keys(FX.tr(k, "ADBE Opacity"), ok);
            FX.sweepLayers(main, "open " + sw.f, f0 + 1, f0 + 13, -250, 2170, f0 + 6, [1, 0.9, 0.7], { gain: 0.85, angle: 10 });
        }
    },

    // speed lines: Fractal Noise stretched along the radius, Polar Coordinates (rect->polar) turns it into rays from the centre,
    // a hole mask keeps the middle clear, screen blended. grow: the rays lengthen/brighten over the shot (exit pushes: 6 f).
    speedLines: function (main, sl, E) {
        var f0 = sl.f0, f1 = sl.f1, n = f1 - f0, W = main.width, H = main.height, i;
        var l = FX.solid(main, "FX speed lines " + sl.id, [0, 0, 0], 0, 0, f0, f1);
        var e = FX.add(l, "ADBE Fractal Noise", "rays");
        FX.set(e, "Contrast", 380); FX.set(e, "Brightness", -95); FX.set(e, "Complexity", 3);
        FX.tryit("rays scale", function () {
            var T = e.property("Transform");
            T.property("Uniform Scaling").setValue(0);
            T.property("Scale Width").setValue(5); T.property("Scale Height").setValue(3200);
        });
        var ev = []; for (i = 0; i < n; i++) ev.push([f0 + i, i * 3.7]);
        FX.tkeys(e, "Evolution", ev);
        e = FX.add(l, "ADBE Polar Coordinates", "to rays"); FX.set(e, "Type of Conversion", 2); FX.set(e, "Interpolation", 100);
        FX.blend(l, BlendingMode.SCREEN);
        // keep the middle open: masks run BEFORE effects, so the hole is a luma track matte (radial ramp, black in the middle)
        var hm = FX.solid(main, "FX speed lines hole " + sl.id, [1, 1, 1], 2400, 2400, f0, f1);
        FX.tr(hm, "ADBE Scale").setValue([84, 48]);   // a 1200 px radius ramp -> an ellipse 1000 x 576 px
        FX.tr(hm, "ADBE Position").setValue([W / 2, H / 2]);
        var rp = FX.add(hm, "ADBE Ramp", "hole");
        FX.set(rp, "Ramp Shape", 2); FX.set(rp, "Start of Ramp", [1200, 1200]); FX.set(rp, "End of Ramp", [2400, 1200]);
        FX.set(rp, "Start Color", [0, 0, 0, 1]); FX.set(rp, "End Color", [1, 1, 1, 1]);
        var lv = FX.add(hm, "ADBE Easy Levels2", "plateau");
        FX.set(lv, "Input Black", 0.28); FX.set(lv, "Input White", 0.9);
        l.setTrackMatte(hm, TrackMatteType.LUMA);
        var ok = [];
        for (i = 0; i < n; i++) { var u = (i + 1) / n; ok.push([f0 + i, 100 * (sl.grow ? Math.min(1, 0.45 + u) : Math.min(1, u * 1.5)) * 0.8]); }
        FX.keys(FX.tr(l, "ADBE Opacity"), ok);
    },

    // letterbox 2.39:1 (S25): 1920/2.39 = 803 px of picture, bars of 138.5 px; eased in over 10 f, out over the last 3 f
    letterbox: function (main, bx) {
        var bar = (main.height - main.width / 2.39) / 2 + 0.5, h = bar + 4, i;
        for (var side = 0; side < 2; side++) {
            var l = FX.solid(main, "FX letterbox " + (side ? "bottom" : "top") + " " + bx.id, [0, 0, 0], main.width, h, bx.f0, bx.f1), pk = [];
            var sgn = side ? 1 : -1, yIn = side ? main.height - bar + h / 2 : bar - h / 2, yOut = side ? main.height + h / 2 + 2 : -h / 2 - 2;
            for (i = bx.f0; i < bx.f1; i++) {
                var u = i < bx.f0 + 10 ? FX.easeOutExpo((i - bx.f0 + 1) / 10) : 1;
                if (i >= bx.f1 - 3) u = 1 - FX.easeInCubic((i - (bx.f1 - 3) + 1) / 3);
                pk.push([i, [main.width / 2, yOut + (yIn - yOut) * u]]);
            }
            FX.keys(FX.tr(l, "ADBE Position"), pk);
        }
    },

    // ---------------------------------------------------------------- build passes
    buildUnder: function (main, E, ctx) {
        FX._c = ctx;
        var P = FX.plan(E), i;
        FX.tryit("looks", function () { FX.looks(main, E, P); });
        for (i = 0; i < P.chromas.length; i++) FX.tryit("chroma", function () { FX.chroma(main, P.chromas[i].f, P.chromas[i].s); });
        for (i = 0; i < P.glitches.length; i++) FX.tryit("glitch", function () { FX.glitch(main, P.glitches[i]); });
        for (i = 0; i < P.shakes.length; i++) FX.tryit("shake", function () {
            var s = P.shakes[i], light = s.s < 0, a = Math.abs(s.s), len = a >= 3 ? 8 : 6;
            FX.shake(main, s.f, len, (light ? 0.5 : 1) * (7 + 14 * (a - 1.8)));
        });
        (P.risers || []).forEach(function (r) {
            FX.tryit("riser", function () { FX.shake(main, r.f0, r.f1 - r.f0, 20, { grow: true, name: "FX riser shake" }); });
        });
    },
    buildOver: function (main, E, ctx) {
        FX._c = ctx;
        var P = FX.plan(E), i;
        FX.tryit("glints", function () { FX.glints(main, E, P); });
        for (i = 0; i < P.lines.length; i++) FX.tryit("speed lines", function () { FX.speedLines(main, P.lines[i], E); });
        for (i = 0; i < P.sweeps.length; i++) FX.tryit("sweep", function () { FX.sweep(main, P.sweeps[i], E); });
        for (i = 0; i < P.boxes.length; i++) FX.tryit("letterbox", function () { FX.letterbox(main, P.boxes[i]); });
        for (i = 0; i < P.inks.length; i++) FX.tryit("ink", function () { FX.ink(main, P.inks[i].f, E); });
        for (i = 0; i < P.flashes.length; i++) FX.tryit("flash", function () { FX.flash(main, P.flashes[i].f, P.flashes[i].s, P.flashes[i].len); });
    },
    looks: function (main, E, P) { },
    glints: function (main, E, P) { }
};
