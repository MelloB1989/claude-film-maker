"""The film option every CLI shares.

`--film <id>` (or `--film=<id>`) may stand anywhere on the command line, before or after a subcommand. It is taken
out before the tool's own parser runs, and selects the film (paths.use_film). Without it the film already selected
in this process stands (a test's), else $FILM, else the default film.
"""
from __future__ import annotations

import argparse
import sys

from . import paths

FILM_HELP = f"the film to work on, films/<id>/ (default: $FILM, else {paths.DEFAULT_FILM})"


def take_film(argv: list[str]) -> tuple[str | None, list[str]]:
    """(the --film value or None, argv without it). The last --film wins."""
    film, rest, i = None, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--film":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise SystemExit("--film needs a film id")
            film, i = argv[i + 1], i + 2
            continue
        if a.startswith("--film="):
            film = a.split("=", 1)[1]
            if not film:
                raise SystemExit("--film needs a film id")
        else:
            rest.append(a)
        i += 1
    return film, rest


def film_argv(argv: list[str] | None = None) -> list[str]:
    """Select the film named by --film in `argv` (default sys.argv[1:]) and return the remaining arguments."""
    film, rest = take_film(list(sys.argv[1:] if argv is None else argv))
    if "-h" in rest or "--help" in rest:
        return rest  # help needs no film
    if film is not None:
        paths.use_film(film)
    else:
        paths.current()  # resolve $FILM / the default now, so a missing film fails before any work
    return rest


def parser(description: str | None = None, **kw) -> argparse.ArgumentParser:
    """An ArgumentParser that lists --film in its help (the option itself is consumed by film_argv)."""
    ap = argparse.ArgumentParser(description=description, **kw)
    ap.add_argument("--film", metavar="ID", help=FILM_HELP)
    return ap


def parse(ap: argparse.ArgumentParser, argv: list[str] | None = None) -> argparse.Namespace:
    """Select the film, then parse the rest with `ap`."""
    return ap.parse_args(film_argv(argv))
