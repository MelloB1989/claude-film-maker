"""film-anime-fetch: a generated picture or clip, fetched into the film's folder with its provenance.

Generations run outside the repo (a generation service's tools hand back a job id and a result URL). This fetches
the result to films/<id>/assets/gen/<name>.<ext> and records how it was made in films/<id>/data/gen.json, keyed by
name: the job id, the model, the prompt, the references it was made from (other names, or job ids), its cost and
when it was fetched. A name is fetched again only with --force (a re-roll keeps the old one as <name>.v<N>.<ext>).

    uv run film-anime-fetch --film <id> --name key-ferry --url <result url> --job <job id> --model gpt_image_2_5 \\
        --prompt-file prompt.txt --refs sheet-shinza,sheet-tsuru --credits 1

`film-anime-fetch --film <id> --list` prints what the film has, and what it cost in all.
"""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
from pathlib import Path

from .. import cli, paths

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def gen_dir() -> Path:
    return paths.current().dir / "assets" / "gen"


def manifest_path() -> Path:
    return paths.current().data / "gen.json"


def load_manifest() -> dict:
    p = manifest_path()
    return json.loads(p.read_text()) if p.is_file() else {}


def save_manifest(m: dict) -> None:
    p = manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(m.items())), indent=2, ensure_ascii=False) + "\n")


def ext_of(url: str) -> str:
    e = Path(url.split("?", 1)[0]).suffix.lower()
    if e not in EXTS:
        raise SystemExit(f"the result {url} is not a picture or clip this pipeline takes ({', '.join(sorted(EXTS))})")
    return ".jpg" if e == ".jpeg" else e


def asset_path(name: str) -> Path:
    """The fetched file for `name` (whatever its extension); a SystemExit when the film has none."""
    m = load_manifest()
    if name not in m:
        raise SystemExit(f"no generated asset {name!r} in {manifest_path()} (film-anime-fetch --list)")
    return paths.current().dir / m[name]["file"]


def fetch(name: str, url: str, *, job: str | None = None, model: str | None = None, prompt: str | None = None,
          refs: list[str] | None = None, credits: float | None = None, force: bool = False, note: str | None = None) -> Path:
    """Download `url` as asset `name` and record it. An existing name is kept unless `force` (then it is renamed
    <name>.v<N> and the manifest keeps its record under that name)."""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise SystemExit(f"an asset name is letters, digits, '-' and '_', got {name!r}")
    m = load_manifest()
    d = gen_dir()
    d.mkdir(parents=True, exist_ok=True)
    if name in m:
        if not force:
            raise SystemExit(f"{name!r} is already fetched ({m[name]['file']}); --force keeps it as a version and fetches again")
        old = paths.current().dir / m[name]["file"]
        n = 1
        while f"{name}.v{n}" in m:
            n += 1
        if old.is_file():
            kept = old.with_name(f"{name}.v{n}{old.suffix}")
            shutil.move(old, kept)
            m[f"{name}.v{n}"] = {**m[name], "file": paths.current().rel(kept)}
    dest = d / f"{name}{ext_of(url)}"
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)
    m[name] = {k: v for k, v in {
        "file": paths.current().rel(dest), "job": job, "model": model, "prompt": prompt, "refs": refs or [],
        "credits": credits, "url": url, "note": note, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }.items() if v is not None}
    save_manifest(m)
    return dest


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Fetch a generated picture or clip into the film, with its provenance.")
    ap.add_argument("--name", help="the asset's name (assets/gen/<name>.<ext>)")
    ap.add_argument("--url", help="the result URL")
    ap.add_argument("--job", help="the generation's job id")
    ap.add_argument("--model")
    ap.add_argument("--prompt", help="the prompt (or --prompt-file)")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--refs", default="", help="comma list of the assets or job ids it was made from")
    ap.add_argument("--credits", type=float)
    ap.add_argument("--note")
    ap.add_argument("--force", action="store_true", help="fetch a name again, keeping the old one as a version")
    ap.add_argument("--list", action="store_true", help="list the film's generated assets and their cost")
    a = cli.parse(ap, argv)
    if a.list:
        m = load_manifest()
        total = 0.0
        for k, v in m.items():
            total += v.get("credits") or 0
            print(f"{k:<28} {v.get('model', '?'):<18} {v.get('credits', '?'):>6}  {v['file']}")
        print(f"{len(m)} assets, {total:g} credits")
        return
    if not (a.name and a.url):
        raise SystemExit("--name and --url are required (or --list)")
    prompt = a.prompt_file.read_text().strip() if a.prompt_file else a.prompt
    refs = [r for r in a.refs.split(",") if r]
    p = fetch(a.name, a.url, job=a.job, model=a.model, prompt=prompt, refs=refs, credits=a.credits, force=a.force, note=a.note)
    print(p)
