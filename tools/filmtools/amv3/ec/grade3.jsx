// grade3.jsx - GRADE3, the v3 finishing grade (one global). Built from v2's GRADE (tools/filmtools/amv2/ec/grade.jsx, which
// stays untouched): the same per-shot trims, act looks and finishing, with three changes for v3:
//   * ONE trim layer for the whole film, its Levels/Hue-Sat parameters keyed per frame by finish_spec.py: a shot's own
//     trim between windows, a linear blend of the A and B trims across each CUTS window (the stage's picture changes shot
//     inside the window, so a hard trim change would pop);
//   * the act looks are pushed toward the references (richer reds and teal, more contrast with lifted toe, see
//     finish_spec.LOOKS), passed in as E.x.finish.looks;
//   * the finishing layers are split: GRADE3.build() adds trim, look, bloom and sharpen (under the text/light passes and
//     titles); GRADE3.buildTop() adds grain and the highlight limiter over everything (0..outro).
// Lumetri parameters are reached by their short names (EFFECTCRAFT-NOTES "grade").
var GRADE3 = (function () {
    var G = {}, WARN = [];
    function log(ctx, m) { try { ctx.log("GRADE3: " + m); } catch (e) { } }
    function TRY(ctx, what, fn) { try { return fn(); } catch (e) { WARN.push(what + ": " + e); log(ctx, what + " failed: " + e); return null; } }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    function fxAdd(l, mn, label) { var e = FXP(l).addProperty(mn); if (label) { e.name = label; return FXP(l).property(label); } return e; }
    function adj(main, name, f0, f1, fps) {
        var l = main.layers.addSolid([1, 1, 1], name, main.width, main.height, 1, main.duration);
        l.adjustmentLayer = true; l.inPoint = f0 / fps; l.outPoint = f1 / fps;
        return l;
    }
    // ks = [[frame, value], ...] -> keys (a single key is a static value)
    function K(prop, ks, fps) {
        if (!ks || !ks.length) return;
        if (ks.length == 1) { prop.setValue(ks[0][1]); return; }
        var ts = [], vs = [];
        for (var i = 0; i < ks.length; i++) { ts.push(ks[i][0] / fps); vs.push(ks[i][1]); }
        prop.setValuesAtTimes(ts, vs);
    }
    // act-keyed value: A = [[frame, actIndex]...] from finish_spec (look keys), L = looks, key = parameter
    function KA(prop, A, L, key, fps, wrap) {
        var ks = [];
        for (var i = 0; i < A.length; i++) { var v = L[A[i][1]][key]; ks.push([A[i][0], wrap ? wrap(v) : v]); }
        var same = true;
        for (var j = 1; j < ks.length; j++) if (String(ks[j][1]) !== String(ks[0][1])) same = false;
        if (same) prop.setValue(ks[0][1]); else K(prop, ks, fps);
    }
    function w4(c) { return [c[0], c[1], c[2], 1]; }

    function buildTrim(main, X, ctx, end) {
        var T = X.trim, fps = ctx.fps, l = adj(main, "GRADE_TRIM (per shot, blended in windows)", 0, end, fps);
        TRY(ctx, "trim levels", function () {
            var e = fxAdd(l, "ADBE Pro Levels2", "trim levels");
            K(e.property("Input Black"), T.ib, fps); K(e.property("Input White"), T.iw, fps); K(e.property("Gamma"), T.g, fps);
            K(e.property("Output Black"), T.ob, fps); K(e.property("Output White"), T.ow, fps);
            K(e.property("Red Output White"), T.r, fps); K(e.property("Green Output White"), T.gg, fps); K(e.property("Blue Output White"), T.b, fps);
        });
        TRY(ctx, "trim hue/sat", function () {
            var e = fxAdd(l, "ADBE HUE SATURATION", "trim saturation");
            K(e.property("Master Saturation"), T.sat, fps); K(e.property("Master Hue"), T.hue, fps);
        });
        return l;
    }

    function buildLook(main, X, ctx, end) {
        var L = X.looks, A = X.actKeys, fps = ctx.fps, l = adj(main, "GRADE_LOOK (act looks, v3 richer)", 0, end, fps);
        TRY(ctx, "look lumetri", function () {
            var e = fxAdd(l, "ADBE Lumetri", "Lumetri act look");
            var bc = e.property("ADBE Lumetri-0002"), tone = bc.property("tone"), wb = bc.property("whiteBalance");
            KA(wb.property("temperature"), A, L, "temp", fps); KA(wb.property("tint"), A, L, "tint", fps);
            KA(tone.property("exposure"), A, L, "exposure", fps); KA(tone.property("contrast"), A, L, "contrast", fps);
            KA(tone.property("highlights"), A, L, "highlights", fps); KA(tone.property("shadows"), A, L, "shadows", fps);
            KA(tone.property("whites"), A, L, "whites", fps); KA(tone.property("blacks"), A, L, "blacks", fps);
            KA(bc.property("saturation"), A, L, "saturation", fps);
            KA(e.property("ADBE Lumetri-0003").property("adjustments").property("vibrance"), A, L, "vibrance", fps);
            var cv = e.property("ADBE Lumetri-0004");
            KA(cv.property("curveMasterShadows"), A, L, "cShadows", fps); KA(cv.property("curveMasterMidtones"), A, L, "cMids", fps);
            KA(cv.property("curveMasterHighlights"), A, L, "cHighlights", fps);
            var wh = e.property("ADBE Lumetri-0005");
            KA(wh.property("shadowsWheel"), A, L, "wShadows", fps, w4); KA(wh.property("midtonesWheel"), A, L, "wMids", fps, w4);
            KA(wh.property("highlightsWheel"), A, L, "wHighlights", fps, w4);
        });
        TRY(ctx, "look color balance", function () {
            var e = fxAdd(l, "ADBE Color Balance 2", "Color Balance act split tone");
            var names = ["Shadow", "Midtone", "Highlight"], keys = ["cbShadows", "cbMids", "cbHighlights"], ch = ["Red", "Green", "Blue"];
            for (var i = 0; i < 3; i++) for (var c = 0; c < 3; c++) {
                (function (k, cc) { KA(e.property(names[i] + " " + ch[c] + " Balance"), A, L, k, fps, function (v) { return v[cc]; }); })(keys[i], c);
            }
            e.property("Preserve Luminosity").setValue(1);
        });
        TRY(ctx, "look hue/sat", function () {
            var e = fxAdd(l, "ADBE HUE SATURATION", "Hue Saturation act colours");
            KA(e.property("Master Saturation"), A, L, "hsSat", fps); KA(e.property("Red Saturation"), A, L, "hsRed", fps);
            KA(e.property("Yellow Saturation"), A, L, "hsYellow", fps); KA(e.property("Cyan Saturation"), A, L, "hsCyan", fps);
            KA(e.property("Blue Saturation"), A, L, "hsBlue", fps);
        });
        return l;
    }

    // bloom above a high threshold, the act's own tint (A & B colours, A = B)
    function buildBloom(main, X, ctx, end) {
        var L = X.looks, A = X.actKeys, fps = ctx.fps, l = adj(main, "GRADE_BLOOM (above a high threshold)", 0, end, fps);
        TRY(ctx, "bloom", function () {
            var e = fxAdd(l, "ADBE Glo2", "Glow bloom");
            KA(e.property("Glow Threshold"), A, L, "bloomThreshold", fps); KA(e.property("Glow Radius"), A, L, "bloomRadius", fps);
            KA(e.property("Glow Intensity"), A, L, "bloomIntensity", fps);
            e.property("Glow Colors").setValue(2);
            KA(e.property("Color A"), A, L, "bloomColor", fps, w4); KA(e.property("Color B"), A, L, "bloomColor", fps, w4);
        });
        return l;
    }

    G.build = function (main, E, ctx) {
        var X = E.x.finish, end = X.gradeEnd;
        buildTrim(main, X, ctx, end);
        buildLook(main, X, ctx, end);
        buildBloom(main, X, ctx, end);
        var F = X.finish, s = adj(main, "GRADE_SHARPEN", 0, end, ctx.fps);
        TRY(ctx, "sharpen", function () {
            var e = fxAdd(s, "ADBE Unsharp Mask2", "Unsharp Mask");
            e.property("Amount").setValue(F.sharpen.amount); e.property("Radius").setValue(F.sharpen.radius);
            e.property("Threshold").setValue(F.sharpen.threshold);
        });
        return WARN;
    };

    G.buildTop = function (main, E, ctx) {
        var X = E.x.finish, F = X.finish, end = X.gradeEnd;
        var g = adj(main, "FINISH_GRAIN", 0, end, ctx.fps);
        TRY(ctx, "grain", function () {
            var e = fxAdd(g, "VISINF Grain Implant", "Fine luma grain");
            e.property("Viewing Mode").setValue(3);
            e.property("Tweaking").property("Intensity").setValue(F.grain.intensity);
            e.property("Tweaking").property("Size").setValue(F.grain.size);
            e.property("Color").property("Monochromatic").setValue(1);
        });
        var v = adj(main, "FINISH_VIGNETTE", 0, end, ctx.fps);
        TRY(ctx, "vignette", function () {
            var e = fxAdd(v, "ADBE Lumetri", "Lumetri vignette"), vg = e.property("ADBE Lumetri-0007");
            vg.property("vignetteAmount").setValue(F.vignette.amount); vg.property("vignetteMidpoint").setValue(F.vignette.midpoint);
            vg.property("vignetteRoundness").setValue(F.vignette.roundness); vg.property("vignetteFeather").setValue(F.vignette.feather);
        });
        var m = adj(main, "FINISH_LIMIT (highlight limiter)", 0, end, ctx.fps);
        TRY(ctx, "limit", function () {
            var e = fxAdd(m, "ADBE Lumetri", "Lumetri highlight shoulder"), tone = e.property("ADBE Lumetri-0002").property("tone");
            tone.property("whites").setValue(F.limit.whites); tone.property("highlights").setValue(F.limit.highlights);
            e = fxAdd(m, "ADBE Pro Levels2", "Levels limit (blacks off zero, white below clip)");
            e.property("Output Black").setValue(F.limit.outBlack); e.property("Output White").setValue(F.limit.outWhite);
        });
        return WARN;
    };
    G.warnings = function () { return WARN; };
    return G;
})();
