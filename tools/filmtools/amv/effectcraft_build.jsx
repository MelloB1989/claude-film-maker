// effectcraft_build.jsx - the interpreter half of tools/filmtools/amv/effectcraft.py (read its docstring first).
// effectcraft.py prepends `var SPEC = {...}; var OUT_PROJECT = "...";` and runs this with `effectcraft-cli script`.
// A port of handover build.jsx that takes every number from SPEC (resolved by plan.py's accessors) instead of PLAN.
// Effect parameters are addressed by display name: EffectCraft's match names are not After Effects' (its
// "ADBE Exposure2-0003" is the Red channel), the names are the same in both.
var FPS = SPEC.fps, W = SPEC.w, H = SPEC.h;
function f2t(f) { return f / FPS; }
function TG(l) { return l.property("ADBE Transform Group"); }
function POS(l) { return TG(l).property("ADBE Position"); }
function SCL(l) { return TG(l).property("ADBE Scale"); }
function ROT(l) { return TG(l).property("ADBE Rotate Z"); }
function OPA(l) { return TG(l).property("ADBE Opacity"); }
function ANC(l) { return TG(l).property("ADBE Anchor Point"); }
function FXP(l) { return l.property("ADBE Effect Parade"); }
function hex(h) { h = h.replace("#", ""); return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
var WARN = [];
function warn(s) { WARN.push(s); }
function TRY(what, fn) { try { return fn(); } catch (e) { warn(what + ": " + e); return null; } }

// effect by match name, renamed, returned fresh (references go stale after the next addProperty)
function fxAdd(l, mn, label) {
    var e = FXP(l).addProperty(mn);
    if (label) { e.name = label; return FXP(l).property(label); }
    return e;
}
function setp(fx, name, v) { fx.property(name).setValue(v); }
// keys: [[frame, value], ...] in comp frames, `f0` = the frame the property's time base starts at
function keys(prop, ks, f0) {
    f0 = f0 || 0;
    if (!ks || !ks.length) return;
    if (ks.length == 1) { prop.setValue(ks[0][1]); return; }
    var ts = [], vs = [];
    for (var i = 0; i < ks.length; i++) { ts.push(f2t(ks[i][0] - f0)); vs.push(ks[i][1]); }
    prop.setValuesAtTimes(ts, vs);
}
function scaleKeys(ks) { var o = []; for (var i = 0; i < ks.length; i++) o.push([ks[i][0], [ks[i][1], ks[i][1]]]); return o; }
function ellipseShape(cx, cy, rx, ry, rotDeg) {
    var k = 0.5523, s = new Shape(), r = (rotDeg || 0) * Math.PI / 180, c = Math.cos(r), sn = Math.sin(r);
    function P(x, y) { return [cx + x * c - y * sn, cy + x * sn + y * c]; }
    function V(x, y) { return [x * c - y * sn, x * sn + y * c]; }
    s.vertices = [P(0, -ry), P(rx, 0), P(0, ry), P(-rx, 0)];
    s.inTangents = [V(-rx * k, 0), V(0, -ry * k), V(rx * k, 0), V(0, ry * k)];
    s.outTangents = [V(rx * k, 0), V(0, ry * k), V(-rx * k, 0), V(0, -ry * k)];
    s.closed = true; return s;
}
function rectShape(x0, y0, x1, y1) { var s = new Shape(); s.vertices = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; s.closed = true; return s; }
function roundRectShape(x0, y0, x1, y1, r) {
    var k = 0.5523 * r, s = new Shape();
    s.vertices = [[x0 + r, y0], [x1 - r, y0], [x1, y0 + r], [x1, y1 - r], [x1 - r, y1], [x0 + r, y1], [x0, y1 - r], [x0, y0 + r]];
    s.inTangents = [[-k, 0], [0, 0], [0, -k], [0, 0], [k, 0], [0, 0], [0, k], [0, 0]];
    s.outTangents = [[0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0], [0, 0], [0, -k]];
    s.closed = true; return s;
}
function solid(comp, name, col, w, h, dur) { return comp.layers.addSolid(col || [0, 0, 0], name, w || comp.width, h || comp.height, 1, dur || comp.duration); }
function adjLayer(comp, name, f0, f1) {
    var l = solid(comp, name, [1, 1, 1]); l.adjustmentLayer = true;
    if (f0 !== undefined) { l.inPoint = f2t(f0); l.outPoint = f2t(f1); }
    return l;
}
function importSeq(path, folder, name) {
    var o = new ImportOptions(new File(path)); o.sequence = true;
    var it = app.project.importFile(o);
    TRY("conform " + name, function () { it.mainSource.conformFrameRate = FPS; });
    if (folder) it.parentFolder = folder;
    if (name) it.name = name;
    return it;
}
function addText(comp, text, size, pos, fill, tracking, fonts) {
    var l = comp.layers.addText(text);
    TRY("text style", function () {
        var tp = l.property("ADBE Text Properties").property("ADBE Text Document");
        var d = tp.value; d.resetCharStyle();
        if (fonts) d.font = fonts[0];
        d.fontSize = size; d.fillColor = fill || [1, 1, 1]; if (tracking) d.tracking = tracking;
        d.justification = ParagraphJustification.CENTER_JUSTIFY;
        tp.setValue(d);
    });
    if (pos) POS(l).setValue(pos);
    return l;
}
function dropShadow(l, opacity, dist, soft) {
    TRY("drop shadow", function () {
        var e = fxAdd(l, "ADBE Drop Shadow", "shadow");
        setp(e, "Opacity", opacity); setp(e, "Distance", dist); setp(e, "Softness", soft);
    });
}

var proj = app.project;
TRY("bitsPerChannel", function () { proj.bitsPerChannel = 8; });
var fFoot = proj.items.addFolder("01_FOOTAGE"), fShots = proj.items.addFolder("02_SHOTS"), fTitles = proj.items.addFolder("03_TITLES"),
    fSolids = proj.items.addFolder("04_SOLIDS"), fMattes = proj.items.addFolder("05_MATTES");

var FOOT = {};
for (var k in SPEC.footage) { var fi = proj.importFile(new ImportOptions(new File(SPEC.footage[k]))); fi.parentFolder = fFoot; fi.name = k; FOOT[k] = fi; }

var comp = proj.items.addComp(SPEC.comp_name, W, H, 1, SPEC.dur / FPS, FPS);
comp.shutterAngle = SPEC.shutter.angle; comp.shutterPhase = SPEC.shutter.phase;
comp.motionBlurSamplesPerFrame = SPEC.shutter.samples; TRY("adaptive limit", function () { comp.motionBlurAdaptiveSampleLimit = SPEC.shutter.limit; });
comp.bgColor = [0, 0, 0];

// ---- titles: Blender PNG sequence when rendered, else an editable text placeholder ----
// `target` = the comp the layer goes into, `base` = the comp frame that comp's time 0 is.
function addTitle(target, base, T, scr) {
    var l;
    if (T.seq) {
        var it = importSeq(T.seq, fTitles, "title " + T.id);
        l = target.layers.add(it);
    } else {
        var txt = T.text + (T.sub ? "\r" + T.sub : "");
        l = addText(target, txt, Math.max(24, Math.round((T.size || 90) * 0.6)), T.pos || [W / 2, H * 0.85],
                    [1, 1, 1], 100);
        l.name = "TITLE (placeholder) " + T.text;
        dropShadow(l, 70, 6, 8);
    }
    if (T.seq) l.name = "TITLE " + T.text;
    l.startTime = f2t(T.f_in - base); l.outPoint = f2t(T.out - base);
    if (T.scale) SCL(l).setValue([T.scale, T.scale]);
    return l;
}

// ---- shots ----
var PC = {}, SRC = {}, LAY = {};
function buildShot(S) {
    var n = S.n, src, pc = null;
    if (S.mode == "baked") {
        src = importSeq(S.baked.first, fShots, "baked " + S.name);
    } else {
        pc = proj.items.addComp("SHOT " + S.name, W, H, 1, n / FPS, FPS); pc.parentFolder = fShots;
        var fl = pc.layers.add(FOOT[S.src]); fl.name = "plate";
        fl.timeRemapEnabled = true;
        var tr = fl.property("ADBE Time Remapping");
        keys(tr, S.remap, 0);
        for (var kk = tr.numKeys; kk >= 1; kk--) if (tr.keyTime(kk) > f2t(n - 1) + 0.0001) tr.removeKey(kk);
        fl.outPoint = pc.duration;
        if (S.flipx) SCL(fl).setValue([-100, 100]);
        if (S.slow) TRY("frame mix", function () { fl.frameBlendingType = FrameBlendingType.FRAME_MIX; pc.frameBlending = true; });
        var ex = fxAdd(fl, "ADBE Exposure2", "balance");
        if (typeof S.ev == "number") setp(ex, "Exposure", S.ev); else keys(ex.property("Exposure"), S.ev, S.a);
        if (S.sat) { var hs = fxAdd(fl, "ADBE HUE SATURATION", "sat trim"); setp(hs, "Master Saturation", S.sat); }
        for (var t = 0; t < S.titles.length; t++) addTitle(pc, S.a, S.titles[t]);
        if (S.matte) {
            var mseq = importSeq(S.matte.first, fMattes, "matte " + S.name);
            var cut = fl.duplicate(); cut.name = "cutout"; cut.moveToBeginning();
            var ml = pc.layers.add(mseq); ml.name = "matte"; ml.moveToBeginning(); ml.startTime = f2t(S.matte.f0);
            cut.setTrackMatte(ml, TrackMatteType.LUMA);
            if (S.matte.rim) { var rg = fxAdd(cut, "ADBE Glo2", "CC rim glow"); setp(rg, "Glow Threshold", 55); setp(rg, "Glow Radius", 18); setp(rg, "Glow Intensity", 0.6); }
        }
        src = pc;
    }
    PC[S.index] = pc; SRC[S.index] = src;
    var L = comp.layers.add(src); L.name = S.name;
    L.startTime = f2t(S.a); L.inPoint = f2t(S.a); L.outPoint = f2t(S.end);
    L.motionBlur = true;
    var ax = S.mode == "baked" ? [S.baked.w / 2, S.baked.h / 2] : [W / 2, H / 2];
    ANC(L).setValue(ax);
    keys(POS(L), S.transform.pos, 0); keys(SCL(L), scaleKeys(S.transform.scale), 0); keys(ROT(L), S.transform.rot, 0);
    if (S.opacity.length) keys(OPA(L), S.opacity, 0);
    if (S.mode == "clips") {
        var tile = fxAdd(L, "ADBE Tile", "edge tile");
        setp(tile, "Output Width", S.tile[0]); setp(tile, "Output Height", S.tile[1]); setp(tile, "Mirror Edges", 1);
        if (S.hole) {   // eye dive: subtract a tracked iris ellipse (layer space) that grows while the layer zooms about it
            var pm = L.property("ADBE Mask Parade");
            var mfull = pm.addProperty("ADBE Mask Atom"); mfull.property("ADBE Mask Shape").setValue(rectShape(-4000, -4000, 5920, 5080)); mfull.maskMode = MaskMode.ADD;
            var mh = pm.addProperty("ADBE Mask Atom"); mh.maskMode = MaskMode.SUBTRACT;
            var hs_ = [], shapes = [], feat = [];
            for (var j = 0; j < S.hole.shape.length; j++) { var r = S.hole.shape[j]; hs_.push(f2t(r[0])); shapes.push(ellipseShape(r[1], r[2], r[3], r[4], 0)); feat.push([r[5], r[5]]); }
            mh.property("ADBE Mask Shape").setValuesAtTimes(hs_, shapes);
            mh.property("ADBE Mask Feather").setValuesAtTimes(hs_, feat);
            keys(mh.property("ADBE Mask Offset"), S.hole.offset, 0);
        }
        if (S.rfb) {
            var rb = fxAdd(L, "CC Radial Fast Blur", "zoom blur");
            keys(rb.property("Amount"), S.rfb.amount, 0); keys(rb.property("Center"), S.rfb.center, 0);
            TRY("rfb zoom", function () { rb.property("Zoom").setValue(2); });      // Brightest: glowing streaks
        }
        if (S.dblur) { var db = fxAdd(L, "ADBE Motion Blur", "whip blur"); setp(db, "Direction", S.dblur.dir); keys(db.property("Blur Length"), S.dblur.length, 0); }
        if (S.bulge) {
            var oc = fxAdd(L, "ADBE Optics Compensation", "lens bulge");
            setp(oc, "Reverse Lens Distortion", 1); setp(oc, "FOV Orientation", 2); setp(oc, "View Center", [W / 2, H / 2]);
            keys(oc.property("Field Of View (FOV)"), S.bulge, 0);
        }
        if (S.defocus) { var gb = fxAdd(L, "ADBE Gaussian Blur 2", "defocus"); setp(gb, "Repeat Edge Pixels", 1); keys(gb.property("Blurriness"), S.defocus, 0); }
    }
    LAY[S.index] = L;
    return L;
}

// ---- portals: shot A seen inside shot B's eye, matte = the tracked eye hole ----
var GL = {};
function buildPortal(P) {
    var LA = LAY[P.A], ain = comp.layers.add(SRC[P.A]); ain.name = "A_in " + P.name;
    ain.startTime = LA.startTime; ain.inPoint = f2t(P.f0); ain.outPoint = f2t(P.f1);
    ain.motionBlur = true; ANC(ain).setValue(SHOT_ANCHOR[P.A]);
    keys(POS(ain), P.pos, 0); keys(SCL(ain), scaleKeys(P.scale), 0); keys(ROT(ain), P.rot, 0); keys(OPA(ain), P.opacity, 0);
    var am = ain.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    am.property("ADBE Mask Shape").setValue(roundRectShape(0, 0, W, H, 140)); am.property("ADBE Mask Feather").setValue([140, 140]);
    var rb2 = fxAdd(ain, "CC Radial Fast Blur", "zoom blur"); keys(rb2.property("Amount"), P.rfb_amount, 0);
    var mt = solid(comp, "hole " + P.name, [1, 1, 1]); mt.parentFolder = fSolids; mt.inPoint = f2t(P.f0); mt.outPoint = f2t(P.f1);
    var hm = mt.property("ADBE Mask Parade").addProperty("ADBE Mask Atom"); hm.maskMode = MaskMode.ADD;
    var ts = [], vs = [], fs = [];
    for (var j = 0; j < P.hole.length; j++) { var r = P.hole[j]; ts.push(f2t(r[0])); vs.push(ellipseShape(r[1], r[2], r[3], r[4], r[6])); fs.push([r[5], r[5]]); }
    hm.property("ADBE Mask Shape").setValuesAtTimes(ts, vs); hm.property("ADBE Mask Feather").setValuesAtTimes(ts, fs);
    mt.moveBefore(ain);                                  // matte directly above its layer
    ain.setTrackMatte(mt, TrackMatteType.ALPHA);
}
var SHOT_ANCHOR = {};

function glint(P, G) {
    var gl = comp.layers.addShape(); gl.name = "glint " + P;
    var root = gl.property("ADBE Root Vectors Group");
    function star(pts, outer, inner, rotd) {
        var g = root.addProperty("ADBE Vector Group"); var st = g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Star");
        st.property("ADBE Vector Star Type").setValue(1); st.property("ADBE Vector Star Points").setValue(pts);
        st.property("ADBE Vector Star Outer Radius").setValue(outer); st.property("ADBE Vector Star Inner Radius").setValue(inner);
        st.property("ADBE Vector Star Rotation").setValue(rotd);
        var fi = g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill"); fi.property("ADBE Vector Fill Color").setValue([1, 1, 1]);
    }
    star(4, G.r, G.r * 0.10, 0); star(4, G.r * 0.5, G.r * 0.08, 45);
    gl.blendingMode = BlendingMode.ADD; ANC(gl).setValue([0, 0]);
    keys(POS(gl), G.pos, 0); gl.inPoint = f2t(G.f0); gl.outPoint = f2t(G.f0 + G.n);
    keys(OPA(gl), [[G.f0, 0], [G.f0 + 1, 100], [G.f0 + 4, 100], [G.f0 + 9, 0]], 0);
    keys(SCL(gl), [[G.f0, [60, 60]], [G.f0 + 2, [100, 100]], [G.f0 + 5, [85, 85]], [G.f0 + 11, [40, 40]]], 0);
    TRY("glint spin", function () { ROT(gl).expression = "time*120"; });
    TRY("glint glow", function () {
        var g1 = fxAdd(gl, "ADBE Glo2", "glow"); setp(g1, "Glow Threshold", 20); setp(g1, "Glow Radius", 20); setp(g1, "Glow Intensity", 1.2);
        var g2 = fxAdd(gl, "ADBE Glo2", "bloom"); setp(g2, "Glow Threshold", 10); setp(g2, "Glow Radius", 60); setp(g2, "Glow Intensity", 0.5);
    });
}

// ---- grade (Premium Glow CC, native stand-ins; handover 13_color_grading.md §2-3) ----
function buildGrade(G) {
    var gr = adjLayer(comp, "CC GRADE (Premium Glow merged)");
    gr.outPoint = f2t(G.out);
    TRY("grade sharpen", function () { var e = fxAdd(gr, "ADBE Unsharp Mask2", "sharpen (S_Sharpen stand-in)"); setp(e, "Amount", G.sharpen.amount); setp(e, "Radius", G.sharpen.radius); });
    TRY("grade looks cb", function () {
        var cb = fxAdd(gr, "ADBE Color Balance 2", "looks cool");
        var nm = ["Shadow Red Balance", "Shadow Green Balance", "Shadow Blue Balance", "Midtone Red Balance", "Midtone Green Balance", "Midtone Blue Balance", "Highlight Red Balance", "Highlight Green Balance", "Highlight Blue Balance"];
        for (var i = 0; i < 9; i++) setp(cb, nm[i], G.looks_cb[i]);
    });
    TRY("grade lumetri", function () {
        var lu = fxAdd(gr, "ADBE Lumetri", "Lumetri");
        var bc = lu.property("ADBE Lumetri-0002"), t = bc.property("tone");
        t.property("exposure").setValue(G.lumetri.exposure); t.property("contrast").setValue(G.lumetri.contrast); t.property("highlights").setValue(G.lumetri.highlights);
        t.property("shadows").setValue(G.lumetri.shadows); t.property("whites").setValue(G.lumetri.whites);
        t.property("blacks").setValue(G.lumetri.blacks); bc.property("saturation").setValue(G.lumetri.saturation);
        var vg = lu.property("ADBE Lumetri-0007");
        vg.property("vignetteAmount").setValue(G.vignette.amount); vg.property("vignetteMidpoint").setValue(G.vignette.midpoint);
    });
    TRY("grade b&c", function () { var e = fxAdd(gr, "ADBE Brightness & Contrast 2", "brightness contrast"); setp(e, "Brightness", G.bc.brightness); setp(e, "Contrast", G.bc.contrast); });
    TRY("grade teal orange", function () {
        var cb = fxAdd(gr, "ADBE Color Balance 2", "teal orange");
        var nm = ["Shadow Red Balance", "Shadow Green Balance", "Shadow Blue Balance", "Midtone Red Balance", "Midtone Green Balance", "Midtone Blue Balance", "Highlight Red Balance", "Highlight Green Balance", "Highlight Blue Balance"];
        for (var i = 0; i < 9; i++) setp(cb, nm[i], G.teal_orange[i]);
        setp(cb, "Preserve Luminosity", 1);
    });
    TRY("grade glow", function () { var bl = fxAdd(gr, "ADBE Glo2", "bloom"); setp(bl, "Glow Threshold", G.glow.threshold); setp(bl, "Glow Radius", G.glow.radius); setp(bl, "Glow Intensity", G.glow.intensity); });
    return gr;
}

// ---- main comp, bottom to top ----
var SH = {}; for (var si = 0; si < SPEC.shots.length; si++) SH[SPEC.shots[si].index] = SPEC.shots[si];
var PORTALS = {};
var GLINT = {};
for (var li = 0; li < SPEC.layers.length; li++) { var LD = SPEC.layers[li]; if (LD.type == "portal") PORTALS[LD.portal.name] = LD.portal; }

if (SPEC.audio) {
    var au = proj.importFile(new ImportOptions(new File(SPEC.audio))); au.parentFolder = fFoot;
    var aul = comp.layers.add(au); aul.name = "MIX"; aul.startTime = 0; aul.outPoint = f2t(SPEC.dur);
}
for (li = 0; li < SPEC.layers.length; li++) {
    LD = SPEC.layers[li];
    if (LD.type == "shot") { var S = SH[LD.shot]; SHOT_ANCHOR[S.index] = S.mode == "baked" ? [S.baked.w / 2, S.baked.h / 2] : [W / 2, H / 2]; buildShot(S); }
    else if (LD.type == "portal") buildPortal(LD.portal);
    else if (LD.type == "black") { var bk = solid(comp, "black " + LD.f, [0, 0, 0]); bk.inPoint = f2t(LD.f); bk.outPoint = f2t(LD.f + 1); }
    else if (LD.type == "invert") {
        var iv = adjLayer(comp, "invert " + LD.f, LD.f, LD.f + 1); fxAdd(iv, "ADBE Invert", "inv");
        var du = fxAdd(iv, "ADBE Tint", "duo"); setp(du, "Map Black To", hex(LD.black)); setp(du, "Map White To", hex(LD.white));
    }
    else if (LD.type == "halftone") {
        var ht = adjLayer(comp, "halftone " + LD.f, LD.f, LD.f + LD.n);
        TRY("halftone", function () { var ba = fxAdd(ht, "CC Ball Action", "dots"); setp(ba, "Grid Spacing", LD.grid); });
    }
    else if (LD.type == "flash") { var fla = adjLayer(comp, "FLASH"); var fe2 = fxAdd(fla, "ADBE Exposure2", "flash exp"); keys(fe2.property("Exposure"), LD.ev, 0); }
    else if (LD.type == "grade") buildGrade(LD);
    else if (LD.type == "bars") {
        var topBar = solid(comp, "letterbox top", [0, 0, 0], W, 400), botBar = solid(comp, "letterbox bottom", [0, 0, 0], W, 400);
        var tk = [], bkk = [];
        for (j = 0; j < LD.top.length; j++) { tk.push([LD.top[j][0], [960, -200 + LD.top[j][1]]]); bkk.push([LD.top[j][0], [960, H + 200 - LD.top[j][1]]]); }
        keys(POS(topBar), tk, 0); keys(POS(botBar), bkk, 0);
        topBar.outPoint = botBar.outPoint = f2t(LD.out);
    }
    else if (LD.type == "accent") {
        var al = comp.layers.addShape(); al.name = "accent " + LD.f + " y" + LD.y;
        var ag = al.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var rr = ag.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
        keys(rr.property("ADBE Vector Rect Size"), [[LD.f, [96, 9]], [LD.f + 8, [1250, 9]], [LD.f + LD.n, [1700, 9]]], 0);
        var af = ag.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill"); af.property("ADBE Vector Fill Color").setValue([1, 1, 1]);
        ANC(al).setValue([0, 0]); POS(al).setValue([960, LD.y]);
        al.inPoint = f2t(LD.f); al.outPoint = f2t(LD.f + LD.n);
        var tint = fxAdd(al, "ADBE Tint", "fade col"); setp(tint, "Map White To", hex("#EEB6BF"));
        keys(tint.property("Amount to Tint"), [[LD.f, 0], [LD.f + LD.n, 100]], 0);
        keys(OPA(al), [[LD.f, 100], [LD.f + LD.n - 4, 90], [LD.f + LD.n, 0]], 0);
    }
    else if (LD.type == "glint") glint(LD.portal, PORTALS[LD.portal].glint);
    else if (LD.type == "title") addTitle(comp, 0, LD.title);
    else if (LD.type == "outro") {
        var ol;
        if (LD.seq) { var oit = importSeq(LD.seq, fTitles, "outro"); ol = comp.layers.add(oit); }
        else {
            ol = addText(comp, "SAU_EDITZ", 200, [W / 2, H / 2], [1, 1, 1], 100);
            TRY("outro glow", function () { var g = fxAdd(ol, "ADBE Glo2", "bloom"); setp(g, "Glow Intensity", 1.0); setp(g, "Glow Radius", 60); });
        }
        ol.name = "OUTRO SAU_EDITZ" + (LD.seq ? "" : " (placeholder)");
        ol.startTime = f2t(LD.f); ol.inPoint = f2t(LD.f); ol.outPoint = f2t(LD.dur);
    }
    else if (LD.type == "watermark") {
        var wm;
        if (LD.seq) { var wit = importSeq(LD.seq, fTitles, "watermark"); wm = comp.layers.add(wit); }
        else wm = addText(comp, LD.text, 30, [960, 1050], [1, 1, 1], 250);
        wm.name = "watermark"; OPA(wm).setValue(62); wm.outPoint = f2t(LD.out);
        keys(OPA(wm), LD.opacity, 0);
        dropShadow(wm, 70, 2, 4);
    }
}
TRY("save", function () { proj.save(new File(OUT_PROJECT)); });
var RESULT = "layers " + comp.numLayers + ", items " + proj.numItems + ", warnings " + WARN.length + (WARN.length ? "\n" + WARN.join("\n") : "");
writeLn(RESULT);
RESULT;
