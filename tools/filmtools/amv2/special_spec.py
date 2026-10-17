"""special_spec.py: the numbers ec/special.jsx needs that Python is better at. The core calls extend(E, ctx_py) and
the result lands under E["x"]["special"] (EDIT.md: rift, drop_portal, panel_slam). Stdlib only.

    rift     iris + lens centres, the caption flip (digit scramble frame by frame)
    portal   lens centre, shock timing
    triptych panel quads (comic panels with a shared slant), the clip crops, earth labels, and the SHARDS: a radial
             Voronoi shatter of the 1920x1080 frame around the impact point, one polygon per shard with its
             flight (direction, speed, spin, delay) so the JSX only has to place layers.
"""
import hashlib
import json
import math
import os
import random
import subprocess
import tempfile

W, H = 1920, 1080

RIFT = dict(f0=244, f1=262, iris=(901, 390), caption_from="EARTH-96283", caption_to="EARTH-120703",
            caption_flip=(247, 258))   # frames the digits scramble between
PORTAL = dict(f0=468, f1=492, drop=480, lens=(1110, 443))
TRIP = dict(margin_x=40, margin_y=48, gutter=40, slant=44, panel_w=572)
IMPACT = (960, 540)


def scramble(frm, to, f0, f1, seed=7):
    """caption text for every frame in [f0-1, f1+1]: the digits tumble, then lock left to right."""
    rnd = random.Random(seed)
    digits_from, digits_to = frm.split("-")[1], to.split("-")[1]
    out = {}
    n = len(digits_to)
    lock = [f0 + 3 + int(round(i * (f1 - f0 - 4) / float(n - 1))) for i in range(n)]
    for f in range(f0 - 1, f1 + 2):
        if f < f0:
            out[f] = frm
        elif f >= f1:
            out[f] = to
        else:
            width = len(digits_from) if f < f0 + 3 else len(digits_to)
            s = ""
            for i in range(width):
                if width == n and i < n and f >= lock[i]:
                    s += digits_to[i]
                else:
                    s += str(rnd.randint(0, 9))
            out[f] = "EARTH-" + s
    return out


def panel_quads():
    t = TRIP
    quads = []
    y0, y1 = t["margin_y"], H - t["margin_y"]
    for i in range(3):
        x = t["margin_x"] + i * (t["panel_w"] + t["gutter"])
        # bottom-left, bottom-right, top-right, top-left; the top edge leans right by `slant`
        q = [(x, y1), (x + t["panel_w"], y1), (x + t["panel_w"] + t["slant"], y0), (x + t["slant"], y0)]
        cx = sum(p[0] for p in q) / 4.0
        quads.append(dict(quad=q, cx=cx, cy=(y0 + y1) / 2.0))
    return quads


def clip_halfplane(poly, p, q):
    """keep the part of `poly` closer to p than to q."""
    mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
    nx, ny = q[0] - p[0], q[1] - p[1]

    def inside(v):
        return (v[0] - mx) * nx + (v[1] - my) * ny <= 0

    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ia, ib = inside(a), inside(b)
        if ia:
            out.append(a)
        if ia != ib:
            da = (a[0] - mx) * nx + (a[1] - my) * ny
            db = (b[0] - mx) * nx + (b[1] - my) * ny
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def area_centroid(poly):
    a = cx = cy = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    a *= 0.5
    if abs(a) < 1e-6:
        return 0.0, poly[0][0], poly[0][1]
    return abs(a), cx / (6 * a), cy / (6 * a)


def in_poly(pt, poly):
    x, y = pt
    c = False
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            c = not c
    return c


def make_shards(quads, seed=11):
    """radial shatter: rings of seed points around IMPACT (small shards near it, big ones far), Voronoi cells."""
    rnd = random.Random(seed)
    cx, cy = IMPACT
    pts = [(cx + rnd.uniform(-20, 20), cy + rnd.uniform(-20, 20))]
    for r, n in ((120, 6), (300, 9), (560, 12), (900, 15)):
        a0 = rnd.uniform(0, math.tau)
        for k in range(n):
            a = a0 + k * math.tau / n + rnd.uniform(-0.28, 0.28) * math.tau / n * 2
            rr = r * rnd.uniform(0.82, 1.18)
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    rect = [(0, 0), (W, 0), (W, H), (0, H)]
    shards = []
    for i, p in enumerate(pts):
        poly = list(rect)
        for j, q in enumerate(pts):
            if i != j:
                poly = clip_halfplane(poly, p, q)
                if len(poly) < 3:
                    break
        if len(poly) < 3:
            continue
        area, gx, gy = area_centroid(poly)
        # keep a shard only if it holds picture: a sample inside a panel quad, or the TIMELESS band
        xs = [v[0] for v in poly]
        ys = [v[1] for v in poly]
        keep = False
        gxs = int(min(xs)) - int(min(xs)) % 20
        y = int(min(ys))
        while y <= max(ys) and not keep:
            x = gxs
            while x <= max(xs):
                if in_poly((x, y), poly) and (any(in_poly((x, y), q["quad"]) for q in quads) or
                                              (300 < y < 780 and 150 < x < 1770)):
                    keep = True
                    break
                x += 20
            y += 20
        if not keep:
            continue
        dx, dy = gx - cx, gy - cy
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        # flight: near shards leave fast, far ones lazily; everything drifts a little towards the camera
        speed = 16 + 420.0 / (1 + d / 160.0) * rnd.uniform(0.7, 1.15)
        shards.append(dict(
            poly=[[round(v[0], 1), round(v[1], 1)] for v in poly],
            c=[round(gx, 1), round(gy, 1)], area=round(area),
            dir=[round(ux, 4), round(uy, 4)], speed=round(speed, 1),
            spin=round(rnd.choice((-1, 1)) * rnd.uniform(5, 26) / (1 + d / 500.0), 2),
            delay=round(d / 900.0 * 2.2, 2),            # frames: the crack front runs outwards
            grow=round(rnd.uniform(0.012, 0.045), 4),   # scale gain per frame
            fall=round(rnd.uniform(0.6, 2.2), 2),       # gravity-ish px/frame^2 downwards
            tilt=round(rnd.uniform(-1, 1), 3)))
    return shards


def extend(E, ctx_py):
    X = E.setdefault("x", {}).setdefault("special", {})
    f0, f1 = RIFT["caption_flip"]
    X["rift"] = dict(RIFT, caption={str(k): v for k, v in
                                    scramble(RIFT["caption_from"], RIFT["caption_to"], f0, f1).items()})
    X["portal"] = dict(PORTAL)
    quads = panel_quads()
    tri = E.get("triptych", {})
    acts = {a["id"]: a for a in E.get("acts", [])}
    panels = []
    for i, p in enumerate(tri.get("panels", [])):
        a = acts.get(p["act"], {})
        panels.append(dict(quad=[list(v) for v in quads[i]["quad"]], cx=quads[i]["cx"], cy=quads[i]["cy"],
                           f=p["f"], clip=p["clip"], file=p["file"], src=list(p["src"]), act=p["act"],
                           earth=a.get("earth", "")))
    # where the head sits in each clip (clip pixels) and how tight the panel crops: measured on the clips
    crop = {"tobey": dict(focus=[1090, 540], scale=92), "andrew": dict(focus=[1010, 540], scale=122),
            "tom": dict(focus=[940, 470], scale=118)}
    for p in panels:
        p.update(crop[p["act"]])
    X["triptych"] = dict(f0=tri.get("f0", 777), f1=tri.get("f1", 819), panels=panels, impact=list(IMPACT),
                         title=tri.get("title", {}), shatter=tri.get("shatter", 819), shards=make_shards(quads),
                         trip=TRIP)
    X["outro"] = dict(E.get("outro", {}))
    X["opts"] = dict(freeze=os.environ.get("SP_FREEZE", "1") != "0")
    X["shatter_still"] = prerender_still(E, ctx_py) if ctx_py.get("prerender", True) else None


HERE = os.path.dirname(os.path.abspath(__file__))
EC = os.environ.get("EFFECTCRAFT_CLI") or "/home/nikhil/code/film-making/bin/artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli"


def prerender_still(E, ctx_py):
    """The shatter cuts one frozen frame of the triptych (36 live precomp re-renders per frame take minutes).
    Renders SP_TRIPTYCH at the shatter frame into <data>/special/ (cached by a hash of what feeds it) and returns the
    path, or None when anything fails (special.jsx then falls back to the live comp)."""
    X = E["x"]["special"]
    f = X["triptych"]["shatter"]
    data = ctx_py.get("data") or os.environ.get("AMV2_DATA") or ""
    out_dir = os.path.join(data, "special")
    if not (data and os.path.isdir(data) and os.access(data, os.W_OK)):     # never invent the shared data tree
        out_dir = os.path.join(ctx_py.get("root") or os.path.abspath(os.path.join(HERE, "..", "..", "..")), "out", "special")
    os.makedirs(out_dir, exist_ok=True)
    jsx = open(os.path.join(HERE, "ec", "special.jsx")).read()
    title_dir = os.path.join(data, "blender", "timeless3d") if data else ""
    title_stamp = ""
    if title_dir and os.path.isdir(title_dir):
        title_stamp = ",".join("%s:%d" % (n, os.path.getsize(os.path.join(title_dir, n))) for n in sorted(os.listdir(title_dir))[:30])
    key = hashlib.sha1((jsx + json.dumps(X["triptych"]["panels"], sort_keys=True, default=str) + title_stamp + str(f)).encode()).hexdigest()[:10]
    still = os.path.join(out_dir, "trip_%d_%s.png" % (f, key))
    if os.path.exists(still):
        return still
    cfg = dict(root=ctx_py.get("root") or "", data=data, src=ctx_py.get("src") or "clips")
    E2 = {"fps": 30, "w": W, "h": H, "dur": E.get("dur", 900), "x": {"special": {"triptych": X["triptych"]}}}
    script = ("var E = %s;\nvar CFG = %s;\n" % (json.dumps(E2, default=str), json.dumps(cfg, default=str)) + jsx + """
var main = app.project.items.addComp("MAIN", 1920, 1080, 1, E.dur / 30, 30);
var ctx = { fps: 30, w: 1920, h: 1080, root: CFG.root, data: CFG.data, src: CFG.src, elements: app.project.items.addFolder("elements"),
            log: function (m) { $.writeln("[special.prerender] " + m); } };
SPECIAL.prerender(main, E, ctx);
app.project.save(new File(OUT_PROJECT));
""")
    tmp = tempfile.mkdtemp(prefix="special_pre_")
    proj = os.path.join(tmp, "trip.ecproj")
    jsx_path = os.path.join(tmp, "trip.jsx")
    open(jsx_path, "w").write("var OUT_PROJECT = %s;\n" % json.dumps(proj) + script)
    try:
        r = subprocess.run([EC, "script", jsx_path, "--empty"], capture_output=True, text=True, timeout=300)
        if r.returncode:
            print("special prerender: script failed", (r.stdout + r.stderr)[-400:])
            return None
        r = subprocess.run([EC, "render-frame", "--project", proj, "--comp", "SP_TRIPTYCH", "--frame", str(f), "--out", still],
                           capture_output=True, text=True, timeout=600)
        if r.returncode or not os.path.exists(still):
            print("special prerender: render failed", (r.stdout + r.stderr)[-400:])
            return None
        return still
    except (OSError, subprocess.SubprocessError) as e:
        print("special prerender:", e)
        return None
