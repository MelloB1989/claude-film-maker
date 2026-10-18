// accents.jsx - ACCENTS, EffectCraft transition effects used as accents in FINISH (one global; lab/TRANSITIONS.md ranks
// them). Python (finish_spec.accents) computes every number into E.x.finish.accents = {rays: [...], raysFx, shatter, glass}.
//   ACCENTS.under(main, E, ctx)  above the PLATE, under the grade (so these are graded and hit by the lens FX):
//     ACCENT <cut> shatter       the landing frame frozen, Shatter (extruded glass) blown outward, fading out
//     ACCENT <cut> glass edge    the plate over itself with CC Glass Wipe: only the moving refractive edge band shows
//   ACCENTS.rays(main, E, ctx)   above the lens FX:
//     ACCENT <cut> light rays    a plate copy cut to its highlights, CC Light Rays from B's brightest non-skin area, ADD
var ACCENTS = (function () {
    var G = {}, WARN = [];
    function log(ctx, m) { try { ctx.log("ACCENTS: " + m); } catch (e) { } }
    function TRY(ctx, what, fn) { try { return fn(); } catch (e) { WARN.push(what + ": " + e); log(ctx, what + " failed: " + e); return null; } }
    function FXP(l) { return l.property("ADBE Effect Parade"); }
    function TG(l) { return l.property("ADBE Transform Group"); }
    function fxAdd(l, mn, label) { var e = FXP(l).addProperty(mn); e.name = label; return FXP(l).property(label); }
    // values per frame from f0: [v0, v1, ...]
    function KF(prop, f0, vs, fps) { var ts = []; for (var i = 0; i < vs.length; i++) ts.push((f0 + i) / fps); prop.setValuesAtTimes(ts, vs); }
    function K(prop, ks, fps) { var ts = [], vs = []; for (var i = 0; i < ks.length; i++) { ts.push(ks[i][0] / fps); vs.push(ks[i][1]); } prop.setValuesAtTimes(ts, vs); }
    function plateCopy(main, ctx, name, f0, f1) {
        var l = main.layers.add(ctx.plateItem); l.name = name;
        l.startTime = ctx.plateStart / ctx.fps; l.inPoint = f0 / ctx.fps; l.outPoint = f1 / ctx.fps;
        if (ctx.plateScale != 100) TG(l).property("ADBE Scale").setValue([ctx.plateScale, ctx.plateScale]);
        return l;
    }

    function shatter(main, S, ctx) {
        var fps = ctx.fps, n = S.radius.length;
        var it = app.project.importFile(new ImportOptions(new File(S.still))); it.name = "shatter still " + S.cut;
        var l = main.layers.add(it); l.name = "ACCENT " + S.cut + " shatter (landing frame, glass)";
        l.startTime = S.f0 / fps; l.inPoint = S.f0 / fps; l.outPoint = (S.f0 + n) / fps;
        if (ctx.plateScale != 100) TG(l).property("ADBE Scale").setValue([ctx.plateScale, ctx.plateScale]);
        var c = [main.width / 2 / ctx.plateScale * 100, main.height / 2 / ctx.plateScale * 100];   // effect space = layer pixels
        TRY(ctx, S.cut + " shatter", function () {
            var e = fxAdd(l, "ec.sim.shatter", "shatter burst");
            e.property("View").setValue(1); e.property("Render").setValue(1);
            var s = e.property("Shape");
            s.property("Pattern").setValue(2); s.property("Repetitions").setValue(S.reps); s.property("Extrusion Depth").setValue(S.extrusion);
            s.property("Origin").setValue(c);
            var f1 = e.property("Force 1");
            f1.property("Position").setValue(c); f1.property("Depth").setValue(S.depth); f1.property("Strength").setValue(S.strength);
            KF(f1.property("Radius"), S.f0, S.radius, fps);
            var ph = e.property("Physics"); ph.property("Gravity").setValue(0); ph.property("Rotation Speed").setValue(S.rotation);
            e.property("Textures").property("Front Mode").setValue(2); e.property("Textures").property("Side Mode").setValue(3);
            var lg = e.property("Lighting");
            lg.property("Light Intensity").setValue(S.lightIntensity); lg.property("Ambient Light").setValue(S.ambient);
            lg.property("Light Position").setValue([S.lightPos[0] / ctx.plateScale * 100, S.lightPos[1] / ctx.plateScale * 100]);
            e.property("Material").property("Specular Reflection").setValue(S.specular);
        });
        KF(TG(l).property("ADBE Opacity"), S.f0, S.opacity, fps);
    }

    function glass(main, A, ctx, plateLayer) {
        var fps = ctx.fps, n = A.completion.length;
        var l = plateCopy(main, ctx, "ACCENT " + A.cut + " glass edge (symbiote peel)", A.f0, A.f0 + n);
        TRY(ctx, A.cut + " glass wipe", function () {
            var e = fxAdd(l, "ec.transition.ccglasswipe", "glass edge");
            e.property("Layer to Reveal").setValue(plateLayer.index); e.property("Gradient Layer").setValue(l.index);
            e.property("Softness").setValue(A.softness); e.property("Displacement Amount").setValue(A.displacement);
            KF(e.property("Completion"), A.f0, A.completion, fps);
        });
        KF(TG(l).property("ADBE Opacity"), A.f0, A.opacity, fps);
    }

    G.under = function (main, E, ctx) {
        var A = E.x.finish.accents;
        if (!A || !ctx.plateItem) return WARN;
        if (A.shatter) TRY(ctx, "shatter", function () { shatter(main, A.shatter, ctx); });
        if (A.glass && ctx.plateLayer) TRY(ctx, "glass", function () { glass(main, A.glass, ctx, ctx.plateLayer); });
        return WARN;
    };

    G.rays = function (main, E, ctx) {
        var A = E.x.finish.accents, R = A ? A.raysFx : null;
        if (!A || !ctx.plateItem) return WARN;
        for (var i = 0; i < A.rays.length; i++) TRY(ctx, "rays " + A.rays[i].id, function () {
            var r = A.rays[i], l = plateCopy(main, ctx, "ACCENT " + r.id + " light rays (landing)", r.f0, r.f1);
            l.blendingMode = BlendingMode.ADD;
            var e = fxAdd(l, "ADBE Pro Levels2", "highlights only");
            e.property("Input Black").setValue(R.knee); e.property("Output White").setValue(R.gain);
            e = fxAdd(l, "ec.generate.cclightrays", "light rays");
            e.property("Intensity").setValue(R.intensity); e.property("Radius").setValue(R.radius / ctx.plateScale * 100);
            e.property("Warp Softness").setValue(R.warpSoftness);
            e.property("Center").setValue([r.center[0] / ctx.plateScale * 100, r.center[1] / ctx.plateScale * 100]);
            K(TG(l).property("ADBE Opacity"), r.opacity, ctx.fps);
        });
        log(ctx, A.rays.length + " ray landings" + (A.shatter ? ", shatter " + A.shatter.cut : "") + (A.glass ? ", glass " + A.glass.cut : ""));
        return WARN;
    };
    G.warnings = function () { return WARN; };
    return G;
})();
