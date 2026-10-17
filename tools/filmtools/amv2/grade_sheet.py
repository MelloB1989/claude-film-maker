"""Before/after contact sheet for the GRADE library.

    python grade_sheet.py [--out DIR] [--scale 0.25] [--frames mid|first]

Builds the test MAIN (test_grade.py: clips as plain layers) twice (plain and graded), with the three triptych panels appended
as extra shots at their EDL frames, renders one frame per shot (32 + 3) and writes into DIR:
    contact_all.png, contact_<act>.png   plain | graded pairs with the measured stats under each pair
    grade_stats.json / grade_stats.md    luma p1/p50/p99, clipped %, mean saturation, skin hue per shot, before and after
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_grade as tg  # noqa: E402
import grade_measure as gm  # noqa: E402
import grade_spec  # noqa: E402

ACT_NOTES = {
    "tobey": "Tobey, nostalgia: warm gold highlights (wheel + Color Balance), a faint teal in the shadows, vibrance and a "
             "soft, high-threshold bloom (halation only on real highlights). Contrast stays gentle so the quiet intro breathes.",
    "andrew": "Andrew, electric: cooler cyan/blue mids and shadows, amber kept in the warm highlights and yellows for the sunset "
              "accents, more contrast and a tighter, cyan-leaning bloom. Crisper than Tobey.",
    "tom": "Tom, impact: rich red/orange against steel-blue shadows, the most contrast, reds pushed in Hue/Saturation, blues pulled "
           "back a little so skin and suit stay hot, a hard highlight shoulder and the smallest bloom.",
}


def act_of(E, f):
    for a in E["acts"]:
        if a["f0"] <= f < a["f1"]:
            return a["id"]
    return "tom"


def sheet_edl():
    E = tg.load_edl()
    grade_spec.extend(E, {})
    pan = E["triptych"]["panels"]
    ends = [pan[1]["f"], pan[2]["f"], E["triptych"]["f1"]]
    for i, p in enumerate(pan):
        E["shots"].append({"id": "P%d" % i, "clip": p["clip"], "file": p["file"], "a": p["f"], "b": ends[i], "src": p["src"], "act": "tom"})
        E["x"]["grade"]["shots"]["P%d" % i] = E["x"]["grade"]["panels"][str(i)]
    return E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tg.ROOT, "out/timeless/amv2/grade"))
    ap.add_argument("--scale", type=float, default=0.25)
    ap.add_argument("--frame", default="mid", choices=["mid", "first"])
    a = ap.parse_args()
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    E = sheet_edl()
    os.makedirs(a.out, exist_ok=True)
    projs = {}
    for tag, with_grade in (("plain", False), ("graded", True)):
        js = tg.make_script(E, with_grade) + "\napp.project.save(new File(%s));\n" % json.dumps(os.path.join(a.out, tag + ".ecproj"))
        p = os.path.join(a.out, tag + ".jsx")
        open(p, "w").write(js)
        r = tg.subprocess.run([tg.EC, "script", p, "--empty"], capture_output=True, text=True)
        sys.stdout.write((r.stdout + r.stderr)[-1500:])
        projs[tag] = os.path.join(a.out, tag + ".ecproj")
    rows = []
    for S in E["shots"]:
        f = (S["a"] + S["b"]) // 2 if a.frame == "mid" else S["a"] + 1
        imgs = {}
        for tag in ("plain", "graded"):
            o = os.path.join(a.out, "cell_%s_%s.png" % (S["id"], tag))
            tg.subprocess.run([tg.EC, "render-frame", "--project", projs[tag], "--comp", "MAIN", "--frame", str(f), "--scale",
                               str(a.scale), "--out", o], check=True, capture_output=True)
            imgs[tag] = Image.open(o).convert("RGB")
        st = {t: gm.stats([np.asarray(im)]) for t, im in imgs.items()}
        rows.append({"id": S["id"], "clip": S["clip"], "frame": f, "act": act_of(E, f), "plain": st["plain"], "graded": st["graded"]})
        rows[-1]["_img"] = imgs
    # stats files
    clean = [{k: v for k, v in r.items() if k != "_img"} for r in rows]
    json.dump(clean, open(os.path.join(a.out, "grade_stats.json"), "w"), indent=1)
    md = ["| shot | clip | frame | luma p1 / p50 / p99 (before) | clipped % | sat | luma p1 / p50 / p99 (after) | clipped % | sat | skin hue |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        p, g = r["plain"], r["graded"]
        md.append("| %s | %s | %d | %.3f / %.3f / %.3f | %.2f | %.2f | %.3f / %.3f / %.3f | %.2f | %.2f | %s |" % (
            r["id"], r["clip"], r["frame"], p["p1"], p["p50"], p["p99"], p["clip"], p["sat"], g["p1"], g["p50"], g["p99"], g["clip"],
            g["sat"], "-" if g["skin_hue"] is None else "%.0f" % g["skin_hue"]))
    open(os.path.join(a.out, "grade_stats.md"), "w").write("\n".join(md) + "\n")
    # contact sheets
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
        big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = big = ImageFont.load_default()
    cw, ch = rows[0]["_img"]["plain"].size
    cols, lab = 2, 46

    def draw(rs, name, title):
        n = len(rs)
        rws = (n + cols - 1) // cols
        W, H = cols * (2 * cw + 8) + 8, rws * (ch + lab) + 34
        im = Image.new("RGB", (W, H), (18, 18, 20))
        d = ImageDraw.Draw(im)
        d.text((8, 8), title, fill=(235, 235, 235), font=big)
        for i, r in enumerate(rs):
            x, y = 8 + (i % cols) * (2 * cw + 8), 34 + (i // cols) * (ch + lab)
            im.paste(r["_img"]["plain"], (x, y))
            im.paste(r["_img"]["graded"], (x + cw, y))
            p, g = r["plain"], r["graded"]
            d.text((x + 2, y + ch + 2), "%s %s f%d" % (r["id"], r["clip"], r["frame"]), fill=(255, 255, 255), font=font)
            d.text((x + 2, y + ch + 16), "before p1 %.3f p50 %.3f p99 %.3f clip %.1f%% sat %.2f" % (p["p1"], p["p50"], p["p99"], p["clip"], p["sat"]),
                   fill=(170, 170, 170), font=font)
            d.text((x + 2, y + ch + 30), "after  p1 %.3f p50 %.3f p99 %.3f clip %.1f%% sat %.2f skin %s" % (
                g["p1"], g["p50"], g["p99"], g["clip"], g["sat"], "-" if g["skin_hue"] is None else "%.0f" % g["skin_hue"]),
                   fill=(130, 230, 150), font=font)
        im.save(os.path.join(a.out, name))

    draw(rows, "contact_all.png", "GRADE before (left) / after (right), one frame per shot")
    for act in ("tobey", "andrew", "tom"):
        draw([r for r in rows if r["act"] == act], "contact_%s.png" % act, "%s" % ACT_NOTES[act][:150])
    json.dump(ACT_NOTES, open(os.path.join(a.out, "act_notes.json"), "w"), indent=1)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
