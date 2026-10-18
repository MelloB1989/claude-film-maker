// lens.jsx - LENS, the v3 lens FX in every CUTS window (one global). Python (finish_spec.lens_plan) computes every number:
// E.x.finish.lens = [{id, type, f, w0, w1, act, center: [x, y], colors: [c1, c2] | null, flash, keys: {blur, ca, bulge,
// bloom, leak, wash, expo, evo, drift}}], each key list [[frame, value], ...] covering [w0, w1). The keys follow the cut's
// time profile (peak on the cut, ramping with the camera speed: zvec when the stage wrote it, else the EDIT.md eases).
//
// Per window, bottom to top (all above the grade, so they act on the graded picture):
//   LENS <id> optics    adjustment: Bulge (lens bulge at the centre) -> CC Radial Fast Blur (the zoom smear boost)
//                       -> radial chromatic split (95 % / VR Chromatic Aberrations / overscan, v2's working recipe)
//   LENS <id> bloom     adjustment: Glow, threshold lowered and intensity swelled with the profile, the act's leak colour
//   LENS <id> leak      a copy of the plate: its own highlights (Levels) blurred huge (Fast Box Blur), tinted to the act's
//                       first leak colour, ADD: the light comes out of the picture's bright parts
//   LENS <id> wash      a black solid with slow Fractal Noise (big soft blobs, evolving, drifting with the camera), tinted
//                       to the second leak colour, ADD: the organic moving part of the leak, never a flat veil
//   LENS <id> exposure  adjustment: Exposure pop (+EV on the flash frames, a small swell at every peak)
var LENS = (function () {
    var G = {}, WARN = [];
    function log(ctx, m) { try { ctx.log("LENS: " + m); } catch (e) { } }
    function TRY(ctx, what, fn) { try { return fn(); } catch (e) { WARN.push(what + ": " + e); log(ctx, what + " failed: " + e); return null; } }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    function TG(l) { return l.property("ADBE Transform Group"); }
    function fxAdd(l, mn, label) { var e = FXP(l).addProperty(mn); if (label) { e.name = label; return FXP(l).property(label); } return e; }
    function K(prop, ks, fps, map) {
        if (!ks || !ks.length) return;
        var ts = [], vs = [];
        for (var i = 0; i < ks.length; i++) { ts.push(ks[i][0] / fps); vs.push(map ? map(ks[i][1]) : ks[i][1]); }
        if (ks.length == 1) prop.setValue(vs[0]); else prop.setValuesAtTimes(ts, vs);
    }
    function solid(main, name, col, f0, f1, fps, isAdj) {
        var l = main.layers.addSolid(col, name, main.width, main.height, 1, main.duration);
        if (isAdj) l.adjustmentLayer = true;
        l.inPoint = f0 / fps; l.outPoint = f1 / fps;
        return l;
    }
    function mx(ks) { var m = 0; for (var i = 0; i < ks.length; i++) m = Math.max(m, Math.abs(ks[i][1])); return m; }

    function optics(main, C, ctx) {
        var fps = ctx.fps, k = C.keys, W = main.width, H = main.height;
        var l = solid(main, "LENS " + C.id + " optics (" + C.type + ")", [1, 1, 1], C.w0, C.w1, fps, true);
        if (mx(k.bulge) > 0) TRY(ctx, C.id + " bulge", function () {
            var e = fxAdd(l, "ec.distort.bulge", "lens bulge");
            e.property("Bulge Center").setValue(C.center);
            e.property("Horizontal Radius").setValue(W * 0.62); e.property("Vertical Radius").setValue(W * 0.62);
            e.property("Taper Radius").setValue(40);
            K(e.property("Bulge Height"), k.bulge, fps);
        });
        if (mx(k.blur) > 0) TRY(ctx, C.id + " zoom blur", function () {
            var e = fxAdd(l, "ec.blur.ccradialfast", "zoom smear");
            e.property("Center").setValue(C.center); e.property("Zoom").setValue(1);
            K(e.property("Amount"), k.blur, fps);
        });
        if (mx(k.ca) > 0) TRY(ctx, C.id + " chroma", function () {
            var e = fxAdd(l, "ADBE Geometry2", "chroma pre"); e.property("Scale Height").setValue(95);
            e.property("Anchor Point").setValue([W / 2, H / 2]); e.property("Position").setValue([W / 2, H / 2]);
            e = fxAdd(l, "ec.vr.chromaticaberrations", "radial rgb split");
            e.property("Falloff Distance").setValue(0);
            K(e.property("Aberration (Red)"), k.ca, fps);
            K(e.property("Aberration (Blue)"), k.ca, fps, function (v) { return -v; });
            e = fxAdd(l, "ADBE Geometry2", "chroma overscan");
            e.property("Anchor Point").setValue([W / 2, H / 2]); e.property("Position").setValue([W / 2, H / 2]);
            K(e.property("Scale Height"), k.ca, fps, function (v) { return 100 / 0.95 * (1 + (Math.abs(v) + 3) / 540); });
        });
        return l;
    }

    function bloom(main, C, ctx) {
        if (!C.colors || mx(k0(C, "bloom")) <= 0) return null;
        var fps = ctx.fps, l = solid(main, "LENS " + C.id + " bloom swell", [1, 1, 1], C.w0, C.w1, fps, true);
        TRY(ctx, C.id + " bloom", function () {
            var e = fxAdd(l, "ADBE Glo2", "bloom swell");
            K(e.property("Glow Threshold"), C.keys.bloomThr, fps);
            e.property("Glow Radius").setValue(C.bloomRadius);
            K(e.property("Glow Intensity"), C.keys.bloom, fps);
            e.property("Glow Colors").setValue(2);
            var c = C.colors[0]; e.property("Color A").setValue([c[0], c[1], c[2], 1]); e.property("Color B").setValue([c[0], c[1], c[2], 1]);
        });
        return l;
    }
    function k0(C, n) { return C.keys[n] || []; }

    function leak(main, C, ctx) {
        if (!C.colors || !ctx.plateItem || mx(k0(C, "leak")) <= 0) return null;
        var fps = ctx.fps, c = C.colors[0];
        var l = main.layers.add(ctx.plateItem);
        l.name = "LENS " + C.id + " leak (picture highlights)";
        l.startTime = ctx.plateStart / fps; l.inPoint = C.w0 / fps; l.outPoint = C.w1 / fps;
        if (ctx.plateScale != 100) TG(l).property("ADBE Scale").setValue([ctx.plateScale, ctx.plateScale]);
        l.blendingMode = BlendingMode.ADD;
        TRY(ctx, C.id + " leak fx", function () {
            var e = fxAdd(l, "ADBE Pro Levels2", "highlights");
            e.property("Input Black").setValue(C.leakKnee); e.property("Gamma").setValue(0.8);
            e = fxAdd(l, "ec.blur.fastbox", "spread");
            e.property("Blur Radius").setValue(C.leakRadius); e.property("Iterations").setValue(3); e.property("Repeat Edge Pixels").setValue(1);
            e = fxAdd(l, "ADBE Tint", "leak colour");
            e.property("Map White To").setValue([c[0], c[1], c[2], 1]);
        });
        K(TG(l).property("ADBE Opacity"), C.keys.leak, fps);
        return l;
    }

    function wash(main, C, ctx) {
        if (!C.colors || mx(k0(C, "wash")) <= 0) return null;
        var fps = ctx.fps, c = C.colors[1] || C.colors[0], W = main.width, H = main.height;
        var l = solid(main, "LENS " + C.id + " wash (organic leak)", [0, 0, 0], C.w0, C.w1, fps, false);
        l.blendingMode = BlendingMode.ADD;
        TRY(ctx, C.id + " wash fx", function () {
            var e = fxAdd(l, "ADBE Fractal Noise", "leak blobs");
            e.property("Fractal Type").setValue(1); e.property("Noise Type").setValue(3);
            e.property("Contrast").setValue(C.washContrast); e.property("Brightness").setValue(C.washBrightness);
            e.property("Complexity").setValue(3);
            var tr = e.property("Transform");
            tr.property("Uniform Scaling").setValue(0);
            tr.property("Scale Width").setValue(C.washScale[0]); tr.property("Scale Height").setValue(C.washScale[1]);
            tr.property("Rotation").setValue(C.washAngle);
            K(tr.property("Offset Turbulence"), C.keys.drift, fps);
            e.property("Evolution Options").property("Random Seed").setValue(C.seed);
            K(e.property("Evolution"), C.keys.evo, fps);
            e = fxAdd(l, "ADBE Tint", "leak colour");
            e.property("Map White To").setValue([c[0], c[1], c[2], 1]);
            e = fxAdd(l, "ec.blur.fastbox", "soften");
            e.property("Blur Radius").setValue(40); e.property("Iterations").setValue(2); e.property("Repeat Edge Pixels").setValue(1);
        });
        K(TG(l).property("ADBE Opacity"), C.keys.wash, fps);
        return l;
    }

    function exposure(main, C, ctx) {
        if (mx(k0(C, "expo")) <= 0) return null;
        var fps = ctx.fps, l = solid(main, "LENS " + C.id + " exposure" + (C.flash ? " (flash " + C.flash + " f)" : ""), [1, 1, 1], C.w0, C.w1, fps, true);
        TRY(ctx, C.id + " exposure", function () {
            var e = fxAdd(l, "ec.color.exposure", "exposure pop");
            K(e.property("Exposure"), C.keys.expo, fps);
        });
        return l;
    }

    G.build = function (main, E, ctx) {
        var L = E.x.finish.lens;
        for (var i = 0; i < L.length; i++) {
            var C = L[i];
            optics(main, C, ctx); bloom(main, C, ctx); leak(main, C, ctx); wash(main, C, ctx); exposure(main, C, ctx);
        }
        log(ctx, L.length + " windows, " + WARN.length + " warnings");
        return WARN;
    };
    G.warnings = function () { return WARN; };
    return G;
})();
