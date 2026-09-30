"""Local listening pages for the checkpoints: C1 (voice takes) and C2 (score variants)."""
import argparse
import html
import json
import os
import webbrowser
from pathlib import Path

from .paths import AUDIO, DATA, OUT

STYLE = """
:root { --ink:#110d10; --panel:#1e181c; --rule:#2b2229; --bone:#ede7ea; --dim:#a99fa5; --faint:#6f6469;
        --blood:#c22b45; --moss:#4aad63; }
* { box-sizing: border-box; }
body { margin:0; background:var(--ink); color:var(--bone); font:15px/1.5 ui-sans-serif,system-ui,sans-serif; padding:40px 16px 80px; }
main { max-width:860px; margin:0 auto; }
h1 { font-size:30px; letter-spacing:-.02em; margin:0 0 20px; }
ol { list-style:none; padding:0; margin:0; display:grid; gap:10px; }
li { background:var(--panel); border:1px solid var(--rule); border-radius:14px; padding:14px 16px; }
.id { font:600 12px ui-monospace,Menlo,monospace; color:var(--blood); }
.text { margin:2px 0 8px; }
.take { display:grid; grid-template-columns:190px 1fr; align-items:center; gap:10px; font:12px ui-monospace,Menlo,monospace; color:var(--faint); }
.take.chosen span { color:var(--moss); }
audio { width:100%; height:32px; }
.sec { font:12px ui-monospace,Menlo,monospace; color:var(--dim); }
"""
PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><title>{title}</title><style>{style}</style></head>'
        '<body><main><h1>{title}</h1>{body}</main></body></html>')


def _rel(p: Path, page: Path) -> str:
    return html.escape(os.path.relpath(p.resolve(), page.parent.resolve()))


def vo_page(script: dict, paced_dir: Path, selects: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in script["lines"]:
        chosen = selects.get(line["id"], {}).get("take", 1)
        items = []
        for tj in sorted((paced_dir / line["id"]).glob("*.json"), key=lambda p: int(p.stem)):
            m = json.loads(tj.read_text())
            cls = "take chosen" if m["take"] == chosen else "take"
            label = f'take {m["take"]} · {m["duration"]:.2f}s · ×{m.get("factor", 1.0):.2f}'
            items.append(f'<div class="{cls}"><span>{label}</span>'
                         f'<audio controls preload="none" src="{_rel(tj.with_suffix(".wav"), out)}"></audio></div>')
        rows.append(f'<li><div class="id">{line["id"]}</div><div class="text">{html.escape(line["text"])}</div>'
                    f'{"".join(items)}</li>')
    out.write_text(PAGE.format(title="Voice takes: Jean", style=STYLE, body="<ol>" + "".join(rows) + "</ol>"))
    return out


def music_page(variants: list[Path], out: Path, sections: list[dict] | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    secs = " · ".join(f'{html.escape(s["name"])} {s["start"]:.1f}s' for s in (sections or []))
    rows = [f'<li><div class="id">{html.escape(v.stem)}</div><div class="sec">{secs}</div>'
            f'<audio controls preload="none" src="{_rel(v, out)}"></audio></li>' for v in variants]
    out.write_text(PAGE.format(title="Score variants", style=STYLE, body="<ol>" + "".join(rows) + "</ol>"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build and open a listening page")
    ap.add_argument("what", choices=["vo", "music"])
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    if a.what == "vo":
        from .pace import load_selects
        from .vo import load_script
        page = vo_page(load_script(), AUDIO / "vo" / "paced", load_selects(), OUT / "auditions" / "vo.html")
    else:
        plan = json.loads((DATA / "music_plan.json").read_text()) if (DATA / "music_plan.json").exists() else {}
        page = music_page(sorted((AUDIO / "music").glob("*.wav")), OUT / "auditions" / "music.html",
                          plan.get("meta", {}).get("sections"))
    print(page)
    if not a.no_open:
        webbrowser.open(page.as_uri())
