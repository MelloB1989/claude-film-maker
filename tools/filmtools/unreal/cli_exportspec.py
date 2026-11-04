"""film-ue export-spec: the live state of materials or assets as spec documents (WP2), the round trip of
`film-ue apply`: capture what is in the project, edit it, apply it elsewhere.

    film-ue export-spec material /Game/Set/Mats/MI_Rock /Game/Set/Mats/MI_Oak > mats.yaml
    film-ue export-spec asset /Game/Set/Props/SM_Chair --json
"""
from __future__ import annotations

import json
import sys

NAMES = ("export-spec",)


def register(sub) -> None:
    p = sub.add_parser("export-spec", help="write material/asset spec documents from what is in the project")
    p.add_argument("what", choices=["material", "asset"])
    p.add_argument("paths", nargs="+", help="content paths")
    p.add_argument("--json", action="store_true", help="a JSON list instead of YAML documents")


def export(what: str, paths: list, ue=None) -> list:
    from . import assets_kinds as K
    if ue is None:
        from .sdk import Unreal
        ue = Unreal()
    docs = []
    for p in paths:
        if what == "material":
            docs.append(K.material_spec(ue.mat.describe(path=p)))
        else:
            docs.append(K.asset_spec(ue.assets.describe(path=p, refs=False)))
    return docs


def dispatch(a) -> bool:
    if a.cmd not in NAMES:
        return False
    docs = export(a.what, a.paths)
    if a.json:
        print(json.dumps(docs, indent=1))
    else:
        import yaml
        print("---\n".join(yaml.safe_dump(d, sort_keys=False) for d in docs), end="")
    sys.stdout.flush()
    raise SystemExit(0)
