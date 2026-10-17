// special.jsx: SPECIAL, the three showpiece transitions of Timeless v2 (EDIT.md "Transitions"):
//   rift (f244-262), drop_portal (f468-492), panel_slam / triptych (f777-819 + the shatter into the outro).
// ONE global (SPECIAL); every helper lives in the closure so the lib concatenates with fx/grade/titles in any order.
// Numbers that Python computes (panel quads, shard polygons, caption scramble) come from E.x.special (special_spec.py).
// EffectCraft notes (bugs, workarounds) are in docs/EFFECTCRAFT-NOTES.md, section "special".
var SPECIAL = (function () {
    var FPS = 30, W = 1920, H = 1080;
    var C = null, MAIN = null, X = null, E = null, WARN = [], CACHE = {};

    // ------------------------------------------------------------------ small helpers
    function f2t(f) { return f / FPS; }
    function TG(l) { return l.property("ADBE Transform Group"); }
    function POS(l) { return TG(l).property("ADBE Position"); }
    function SCL(l) { return TG(l).property("ADBE Scale"); }
    function ROT(l) { return TG(l).property("ADBE Rotate Z"); }
    function OPA(l) { return TG(l).property("ADBE Opacity"); }
    function ANC(l) { return TG(l).property("ADBE Anchor Point"); }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    function warn(s) { WARN.push(s); if (C && C.log) C.log("WARN " + s); }
    function TRY(what, fn) { try { return fn(); } catch (e) { warn(what + ": " + e); return null; } }
    function fxAdd(l, mn, label) {
        var e = FXP(l).addProperty(mn);
        if (label) { e.name = label; return FXP(l).property(label); }
        return e;
    }
    function setp(fx, name, v) { TRY("set " + name, function () { fx.property(name).setValue(v); }); }
    function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }
    function lerp(a, b, t) { return a + (b - a) * t; }
    function lerp2(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t)]; }
    function eOutExpo(t) { t = clamp(t, 0, 1); return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t); }
    function eInExpo(t) { t = clamp(t, 0, 1); return t <= 0 ? 0 : Math.pow(2, 10 * (t - 1)); }
    function eInQuad(t) { t = clamp(t, 0, 1); return t * t; }
    function eInCubic(t) { t = clamp(t, 0, 1); return t * t * t; }
    function eOutCubic(t) { t = clamp(t, 0, 1); return 1 - Math.pow(1 - t, 3); }
    function eInOut(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
    // seeded rng (the shake must be the same on every build)
    function rng(seed) {
        var s = seed >>> 0 || 1;
        return function () { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    }
    // a property keyed at every integer frame in [fa, fb] from fn(frame) -> value (the easing lives in fn)
    function keyFn(prop, fa, fb, fn, step) {
        step = step || 1;
        var ts = [], vs = [];
        for (var f = fa; f <= fb + 1e-6; f += step) { ts.push(f2t(f)); vs.push(fn(f)); }
        if (ts.length == 1) prop.setValue(vs[0]); else prop.setValuesAtTimes(ts, vs);
    }
    function keyList(prop, ks) {   // [[frame, value], ...]
        var ts = [], vs = [];
        for (var i = 0; i < ks.length; i++) { ts.push(f2t(ks[i][0])); vs.push(ks[i][1]); }
        if (ts.length == 1) prop.setValue(vs[0]); else prop.setValuesAtTimes(ts, vs);
    }
    function sc(v) { return [v, v]; }
    function clearKeys(prop, f0, f1) {      // remove the keys in [f0, f1] (frames)
        for (var i = prop.numKeys; i >= 1; i--) {
            var t = prop.keyTime(i) * FPS;
            if (t >= f0 - 1e-4 && t <= f1 + 1e-4) prop.removeKey(i);
        }
    }
    function shape(verts, closed) {
        var s = new Shape(); s.vertices = verts; s.closed = closed !== false; return s;
    }
    function ellipseShape(cx, cy, rx, ry) {
        var k = 0.5523, s = new Shape();
        s.vertices = [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]];
        s.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
        s.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
        s.closed = true; return s;
    }
    function addMask(l, shp, feather) {
        var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        m.property("ADBE Mask Shape").setValue(shp);
        if (feather) m.property("ADBE Mask Feather").setValue([feather, feather]);
        return m;
    }
    function solid(comp, name, col, w, h) {
        return comp.layers.addSolid(col || [0, 0, 0], name, w || comp.width, h || comp.height, 1, comp.duration);
    }
    function adj(comp, name) { var l = solid(comp, name, [1, 1, 1]); l.adjustmentLayer = true; return l; }
    function span(l, f0, f1) { l.outPoint = f2t(f1); l.inPoint = f2t(f0); if (l.inPoint * FPS < f0 - 0.5) { l.outPoint = f2t(f1); l.inPoint = f2t(f0); } }
    function newComp(name, w, h, durF) {
        var c = app.project.items.addComp(name, w || W, h || H, 1, (durF || MAIN.duration * FPS) / FPS, FPS);
        TRY("parent folder", function () { if (C.elements) c.parentFolder = C.elements; });
        TRY("comp mb", function () { c.shutterAngle = 270; c.motionBlurSamplesPerFrame = 12; });
        TRY("comp mb on", function () { c.motionBlur = true; });
        c.bgColor = [0, 0, 0];
        return c;
    }
    // File.exists is always false in EffectCraft 0.10 (docs/EFFECTCRAFT-NOTES.md), so probe by importing
    function importOk(path) {
        if (CACHE[path]) return true;
        var it = TRY("probe " + path, function () { return app.project.importFile(new ImportOptions(new File(path))); });
        if (it) { CACHE[path] = it; TRY("folder", function () { it.parentFolder = C.elements; }); return true; }
        return false;
    }
    function footage(path) {
        if (!CACHE[path]) { CACHE[path] = app.project.importFile(new ImportOptions(new File(path))); TRY("folder", function () { CACHE[path].parentFolder = C.elements; }); }
        return CACHE[path];
    }
    function clipFile(id, file) {
        if (C.src === "src240") { var p = C.data + "/src240/clip_" + id + ".mp4"; if (importOk(p)) return p; }
        return file;
    }
    // an RGBA image sequence by its first frame; returns the footage item or null when the folder is missing
    function sequence(dir, firstFrame) {
        var p = dir + "/" + ("0000" + firstFrame).slice(-4) + ".png";
        var o = new ImportOptions(new File(p)); o.sequence = true;
        var it = null;
        try { it = app.project.importFile(o); } catch (e) { return null; }
        if (!it) return null;
        TRY("conform", function () { it.mainSource.conformFrameRate = FPS; });
        TRY("folder", function () { it.parentFolder = C.elements; });
        return it;
    }
    function addText(comp, text, size, pos, fill, font, tracking, just) {
        var l = comp.layers.addText(text);
        TRY("text style", function () {
            var tp = l.property("ADBE Text Properties").property("ADBE Text Document");
            var d = tp.value; d.resetCharStyle();
            if (font) d.font = font;
            d.fontSize = size; d.fillColor = fill || [1, 1, 1]; if (tracking) d.tracking = tracking;
            d.justification = just || ParagraphJustification.CENTER_JUSTIFY;
            tp.setValue(d);
        });
        if (pos) POS(l).setValue(pos);
        return l;
    }
    function shapeLayer(comp, name) { var l = comp.layers.addShape(); l.name = name; POS(l).setValue([0, 0]); return l; }   // shape coordinates = comp pixels
    // adds a polygon (or any Shape) with fill and/or stroke to a shape layer; returns the group
    function addShapeGroup(l, shp, fill, stroke, strokeW) {
        var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var v = g.property("ADBE Vectors Group");
        v.addProperty("ADBE Vector Shape - Group").property("ADBE Vector Shape").setValue(shp);
        if (fill) v.addProperty("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(fill);
        if (stroke) {
            var st = v.addProperty("ADBE Vector Graphic - Stroke");
            st.property("ADBE Vector Stroke Color").setValue(stroke);
            st.property("ADBE Vector Stroke Width").setValue(strokeW || 4);
        }
        return g;
    }
    function shakeAt(u, amp, decay, seed) {   // decaying 2-D shake u frames after the hit
        if (u < 0) return [0, 0];
        var a = amp * Math.exp(-u / decay);
        return [a * Math.sin(u * 2.9 + seed), a * Math.cos(u * 3.7 + seed * 2.1)];
    }
    function clipDuration(item) { return item.duration; }

    // ------------------------------------------------------------------ the act grade feel of a panel
    var LOOKS = {
        tobey: { cb: [-12, 4, 14, 6, 1, -4, 16, 8, -14], contrast: 8, glow: [80, 40, 0.5] },
        andrew: { cb: [-10, 4, 14, -4, 0, 10, -4, 3, 12], contrast: 12, glow: [78, 36, 0.45] },
        tom: { cb: [-6, -2, 12, 14, 2, -8, 16, 8, -6], contrast: 22, glow: [82, 30, 0.4] }
    };
    var CB_NAMES = ["Shadow Red Balance", "Shadow Green Balance", "Shadow Blue Balance", "Midtone Red Balance",
        "Midtone Green Balance", "Midtone Blue Balance", "Highlight Red Balance", "Highlight Green Balance", "Highlight Blue Balance"];
    function gradeLayer(comp, act, name) {
        var g = adj(comp, name || "GRADE " + act);
        applyGradeFx(g, act);
        return g;
    }
    function applyGradeFx(g, act) {
        var L = LOOKS[act] || LOOKS.tom;
        TRY("grade sharpen", function () { var e = fxAdd(g, "ADBE Unsharp Mask2", "sharpen"); setp(e, "Amount", 55); setp(e, "Radius", 1.2); });
        TRY("grade cb", function () { var cb = fxAdd(g, "ADBE Color Balance 2", "act balance"); for (var i = 0; i < 9; i++) setp(cb, CB_NAMES[i], L.cb[i]); setp(cb, "Preserve Luminosity", 1); });
        TRY("grade bc", function () { var e = fxAdd(g, "ADBE Brightness & Contrast 2", "contrast"); setp(e, "Contrast", L.contrast); });
        TRY("grade glow", function () { var e = fxAdd(g, "ADBE Glo2", "bloom"); setp(e, "Glow Threshold", L.glow[0]); setp(e, "Glow Radius", L.glow[1]); setp(e, "Glow Intensity", L.glow[2]); });
    }

    // ================================================================== TRIPTYCH
    function quadShape(q, grow) {   // q = [[x,y]..] screen quad; grow pushes the edges out by px
        var cx = 0, cy = 0, i;
        for (i = 0; i < 4; i++) { cx += q[i][0] / 4; cy += q[i][1] / 4; }
        var v = [];
        for (i = 0; i < 4; i++) {
            var dx = q[i][0] - cx, dy = q[i][1] - cy, d = Math.sqrt(dx * dx + dy * dy) || 1;
            v.push([q[i][0] + dx / d * (grow || 0), q[i][1] + dy / d * (grow || 0)]);
        }
        return shape(v, true);
    }

    // one comic panel as its own comp (screen space 1920x1080: the quad is cut out by a mask in TRIP)
    function buildPanelComp(P, idx, T) {
        var pc = newComp("SP_PANEL_" + (idx + 1) + "_" + P.act, W, H);
        var item = footage(clipFile(P.clip, P.file));
        var fl = pc.layers.add(item); fl.name = "plate " + P.clip;
        fl.timeRemapEnabled = true;
        var dur = clipDuration(item), n = T.f1 - P.f + 9;      // plays slowly from its hit to just past the shatter
        var s0 = clamp(P.src[0], 0, dur - 0.05), s1 = clamp(P.src[1], s0 + 0.05, dur - 0.02);
        var tr = fl.property("ADBE Time Remapping");
        tr.setValuesAtTimes([0, f2t(P.f), f2t(P.f + n)], [s0, s0, s1]);
        for (var k = tr.numKeys; k > 3; k--) tr.removeKey(k);
        fl.outPoint = pc.duration; fl.inPoint = 0;
        var sFit = P.scale;
        // plate: head on the panel centre, a slow push while the panel lives
        ANC(fl).setValue(P.focus);
        POS(fl).setValue([P.cx + P.slant_shift, P.cy]);
        keyList(SCL(fl), [[P.f, sc(sFit)], [P.f + n, sc(sFit * 1.07)]]);
        gradeLayer(pc, P.act);
        // ink border on the quad's edge (the TRIP mask cuts the outer half away)
        var bl = shapeLayer(pc, "border");
        addShapeGroup(bl, quadShape(P.quad, 0), null, [0.97, 0.96, 0.92], 12);
        // the small earth label: comic caption box, bottom left of the panel
        var lx = P.quad[0][0] + 26, ly = P.quad[0][1] - 76, bw = 250, bh = 46;
        var lb = shapeLayer(pc, "label box");
        addShapeGroup(lb, shape([[lx, ly], [lx + bw, ly], [lx + bw, ly + bh], [lx, ly + bh]], true), [1, 0.83, 0.05], [0, 0, 0], 4);
        addShapeGroup(lb, shape([[lx + 5, ly + 5], [lx + bw + 5, ly + 5], [lx + bw + 5, ly + bh + 5], [lx + 5, ly + bh + 5]], true), [0, 0, 0], null);   // print shadow (first group is on top)
        var lt = addText(pc, P.earth, 30, [lx + bw / 2, ly + bh / 2 + 13], [0.04, 0.04, 0.04], "Anton-Regular", 40);
        lt.name = "label " + P.earth;
        return pc;
    }

    // slam transform for a layer whose anchor/position sit at (cx, cy): scale, tilt and shake over the hit at f
    function slamKeys(l, cx, cy, f, f_end, o) {
        o = o || {};
        var dir = o.dir || 1, seed = o.seed || 1, s0 = o.s0 || 158, tilt = o.tilt === undefined ? 5 : o.tilt, amp = o.amp || 26;
        keyFn(SCL(l), f - 1, f_end, function (k) {
            var u = k - f; if (u < 0) return sc(s0);
            var idle = o.idle ? o.idle * clamp(u / 40, 0, 1.5) : 0;
            return sc(100 + (s0 - 100) * (1 - eOutExpo(u / 6.5)) + idle);
        });
        keyFn(ROT(l), f - 1, f_end, function (k) {
            var u = k - f; if (u < 0) return dir * tilt;
            return dir * tilt * (1 - eOutExpo(u / 8)) + (o.rest || 0);
        });
        keyFn(POS(l), f - 1, f_end, function (k) {
            var sh = shakeAt(k - f, amp, 3.4, seed);
            return [cx + sh[0], cy + sh[1]];
        });
        keyList(OPA(l), [[f - 1, 0], [f, 100]]);
        ANC(l).setValue([cx, cy]);
    }

    // halftone: a grid of dots (two nested repeaters), optionally clipped to a quad; position drifts so the page lives
    function dotGrid(comp, name, col, sp, size, quad, drift) {
        var l = comp.layers.addShape(); l.name = name;
        var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var gc = g.property("ADBE Vectors Group");
        var cols = Math.ceil(W / sp) + 4, rows = Math.ceil(H / sp) + 4;
        var el = gc.addProperty("ADBE Vector Shape - Ellipse"); el.property("ADBE Vector Ellipse Size").setValue([size, size]);
        var fl = gc.addProperty("ADBE Vector Graphic - Fill"); fl.property("ADBE Vector Fill Color").setValue(col);
        var r1 = gc.addProperty("ADBE Vector Filter - Repeater"); r1.property("ADBE Vector Repeater Copies").setValue(cols);
        r1.property("ADBE Vector Repeater Transform").property("ADBE Vector Position").setValue([sp, 0]);
        var r2 = gc.addProperty("ADBE Vector Filter - Repeater"); r2.property("ADBE Vector Repeater Copies").setValue(rows);
        r2.property("ADBE Vector Repeater Transform").property("ADBE Vector Position").setValue([0, sp]);
        ANC(l).setValue([0, 0]);
        POS(l).setValue([-sp * 2, -sp * 2]);
        if (quad) {   // the mask lives in layer space: shift the quad by the layer's offset (no drift on masked grids)
            var q2 = [], k; for (k = 0; k < 4; k++) q2.push([quad[k][0] + sp * 2, quad[k][1] + sp * 2]);
            addMask(l, shape(q2, true), 0);
        } else if (drift) keyList(POS(l), [[drift[0], [-sp * 2, -sp * 2]], [drift[1], [-sp * 2 + sp * 0.9, -sp * 2 + sp * 0.9]]]);
        return l;
    }
    var ACT_COL = { tobey: [0.95, 0.2, 0.22], andrew: [0.15, 0.55, 1.0], tom: [0.62, 0.3, 0.95] };

    // the designed page under the panels: dark halftone, the frozen M14 dimmed and blurred behind, and each
    // not-yet-arrived slot already inked and tinted in its act colour (a ghost the real panel then slams onto)
    function buildTripBackground(trip, T) {
        var panels = T.panels, i, P, fa = T.f0 - 2, fb = T.shatter + 12;
        var page = solid(trip, "page", [0.035, 0.02, 0.07]);
        // the frozen M14 (SHOT_S32's held frame), dimmed and blurred
        var comp = C.shotComp ? C.shotComp("S32") : null, S = C.shot ? C.shot("S32") : null;   // (the shatter-still pre-render has no shots)
        if (comp && S) {
            var bgL = trip.layers.add(comp); bgL.name = "M14 backdrop";
            bgL.timeRemapEnabled = true;
            var shotA = 0, j;
            for (j = 0; j < E.shots.length; j++) if (E.shots[j].id == "S32") shotA = E.shots[j].a;
            var held = f2t(770) - S.startTime, trk = bgL.property("ADBE Time Remapping");
            bgL.startTime = 0; bgL.outPoint = f2t(fb); bgL.inPoint = f2t(fa);
            trk.setValuesAtTimes([f2t(fa), f2t(fb)], [held, held]);
            for (j = trk.numKeys; j >= 1; j--) if (Math.abs(trk.keyValue(j) - held) > 1e-6) trk.removeKey(j);
            ANC(bgL).setValue([975, 470]);
            keyList(POS(bgL), [[fa, [940, 520]], [fb, [980, 540]]]);
            keyList(SCL(bgL), [[fa, sc(168)], [fb, sc(182)]]);
            OPA(bgL).setValue(88);
            TRY("backdrop blur", function () { var b = fxAdd(bgL, "ADBE Gaussian Blur 2", "blur"); setp(b, "Blurriness", 30); });
            TRY("backdrop grade", function () { var g = fxAdd(bgL, "ADBE Tint", "tint"); setp(g, "Map White To", [0.75, 0.55, 1.0]); setp(g, "Amount to Tint", 55); });
        }
        // page halftone (two screens, offset, slowly drifting)
        var d1 = dotGrid(trip, "page halftone", [0.55, 0.2, 0.75], 30, 12, null, [fa, fb]); OPA(d1).setValue(30);
        var vg = solid(trip, "page vignette", [1, 1, 1]); vg.blendingMode = BlendingMode.MULTIPLY;
        TRY("vignette", function () {
            var rp = fxAdd(vg, "ADBE Ramp", "vig"); setp(rp, "Ramp Shape", 2);
            setp(rp, "Start of Ramp", [W / 2, H / 2]); setp(rp, "Start Color", [1, 1, 1]); setp(rp, "End of Ramp", [W * 0.8, H * 0.95]); setp(rp, "End Color", [0.45, 0.4, 0.5]);
        });
        span(vg, fa, fb);
        // each slot: tint + halftone in the act colour + ink outline, from the start until its panel covers it
        for (i = 0; i < panels.length; i++) {
            P = panels[i]; var col = ACT_COL[P.act] || ACT_COL.tom;
            var tint = solid(trip, "slot tint " + (i + 1), col); OPA(tint).setValue(30);
            addMask(tint, quadShape(P.quad, 0), 0);
            var dg = dotGrid(trip, "slot dots " + (i + 1), col, 20, 11, P.quad, null); OPA(dg).setValue(48);
            var ol = shapeLayer(trip, "slot border " + (i + 1));
            addShapeGroup(ol, quadShape(P.quad, 0), null, [0.97, 0.96, 0.92], 12);
            OPA(ol).setValue(80);
            var slotL = [tint, dg, ol];
            for (var q = 0; q < 3; q++) { slotL[q].motionBlur = false; span(slotL[q], fa, P.f + 8); }
        }
    }

    function buildTriptych(T) {
        var panels = T.panels, i, P;
        var fs = T.f0, fe = T.f1, shat = T.shatter;
        var trip = newComp("SP_TRIPTYCH", W, H);
        var bg = solid(trip, "black", [0, 0, 0]); bg.name = "black";
        TRY("trip background", function () { buildTripBackground(trip, T); });
        var panelComps = [];
        for (i = 0; i < panels.length; i++) {
            P = panels[i]; P.slant_shift = 0;
            panelComps.push(buildPanelComp(P, i, T));
            var L = trip.layers.add(panelComps[i]); L.name = "PANEL_" + (i + 1);
            L.motionBlur = true;
            addMask(L, quadShape(P.quad, 0), 0);
            slamKeys(L, P.cx, P.cy, P.f, shat + 12, { dir: i % 2 ? -1 : 1, seed: 3 + i * 5, idle: 2.5, rest: (i - 1) * 0.45 });
            span(L, P.f - 1, shat + 12);
            // white impact flash on the quad (same transform)
            var fq = solid(trip, "hit flash " + (i + 1), [1, 1, 1]);
            fq.motionBlur = true; fq.blendingMode = BlendingMode.ADD;
            addMask(fq, quadShape(P.quad, 0), 0);
            slamKeys(fq, P.cx, P.cy, P.f, P.f + 6, { dir: i % 2 ? -1 : 1, seed: 3 + i * 5, rest: (i - 1) * 0.45 });
            keyList(OPA(fq), [[P.f - 1, 0], [P.f, 85], [P.f + 1, 55], [P.f + 3, 0]]);
            span(fq, P.f - 1, P.f + 4);
        }
        // TIMELESS: the Blender chrome render when it exists (frames 802-826), else an EffectCraft stand-in
        var tf = T.title.f || 802, tseq = sequence(C.data + "/blender/timeless3d", tf), title;
        if (tseq) {
            title = trip.layers.add(tseq); title.name = "TIMELESS 3D (blender)";
            title.startTime = f2t(tf); title.inPoint = f2t(tf); title.outPoint = f2t(tf + (tseq.duration * FPS) | 0);
        } else {
            var pcT = buildTimelessPlaceholder(tf);
            title = trip.layers.add(pcT); title.name = "TIMELESS (placeholder)"; title.motionBlur = true;
            span(title, tf - 1, 900);
            slamKeys(title, 960, 540, tf, tf + 24, { s0: 300, tilt: 0, amp: 30, seed: 9 });
        }
        return { comp: trip, title: title };
    }

    // the TIMELESS stand-in lives in its own comp: slam in at tf, chrome ramp through the glyphs, bevel and bloom
    function buildTimelessPlaceholder(tf) {
        var pc = newComp("SP_TIMELESS_PLACEHOLDER", W, H);
        var t = addText(pc, "TIMELESS", 330, [960, 540 + 0.44 * 330], [1, 1, 1], "Anton-Regular", 30);
        t.name = "TIMELESS text";
        var rp = solid(pc, "chrome ramp", [1, 1, 1]);
        TRY("ramp", function () {
            var e = fxAdd(rp, "ADBE Ramp", "chrome");
            setp(e, "Start of Ramp", [960, 380]); setp(e, "Start Color", [1, 1, 1]);
            setp(e, "End of Ramp", [960, 700]); setp(e, "End Color", [0.35, 0.42, 0.55]);
        });
        rp.moveBefore(t);
        TRY("matte", function () { rp.setTrackMatte(t, TrackMatteType.ALPHA); });
        return pc;
    }

    // ---- S32 (M14 head raise) freezes and slams into the first panel: SHOT_S32 itself is frozen with Posterize Time,
    // boxed by an animated mask that closes from the frame to panel 1's quad while its picture lands head-on-centre.
    function vAt(prop, f) { var v = prop.valueAtTime(f2t(f), false); return [v[0], v[1]]; }
    function buildFreezeSlam(T) {
        var S = C.shot("S32"), comp = C.shotComp("S32"); if (!S || !comp) { warn("no SHOT_S32"); return; }
        var P = T.panels[0], f0 = 770, fc = 771, f1 = T.f0 - 1, i, f;     // freeze, start closing, last frame before panel 1 hits
        var shotA = 760;
        for (i = 0; i < E.shots.length; i++) if (E.shots[i].id == "S32") shotA = E.shots[i].a;
        var a = vAt(ANC(S), f0), pos0 = vAt(POS(S), f0), s0 = vAt(SCL(S), f0)[0], r0 = ROT(S).valueAtTime(f2t(f0), false);
        var head = [975, 470], sEnd = 128, tgt = [P.cx, P.cy];
        // a held copy of the shot (Posterize Time freezes the layer's masks too, a time-remap hold does not), graded like panel 3
        var F = MAIN.layers.add(comp); F.name = "SPECIAL_S32_freeze"; F.motionBlur = true;
        F.timeRemapEnabled = true;
        F.startTime = 0; F.outPoint = f2t(f1 + 1); F.inPoint = f2t(f0);
        var held = f2t(f0) - S.startTime, trk = F.property("ADBE Time Remapping");
        trk.setValuesAtTimes([f2t(f0), f2t(f1 + 1)], [held, held]);
        for (i = trk.numKeys; i >= 1; i--) if (Math.abs(trk.keyValue(i) - held) > 1e-6) trk.removeKey(i);
        applyGradeFx(F, "tom");
        ANC(F).setValue(a);
        var blk = solid(MAIN, "SPECIAL_S32_black", [0, 0, 0]); span(blk, fc, f1 + 1);
        blk.moveAfter(F);
        keyList(OPA(F), [[f0, 0], [fc, 100]]);
        var m = addMask(F, shape([[-2000, -2000], [4000, -2000], [4000, 3000], [-2000, 3000]], true), 0);
        var endPos = [tgt[0] - (head[0] - a[0]) * sEnd / 100, tgt[1] - (head[1] - a[1]) * sEnd / 100];
        var ts = [], ps = [], ss = [], rs = [], shp = [], quad = P.quad, full = [[0, 0], [W, 0], [W, H], [0, H]];
        for (f = f0; f <= f1; f++) {
            var u = clamp((f - fc) / (f1 - fc), 0, 1), e = eInQuad(u), sN = lerp(s0, sEnd, e), p = lerp2(pos0, endPos, e), verts = [];
            for (i = 0; i < 4; i++) {
                var qi = [3, 2, 1, 0][i], c = lerp2(full[i], quad[qi], e);   // full-frame corners TL TR BR BL -> the quad (BL BR TR TL)
                verts.push([a[0] + (c[0] - p[0]) * 100 / sN, a[1] + (c[1] - p[1]) * 100 / sN]);
            }
            ts.push(f2t(f)); ps.push(p); ss.push(sc(sN)); rs.push(r0 * (1 - e)); shp.push(shape(verts, true));
        }
        POS(F).setValuesAtTimes(ts, ps); SCL(F).setValuesAtTimes(ts, ss); ROT(F).setValuesAtTimes(ts, rs);
        m.property("ADBE Mask Shape").setValuesAtTimes(ts, shp);
    }

    // ---- the shatter at 819: each shard is the triptych comp cut by its polygon, flung out, spinning, fading to the outro
    function buildShatter(T, trip) {
        var f = T.shatter, shards = T.shards, i, S;
        // the outro underneath (core or us): Blender sequence if present, else black
        var have = false;
        for (i = 1; i <= MAIN.numLayers; i++) if (MAIN.layer(i).name.toUpperCase().indexOf("OUTRO") >= 0) have = true;
        if (!have) {
            var oseq = sequence(C.data + "/blender/outro", f);
            var ol;
            if (oseq) { ol = MAIN.layers.add(oseq); ol.name = "OUTRO (special)"; ol.startTime = f2t(f); }
            else { ol = solid(MAIN, "OUTRO black (placeholder)", [0, 0, 0]); }
            span(ol, f, 900);
        }
        var L = MAIN.layers.add(trip); L.name = "SPECIAL_TRIPTYCH"; span(L, T.f0, f);
        // the shards cut either a frozen still of the triptych at 819 (special_spec.prerender: cheap) or, when that
        // is missing, the live triptych comp (correct but ~36x slower: every shard re-renders the whole comp)
        var still = X.shatter_still && importOk(X.shatter_still) ? footage(X.shatter_still) : null;
        if (!still) warn("no pre-rendered triptych still: shards re-render the live comp (slow)");
        var crack = shapeLayer(MAIN, "SPECIAL_CRACKS");
        for (i = 0; i < shards.length; i++) {
            S = shards[i];
            var sl = MAIN.layers.add(still || trip); sl.name = "SHARD_" + (i < 10 ? "0" : "") + i;
            sl.motionBlur = true;
            addMask(sl, shape(S.poly, true), 0);
            var cx = S.c[0], cy = S.c[1], rr = rng(100 + i);
            ANC(sl).setValue([cx, cy]);
            var d0 = S.speed * 0.34, acc = S.speed * 0.045;
            var fa = f - 1, fb = f + 10;
            keyFn(POS(sl), fa, fb, function (k) {
                var u = Math.max(k - f - S.delay, 0);
                var d = d0 * u + 0.5 * acc * u * u;
                return [cx + S.dir[0] * d, cy + S.dir[1] * d + S.fall * u * u];
            });
            keyFn(ROT(sl), fa, fb, function (k) { var u = Math.max(k - f - S.delay, 0); return S.spin * u * (1 + 0.08 * u); });
            keyFn(SCL(sl), fa, fb, function (k) { var u = Math.max(k - f - S.delay, 0); return sc(100 * (1 + S.grow * u * (1 + 0.1 * u))); });
            keyFn(OPA(sl), fa, fb, function (k) { var u = Math.max(k - f - S.delay, 0); return 100 * (1 - eInQuad((u - 3.5) / 5)); });
            span(sl, f, f + 10);
            TRY("shard bevel", function () {
                var bv = fxAdd(sl, "ADBE Bevel Alpha", "rim");
                setp(bv, "Edge Thickness", 3); setp(bv, "Light Angle", Math.round(rr() * 360)); setp(bv, "Light Intensity", 0.7);
            });
            // crack line along the polygon (flashes on the hit)
            addShapeGroup(crack, shape(S.poly, true), null, [1, 1, 1], 3);
        }
        span(crack, f, f + 4);
        keyList(OPA(crack), [[f, 100], [f + 1, 90], [f + 3, 0]]);
        // white flash on the 819 hit
        var fl = solid(MAIN, "SPECIAL_SHATTER_FLASH", [1, 1, 1]); span(fl, f, f + 4);
        keyList(OPA(fl), [[f, 80], [f + 1, 35], [f + 3, 0]]);
        fl.blendingMode = BlendingMode.ADD;
    }

    // ================================================================== DROP PORTAL (f468-492)
    function ellipseRot(cx, cy, rx, ry, deg) {
        var k = 0.5523, r = deg * Math.PI / 180, c = Math.cos(r), sn = Math.sin(r), sh = new Shape();
        function P(x, y) { return [cx + x * c - y * sn, cy + x * sn + y * c]; }
        function V(x, y) { return [x * c - y * sn, x * sn + y * c]; }
        sh.vertices = [P(0, -ry), P(rx, 0), P(0, ry), P(-rx, 0)];
        sh.inTangents = [V(-rx * k, 0), V(0, -ry * k), V(rx * k, 0), V(0, ry * k)];
        sh.outTangents = [V(rx * k, 0), V(0, ry * k), V(-rx * k, 0), V(0, -ry * k)];
        sh.closed = true; return sh;
    }
    function radialBlur(l, label, ks, center) {   // CC Radial Fast Blur in glowing-streak mode, keyed [[frame, amount]]
        TRY(label, function () {
            var rb = fxAdd(l, "ec.blur.ccradialfast", label);
            setp(rb, "Center", center); TRY("zoom", function () { rb.property("Zoom").setValue(2); });
            keyList(rb.property("Amount"), ks);
        });
    }
    // anime speed lines: one shape layer of thin wedges around the origin, boiled by random rotations each frame
    function speedLines(name, f0, f1, centerFn, o) {
        var l = shapeLayer(MAIN, name), rr = rng(o.seed || 21), i, n = o.n || 56;
        for (i = 0; i < n; i++) {
            var th = rr() * Math.PI * 2, r0 = o.r0 * (0.8 + rr() * 0.9), r1 = r0 + o.len * (0.45 + rr() * 0.8), w = (o.w || 14) * (0.4 + rr() * 0.9);
            var c = Math.cos(th), sn = Math.sin(th);
            addShapeGroup(l, shape([[c * r0 - sn * w, sn * r0 + c * w], [c * r1, sn * r1], [c * r0 + sn * w, sn * r0 - c * w]], true), [1, 1, 1], null);
        }
        l.blendingMode = BlendingMode.ADD;
        span(l, f0, f1);
        keyFn(POS(l), f0, f1, centerFn);
        var r2 = rng((o.seed || 21) + 5);
        keyFn(ROT(l), f0, f1, function (f) { return r2() * 360; });
        keyFn(SCL(l), f0, f1, function (f) { return sc(100 + 30 * r2() * (o.boil || 1)); });
        keyList(OPA(l), o.opa);
        return l;
    }

    function buildPortal(Pt) {
        var lens = Pt.lens, drop = Pt.drop, A = C.shot("S17"), B = C.shot("S18"), centre = [W / 2, H / 2], f, i;
        if (!A || !B) { warn("portal: SHOT_S17/S18 missing"); return; }
        var own = Pt.own || {};
        // ---- 1. A09 slams into Andrew's lens (f472-479): scale in on the lens, lens to frame centre, shake grows with the riser
        var fS = drop - 8, aA = vAt(ANC(A), fS), pA = vAt(POS(A), fS), sA = vAt(SCL(A), fS)[0];
        var sp0 = [pA[0] + (lens[0] - aA[0]) * sA / 100, pA[1] + (lens[1] - aA[1]) * sA / 100], sEnd = 520;
        clearKeys(POS(A), fS, drop + 1); clearKeys(SCL(A), fS, drop + 1); clearKeys(ROT(A), fS, drop + 1);
        var rA = rng(77), ts = [], ps = [], ss = [], rs = [], s_;
        function slamA(f) {
            var u = (f - fS) / 8, s = sA * Math.pow(sEnd / sA, Math.pow(u, 2.1)), amp = 22 * u * u;
            var sp = lerp2(sp0, centre, eInOut(u));
            return { s: s, p: [sp[0] - (lens[0] - aA[0]) * s / 100 + (rA() - 0.5) * 2 * amp, sp[1] - (lens[1] - aA[1]) * s / 100 + (rA() - 0.5) * 2 * amp],
                     r: (rA() - 0.5) * 2 * 1.1 * u };
        }
        for (f = fS; f <= drop; f++) { s_ = slamA(f); ts.push(f2t(f)); ps.push(s_.p); ss.push(sc(s_.s)); rs.push(s_.r); }
        POS(A).setValuesAtTimes(ts, ps); SCL(A).setValuesAtTimes(ts, ss); ROT(A).setValuesAtTimes(ts, rs);
        radialBlur(A, "slam zoom blur", [[fS + 1, 0], [drop - 3, 45], [drop, 95]], lens);
        // ---- 2. the lens interior carries on under the portal: S17's last frame, held, still pushing in
        var holdComp = C.shotComp("S17"), hold = null;
        if (holdComp) {
            hold = MAIN.layers.add(holdComp); hold.name = "SPECIAL_S17_hold"; hold.motionBlur = true;
            hold.timeRemapEnabled = true;
            var bA = drop; for (i = 0; i < E.shots.length; i++) if (E.shots[i].id == "S17") bA = E.shots[i].b;
            var lastT = Math.min(f2t(bA - 1) - A.startTime, holdComp.duration - 1 / FPS);   // S17's last on-screen frame (the comp carries handle frames after it)
            hold.startTime = 0; hold.outPoint = f2t(drop + 14); hold.inPoint = f2t(drop);
            var trk = hold.property("ADBE Time Remapping");
            trk.setValuesAtTimes([f2t(drop), f2t(drop + 14)], [lastT, lastT]);
            for (i = trk.numKeys; i >= 1; i--) if (Math.abs(trk.keyValue(i) - lastT) > 1e-6) trk.removeKey(i);
            ANC(hold).setValue(aA);
            keyFn(SCL(hold), drop, drop + 14, function (f) { return sc(lerp(sEnd, sEnd * 2.2, (f - drop) / 14)); });
            keyFn(POS(hold), drop, drop + 14, function (f) { var s = lerp(sEnd, sEnd * 2.2, (f - drop) / 14); return [centre[0] - (lens[0] - aA[0]) * s / 100, centre[1] - (lens[1] - aA[1]) * s / 100]; });
            keyList(OPA(hold), [[drop, 100], [drop + 8, 85], [drop + 14, 0]]);
            radialBlur(hold, "hold blur", [[drop, 95], [drop + 14, 30]], lens);
            hold.moveAfter(B);
            C.log("hold in=" + hold.inPoint * FPS + " out=" + hold.outPoint * FPS + " idx=" + hold.index + " B.idx=" + B.index + " remap0=" + trk.valueAtTime(f2t(481), false) + " nk=" + trk.numKeys + " dur=" + holdComp.duration);
        }
        // ---- 3. M01 pulls out of Tom's lens: seen first inside the lens shape, a matte that grows to the full frame
        var aB = vAt(ANC(B), drop), fB = drop + 16, core = {};
        for (f = drop; f <= fB; f++) core[f] = { p: vAt(POS(B), f), s: vAt(SCL(B), f)[0], r: ROT(B).valueAtTime(f2t(f), false) };
        clearKeys(POS(B), drop, fB); clearKeys(SCL(B), drop, fB); clearKeys(ROT(B), drop, fB);
        var mB = addMask(B, ellipseRot(lens[0], lens[1], 80, 60, -18), 8);
        var tb = [], pb = [], sb = [], rb_ = [], mshape = [], mfeath = [], ring = [], rB = rng(55), sB0 = 300;
        function R(f) { var g = clamp((f - (drop + 1)) / 11, 0, 1); return 70 + 1430 * Math.pow(g, 2.2); }
        for (f = drop; f <= fB; f++) {
            var e = eOutExpo((f - drop) / 16), c0 = core[f];
            var sN = c0.s, spN = [c0.p[0] + (lens[0] - aB[0]) * sN / 100, c0.p[1] + (lens[1] - aB[1]) * sN / 100];
            var s = Math.exp(lerp(Math.log(sB0), Math.log(sN), e)), sp = lerp2(centre, spN, e), sh = shakeAt(f - drop, 24, 3.2, 5);
            var p = [sp[0] - (lens[0] - aB[0]) * s / 100 + sh[0], sp[1] - (lens[1] - aB[1]) * s / 100 + sh[1]];
            tb.push(f2t(f)); pb.push(p); sb.push(sc(s)); rb_.push(c0.r + 7 * (1 - e) + sh[0] * 0.04);
            var Rf = R(f), spx = [sp[0] + sh[0], sp[1] + sh[1]];
            mshape.push(ellipseRot(lens[0], lens[1], Rf * 1.3 * 100 / s, Rf * 0.95 * 100 / s, -18));
            mfeath.push([(6 + 40 * clamp((f - drop - 1) / 11, 0, 1)) * 100 / s, (6 + 40 * clamp((f - drop - 1) / 11, 0, 1)) * 100 / s]);
            ring.push({ f: f, c: spx, R: Rf });
        }
        POS(B).setValuesAtTimes(tb, pb); SCL(B).setValuesAtTimes(tb, sb); ROT(B).setValuesAtTimes(tb, rb_);
        mB.property("ADBE Mask Shape").setValuesAtTimes(tb, mshape); mB.property("ADBE Mask Feather").setValuesAtTimes(tb, mfeath);
        radialBlur(B, "pull-out zoom blur", [[drop, 80], [drop + 6, 40], [drop + 14, 0]], lens);
        // ---- 4. speed lines on the riser (S17)
        var cl = function (f) { var a_ = slamA(clamp(f, fS, drop)); return [a_.p[0] + (lens[0] - aA[0]) * a_.s / 100, a_.p[1] + (lens[1] - aA[1]) * a_.s / 100]; };
        if (own.lines !== false)
            speedLines("SPECIAL_SPEEDLINES", drop - 8, drop - 1, cl, { n: 60, r0: 300, len: 1100, w: 9, seed: 31,
                opa: [[drop - 8, 0], [drop - 6, 55], [drop - 3, 85], [drop - 1, 100]] });
        // ---- 5. THE DROP at f480: white flash, shockwave (Ripple) + ring, chromatic split
        if (own.shock !== false) {
            var sw = adj(MAIN, "SPECIAL_SHOCKWAVE"); span(sw, drop, drop + 14);
            TRY("ripple", function () {
                var rp = fxAdd(sw, "ADBE Ripple", "shockwave");
                setp(rp, "Center of Ripple", centre); setp(rp, "Wave Width", 150); setp(rp, "Wave Speed", 0);
                keyFn(rp.property("Radius"), drop, drop + 14, function (f) { return 40 + 1400 * eOutCubic((f - drop) / 13); });
                keyFn(rp.property("Wave Height"), drop, drop + 14, function (f) { return 20 * Math.pow(1 - clamp((f - drop) / 13, 0, 1), 1.4); });
            });
        }
        if (own.chroma !== false) {
            var ch = adj(MAIN, "SPECIAL_CHROMA_SPLIT"); span(ch, drop, drop + 8);
            TRY("chroma", function () {
                var ca = fxAdd(ch, "ec.vr.chromaticaberrations", "split");
                keyFn(ca.property("Aberration (Red)"), drop, drop + 8, function (f) { return 5 * Math.pow(1 - (f - drop) / 8, 1.5); });
                keyFn(ca.property("Aberration (Blue)"), drop, drop + 8, function (f) { return -5 * Math.pow(1 - (f - drop) / 8, 1.5); });
            });
        }
        if (own.ring !== false) {
            var rl = shapeLayer(MAIN, "SPECIAL_PORTAL_RING");
            var rg = addShapeGroup(rl, ellipseRot(0, 0, 100, 70, -18), null, [0.82, 0.94, 1], 18);
            var rpath = rg.property("ADBE Vectors Group").property("ADBE Vector Shape - Group").property("ADBE Vector Shape");
            var rts = [], rvs = [], rps = [];
            for (i = 0; i < ring.length; i++) { rts.push(f2t(ring[i].f)); rvs.push(ellipseRot(0, 0, ring[i].R * 1.3, ring[i].R * 0.95, -18)); rps.push(ring[i].c); }
            rpath.setValuesAtTimes(rts, rvs); POS(rl).setValuesAtTimes(rts, rps);
            keyList(rg.property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke").property("ADBE Vector Stroke Width"), [[drop, 30], [drop + 6, 12], [drop + 12, 3]]);
            keyList(OPA(rl), [[drop, 100], [drop + 9, 80], [drop + 13, 0]]);
            rl.blendingMode = BlendingMode.ADD; span(rl, drop, drop + 14);
            TRY("ring glow", function () { var g = fxAdd(rl, "ADBE Glo2", "ring glow"); setp(g, "Glow Threshold", 30); setp(g, "Glow Radius", 40); setp(g, "Glow Intensity", 1.4); });
        }
        if (own.flash !== false) {
            var fl = solid(MAIN, "SPECIAL_DROP_FLASH", [1, 1, 1]); span(fl, drop - 1, drop + 8);
            fl.blendingMode = BlendingMode.ADD;
            keyList(OPA(fl), [[drop - 1, 22], [drop, 100], [drop + 1, 100], [drop + 2, 72], [drop + 3, 44], [drop + 5, 16], [drop + 7, 0]]);
        }
    }

    // ================================================================== RIFT (f244-262)
    // the EffectCraft-native rift: fractal noise -> twirl -> polar (swirl rings) -> turbulent tear, tritone-coloured
    // magenta/cyan, halftone dots from CC Ball Action, a white-hot core. Used whenever no Blender element exists.
    function buildRiftComp(Rf) {
        // a centred vortex tunnel: horizontal noise streaks -> Rect to Polar = concentric rings (x -> angle, y -> radius);
        // a rotated noise makes them spiral arms; scrolling y runs the rings toward the viewer; ring strokes grow
        // exponentially for depth; a white-hot core at the vanishing point
        var rc = newComp("SP_RIFT", W, H), f0 = Rf.f0 - 2, f1 = Rf.f1 + 2;
        solid(rc, "void", [0.02, 0.0, 0.07]);
        function tunnelLayer(name, seed, dir, rot, tri, blend, opacity, speed) {
            var sw = solid(rc, name, [0.5, 0.5, 0.5]);
            TRY(name + " noise", function () {
                var fn = fxAdd(sw, "ADBE Fractal Noise", "noise");
                setp(fn, "Contrast", 230); setp(fn, "Brightness", -10); setp(fn, "Complexity", 5);
                TRY("uniform", function () { fn.property("Uniform Scaling").setValue(0); });
                TRY("noise sw", function () { fn.property("Transform").property("Scale Width").setValue(520); });
                TRY("noise sh", function () { fn.property("Transform").property("Scale Height").setValue(34); });
                TRY("noise rot", function () { fn.property("Transform").property("Rotation").setValue(rot); });
                TRY("noise offset", function () { keyFn(fn.property("Transform").property("Offset Turbulence"), f0, f1, function (f) { return [960 + dir * (f - f0) * 40 + seed * 300, 540 - (f - f0) * speed]; }); });
                TRY("noise evo", function () { keyFn(fn.property("Evolution"), f0, f1, function (f) { return seed * 90 + (f - f0) * 40; }); });
            });
            TRY(name + " polar", function () { var pl = fxAdd(sw, "ADBE Polar Coordinates", "polar"); setp(pl, "Interpolation", 100); setp(pl, "Type of Conversion", 2); });
            TRY(name + " twist", function () {   // slight extra twist toward the middle: the funnel
                var tw = fxAdd(sw, "ADBE Twirl", "twirl"); setp(tw, "Twirl Radius", 100);
                keyFn(tw.property("Angle"), f0, f1, function (f) { return dir * (70 + (f - f0) * 9); });
            });
            TRY(name + " warp", function () {
                var tb = fxAdd(sw, "ADBE Turbulent Displace", "warp"); setp(tb, "Amount", 28); setp(tb, "Size", 160);
                TRY("turb evo", function () { keyFn(tb.property("Evolution"), f0, f1, function (f) { return seed * 50 + (f - f0) * 50; }); });
            });
            TRY(name + " tritone", function () {
                var tt = fxAdd(sw, "ADBE Tritone", "colours");
                setp(tt, "Highlights", tri[0]); setp(tt, "Midtones", tri[1]); setp(tt, "Shadows", tri[2]);
            });
            if (blend) sw.blendingMode = blend;
            OPA(sw).setValue(opacity);
            return sw;
        }
        tunnelLayer("tunnel magenta", 0, 1, 24, [[0.9, 1.0, 1.0], [0.95, 0.1, 0.6], [0.04, 0.0, 0.22]], null, 100, 70);
        tunnelLayer("tunnel cyan", 1, -1, -24, [[0.8, 1.0, 1.0], [0.0, 0.75, 1.0], [0.0, 0.0, 0.0]], BlendingMode.ADD, 60, 95);
        // depth: dark toward the vanishing point and out at the rim (a radial band of light between)
        var dk = solid(rc, "depth shade", [1, 1, 1]); dk.blendingMode = BlendingMode.MULTIPLY;
        TRY("shade", function () {
            var rp = fxAdd(dk, "ADBE Ramp", "shade"); setp(rp, "Ramp Shape", 2);
            setp(rp, "Start of Ramp", [W / 2, H / 2]); setp(rp, "Start Color", [0.55, 0.55, 0.6]);
            setp(rp, "End of Ramp", [W / 2 + 1150, H / 2]); setp(rp, "End Color", [1, 1, 1]);
        });
        // ring strokes racing outward (exponential growth = perspective)
        var rg = shapeLayer(rc, "depth rings"), RG = 7, j;
        rg.blendingMode = BlendingMode.ADD;
        for (j = 0; j < RG; j++) addShapeGroup(rg, ellipseRot(W / 2, H / 2, 100, 100, 0), null, j % 2 ? [0.1, 0.85, 1.0] : [1.0, 0.2, 0.7], 5);
        for (j = 0; j < RG; j++) {
            (function (j) {
                var grp = rg.property("ADBE Root Vectors Group").property(j + 1);
                var tr = grp.property("ADBE Vector Transform Group"), cyc = 9;
                // scale about the comp centre: each ring is born tiny and grows to ~2200% over 'cyc' frames, staggered
                TRY("ring anchor", function () { tr.property("ADBE Vector Anchor").setValue([W / 2, H / 2]); tr.property("ADBE Vector Position").setValue([W / 2, H / 2]); });
                keyFn(tr.property("ADBE Vector Scale"), f0, f1, function (f) { var u = (((f - f0) / cyc + j / RG) % 1); return [2 + 2300 * Math.pow(u, 3.2), 2 + 2300 * Math.pow(u, 3.2)]; }, 1);
                keyFn(tr.property("ADBE Vector Group Opacity"), f0, f1, function (f) { var u = (((f - f0) / cyc + j / RG) % 1); return 100 * Math.sin(Math.min(u * 1.15, 1) * Math.PI) * 0.9; }, 1);
            })(j);
        }
        TRY("ring glow", function () { var g = fxAdd(rg, "ADBE Glo2", "ring glow"); setp(g, "Glow Threshold", 25); setp(g, "Glow Radius", 22); setp(g, "Glow Intensity", 1.0); });
        // halftone dots over the swirl (a fraction, so the dots read as texture)
        var ht = adj(rc, "halftone dots"); OPA(ht).setValue(28);
        TRY("dots", function () { var ba = fxAdd(ht, "ec.sim.ccballaction", "dots"); setp(ba, "Grid Spacing", 14); });
        // the white-hot core at the vanishing point
        var core = solid(rc, "core", [0, 0, 0]); core.blendingMode = BlendingMode.ADD;
        TRY("core", function () {
            var rp = fxAdd(core, "ADBE Ramp", "core"); setp(rp, "Ramp Shape", 2);
            setp(rp, "Start of Ramp", [W / 2, H / 2]); setp(rp, "Start Color", [1, 1, 1]);
            setp(rp, "End of Ramp", [W / 2 + 180, H / 2]); setp(rp, "End Color", [0, 0, 0]);
        });
        keyList(OPA(core), [[f0, 0], [Rf.f0 + 6, 38], [Rf.f0 + 10, 50], [Rf.f1, 12]]);
        return rc;
    }

    function jagged(cx, cy, R, factors, rot) {   // tear outline: a star-ish polygon with fixed jag factors
        var v = [], n = factors.length;
        for (var i = 0; i < n; i++) { var a = rot + i / n * Math.PI * 2; v.push([cx + Math.cos(a) * R * factors[i], cy + Math.sin(a) * R * factors[i]]); }
        return shape(v, true);
    }

    function buildRift(Rf) {
        var iris = Rf.iris, S8 = C.shot("S08"), S9 = C.shot("S09"), centre = [W / 2, H / 2], f, i;
        if (!S8 || !S9) { warn("rift: SHOT_S08/S09 missing"); return; }
        var fa = Rf.f0, fcut = 252, fe = Rf.f1;
        // ---- 1. S08: the push into Tobey's left iris. The core's drift moves the layer, so read its transform each
        // frame to know where the iris is, then take over from f244 (continuous at 244) and bring the iris to centre.
        var a8 = vAt(ANC(S8), fa), c8 = {};
        for (f = fa; f <= fcut; f++) c8[f] = { p: vAt(POS(S8), f), s: vAt(SCL(S8), f)[0] };
        function irisScreen(f, p, s) { return [p[0] + (iris[0] - a8[0]) * s / 100, p[1] + (iris[1] - a8[1]) * s / 100]; }
        var sp0 = irisScreen(fa, c8[fa].p, c8[fa].s), s8 = c8[fa].s, sEnd8 = 1100;
        clearKeys(POS(S8), fa, fcut + 1); clearKeys(SCL(S8), fa, fcut + 1);
        var ts = [], ps = [], ss = [], irisTrack = {}, r8 = rng(88);
        for (f = fa; f <= fcut - 1; f++) {
            var u = (f - fa) / (fcut - 1 - fa), s = s8 * Math.pow(sEnd8 / s8, Math.pow(u, 1.8));
            var sp = lerp2(sp0, centre, eInOut(clamp(u * 1.25, 0, 1))), am = 14 * u * u;
            var p = [sp[0] - (iris[0] - a8[0]) * s / 100 + (r8() - 0.5) * 2 * am, sp[1] - (iris[1] - a8[1]) * s / 100 + (r8() - 0.5) * 2 * am];
            ts.push(f2t(f)); ps.push(p); ss.push(sc(s)); irisTrack[f] = [sp[0], sp[1]];
        }
        POS(S8).setValuesAtTimes(ts, ps); SCL(S8).setValuesAtTimes(ts, ss);
        radialBlur(S8, "dive zoom blur", [[fa + 2, 0], [fcut - 1, 70]], iris);
        var ip = function (f) { return irisTrack[clamp(f, fa, fcut - 1)]; };
        // ---- 2. the rift layer: Blender RGBA element when rendered, else the native comp
        var seq = sequence(C.data + "/blender/rift", fa), rl;
        if (seq) {
            rl = MAIN.layers.add(seq); rl.name = "RIFT (blender)"; rl.startTime = f2t(fa);
            span(rl, fa, fe);
        } else {
            var rc = buildRiftComp(Rf);
            rl = MAIN.layers.add(rc); rl.name = "RIFT (native)"; rl.motionBlur = true; span(rl, 246, fe);
            // outer mask: the iris tears, jagged, until it swallows the frame at the cut
            var jf = []; var rj = rng(5); for (i = 0; i < 22; i++) jf.push(0.62 + rj() * 0.7);
            var mo = addMask(rl, jagged(iris[0], iris[1], 1, jf, 0.3), 6);
            var rOut = { 246: 8, 247: 26, 248: 62, 249: 120, 250: 230, 251: 480, 252: 1900 }, mts = [], msh = [];
            for (f = 246; f <= 253; f++) { var R = rOut[Math.min(f, 252)]; var c = f <= 251 ? ip(f) : centre; mts.push(f2t(f)); msh.push(jagged(c[0], c[1], R, jf, 0.3 + (f - 246) * 0.05)); }
            mo.property("ADBE Mask Shape").setValuesAtTimes(mts, msh);
            // the hole A01 is seen through: smooth, grows from the rift's heart, a lens opening
            var mh = addMask(rl, ellipseRot(centre[0], centre[1], 1, 1, 0), 10); mh.maskMode = MaskMode.SUBTRACT;
            var hts = [], hsh = [];
            for (f = fcut; f <= fe + 1; f++) { var u2 = (f - fcut) / (fe - fcut); var Rh = f <= fcut ? 1 : 40 + 1560 * Math.pow(u2, 2.0); hts.push(f2t(f)); hsh.push(ellipseRot(centre[0], centre[1], Rh, Rh, 0)); }
            mh.property("ADBE Mask Shape").setValuesAtTimes(hts, hsh);
            keyList(OPA(rl), [[246, 100], [fe - 3, 100], [fe, 0]]);
        }
        // ---- 3. A01 pulls out of the rift (seen through the hole): scale in from 320 % with a twist, lens to centre
        var aN = vAt(ANC(S9), fcut), lensN = [1036, 546], core9 = {};
        for (f = fcut; f <= fe; f++) core9[f] = { p: vAt(POS(S9), f), s: vAt(SCL(S9), f)[0], r: ROT(S9).valueAtTime(f2t(f), false) };
        clearKeys(POS(S9), fcut, fe); clearKeys(SCL(S9), fcut, fe); clearKeys(ROT(S9), fcut, fe);
        var t9 = [], p9 = [], s9 = [], r9 = [], r9n = rng(90);
        for (f = fcut; f <= fe; f++) {
            var e9 = eOutExpo((f - fcut) / (fe - fcut)), cN = core9[f], sN = cN.s;
            var spN = [cN.p[0] + (lensN[0] - aN[0]) * sN / 100, cN.p[1] + (lensN[1] - aN[1]) * sN / 100];
            var sc9 = Math.exp(lerp(Math.log(340), Math.log(sN), e9)), spc = lerp2(centre, spN, e9), sh9 = shakeAt(f - fcut, 14, 3, 2);
            t9.push(f2t(f)); s9.push(sc(sc9)); r9.push(cN.r + 25 * (1 - e9));
            p9.push([spc[0] - (lensN[0] - aN[0]) * sc9 / 100 + sh9[0], spc[1] - (lensN[1] - aN[1]) * sc9 / 100 + sh9[1]]);
        }
        POS(S9).setValuesAtTimes(t9, p9); SCL(S9).setValuesAtTimes(t9, s9); ROT(S9).setValuesAtTimes(t9, r9);
        radialBlur(S9, "pull-out zoom blur", [[fcut, 85], [fcut + 5, 35], [fe, 0]], lensN);
        // ---- 4. hot rim of the opening (magenta/cyan misregistered rings) + cracks on the iris + flash on the cut
        var rim = shapeLayer(MAIN, "SPECIAL_RIFT_RIM"); span(rim, fcut, fe);
        var cols = [[0.0, 0.9, 1.0], [1.0, 0.1, 0.55]], gs = [];
        for (i = 0; i < 2; i++) gs.push(addShapeGroup(rim, ellipseRot(0, 0, 10, 10, 0), null, cols[i], 10));
        var rts = [], rvs = [];
        for (f = fcut; f <= fe + 1; f++) { var u3 = (f - fcut) / (fe - fcut); rts.push(f2t(f)); rvs.push(u3); }
        for (i = 0; i < 2; i++) {
            var path = gs[i].property("ADBE Vectors Group").property("ADBE Vector Shape - Group").property("ADBE Vector Shape"), pv = [];
            for (f = fcut; f <= fe + 1; f++) { var u4 = (f - fcut) / (fe - fcut), Rh2 = 40 + 1560 * Math.pow(u4, 2.0) + (i ? 9 : -9); pv.push(ellipseRot(centre[0], centre[1], Math.max(Rh2, 1), Math.max(Rh2, 1), 0)); }
            path.setValuesAtTimes(rts, pv);
        }
        rim.blendingMode = BlendingMode.ADD;
        keyList(OPA(rim), [[fcut, 100], [fe - 4, 70], [fe, 0]]);
        TRY("rim glow", function () { var g = fxAdd(rim, "ADBE Glo2", "rim glow"); setp(g, "Glow Threshold", 20); setp(g, "Glow Radius", 30); setp(g, "Glow Intensity", 1.2); });
        // cracks: jagged white lines out of the iris while it tears (f245-251)
        var ck = shapeLayer(MAIN, "SPECIAL_IRIS_CRACKS"); span(ck, 245, 251);
        var rk = rng(12);
        for (i = 0; i < 9; i++) {
            var th = rk() * Math.PI * 2, v = [[0, 0]], rr_ = 0;
            for (var j = 1; j <= 7; j++) { rr_ += 24 + rk() * 40; var dev = (rk() - 0.5) * 0.5; v.push([Math.cos(th + dev) * rr_, Math.sin(th + dev) * rr_]); }
            addShapeGroup(ck, shape(v, false), null, [1, 1, 1], 3);
        }
        keyFn(POS(ck), 245, 251, function (f) { return ip(f); });
        keyFn(SCL(ck), 245, 251, function (f) { return sc(35 + (f - 245) * 24); });
        keyList(OPA(ck), [[245, 0], [246, 90], [250, 100], [251, 0]]);
        ck.blendingMode = BlendingMode.ADD;
        TRY("crack glow", function () { var g = fxAdd(ck, "ADBE Glo2", "crack glow"); setp(g, "Glow Threshold", 20); setp(g, "Glow Radius", 18); setp(g, "Glow Intensity", 1.5); });
        // chromatic split over the whole tear
        var ch = adj(MAIN, "SPECIAL_RIFT_CHROMA"); span(ch, 247, fe);
        TRY("rift chroma", function () {
            var ca = fxAdd(ch, "ec.vr.chromaticaberrations", "split");
            keyList(ca.property("Aberration (Red)"), [[247, 0], [251, 6], [253, 7], [fe, 0]]);
            keyList(ca.property("Aberration (Blue)"), [[247, 0], [251, -6], [253, -7], [fe, 0]]);
        });
        var fl = solid(MAIN, "SPECIAL_RIFT_FLASH", [1, 1, 1]); span(fl, 250, 256); fl.blendingMode = BlendingMode.ADD;
        keyList(OPA(fl), [[250, 0], [251, 30], [252, 38], [253, 18], [255, 0]]);
        // ---- 5. the caption flip EARTH-96283 -> EARTH-120703 (digits tumble, then lock), comic caption box top left
        buildCaptionFlip(Rf);
    }

    function buildCaptionFlip(Rf) {
        var cap = Rf.caption, keysF = [], k;
        for (k in cap) keysF.push(parseInt(k, 10));
        keysF.sort(function (a, b) { return a - b; });
        var fIn = Rf.f0 + 1, fOut = Rf.f1 + 3, x = 96, y = 84, bw = 400, bh = 70;
        var box = shapeLayer(MAIN, "SPECIAL_CAPTION_BOX");
        addShapeGroup(box, shape([[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]], true), [1, 0.83, 0.05], [0, 0, 0], 6);
        addShapeGroup(box, shape([[x + 8, y + 8], [x + bw + 8, y + 8], [x + bw + 8, y + bh + 8], [x + 8, y + bh + 8]], true), [0, 0, 0], null);
        ANC(box).setValue([x + bw / 2, y + bh / 2]);
        span(box, fIn, fOut);
        keyFn(SCL(box), fIn, fIn + 7, function (f) { var u = (f - fIn) / 7; return sc(100 * (1 + 0.25 * Math.sin(Math.min(u, 1) * Math.PI) * (1 - u) * 1.6 + (u < 0.35 ? -(1 - u / 0.35) : 0))); });
        keyList(OPA(box), [[fIn - 1, 0], [fIn, 100], [fOut - 1, 100], [fOut, 0]]);
        POS(box).setValue([x + bw / 2, y + bh / 2]);
        // one text layer per distinct state; each is visible only while that state holds
        var prev = null, st = [];
        for (var i = 0; i < keysF.length; i++) {
            var f = keysF[i], txt = cap[String(f)];
            if (st.length && st[st.length - 1].t == txt) { st[st.length - 1].f1 = f + 1; } else st.push({ t: txt, f0: f, f1: f + 1 });
        }
        st[0].f0 = fIn; st[st.length - 1].f1 = fOut;
        for (i = 0; i < st.length; i++) {
            var tl = addText(MAIN, st[i].t, 40, [x + bw / 2, y + bh / 2 + 17], [0.04, 0.04, 0.04], "Anton-Regular", 60);
            tl.name = "SPECIAL_CAPTION " + st[i].t; span(tl, st[i].f0, st[i].f1);
            if (st[i].f0 == fIn) { keyList(OPA(tl), [[fIn - 1, 0], [fIn + 1, 100]]); }
        }
    }

    // ------------------------------------------------------------------ build
    function build(main, e, ctx) {
        MAIN = main; E = e; C = ctx; X = (e.x && e.x.special) || {};
        FPS = ctx.fps || 30; W = ctx.w || 1920; H = ctx.h || 1080;
        if (X.rift) TRY("rift", function () { buildRift(X.rift); });
        if (X.portal) TRY("drop portal", function () { buildPortal(X.portal); });
        if (X.triptych) {
            TRY("triptych", function () { var r = buildTriptych(X.triptych); buildShatter(X.triptych, r.comp); });
            TRY("freeze slam", function () { buildFreezeSlam(X.triptych); });
        }
        if (WARN.length) ctx.log("special: " + WARN.length + " warnings");
    }
    // special_spec.prerender() runs this on an empty project to render the triptych still the shards cut
    function prerender(main, e, ctx) {
        MAIN = main; E = e; C = ctx; X = (e.x && e.x.special) || {};
        FPS = ctx.fps || 30; W = ctx.w || 1920; H = ctx.h || 1080;
        buildTriptych(X.triptych);
        return WARN;
    }
    return { build: build, prerender: prerender };
})();
