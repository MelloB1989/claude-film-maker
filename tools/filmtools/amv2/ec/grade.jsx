// grade.jsx - GRADE, the EffectCraft colour library for Timeless v2. Defines exactly one global: GRADE.
//
//   GRADE.build(main, E, ctx)   adds the adjustment layers (called by the core after the shots and FX.buildUnder)
//   GRADE.applyTrim(layer, t)   puts one per-shot trim (E.x.grade.shots[id]) on any layer (SPECIAL uses it for the triptych panels)
//
// Stack, bottom to top (every layer is a plain EffectCraft adjustment layer, all effects are native and editable):
//   GRADE_TRIM_<id>   one per shot, timed [a, b): Levels (Individual Controls) + Hue/Saturation, numbers from grade_spec.py
//   GRADE_LOOK        the act look. ONE layer for the whole film: Lumetri Color (tone, curves, colour wheels), Color Balance,
//                     Hue/Saturation, Vibrance. Every parameter is keyed tobey -> andrew -> tom, blended over BLEND frames at
//                     each act change, so a look is edited by changing the keys at its act.
//   GRADE_GLOW        bloom above a high threshold (Glow), keyed per act
//   GRADE_SHARPEN     Unsharp Mask, small radius (the clips are soft upscales)
//   GRADE_GRAIN       fine luma grain (Grain Implant, monochrome)
//   GRADE_VIGNETTE    subtle Lumetri vignette
//   GRADE_LIMIT       Levels: output black just off zero, output white below clipping, plus an identity Curves to tweak by hand
// All grade layers end at the outro (E.outro.f0): the Blender outro keeps its own look.
//
// EffectCraft notes (see docs/EFFECTCRAFT-NOTES.md, section "grade"): Lumetri parameters are nested by their short names
// (Lumetri Basic Correction > tone > contrast); the Curves effect's curve strings can not be set from a script, so the curves
// are the Lumetri curve sliders; Lumetri Sharpen and Faded Film do nothing visible here.
var GRADE = (function () {
    var G = {};
    var BLEND = 6;                       // frames of look blend at an act change (centred on the change)

    // ---------------------------------------------------------------- the three act looks
    // Colour wheels are Lumetri's: 0.5 is neutral, a channel above 0.5 adds that colour. All other numbers are Lumetri units.
    G.LOOKS = {
        // Tobey: nostalgia. Warm gold highlights, teal shadows, soft bloom.
        tobey: {
            contrast: 12, highlights: -10, shadows: 6, whites: -3, blacks: 0, exposure: 0, saturation: 104, vibrance: 8,
            cShadows: 4, cMids: 4, cHighlights: -4,
            wShadows: [0.47, 0.515, 0.55], wMids: [0.51, 0.50, 0.49], wHighlights: [0.58, 0.525, 0.42],
            cbShadows: [-2, 1, 3], cbMids: [1, 0, -1], cbHighlights: [4, 2, -5],
            hsSat: 0, hsRed: 4, hsYellow: 6, hsCyan: 4, hsBlue: 0,
            glow: { threshold: 82, radius: 70, intensity: 0.30 }
        },
        // Andrew: electric. Cool cyan/blue, amber in the warm highlights (the sunset accents), crisp.
        andrew: {
            contrast: 16, highlights: -12, shadows: 5, whites: -3, blacks: 0, exposure: 0, saturation: 106, vibrance: 8,
            cShadows: 3, cMids: 3, cHighlights: -6,
            wShadows: [0.43, 0.51, 0.60], wMids: [0.48, 0.50, 0.54], wHighlights: [0.55, 0.51, 0.43],
            cbShadows: [-4, 1, 6], cbMids: [-1, 1, 3], cbHighlights: [4, 1, -4],
            hsSat: 0, hsRed: 4, hsYellow: 8, hsCyan: 10, hsBlue: 6,
            glow: { threshold: 84, radius: 44, intensity: 0.24 }
        },
        // Tom: impact. Rich red/orange against steel blue, punchy.
        tom: {
            contrast: 20, highlights: -14, shadows: 4, whites: -4, blacks: 0, exposure: 0, saturation: 106, vibrance: 6,
            cShadows: 2, cMids: 0, cHighlights: -8,
            wShadows: [0.45, 0.50, 0.57], wMids: [0.53, 0.50, 0.47], wHighlights: [0.56, 0.515, 0.45],
            cbShadows: [-3, 0, 5], cbMids: [3, 0, -2], cbHighlights: [4, 1, -4],
            hsSat: 0, hsRed: 10, hsYellow: 2, hsCyan: -4, hsBlue: -6,
            glow: { threshold: 86, radius: 36, intensity: 0.18 }
        }
    };

    G.FINISH = {
        sharpen: { amount: 42, radius: 0.9, threshold: 2 },
        grain: { intensity: 0.22, size: 0.7 },
        vignette: { amount: -0.38, midpoint: 52, roundness: 0, feather: 75 },
        limit: { outBlack: 0.022, outWhite: 0.97 }
    };

    // ---------------------------------------------------------------- helpers (all inside GRADE)
    var WARN = [];
    function log(ctx, m) { try { ctx.log("GRADE: " + m); } catch (e) { } }
    function TRY(ctx, what, fn) { try { return fn(); } catch (e) { WARN.push(what + ": " + e); log(ctx, what + " failed: " + e); return null; } }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    // add an effect, rename it, return it fresh (references go stale after the next addProperty)
    function fxAdd(l, mn, label) {
        var e = FXP(l).addProperty(mn);
        if (label) { e.name = label; return FXP(l).property(label); }
        return e;
    }
    function adj(main, name, t0, t1) {
        var l = main.layers.addSolid([1, 1, 1], name, main.width, main.height, 1, main.duration);
        l.adjustmentLayer = true;
        l.inPoint = t0; l.outPoint = t1;
        return l;
    }
    function lum(e, group) { return e.property(group); }
    // keyed property: values = [tobey, andrew, tom]; times in seconds. A property that does not change is just set.
    function same(a, b) { return String(a) === String(b); }
    function setAct(prop, vals, T) {
        if (same(vals[0], vals[1]) && same(vals[1], vals[2])) { prop.setValue(vals[0]); return; }
        prop.setValuesAtTimes(T.t, [vals[0], vals[0], vals[1], vals[1], vals[2], vals[2]].slice(0, T.t.length));
    }
    function acts(L, key) { return [L.tobey[key], L.andrew[key], L.tom[key]]; }
    function wheel(c) { return [c[0], c[1], c[2], 1]; }
    function wheels(L, key) { return [wheel(L.tobey[key]), wheel(L.andrew[key]), wheel(L.tom[key])]; }

    // ---------------------------------------------------------------- per-shot trim
    // t = E.x.grade.shots[id] = {lev: {ib, iw, g, ob, ow}, ch: {r, g, b}, sat, hue}
    G.applyTrim = function (layer, t, tag) {
        tag = tag || "";
        var lv = fxAdd(layer, "ADBE Pro Levels2", "trim levels" + tag);
        lv.property("Input Black").setValue(t.lev.ib);
        lv.property("Input White").setValue(t.lev.iw);
        lv.property("Gamma").setValue(t.lev.g);
        lv.property("Output Black").setValue(t.lev.ob);
        lv.property("Output White").setValue(t.lev.ow);
        lv.property("Red Output White").setValue(t.ch.r);
        lv.property("Green Output White").setValue(t.ch.g);
        lv.property("Blue Output White").setValue(t.ch.b);
        if (t.sat || t.hue) {
            var hs = fxAdd(layer, "ADBE HUE SATURATION", "trim saturation" + tag);
            if (t.sat) hs.property("Master Saturation").setValue(t.sat);
            if (t.hue) hs.property("Master Hue").setValue(t.hue);
        }
    };

    // ---------------------------------------------------------------- the look (one layer, keyed per act)
    function buildLook(main, E, ctx, t0, t1, T) {
        var L = G.LOOKS, ov = (E.x && E.x.grade && E.x.grade.looks) || null;
        if (ov) { for (var k in ov) { if (L[k]) for (var p in ov[k]) L[k][p] = ov[k][p]; } }
        var l = adj(main, "GRADE_LOOK", t0, t1);

        TRY(ctx, "look lumetri", function () {
            var e = fxAdd(l, "ADBE Lumetri", "Lumetri act look");
            var tone = e.property("ADBE Lumetri-0002").property("tone");
            setAct(tone.property("exposure"), acts(L, "exposure"), T);
            setAct(tone.property("contrast"), acts(L, "contrast"), T);
            setAct(tone.property("highlights"), acts(L, "highlights"), T);
            setAct(tone.property("shadows"), acts(L, "shadows"), T);
            setAct(tone.property("whites"), acts(L, "whites"), T);
            setAct(tone.property("blacks"), acts(L, "blacks"), T);
            setAct(e.property("ADBE Lumetri-0002").property("saturation"), acts(L, "saturation"), T);
            setAct(e.property("ADBE Lumetri-0003").property("adjustments").property("vibrance"), acts(L, "vibrance"), T);
            var cv = e.property("ADBE Lumetri-0004");
            setAct(cv.property("curveMasterShadows"), acts(L, "cShadows"), T);
            setAct(cv.property("curveMasterMidtones"), acts(L, "cMids"), T);
            setAct(cv.property("curveMasterHighlights"), acts(L, "cHighlights"), T);
            var wh = e.property("ADBE Lumetri-0005");
            setAct(wh.property("shadowsWheel"), wheels(L, "wShadows"), T);
            setAct(wh.property("midtonesWheel"), wheels(L, "wMids"), T);
            setAct(wh.property("highlightsWheel"), wheels(L, "wHighlights"), T);
        });
        TRY(ctx, "look color balance", function () {
            var e = fxAdd(l, "ADBE Color Balance 2", "Color Balance act split tone");
            var names = ["Shadow", "Midtone", "Highlight"], keys = ["cbShadows", "cbMids", "cbHighlights"], ch = ["Red", "Green", "Blue"];
            for (var i = 0; i < 3; i++) for (var c = 0; c < 3; c++) {
                setAct(e.property(names[i] + " " + ch[c] + " Balance"), [L.tobey[keys[i]][c], L.andrew[keys[i]][c], L.tom[keys[i]][c]], T);
            }
            e.property("Preserve Luminosity").setValue(1);
        });
        TRY(ctx, "look hue/sat", function () {
            var e = fxAdd(l, "ADBE HUE SATURATION", "Hue Saturation act colours");
            setAct(e.property("Master Saturation"), acts(L, "hsSat"), T);
            setAct(e.property("Red Saturation"), acts(L, "hsRed"), T);
            setAct(e.property("Yellow Saturation"), acts(L, "hsYellow"), T);
            setAct(e.property("Cyan Saturation"), acts(L, "hsCyan"), T);
            setAct(e.property("Blue Saturation"), acts(L, "hsBlue"), T);
        });
        return l;
    }

    function buildGlow(main, E, ctx, t0, t1, T) {
        var L = G.LOOKS, l = adj(main, "GRADE_GLOW", t0, t1);
        TRY(ctx, "glow", function () {
            var e = fxAdd(l, "ADBE Glo2", "Glow bloom");
            setAct(e.property("Glow Threshold"), [L.tobey.glow.threshold, L.andrew.glow.threshold, L.tom.glow.threshold], T);
            setAct(e.property("Glow Radius"), [L.tobey.glow.radius, L.andrew.glow.radius, L.tom.glow.radius], T);
            setAct(e.property("Glow Intensity"), [L.tobey.glow.intensity, L.andrew.glow.intensity, L.tom.glow.intensity], T);
        });
        return l;
    }

    function buildFinish(main, E, ctx, t0, t1) {
        var F = G.FINISH;
        var s = adj(main, "GRADE_SHARPEN", t0, t1);
        TRY(ctx, "sharpen", function () {
            var e = fxAdd(s, "ADBE Unsharp Mask2", "Unsharp Mask");
            e.property("Amount").setValue(F.sharpen.amount);
            e.property("Radius").setValue(F.sharpen.radius);
            e.property("Threshold").setValue(F.sharpen.threshold);
        });
        var g = adj(main, "GRADE_GRAIN", t0, t1);
        TRY(ctx, "grain", function () {
            var e = fxAdd(g, "VISINF Grain Implant", "Fine luma grain");
            e.property("Viewing Mode").setValue(3);
            e.property("Tweaking").property("Intensity").setValue(F.grain.intensity);
            e.property("Tweaking").property("Size").setValue(F.grain.size);
            e.property("Color").property("Monochromatic").setValue(1);
        });
        var v = adj(main, "GRADE_VIGNETTE", t0, t1);
        TRY(ctx, "vignette", function () {
            var e = fxAdd(v, "ADBE Lumetri", "Lumetri vignette");
            var vg = e.property("ADBE Lumetri-0007");
            vg.property("vignetteAmount").setValue(F.vignette.amount);
            vg.property("vignetteMidpoint").setValue(F.vignette.midpoint);
            vg.property("vignetteRoundness").setValue(F.vignette.roundness);
            vg.property("vignetteFeather").setValue(F.vignette.feather);
        });
        var m = adj(main, "GRADE_LIMIT", t0, t1);
        TRY(ctx, "limit levels", function () {
            var e = fxAdd(m, "ADBE Pro Levels2", "Levels limit (blacks off zero, white below clip)");
            e.property("Output Black").setValue(F.limit.outBlack);
            e.property("Output White").setValue(F.limit.outWhite);
        });
        TRY(ctx, "curves (tweak)", function () { fxAdd(m, "ADBE CurvesCustom", "Curves (identity, tweak by hand)"); });
    }

    // ---------------------------------------------------------------- build
    G.build = function (main, E, ctx) {
        var fps = ctx.fps, end = (E.outro && E.outro.f0) || E.dur;
        var t0 = 0, t1 = end / fps;
        var X = (E.x && E.x.grade) || { shots: {} };

        // 1. per-shot normalisation, timed to each shot's [a, b)
        for (var i = 0; i < E.shots.length; i++) {
            var S = E.shots[i], t = X.shots[S.id];
            if (!t) continue;
            var l = adj(main, "GRADE_TRIM_" + S.id, S.a / fps, Math.min(S.b, end) / fps);
            TRY(ctx, "trim " + S.id, function () { G.applyTrim(l, t); });
        }

        // 2. act look and bloom: keys at the act changes, BLEND frames wide and centred on the change
        var A = E.acts, h = BLEND / 2.0;
        var c1 = A[1].f0, c2 = A[2].f0;
        var T = { t: [t0, (c1 - h) / fps, (c1 + h) / fps, (c2 - h) / fps, (c2 + h) / fps, t1] };
        buildLook(main, E, ctx, t0, t1, T);
        buildGlow(main, E, ctx, t0, t1, T);

        // 3. finishing
        buildFinish(main, E, ctx, t0, t1);
        if (WARN.length) log(ctx, WARN.length + " warnings");
        return WARN;
    };

    return G;
})();
