// transitions_probe.jsx - EffectCraft 0.10 transition effects on two real cuts (operator request, task v3-finish).
// One comp per (pair, effect): 12 frames, A (end of the outgoing clip) over B (start of the incoming clip), the effect
// on A with its completion eased 0 -> 100 over frames 2..9 (the cut sits at frame 6). Run:
//   effectcraft-cli script tools/filmtools/amv3/lab/transitions_probe.jsx --empty   (writes build/amv3/transitions_probe.ecproj)
// then render each comp T_<pair>_<fx> frames 0-11 (filmtools.amv3.lab_transitions does both through the render queue).
var CLIPS = "/home/nikhil/code/film-making/handover/amv_handover/footage_clips/";
var PAIRS = [
    { id: "S12S13", a: "clip_A04_bridge_flip.mp4", ta: 1.05, b: "clip_A05_topdown_fall.mp4", tb: 0.05 },
    { id: "S26S27", a: "clip_M09_punches.mp4", ta: 0.50, b: "clip_M10_tank_snap.mp4", tb: 0.05 }
];
var N = 12, F0 = 2, F1 = 9, FPS = 30, W = 1920, H = 1080;
var proj = app.project, ITEMS = {};
function item(f) { if (!ITEMS[f]) ITEMS[f] = proj.importFile(new ImportOptions(new File(CLIPS + f))); return ITEMS[f]; }
function FXP(l) { return l.property("ADBE Effect Parade"); }
function fx(l, mn, label) { var e = FXP(l).addProperty(mn); e.name = label; return FXP(l).property(label); }
function ease(u) { return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; }      // cubic in-out
function keyC(prop, lo, hi, f0, f1) {
    var ts = [], vs = [];
    for (var f = 0; f < N; f++) { var u = Math.max(0, Math.min(1, (f - f0) / (f1 - f0))); ts.push(f / FPS); vs.push(lo + (hi - lo) * ease(u)); }
    prop.setValuesAtTimes(ts, vs);
}
function set(e, n, v) { try { e.property(n).setValue(v); } catch (er) { writeLn("WARN " + e.name + " " + n + ": " + er); } }

var FX = {
    cardwipe: function (A, B, c) {
        var e = fx(A, "ec.transition.cardwipe", "card wipe");
        keyC(e.property("Transition Completion"), 0, 100, F0, F1);
        set(e, "Back Layer", B.index); set(e, "Rows", 5); set(e, "Columns", 9); set(e, "Flip Axis", 3); set(e, "Flip Direction", 3);
        set(e, "Transition Width", 45); set(e, "Timing Randomness", 0.35); set(e, "Card Scale", 0.98);
        A.property("ADBE Effect Parade").property("card wipe").property("Camera Position").property("Y Rotation").setValue(-14);
    },
    twister: function (A, B, c) {
        var e = fx(A, "ec.transition.cctwister", "twister");
        keyC(e.property("Completion"), 0, 100, F0, F1); set(e, "Backside", B.index); set(e, "Axis", 30);
    },
    glasswipe: function (A, B, c) {
        var e = fx(A, "ec.transition.ccglasswipe", "glass wipe");
        keyC(e.property("Completion"), 0, 100, F0, F1); set(e, "Layer to Reveal", B.index); set(e, "Gradient Layer", A.index);
        set(e, "Softness", 25); set(e, "Displacement Amount", 60);
    },
    lightwipe: function (A, B, c) {
        var e = fx(A, "ec.transition.cclightwipe", "light wipe");
        keyC(e.property("Completion"), 0, 100, F0, F1); set(e, "Shape", 2); set(e, "Intensity", 140); set(e, "Color from Source", 1);
    },
    gradwipe: function (A, B, c) {       // luma of A drives the wipe (stand-in for the subject matte / depth)
        var e = fx(A, "ec.transition.gradientwipe", "gradient wipe");
        keyC(e.property("Transition Completion"), 0, 100, F0, F1); set(e, "Transition Softness", 35); set(e, "Gradient Layer", A.index);
    },
    shatter: function (A, B, c) {
        var e = fx(A, "ec.sim.shatter", "shatter");
        set(e, "View", 1); set(e, "Render", 1);
        var s = e.property("Shape"); s.property("Pattern").setValue(2); s.property("Repetitions").setValue(14); s.property("Extrusion Depth").setValue(0.15);
        var f1 = e.property("Force 1"); f1.property("Depth").setValue(0.05); f1.property("Strength").setValue(6);
        keyC(f1.property("Radius"), 0, 0.9, 4, 8);
        e.property("Physics").property("Gravity").setValue(0);
        e.property("Textures").property("Front Mode").setValue(2); e.property("Textures").property("Side Mode").setValue(3);
    },
    scatterize: function (A, B, c) {
        var e = fx(A, "ec.sim.ccscatterize", "scatterize");
        keyC(e.property("Scatter"), 0, 260, F0, F1); keyC(e.property("Right Twist"), 0, 90, F0, F1);
        keyC(A.property("ADBE Transform Group").property("ADBE Opacity"), 100, 0, 4, F1);
    },
    warpomatic: function (A, B, c) {
        var e = fx(A, "ec.transition.ccwarpomatic", "warpomatic");
        keyC(e.property("Completion"), 0, 100, F0, F1); set(e, "Layer to Reveal", B.index); set(e, "Warp Amount", 90); set(e, "Blend Span", 25);
    },
    rays: function (A, B, c) {           // accents for a hit: Light Burst grows on A into the cut, Light Rays decay on B after it
        var e = fx(A, "ec.generate.cclightburst", "light burst");
        keyC(e.property("Ray Length"), 0, 140, 1, 5); keyC(e.property("Intensity"), 60, 200, 1, 5);
        A.outPoint = 6 / FPS;
        var r = fx(B, "ec.generate.cclightrays", "light rays");
        set(r, "Radius", 90); set(r, "Warp Softness", 30);
        var ts = [], vs = [];
        for (var f = 0; f < N; f++) { ts.push(f / FPS); vs.push(f < 6 ? 0 : 320 * Math.pow(0.62, f - 6)); }
        r.property("Intensity").setValuesAtTimes(ts, vs);
    }
};

for (var p = 0; p < PAIRS.length; p++) {
    var P = PAIRS[p];
    for (var k in FX) {
        var c = proj.items.addComp("T_" + P.id + "_" + k, W, H, 1, N / FPS, FPS);
        c.bgColor = [0, 0, 0];
        var B = c.layers.add(item(P.b)); B.startTime = -P.tb; B.inPoint = 0; B.outPoint = N / FPS; B.name = "B";
        var A = c.layers.add(item(P.a)); A.startTime = -(P.ta - 6 / FPS); A.inPoint = 0; A.outPoint = N / FPS; A.name = "A";
        // B is the layer below A: index 2 after A was added on top
        B = c.layer("B"); A = c.layer("A");
        try { FX[k](A, B, c); } catch (er) { writeLn("WARN " + c.name + ": " + er); }
    }
}
proj.save(new File("OUT_PROJECT"));
writeLn("PROBE_DONE comps " + proj.numItems);
