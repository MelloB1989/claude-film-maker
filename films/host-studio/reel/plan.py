"""Rewrite PLAN.md's shot list (between its shots markers) from shots.py.

    python films/host-studio/reel/plan.py
"""
from __future__ import annotations

import re
from pathlib import Path

import shots as S

PLAN = Path(__file__).with_name("PLAN.md")


def tc(f: int) -> str:
    return f"{f // 24 // 60}:{f // 24 % 60:02d}.{f % 24:02d}"


def shot_md(s: S.Shot) -> str:
    r = lambda v: [round(x, 1) for x in v]  # noqa: E731
    out = [f"### {s.id} · {s.title} — {tc(s.start)}–{tc(s.end)} (bars {s.start // S.BAR + 1}–{s.end // S.BAR}, "
           f"f{s.start}–{s.end - 1}, {s.frames / 24:.1f} s)", "",
           f"- **Camera:** {s.lens:g} mm full frame, T{s.stop:g}. {s.move[0].upper() + s.move[1:]}. "
           f"From `{r(s.keys[0][1])}` → `{r(s.keys[-1][1])}`, aimed at `{r(s.keys[-1][2])}`."]
    if s.focus:
        out.append("- **Focus pull:** " + ", ".join(f"+{f} f: {d} cm" for f, d in s.focus) + ".")
    out.append(f"- **In frame:** {s.frame}.")
    out.append(f"- **Light:** {s.light}.")
    if s.action:
        out.append(f"- **Action:** {s.action}.")
    out.append(f"- **Sound:** {s.sound}.")
    pv = f" **Previs:** [`previs/{s.id}.png`](previs/{s.id}.png)." if s.previs is not None else ""
    out.append(f"- **Into the next:** {s.into}. **9:16:** crop centred at {round(s.vcrop * 100)}% of the width.{pv}")
    return "\n".join(out) + "\n"


def main() -> None:
    body = "\n".join(shot_md(s) for s in S.SHOTS)
    text = PLAN.read_text()
    text = re.sub(r"(<!-- shots:begin -->\n).*?(<!-- shots:end -->)", lambda m: m[1] + "\n" + body + "\n" + m[2],
                  text, flags=re.S)
    PLAN.write_text(text)


if __name__ == "__main__":
    main()
