// titles.jsx - the TITLES library of the Timeless v2 EffectCraft build (one global: TITLES).
// Called last by the core builder: TITLES.build(main, E, ctx). Every title is a native EffectCraft precomp built from text
// layers, text animators (tracking / position), masks, shape layers, track mattes and effects, so it can be edited in the app.
// Data computed in Python (word timings, shot ids, the transition each title leaves on) is E.x.titles (titles_spec.py).
//
// Layout of each title comp: 1920x1080, local frame 0 = the title's in frame (`f`), duration f1 - f.
// Fonts: Anton / Bebas Neue (sub, watermark), Montserrat Light (namecard, tags), Bangers (caption box), Chinese Rocks (novax).
// EffectCraft notes that shaped this file are in docs/EFFECTCRAFT-NOTES.md ("titles").
var TITLES = (function () {
    var FPS = 30, W = 1920, H = 1080;
    var DBG_WIPE = 38;
    var CTX = null, FOLDER = null, WARN = [];

    // ---------------------------------------------------------------- generic helpers
    function f2t(f) { return f / FPS; }
    function TG(l) { return l.property("ADBE Transform Group"); }
    function POS(l) { return TG(l).property("ADBE Position"); }
    function SCL(l) { return TG(l).property("ADBE Scale"); }
    function ROT(l) { return TG(l).property("ADBE Rotate Z"); }
    function OPA(l) { return TG(l).property("ADBE Opacity"); }
    function ANC(l) { return TG(l).property("ADBE Anchor Point"); }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    function hex(h) { h = h.replace("#", ""); return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
    function warn(s) { WARN.push(s); if (CTX && CTX.log) CTX.log("TITLES warning: " + s); }
    function TRY(what, fn) { try { return fn(); } catch (e) { warn(what + ": " + e); return null; } }
    function fxAdd(l, mn, label) {                       // the fresh effect: references go stale after the next addProperty
        var e = FXP(l).addProperty(mn);
        if (label) { e.name = label; return FXP(l).property(label); }
        return e;
    }
    function setp(e, name, v) { e.property(name).setValue(v); }

    // keyframes in local frames. ease: "out" (decelerate, expo-out-ish), "in" (accelerate), "io", "lin", "hold".
    function easeArr(n, speed, infl) { var a = []; for (var i = 0; i < n; i++) a.push(new KeyframeEase(speed, infl)); return a; }
    function K(prop, ks, ease) {
        if (!ks || !ks.length) return;
        if (ks.length == 1) { prop.setValue(ks[0][1]); return; }
        var ts = [], vs = [];
        for (var i = 0; i < ks.length; i++) { ts.push(f2t(ks[i][0])); vs.push(ks[i][1]); }
        prop.setValuesAtTimes(ts, vs);
        if (!ease || ease == "lin") return;
        var n = (ks[0][1] instanceof Array) ? ks[0][1].length : 1;
        for (var k = 1; k <= ks.length; k++) {
            TRY("ease " + ease, function () {
                if (ease == "hold") { prop.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD); return; }
                var ein = 0.1, eout = 0.1;
                if (ease == "out") { ein = 88; eout = 6; }
                else if (ease == "in") { ein = 6; eout = 88; }
                else if (ease == "io") { ein = 70; eout = 70; }
                try { prop.setTemporalEaseAtKey(k, easeArr(n, 0, ein), easeArr(n, 0, eout)); }
                catch (e1) { prop.setTemporalEaseAtKey(k, easeArr(1, 0, ein), easeArr(1, 0, eout)); }
            });
        }
    }
    function rectShape(x0, y0, x1, y1) { var s = new Shape(); s.vertices = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; s.closed = true; return s; }
    function newComp(name, f0, f1) {
        var c = app.project.items.addComp(name, W, H, 1, (f1 - f0) / FPS, FPS);
        c.bgColor = [0, 0, 0];
        TRY("comp folder", function () { if (FOLDER) c.parentFolder = FOLDER; });
        TRY("comp mb", function () { c.shutterAngle = 270; c.shutterPhase = -135; c.motionBlurSamplesPerFrame = 12; });
        return c;
    }
    function textStyle(l, o) {
        var tp = l.property("ADBE Text Properties").property("ADBE Text Document");
        var d = tp.value;
        d.resetCharStyle();
        d.font = o.font; d.fontSize = o.size;
        d.tracking = o.track || 0;
        d.fauxItalic = !!o.italic;
        d.applyFill = (o.fill !== null && o.fill !== undefined);
        if (d.applyFill) d.fillColor = o.fill;
        d.applyStroke = !!(o.stroke && o.sw > 0);
        if (d.applyStroke) { d.strokeColor = o.stroke; d.strokeWidth = o.sw; d.strokeOverFill = true; }
        d.justification = (o.just == "l") ? ParagraphJustification.LEFT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY;
        tp.setValue(d);
    }
    function mkText(comp, s, o) {
        var l = comp.layers.addText(s);
        textStyle(l, o);
        if (o.name) l.name = o.name;
        return l;
    }
    function rect(l) { return l.sourceRectAtTime(0, false); }
    // vertical extent of an all-caps line in this font, relative to the baseline (measured on "H": stable and cap-tight)
    var CAPS = {};
    function capBox(comp, font, size) {
        var key = font + "@" + size;
        if (!CAPS[key]) {
            var t = mkText(comp, "H", { font: font, size: size, fill: [1, 1, 1] });
            var r = rect(t); CAPS[key] = { top: r.top, height: r.height }; t.remove();
        }
        return CAPS[key];
    }
    // place a text layer so the CAP-LINE centre is (cx, cy); horizontally the ink centre (centre-justified) or ink left (left-justified)
    function place(comp, l, o, cx, cy) {
        var r = rect(l), cb = capBox(comp, o.font, o.size), y = cy - (cb.top + cb.height / 2);
        var x = (o.just == "l") ? cx - r.left : cx - (r.left + r.width / 2);
        POS(l).setValue([x, y]);
        return { x: x, y: y, r: r, cb: cb };
    }
    // tracking animator ("Before & After" tracking type): a, b in 1/1000 em, keys in local frames
    function trackAnim(l, ks, ease) {
        var an = l.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
        an.property("ADBE Text Selectors").addProperty("ADBE Text Selector");
        var ap = an.property("ADBE Text Animator Properties");
        ap.addProperty("ADBE Text Tracking Amount");           // adds trackingType and tracking (EffectCraft names)
        TRY("tracking type", function () { ap.property("trackingType").setValue(1); });
        K(ap.property("tracking"), ks, ease);
        return an;
    }
    function posAnim(l, ks, ease) {                            // text animator Position (moves the glyphs inside the layer, so a layer mask stays put)
        var an = l.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
        an.property("ADBE Text Selectors").addProperty("ADBE Text Selector");
        var p = an.property("ADBE Text Animator Properties").addProperty("ADBE Text Position 3D");
        var v3 = [];
        for (var i = 0; i < ks.length; i++) v3.push([ks[i][0], [ks[i][1][0], ks[i][1][1], 0]]);
        K(p, v3, ease);
        return an;
    }
    function layerMask(l, shape, feather) {
        var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        m.property("ADBE Mask Shape").setValue(shape);
        m.property("ADBE Mask Feather").setValue([feather || 0, feather || 0]);
        return m;
    }
    function inout(l, f0, f1) { l.inPoint = f2t(f0); l.outPoint = f2t(f1); }
    function putInMain(main, comp, name, f, f1) {
        var L = main.layers.add(comp);
        L.name = name;
        L.startTime = f2t(f); L.inPoint = f2t(f); L.outPoint = f2t(f1);
        TRY("title mb", function () { L.motionBlur = true; });
        ANC(L).setValue([W / 2, H / 2]); POS(L).setValue([W / 2, H / 2]);
        return L;
    }
    function dropShadow(l, op, dist, soft, dir, label) {
        TRY("drop shadow", function () {
            var e = fxAdd(l, "ADBE Drop Shadow", label || "shadow");
            setp(e, "Opacity", op); setp(e, "Distance", dist); setp(e, "Softness", soft); setp(e, "Direction", dir === undefined ? 135 : dir);
            setp(e, "Shadow Color", [0, 0, 0]);
        });
    }
    function glow(l, label, thr, rad, inten, colA, colB, basedOn) {   // basedOn: 1 = colour channels (bright pixels), 2 = alpha (the shape's edge)
        return TRY("glow " + label, function () {
            var g = fxAdd(l, "ADBE Glo2", label);
            setp(g, "Glow Based On", basedOn || 2); setp(g, "Glow Threshold", thr); setp(g, "Glow Radius", rad); setp(g, "Glow Intensity", inten);
            if (colA) { setp(g, "Glow Colors", 3); setp(g, "Color A", colA); setp(g, "Color B", colB || colA); }
            return g;
        });
    }

    // ---------------------------------------------------------------- the exit of a hero title, timed to the cut it leaves on
    // `cut` = the transition at the end frame (titles_spec.py). The shot moves out with that transition's motion, so the title
    // leaves with the same direction and speed (parallax 1.15) and the same blur.
    function exitMotion(L, f1, cut) {
        var e = f1 - 1, n = 4, a = e - n + 1;                  // last visible frame e; the motion fills the last n frames
        var P = POS(L), S = SCL(L), R = ROT(L), O = OPA(L);
        var wh = { whip_l: [-1, 0], whip_r: [1, 0], whip_u: [0, -1], whip_d: [0, 1] }[cut];
        var blurDir = null, blurLen = 0;
        if (wh) {
            K(P, [[a - 1, [W / 2, H / 2]], [f1, [W / 2 + wh[0] * W * 1.3 * 1.15, H / 2 + wh[1] * H * 1.3 * 1.15]]], "in");
            blurDir = wh[0] ? 0 : 90; blurLen = 140;
        } else if (cut == "zoom_in") {
            K(S, [[a - 1, [100, 100]], [f1, [250, 250]]], "in"); K(O, [[e - 1, 100], [e, 0]], "lin"); blurDir = null;
        } else if (cut == "zoom_out" || cut == "panel_slam") {
            K(S, [[a - 1, [100, 100]], [f1, [58, 58]]], "in"); K(O, [[e - 2, 100], [e, 0]], "lin");
        } else if (cut == "spin_cw" || cut == "spin_ccw") {
            var sg = (cut == "spin_cw") ? 1 : -1;
            K(R, [[a - 1, 0], [f1, sg * 50]], "in"); K(S, [[a - 1, [100, 100]], [f1, [150, 150]]], "in"); K(O, [[e - 1, 100], [e, 0]], "lin");
        } else if (cut == "impact") {                           // hard cut on the hit: the title punches toward camera as the picture cuts
            K(S, [[a, [100, 100]], [e, [116, 116]]], "in"); K(O, [[e - 1, 100], [e, 0]], "lin");
        } else if (cut && cut.indexOf("glitch") == 0) {         // RGB-split slice jitter, then gone
            K(P, [[e - 3, [W / 2, H / 2]], [e - 2, [W / 2 - 34, H / 2]], [e - 1, [W / 2 + 46, H / 2]], [e, [W / 2 - 18, H / 2]]], "hold"); K(O, [[e - 2, 100], [e - 1, 40], [e, 0]], "lin");
        } else {                                                // light_sweep / none: a quick designed fade-and-drift
            K(S, [[a, [100, 100]], [f1, [106, 106]]], "io"); K(O, [[a, 100], [e, 0]], "lin");
        }
        if (blurDir !== null) TRY("exit blur", function () {
            var b = fxAdd(L, "ADBE Motion Blur", "exit blur");
            setp(b, "Direction", blurDir);
            K(b.property("Blur Length"), [[a - 1, 0], [f1, blurLen]], "in");
        });
    }

    // ---------------------------------------------------------------- watermark
    function watermark(main, wm) {
        var f0 = wm.f0, f1 = wm.f1, n = f1 - f0;
        var o = { font: "BebasNeue-Regular", size: 40, fill: [1, 1, 1], track: 260 };          // Bebas cap height 0.7 em: 40 px = 28 px caps
        var l = mkText(main, wm.text, o);
        l.name = "WATERMARK " + wm.text;
        var r = rect(l), cb = capBox(main, o.font, o.size);
        POS(l).setValue([wm.pos[0] - (r.left + r.width / 2), wm.pos[1] - (cb.top + cb.height / 2)]);
        l.startTime = f2t(f0); inout(l, f0, f1);
        var base = f2t(f0);
        trackAnim(l, [[0, 700], [26, 0]], "out");              // letter-spacing settles in
        // the watermark layer starts at f0 (layer time 0 = f0): keys are layer-local, the comp keys below are absolute
        var op = OPA(l);
        op.setValuesAtTimes([f2t(f0), f2t(f0 + 14), f2t(f1 - 7), f2t(f1 - 1)], [0, 70, 70, 0]);
        dropShadow(l, 55, 2, 7, 135);
        return l;
    }

    // ---------------------------------------------------------------- sub: word-synced subtitles
    var SUB = { font: "Anton-Regular", size: 98, track: 30, cy: 930 };
    function subTitle(main, T, X, idx, E) {
        var d = X.sub[String(idx)];
        if (!d) { warn("no word timing for sub " + T.text); return null; }
        var n = T.f1 - T.f, comp = newComp("SUB " + T.text, T.f, T.f1);
        var o = { font: SUB.font, size: SUB.size, fill: [1, 1, 1], track: SUB.track, just: "l" };
        var probe = mkText(comp, "A A", o), probe2 = mkText(comp, "AA", o);
        var space = rect(probe).width - rect(probe2).width; probe.remove(); probe2.remove();
        for (var p = 0; p < d.pages.length; p++) {
            var page = d.pages[p], words = [], total = 0, i;
            for (i = 0; i < page.length; i++) {
                var l = mkText(comp, page[i].w, o); l.name = "word " + page[i].w;
                var r = rect(l); words.push({ l: l, r: r, w: page[i], x: total });
                total += r.width + (page[i].join ? 0 : space + 8);
            }
            total -= (page[page.length - 1].join ? 0 : space + 8);
            var x0 = W / 2 - total / 2;
            var tEnd = (p + 1 < d.pages.length) ? d.pages[p + 1][0].f - T.f : n - 1;     // page leaves as the next one starts / at the exit
            var out0 = Math.max(tEnd - 3, 0);
            for (i = 0; i < words.length; i++) {
                var wd = words[i], l2 = wd.l, f = wd.w.f - T.f;
                var cb = capBox(comp, o.font, o.size);
                var cx = x0 + wd.x + wd.r.width / 2, cy = SUB.cy;
                // anchor = ink centre of the word, position = where that centre sits
                ANC(l2).setValue([wd.r.left + wd.r.width / 2, cb.top + cb.height / 2]);
                POS(l2).setValue([cx, cy]);
                inout(l2, f, tEnd + 1);
                K(SCL(l2), [[f, [113, 113]], [f + 3, [100, 100]]], "out");
                K(OPA(l2), [[f, 55], [f + 1, 100], [out0, 100], [tEnd, 0]], "lin");
                var py = [[f, [cx, cy + 14]], [f + 3, [cx, cy]], [out0, [cx, cy]], [tEnd, [cx, cy - 10]]];
                K(POS(l2), py, "out");
            }
        }
        var L = putInMain(main, comp, "TITLE sub: " + T.text, T.f, T.f1);
        // soft dark shadow, stacked so it reads on any background (the white flash frames included)
        dropShadow(L, 80, 0, 46, 135, "shadow wide");
        dropShadow(L, 85, 5, 14, 135, "shadow mid");
        dropShadow(L, 70, 2, 3, 135, "shadow tight");
        return L;
    }

    // ---------------------------------------------------------------- namecard
    var ACT_ACCENT = { tobey: "#E9C46A", andrew: "#5BC8FF", tom: "#FF5A3C" };
    var CARD = { x: 96, nameCy: 804, ruleY: 840, subCy: 874, nameSize: 52, subSize: 24 };
    function namecard(main, T, X, idx) {
        var n = T.f1 - T.f, comp = newComp("NAMECARD " + T.text, T.f, T.f1), act = X.act[String(idx)];
        var on = { font: "Montserrat-Light", size: CARD.nameSize, fill: [1, 1, 1], track: 380, just: "l" };
        var os = { font: "Montserrat-Light", size: CARD.subSize, fill: [1, 1, 1], track: 300, just: "l" };
        var nameL = mkText(comp, T.text, on); nameL.name = "name";
        var pn = place(comp, nameL, on, CARD.x, CARD.nameCy);
        var ink = pn.r.width;
        var subL = mkText(comp, T.sub, os); subL.name = "sub line";
        var ps = place(comp, subL, os, CARD.x, CARD.subCy);
        OPA(subL).setValue(82);
        var rise = Math.min(14, Math.round(n * 0.3)), outN = Math.min(10, Math.round(n * 0.3)), out0 = n - 1 - outN;   // entry and exit scale down for short cards
        // mask reveal: a static layer mask in comp space, the glyphs rise into it (text animator position)
        function reveal(l, p, o, f0) {
            var m = layerMask(l, rectShape(p.r.left - 10, p.r.top - 8, p.r.left + p.r.width + 900, p.r.top + p.r.height + 10), 0);
            var cap = capBox(comp, o.font, o.size);
            posAnim(l, [[f0, [0, 52]], [f0 + rise, [0, 0]], [out0, [0, 0]], [n - 1, [-(p.r.width + 90), 0]]], "out");
            // the exit accelerates: re-key the last segment with ease-in
        }
        reveal(nameL, pn, on, 0);
        reveal(subL, ps, os, 4);
        trackAnim(nameL, [[0, 520], [rise + 3, 0]], "out");
        trackAnim(subL, [[4, 420], [rise + 5, 0]], "out");
        // rule + accent tick (shape layers, scale-X reveal from the left, slide out to the left with the text)
        var rule = comp.layers.addShape(); rule.name = "rule";
        var g = rule.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var rc = g.property("ADBE Vectors Group");
        var rr = rc.addProperty("ADBE Vector Shape - Rect"); rr.property("ADBE Vector Rect Size").setValue([ink + 24, 2]); rr.property("ADBE Vector Rect Position").setValue([(ink + 24) / 2, 0]);
        var rf = rc.addProperty("ADBE Vector Graphic - Fill"); rf.property("ADBE Vector Fill Color").setValue([1, 1, 1]);
        ANC(rule).setValue([0, 0]); POS(rule).setValue([CARD.x, CARD.ruleY]);
        K(SCL(rule), [[2, [0, 100]], [rise + 2, [100, 100]], [out0 + 2, [100, 100]], [n - 1, [0, 100]]], "out");
        K(OPA(rule), [[0, 85]], "lin");
        var tick = comp.layers.addShape(); tick.name = "accent tick";
        var tg = tick.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var tr = tg.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect"); tr.property("ADBE Vector Rect Size").setValue([64, 6]); tr.property("ADBE Vector Rect Position").setValue([32, 0]);
        var tf = tg.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill"); tf.property("ADBE Vector Fill Color").setValue(hex(ACT_ACCENT[act] || "#FFFFFF"));
        ANC(tick).setValue([0, 0]); POS(tick).setValue([CARD.x, CARD.ruleY]);
        K(SCL(tick), [[3, [0, 100]], [rise, [100, 100]], [out0, [100, 100]], [n - 1, [0, 100]]], "out");
        var L = putInMain(main, comp, "TITLE namecard: " + T.text, T.f, T.f1);
        dropShadow(L, 85, 0, 30, 135, "shadow wide");
        dropShadow(L, 75, 3, 9, 135, "shadow soft");
        dropShadow(L, 60, 1, 2, 135, "shadow tight");
        return L;
    }

    // ---------------------------------------------------------------- caption_box: the Spider-Verse comic caption
    var CAP = { x: 96, y: 96, size: 64, padX: 26, padY: 16, border: 6, shadow: 11 };
    function dotLayer(comp, x0, y0, x1, y1, col, name) {          // halftone: a grid of dots (two nested repeaters) clipped to the box, fading out along a diagonal
        var l = comp.layers.addShape(); l.name = name;
        var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var gc = g.property("ADBE Vectors Group");
        var sp = 13, cols = Math.ceil((x1 - x0) / sp) + 2, rows = Math.ceil((y1 - y0) / sp) + 2;
        var el = gc.addProperty("ADBE Vector Shape - Ellipse"); el.property("ADBE Vector Ellipse Size").setValue([6.5, 6.5]);
        var fl = gc.addProperty("ADBE Vector Graphic - Fill"); fl.property("ADBE Vector Fill Color").setValue(col);
        var r1 = gc.addProperty("ADBE Vector Filter - Repeater"); r1.property("ADBE Vector Repeater Copies").setValue(cols);
        r1.property("ADBE Vector Repeater Transform").property("ADBE Vector Position").setValue([sp, 0]);
        var r2 = gc.addProperty("ADBE Vector Filter - Repeater"); r2.property("ADBE Vector Repeater Copies").setValue(rows);
        r2.property("ADBE Vector Repeater Transform").property("ADBE Vector Position").setValue([0, sp]);
        POS(l).setValue([x0, y0]); ANC(l).setValue([0, 0]);
        layerMask(l, rectShape(0, 0, x1 - x0, y1 - y0), 0);
        TRY("halftone fade", function () {
            var wp = fxAdd(l, "ADBE Linear Wipe", "density fade");
            setp(wp, "Transition Completion", DBG_WIPE); setp(wp, "Wipe Angle", 135); setp(wp, "Feather", 70);
        });
        return l;
    }
    function captionArt(T) {                                      // the static caption art (its own comp so the CMY ghosts can reuse it)
        var comp = app.project.items.addComp("CAPTION ART " + T.text, W, H, 1, 1, FPS);
        TRY("comp folder", function () { if (FOLDER) comp.parentFolder = FOLDER; });
        var o = { font: "Bangers-Regular", size: CAP.size, fill: hex("#0B0B0B"), track: 40, just: "l" };
        var t = mkText(comp, T.text, o); t.name = "caption text";
        var r = rect(t), cb = capBox(comp, o.font, o.size);
        var bw = Math.round(r.width + CAP.padX * 2), bh = Math.round(cb.height + CAP.padY * 2);
        var x0 = CAP.x, y0 = CAP.y, x1 = x0 + bw, y1 = y0 + bh;
        POS(t).setValue([x0 + CAP.padX - r.left, y0 + CAP.padY - cb.top]);
        // layers, bottom to top: print shadow, box, halftone, ink border, text
        function shapeRect(name, ax0, ay0, ax1, ay1, fill, stroke, sw) {
            var l = comp.layers.addShape(); l.name = name;
            var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group"), gc = g.property("ADBE Vectors Group");
            var rr = gc.addProperty("ADBE Vector Shape - Rect"); rr.property("ADBE Vector Rect Size").setValue([ax1 - ax0, ay1 - ay0]);
            rr.property("ADBE Vector Rect Position").setValue([(ax0 + ax1) / 2, (ay0 + ay1) / 2]);
            if (fill) { var f = gc.addProperty("ADBE Vector Graphic - Fill"); f.property("ADBE Vector Fill Color").setValue(fill); }
            if (stroke) {
                var s = gc.addProperty("ADBE Vector Graphic - Stroke"); s.property("ADBE Vector Stroke Color").setValue(stroke);
                s.property("ADBE Vector Stroke Width").setValue(sw); TRY("miter", function () { s.property("ADBE Vector Stroke Line Join").setValue(1); });
            }
            ANC(l).setValue([0, 0]); POS(l).setValue([0, 0]);
            return l;
        }
        var shadow = shapeRect("print shadow", x0 + CAP.shadow, y0 + CAP.shadow, x1 + CAP.shadow, y1 + CAP.shadow, hex("#E8267F"), null, 0);
        var box = shapeRect("box", x0, y0, x1, y1, hex("#FFD61F"), null, 0);
        var dots = dotLayer(comp, x0, y0, x1, y1, hex("#F29A00"), "halftone");
        var border = shapeRect("ink border", x0, y0, x1, y1, null, hex("#0B0B0B"), CAP.border);
        t.moveToBeginning();                                        // top -> bottom: text, border, halftone, box, shadow
        return { comp: comp, box: [x0, y0, x1 + CAP.shadow, y1 + CAP.shadow] };
    }
    function captionBox(main, T, X, idx) {
        var n = T.f1 - T.f, comp = newComp("CAPTION " + T.text, T.f, T.f1);
        var art = captionArt(T), b = art.box, cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
        var e = n - 1;
        function addArt(name, tint, dx, dy, f0, f1, blend) {
            var l = comp.layers.add(art.comp); l.name = name;
            ANC(l).setValue([cx, cy]);
            inout(l, f0, f1);
            K(POS(l), [[0, [cx + dx, cy + dy]]], "lin");
            // pop in with overshoot, then settle; pop out: anticipation then collapse
            K(SCL(l), [[0, [55, 55]], [2, [124, 124]], [4, [94, 94]], [6, [101, 101]], [8, [100, 100]], [e - 6, [100, 100]], [e - 4, [108, 108]], [e, [0, 0]]], "io");
            K(ROT(l), [[0, -6], [2, 2.5], [4, -1], [7, 0], [e - 6, 0], [e, 5]], "io");
            if (tint) TRY("tint", function () { var fx = fxAdd(l, "ADBE Fill", "tint"); setp(fx, "Color", tint); });
            if (blend) TRY("blend", function () { l.blendingMode = blend; });
            return l;
        }
        // the main art on top, the CMY misregistration ghosts under it for the first 2 frames
        var ghostC = addArt("misreg cyan", hex("#00B7EB"), -9, 3, 0, 2);
        var ghostM = addArt("misreg magenta", hex("#EC008C"), 8, -4, 0, 2);
        var ghostY = addArt("misreg yellow", hex("#FFF200"), 2, 7, 0, 2);
        var main_ = addArt("caption art", null, 0, 0, 0, n);
        ghostC.moveAfter(main_); ghostM.moveAfter(ghostC); ghostY.moveAfter(ghostM);
        // a second, 1-frame kick of misregistration as it leaves
        var kC = addArt("misreg exit cyan", hex("#00B7EB"), 7, -2, e - 5, e - 3);
        kC.moveAfter(main_);
        var L = putInMain(main, comp, "TITLE caption_box: " + T.text, T.f, T.f1);
        dropShadow(L, 35, 0, 18, 135, "lift");
        return L;
    }

    // ---------------------------------------------------------------- novax
    var PAL = {
        cyan:          { settle: 40, top: "#FFFFFF", bot: "#4CCBFF", stroke: "#4FD2FF", glowA: "#E4F8FF", glowB: "#0FA9FF" },
        red_gold:      { settle: 40, top: "#FFE08A", bot: "#FF2E1F", stroke: "#FF3A2A", glowA: "#FFE9A6", glowB: "#FF2A12" },
        crimson_white: { settle: 55, top: "#FFFFFF", bot: "#E0123F", stroke: "#FF2A55", glowA: "#FFFFFF", glowB: "#FF1744" }
    };
    var NOVAX_FONT = "ChineseRocksRg-Regular", TAG_FONT = "Montserrat-Light";
    var ACT_TAG = { tobey: "TOBEY MAGUIRE", andrew: "ANDREW GARFIELD", tom: "TOM HOLLAND" };
    function slantBar(cx, top, bot, w, lean) { var s = new Shape(); s.vertices = [[cx - w / 2, top], [cx + w / 2, top], [cx + w / 2 + lean, bot], [cx - w / 2 + lean, bot]]; s.closed = true; return s; }
    function novax(main, T, X, idx, ctx) {
        var n = T.f1 - T.f, comp = newComp("NOVAX " + T.text, T.f, T.f1), pal = PAL[T.palette] || PAL.cyan, act = X.act[String(idx)];
        var cx = W / 2, cy = T.y || 470;
        // hero size: the final (tracked-open) word spans <= 1380 px, so it is fully in frame and never clipped
        var probe = mkText(comp, T.text, { font: NOVAX_FONT, size: 300, fill: [1, 1, 1], italic: true });
        var w300 = rect(probe).width; probe.remove();
        var gaps = T.text.length - 1;
        var maxW = (X.behind[String(idx)] ? 1520 : 1380);
        var S = Math.min(420, Math.floor(300 * maxW / (w300 + gaps * 0.048 * 300)));
        var oh = { font: NOVAX_FONT, size: S, fill: [1, 1, 1], italic: true };
        var cb = capBox(comp, NOVAX_FONT, S), capH = cb.height, top = cy - capH / 2, bot = cy + capH / 2;
        var heroW = w300 * S / 300 + gaps * 0.048 * S;
        var tr = [[0, -26], [18, 48]];
        function hero(name, o) {
            var l = mkText(comp, T.text, o); l.name = name; place(comp, l, o, cx, cy);
            trackAnim(l, tr, "out");
            return l;
        }
        // ---- bottom to top
        // tag on a rough black brush bar, just under the baseline (its own comp: it stays in FRONT of the subject)
        var tcomp = newComp("NOVAX TAG " + T.text, T.f, T.f1);
        var tagText = T.tag || ACT_TAG[act] || "";
        var barH = Math.max(46, Math.round(capH * 0.17)), barW = Math.round(Math.max(heroW * 0.3, tagText.length * barH * 0.62 + 90)), barCy = bot + capH * 0.08 + barH / 2 + 10, barL = cx - heroW / 2 + heroW * 0.03;
        var bar = tcomp.layers.addShape(); bar.name = "tag bar";
        var bg = bar.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var br = bg.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect"); br.property("ADBE Vector Rect Size").setValue([barW, barH]); br.property("ADBE Vector Rect Position").setValue([barW / 2, 0]);
        var bf = bg.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill"); bf.property("ADBE Vector Fill Color").setValue([0, 0, 0]);
        ANC(bar).setValue([0, 0]); POS(bar).setValue([barL, barCy]);
        K(SCL(bar), [[4, [0, 100]], [15, [100, 100]]], "out");
        TRY("bar roughen", function () {
            var rg = fxAdd(bar, "ADBE Roughen Edges", "brush edge");
            setp(rg, "Border", 7); setp(rg, "Edge Sharpness", 1); setp(rg, "Fractal Influence", 1); setp(rg, "Scale", 100);
            setp(rg, "Stretch Width or Height", 39); setp(rg, "Complexity", 7);
        });
        dropShadow(bar, 55, 6, 10, 135, "bar shadow");
        var ot = { font: TAG_FONT, size: Math.max(26, Math.round(barH * 0.52)), fill: [1, 1, 1], track: 120 };
        if (tagText) {
            var tag = mkText(tcomp, tagText, ot); tag.name = "tag";
            place(tcomp, tag, ot, barL + barW / 2, barCy);
            trackAnim(tag, [[6, 0], [20, 260]], "out");
            K(OPA(tag), [[6, 0], [11, 100]], "lin");
        }
        // gradient fill: a ramp solid cut by the alpha of the (hidden) fill text. White at the top, the hue at the bottom.
        var fillT = hero("fill text (matte)", oh);
        TRY("fill roughen", function () { var rg = fxAdd(fillT, "ADBE Roughen Edges", "distress"); setp(rg, "Border", 1.2); setp(rg, "Scale", 35); });
        var ramp = comp.layers.addSolid([1, 1, 1], "fill gradient", W, H, 1, n / FPS);
        TRY("ramp", function () {
            var rp = fxAdd(ramp, "ADBE Ramp", "white to hue");
            setp(rp, "Start of Ramp", [cx, top + capH * 0.12]); setp(rp, "Start Color", hex(pal.top));
            setp(rp, "End of Ramp", [cx, bot]); setp(rp, "End Color", hex(pal.bot));
        });
        ramp.moveBefore(fillT);
        ramp.setTrackMatte(fillT, TrackMatteType.ALPHA); fillT.enabled = false;
        K(OPA(ramp), [[0, 100], [5, 100], [20, pal.settle || 38]], "io");           // settles to a mostly-outline word; a thin fill stays so it reads over footage
        TRY("fill shadow", function () { dropShadow(ramp, 50, 5, 8, 135, "fill shadow"); });
        // light sweep: a white copy under a slanted moving mask, added on top, with its own bloom
        var sweepO = { font: NOVAX_FONT, size: S, fill: [1, 1, 1], italic: true };
        var sw = hero("light sweep", sweepO);
        var barW2 = capH * 0.36, lean = -capH * 0.4, t0 = top - capH * 0.5, t1 = bot + capH * 0.5;
        var lx0 = cx - heroW / 2 - barW2 - 30, lx1 = cx + heroW / 2 + barW2 + 60 - lean;
        // masks live in layer space (origin = the text's baseline point), so the comp-space bar is shifted by the layer position
        function sweepMask(l, w, feather, f0, f1) {
            var pp = POS(l).value, ox = pp[0], oy = pp[1];
            var m = layerMask(l, slantBar(lx0 - ox, t0 - oy, t1 - oy, w, lean), feather);
            m.property("ADBE Mask Shape").setValuesAtTimes([f2t(f0), f2t(f1)], [slantBar(lx0 - ox, t0 - oy, t1 - oy, w, lean), slantBar(lx1 - ox, t0 - oy, t1 - oy, w, lean)]);
        }
        sweepMask(sw, barW2, 9, 0, 13);
        sw.blendingMode = BlendingMode.ADD;
        glow(sw, "sweep glow", 60, 26, 2.2, hex(pal.glowA), hex(pal.glowB), 1);
        K(OPA(sw), [[0, 100], [13, 100], [14, 0]], "lin");
        // bloom: the big flare that peaks mid-sweep and is gone a few frames later (a tight, intense bloom, never a haze)
        var bl = hero("bloom", sweepO);
        sweepMask(bl, barW2 * 1.4, 60, 0, 13);
        bl.blendingMode = BlendingMode.ADD;
        glow(bl, "bloom wide", 65, 110, 5.0, hex(pal.glowA), hex(pal.glowB), 1);
        glow(bl, "bloom tight", 65, 28, 3.5, hex(pal.glowA), hex(pal.glowB), 1);
        K(OPA(bl), [[0, 0], [6, 100], [15, 0]], "lin");
        // outline (the held look): a stroke-only copy with a tight palette glow
        var oS = { font: NOVAX_FONT, size: S, fill: null, stroke: hex(pal.stroke), sw: Math.max(3, Math.round(S / 90)), italic: true };
        var st = hero("outline", oS);
        glow(st, "outline glow tight", 40, 12, 1.0, hex(pal.glowA), hex(pal.glowB));
        glow(st, "outline glow", 40, 42, 0.55, hex(pal.glowB), hex(pal.glowB));
        dropShadow(st, 75, 6, 16, 135, "outline shadow");
        // thin white sub, laid across the middle of the hero
        if (T.sub) {
            var os = { font: TAG_FONT, size: Math.round(S * 0.3), fill: [1, 1, 1], track: 200 };
            var sb = mkText(comp, T.sub, os); sb.name = "sub"; place(comp, sb, os, cx, cy);
            trackAnim(sb, [[2, -67], [20, 28]], "out");
            K(OPA(sb), [[3, 0], [9, 100]], "lin");
            dropShadow(sb, 85, 0, 18, 135, "sub shadow wide");
            dropShadow(sb, 80, 3, 5, 135, "sub shadow");
        }
        var L = putInMain(main, comp, "TITLE novax: " + T.text, T.f, T.f1);
        // behind the subject: inverted luma track matte from MATTE_<id>; in front when there is no matte
        var bid = X.behind[String(idx)], ml = null;
        if (bid && ctx.matte) ml = ctx.matte(bid);
        if (ml) {
            L.setTrackMatte(ml, TrackMatteType.LUMA_INVERTED);
            L.name += " (behind subject)";
        } else if (T.behind) warn("no matte for " + T.behind + ": '" + T.text + "' goes in front of the subject");
        exitMotion(L, T.f1, X.cut[String(idx)]);
        if (tagText) {
            var TL = putInMain(main, tcomp, "TITLE novax tag: " + tagText, T.f, T.f1);
            exitMotion(TL, T.f1, X.cut[String(idx)]);
            TL.moveBefore(L);
        }
        return L;
    }

    // ---------------------------------------------------------------- build
    function build(main, E, ctx) {
        CTX = ctx; FPS = E.fps || ctx.fps || 30; W = E.w || ctx.w || 1920; H = E.h || ctx.h || 1080;
        var X = (E.x && E.x.titles) || { sub: {}, shot: {}, behind: {}, cut: {}, act: {} };
        FOLDER = app.project.items.addFolder("TITLES");
        var made = [];
        for (var i = 0; i < E.titles.length; i++) {
            var T = E.titles[i], L = null;
            try {
                if (T.style == "sub") L = subTitle(main, T, X, i, E);
                else if (T.style == "namecard") L = namecard(main, T, X, i);
                else if (T.style == "caption_box") L = captionBox(main, T, X, i);
                else if (T.style == "novax") L = novax(main, T, X, i, ctx);
                // blender_* titles come from Blender
            } catch (err) { warn("title " + i + " " + T.style + " '" + T.text + "': " + err); }
            if (L) made.push(L);
        }
        if (E.watermark) TRY("watermark", function () { watermark(main, E.watermark); });
        return { layers: made.length, warnings: WARN };
    }
    return { build: build, PAL: PAL };
})();
