// core.jsx - the Timeless v2 EffectCraft builder (agent "core"). ecbuild.py prepends
//   var E = {...edl + x...}; var CORE = {...per-shot keys...}; var OUT_PROJECT = "..."; and the libs (fx, grade, special, titles).
// It builds SHOT_<id> precomps + MAIN, then calls the libs in stacking order (see ec/README.md).
var FPS = E.fps, W = E.w, H = E.h;
function f2t(f) { return f / FPS; }
function TG(l) { return l.property("ADBE Transform Group"); }
function POS(l) { return TG(l).property("ADBE Position"); }
function SCL(l) { return TG(l).property("ADBE Scale"); }
function ROT(l) { return TG(l).property("ADBE Rotate Z"); }
function OPA(l) { return TG(l).property("ADBE Opacity"); }
function ANC(l) { return TG(l).property("ADBE Anchor Point"); }
function FXP(l) { return l.property("ADBE Effect Parade"); }
var WARN = [];
function warn(s) { WARN.push(s); }
function TRY(what, fn) { try { return fn(); } catch (e) { warn(what + ": " + e); return null; } }
function log(s) { writeLn("[core] " + s); }

var proj = app.project;
TRY("bitsPerChannel", function () { proj.bitsPerChannel = 8; });
var fFoot = proj.items.addFolder("01_FOOTAGE"), fShots = proj.items.addFolder("02_SHOTS"),
    fElem = proj.items.addFolder("03_ELEMENTS"), fMattes = proj.items.addFolder("04_MATTES");

var FOOT = {};     // file path -> FootageItem
function footage(path) {
    if (!FOOT[path]) {
        var it = proj.importFile(new ImportOptions(new File(path)));
        it.parentFolder = fFoot; FOOT[path] = it;
    }
    return FOOT[path];
}

var PC = {}, LAYS = {}, MATTES = {};
var main = proj.items.addComp("MAIN", W, H, 1, E.dur / FPS, FPS);
main.shutterAngle = CORE.shutter.angle; main.shutterPhase = CORE.shutter.phase;
main.motionBlurSamplesPerFrame = CORE.shutter.samples;
TRY("adaptive limit", function () { main.motionBlurAdaptiveSampleLimit = CORE.shutter.samples; });
main.bgColor = [0, 0, 0];

var ctx = {
    fps: FPS, w: W, h: H, root: CORE.root, data: CORE.data, src: CORE.src, elements: fElem, log: log,
    handles: [CORE.hin, CORE.hout],
    shot: function (id) { return LAYS[id] || null; },
    shotComp: function (id) { return PC[id] || null; },
    matte: function (id) { return MATTES[id] || null; }
};

// ---- one precomp per shot: the footage with time remap (time 0 = frame a - hin) ----
function buildShotComp(S, K, item, cname) {
    var n = S.b - S.a, tot = CORE.hin + n + CORE.hout;
    var pc = proj.items.addComp(cname, W, H, 1, tot / FPS, FPS); pc.parentFolder = item ? (K.isMatte ? fMattes : fShots) : fShots;
    pc.bgColor = [0, 0, 0];
    var fi = item || footage(K.file);
    var fl = pc.layers.add(fi); fl.name = "footage " + S.clip;
    fl.timeRemapEnabled = true;
    var tr = fl.property("ADBE Time Remapping");
    var ts = [], vs = [];
    for (var i = 0; i < K.remap.length; i++) { ts.push(K.remap[i][0]); vs.push(K.remap[i][1]); }
    tr.setValuesAtTimes(ts, vs);
    for (var kk = tr.numKeys; kk >= 1; kk--) if (tr.keyTime(kk) > ts[ts.length - 1] + 1e-6) tr.removeKey(kk);
    TRY("frame blend off", function () { fl.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND; });
    fl.outPoint = pc.duration;
    // the clip's native size is 1920x1080; scale a different source to fit
    var fw = fi.width, fh = fi.height;
    if (fw != W || fh != H) { var sc = Math.max(W / fw, H / fh) * 100; SCL(fl).setValue([sc, sc]); }
    return pc;
}

function buildShotLayer(S, K, pc, lname) {
    var L = main.layers.add(pc); L.name = lname;
    L.startTime = f2t(S.a - CORE.hin); L.inPoint = f2t(S.a); L.outPoint = f2t(S.b);
    L.motionBlur = true;
    var F = S.focus || [W / 2, H / 2];
    ANC(L).setValue(F);
    var ts = [], ps = [], ss = [], rs = [], os = [], tw = [], th = [];
    var anyTile = false, anyOp = false;
    for (var i = 0; i < K.keys.length; i++) {
        var k = K.keys[i];
        ts.push(f2t(k.f)); ps.push(k.pos); ss.push([k.scale, k.scale]); rs.push(k.rot); os.push(k.opacity);
        tw.push(k.tile ? k.tile[0] : 100); th.push(k.tile ? k.tile[1] : 100); if (k.tile) anyTile = true; if (k.opacity < 100) anyOp = true;
    }
    POS(L).setValuesAtTimes(ts, ps); SCL(L).setValuesAtTimes(ts, ss);
    ROT(L).setValuesAtTimes(ts, rs);
    if (anyOp) OPA(L).setValuesAtTimes(ts, os);
    if (anyTile) {
        TRY("tile " + S.id, function () {
            var e = FXP(L).addProperty("ADBE Tile"); e.name = "edge tile";
            e = FXP(L).property("edge tile");
            e.property("Mirror Edges").setValue(1);
            e.property("Output Width").setValuesAtTimes(ts, tw); e.property("Output Height").setValuesAtTimes(ts, th);
        });
    }
    if (K.keys[0].wb) {
        TRY("whip blur " + S.id, function () {
            var wl = [], wdn = [];
            for (var j = 0; j < K.keys.length; j++) { wl.push(K.keys[j].wb[0]); wdn.push(K.keys[j].wb[1]); }
            var b = FXP(L).addProperty("ADBE Motion Blur"); b.name = "whip blur";
            b = FXP(L).property("whip blur");
            b.property("Direction").setValuesAtTimes(ts, wdn); b.property("Blur Length").setValuesAtTimes(ts, wl);
        });
    }
    return L;
}

for (var si = 0; si < E.shots.length; si++) {
    var S = E.shots[si], K = CORE.shots[S.id];
    PC[S.id] = buildShotComp(S, K, null, "SHOT_" + S.id);
    LAYS[S.id] = buildShotLayer(S, K, PC["SHOT_" + S.id] || PC[S.id], "SHOT_" + S.id);
}
// ---- MATTE_<id>: the subject matte (white on black) mirroring the shot's remap + transform, disabled ----
for (var mi = 0; mi < E.shots.length; mi++) {
    var MS = E.shots[mi], MK = CORE.shots[MS.id];
    if (!MK.matte) continue;
    TRY("matte " + MS.id, function () {
        var o = new ImportOptions(new File(MK.matte.first)); o.sequence = true;
        var it = proj.importFile(o); it.parentFolder = fMattes; it.name = "matte " + MS.clip;
        it.mainSource.conformFrameRate = MK.matte.fps;
        var mk = { remap: MK.remap, keys: MK.keys, isMatte: true };
        var mpc = buildShotComp(MS, mk, it, "MATTE_" + MS.id);
        var ml = buildShotLayer(MS, mk, mpc, "MATTE_" + MS.id);
        ml.enabled = false; MATTES[MS.id] = ml;
    });
}
log("shots " + E.shots.length);

// ---- fallback triptych (only when the SPECIAL lib is missing): three vertical panels, one per hit ----
function fallbackTriptych() {
    var T = E.triptych, pw = W / 3;
    for (var i = 0; i < T.panels.length; i++) {
        var P = T.panels[i];
        var fi = footage(CORE.src == "src240" ? CORE.data + "/src240/clip_" + P.clip + ".mp4" : P.file);
        var l = main.layers.add(fi); l.name = "PANEL_" + (i + 1) + " " + P.clip;
        l.startTime = f2t(P.f) - P.src[0]; l.inPoint = f2t(P.f); l.outPoint = f2t(T.shatter);
        var sc = 112; SCL(l).setValue([sc, sc]);
        var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        var x0 = i * pw, sh = new Shape();
        sh.vertices = [[x0, 0], [x0 + pw, 0], [x0 + pw, H], [x0, H]]; sh.closed = true;
        m.property("ADBE Mask Shape").setValue(sh);
        l.motionBlur = true;
    }
    log("fallback triptych built (SPECIAL missing)");
}

// ---- libraries, bottom to top ----
function callLib(o, name, fn) {
    if (!o || typeof o[fn] != "function") { log("skip " + name + " (missing)"); return; }
    TRY(name, function () { o[fn](main, E, ctx); });
    log("ran " + name);
}
callLib(typeof FX === "undefined" ? null : FX, "FX.buildUnder", "buildUnder");
callLib(typeof GRADE === "undefined" ? null : GRADE, "GRADE.build", "build");
callLib(typeof FX === "undefined" ? null : FX, "FX.buildOver", "buildOver");
if (typeof SPECIAL === "undefined" || !SPECIAL || typeof SPECIAL.build != "function") TRY("fallback triptych", fallbackTriptych);
else callLib(SPECIAL, "SPECIAL.build", "build");
callLib(typeof TITLES === "undefined" ? null : TITLES, "TITLES.build", "build");

TRY("save", function () { proj.save(new File(OUT_PROJECT)); });
writeLn("CORE_DONE layers " + main.numLayers + " items " + proj.numItems + " warnings " + WARN.length);
for (var wi = 0; wi < WARN.length; wi++) writeLn("WARN " + WARN[wi]);
"done";
