// finish.jsx - the Timeless v3 finishing comp FINISH (EffectCraft). ecfinish.py prepends
//   var E = {edl + E.x.finish + E.x.titles}; var OUT_PROJECT = "...";  and the libs grade3.jsx (GRADE3), lens.jsx (LENS),
//   v2's titles.jsx (TITLES, unchanged).
// Stack, bottom to top (new layers go on top, so the call order is the stacking order):
//   1. OUTRO        v2 outro frames (819-899), under the plate (the plate is transparent after the triptych shatter)
//   2. PLATE        the stage `plate` pass
//   3. GRADE3       per-shot trims (blended in windows), act looks, bloom, sharpen          (0 .. outro)
//   4. LENS         chromatic split, zoom smear, bulge, light leaks, bloom swell, flashes in every CUTS window
//   5. TEXT         the stage `text` pass (3D titles): a subtle act tint and a soft glow on the outlines
//   6. LIGHT        the stage `light` pass three times, ADD, each a Glow only (tight core, mid halo, wide bloom)
//   7. TITLES       v2 2D titles (subs, name cards, caption boxes, watermark), letterbox on `letterbox` shots
//   8. GRADE3 top   grain, vignette, highlight limiter                                        (0 .. outro)
var FPS = E.fps, W = E.w, H = E.h, X = E.x.finish;
var WARN = [];
function warn(s) { WARN.push(s); }
function TRY(what, fn) { try { return fn(); } catch (e) { warn(what + ": " + e); return null; } }
function log(s) { writeLn("[finish] " + s); }
function TG(l) { return l.property("ADBE Transform Group"); }
function FXP(l) { return l.property("ADBE Effect Parade"); }
function fxAdd(l, mn, label) { var e = FXP(l).addProperty(mn); if (label) { e.name = label; return FXP(l).property(label); } return e; }

var proj = app.project;
TRY("bitsPerChannel", function () { proj.bitsPerChannel = 8; });
var fPass = proj.items.addFolder("01_PASSES");
var main = proj.items.addComp("FINISH", W, H, 1, E.dur / FPS, FPS);
main.bgColor = [0, 0, 0];

// an image sequence (first file, frame count, first comp frame) as a layer timed to its comp frames
function seqItem(P, name) {
    var o = new ImportOptions(new File(P.first)); o.sequence = true;
    var it = proj.importFile(o); it.parentFolder = fPass; it.name = name;
    TRY("conform " + name, function () { it.mainSource.conformFrameRate = FPS; });
    return it;
}
function seqLayer(it, P, name) {
    var l = main.layers.add(it); l.name = name;
    l.startTime = P.start / FPS; l.inPoint = P.start / FPS; l.outPoint = (P.start + P.n) / FPS;
    var sc = 100 * W / P.w;
    if (Math.abs(sc - 100) > 0.01) TG(l).property("ADBE Scale").setValue([sc, sc]);
    return l;
}

var ctx = { fps: FPS, w: W, h: H, log: log, plateItem: null, plateStart: 0, plateScale: 100 };

// 1. outro
if (X.passes.outro) TRY("outro", function () { seqLayer(seqItem(X.passes.outro, "outro v2"), X.passes.outro, "OUTRO (v2 Blender)"); });
// 2. plate
if (X.passes.plate) TRY("plate", function () {
    var P = X.passes.plate, it = seqItem(P, "plate pass");
    seqLayer(it, P, "PLATE (stage)");
    ctx.plateItem = it; ctx.plateStart = P.start; ctx.plateScale = 100 * W / P.w;
});
// 3. grade
TRY("GRADE3.build", function () { GRADE3.build(main, E, ctx); });
// 4. lens FX
TRY("LENS.build", function () { LENS.build(main, E, ctx); });
// 5. text pass: not graded by the act look; a light act tint and a soft glow on its outlines
if (X.passes.text) TRY("text", function () {
    var P = X.passes.text, l = seqLayer(seqItem(P, "text pass"), P, "TEXT (stage 3D titles)");
    var T = X.textTint, A = X.actKeys;
    var e = fxAdd(l, "ADBE Color Balance 2", "act tint (subtle)");
    var names = ["Shadow", "Midtone", "Highlight"];
    for (var i = 0; i < 3; i++) for (var c = 0; c < 3; c++) {
        var ks = [], ts = [];
        for (var j = 0; j < A.length; j++) { ts.push(A[j][0] / FPS); ks.push(T[A[j][1]][i][c]); }
        var p = e.property(names[i] + " " + ["Red", "Green", "Blue"][c] + " Balance");
        if (ts.length > 1) p.setValuesAtTimes(ts, ks); else p.setValue(ks[0]);
    }
    e = fxAdd(l, "ADBE Glo2", "outline glow");
    e.property("Glow Threshold").setValue(X.textGlow.threshold); e.property("Glow Radius").setValue(X.textGlow.radius);
    e.property("Glow Intensity").setValue(X.textGlow.intensity);
});
// 6. light pass: glow only, added
if (X.passes.light) TRY("light", function () {
    var P = X.passes.light, it = seqItem(P, "light pass");
    for (var i = 0; i < X.lightGlows.length; i++) {
        var g = X.lightGlows[i], l = seqLayer(it, P, "LIGHT glow " + g.name);
        l.blendingMode = BlendingMode.ADD;
        var e = fxAdd(l, "ADBE Glo2", "glow " + g.name);
        e.property("Glow Threshold").setValue(g.threshold); e.property("Glow Radius").setValue(g.radius);
        e.property("Glow Intensity").setValue(g.intensity); e.property("Composite Original").setValue(3);
        TG(l).property("ADBE Opacity").setValue(g.opacity);
    }
});
// 7. 2D titles (v2 TITLES lib) and the letterbox
if (typeof TITLES !== "undefined") TRY("TITLES.build", function () {
    var r = TITLES.build(main, E, { fps: FPS, w: W, h: H, log: log, matte: function () { return null; } });
    for (var i = 0; r && i < r.warnings.length; i++) warn("TITLES " + r.warnings[i]);
});
for (var bi = 0; bi < X.letterbox.length; bi++) TRY("letterbox", function () {
    var bx = X.letterbox[bi];
    for (var side = 0; side < 2; side++) {
        var l = main.layers.addSolid([0, 0, 0], "LETTERBOX " + (side ? "bottom" : "top") + " " + bx.id, W, bx.h, 1, main.duration);
        l.inPoint = bx.f0 / FPS; l.outPoint = bx.f1 / FPS;
        var ts = [], vs = [];
        for (var i = 0; i < bx.y[side].length; i++) { ts.push(bx.y[side][i][0] / FPS); vs.push([W / 2, bx.y[side][i][1]]); }
        TG(l).property("ADBE Position").setValuesAtTimes(ts, vs);
    }
});
// 8. grain, vignette, limiter over everything
TRY("GRADE3.buildTop", function () { GRADE3.buildTop(main, E, ctx); });
var gw = GRADE3.warnings(), lw = LENS.warnings();
for (var q = 0; q < gw.length; q++) warn("GRADE3 " + gw[q]);
for (q = 0; q < lw.length; q++) warn("LENS " + lw[q]);

TRY("save", function () { proj.save(new File(OUT_PROJECT)); });
writeLn("FINISH_DONE layers " + main.numLayers + " items " + proj.numItems + " warnings " + WARN.length);
for (var wi = 0; wi < WARN.length; wi++) writeLn("WARN " + WARN[wi]);
"done";
