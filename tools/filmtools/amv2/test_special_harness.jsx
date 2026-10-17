// test_special_harness.jsx: stands in for the core builder (ecbuild.py) while it does not exist.
// test_special.py prepends `var E = {...}; var CFG = {...};` and appends the lib + `SPECIAL.build(main, E, ctx)`.
// MAIN holds each shot as a layer SHOT_<id> (a precomp of the clip, linear time map, drift scale about the focus).
var FPS = E.fps, W = E.w, H = E.h;
var LOGS = [];
function clipPath(clipId, file) {
    if (CFG.src === "src240") { var p = CFG.data + "/src240/clip_" + clipId + ".mp4"; if (new File(p).exists) return p; }
    return file;
}
var IMPORTED = {};
function footage(clipId, file) {
    var p = clipPath(clipId, file);
    if (!IMPORTED[p]) IMPORTED[p] = app.project.importFile(new ImportOptions(new File(p)));
    return IMPORTED[p];
}
var folderEl = app.project.items.addFolder("elements");
var main = app.project.items.addComp("MAIN", W, H, 1, E.dur / FPS, FPS);
main.shutterAngle = 270; main.motionBlurSamplesPerFrame = CFG.samples || 16; main.bgColor = [0, 0, 0];
var SHOTS = {}, SHOTCOMPS = {};
for (var i = 0; i < E.shots.length; i++) {
    var S = E.shots[i];
    if (CFG.shots.indexOf(S.id) < 0) continue;
    var n = S.b - S.a, pc = app.project.items.addComp("SHOT_" + S.id, W, H, 1, n / FPS, FPS);
    var fl = pc.layers.add(footage(S.clip, S.file));
    fl.timeRemapEnabled = true;
    var tr = fl.property("ADBE Time Remapping");
    // never leave the clip's own duration (reverse clips read src[0] > src[1])
    tr.setValuesAtTimes([0, n / FPS], [S.src[0], S.src[1]]);
    for (var k = tr.numKeys; k > 2; k--) tr.removeKey(k);
    SHOTCOMPS[S.id] = pc;
    var L = main.layers.add(pc); L.name = "SHOT_" + S.id;
    L.startTime = S.a / FPS; L.inPoint = S.a / FPS; L.outPoint = S.b / FPS; L.motionBlur = true;
    var tg = L.property("ADBE Transform Group"), ax = S.focus || [W / 2, H / 2];
    tg.property("ADBE Anchor Point").setValue(ax); tg.property("ADBE Position").setValue(ax);
    tg.property("ADBE Scale").setValuesAtTimes([S.a / FPS, S.b / FPS], [[S.drift[0], S.drift[0]], [S.drift[1], S.drift[1]]]);
    SHOTS[S.id] = L;
}
var ctx = {
    fps: FPS, w: W, h: H, root: CFG.root, data: CFG.data, src: CFG.src, elements: folderEl,
    log: function (m) { LOGS.push(m); $.writeln("[special] " + m); },
    shot: function (id) { return SHOTS[id] || null; },
    shotComp: function (id) { return SHOTCOMPS[id] || null; },
    matte: function (id) { return null; }
};
