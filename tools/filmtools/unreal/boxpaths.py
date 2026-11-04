"""Paths on the box (the machine running the editor), Windows or Linux, in one place (BACKLOG B42). Client code asks
for a named location instead of joining strings, so a path is right on both platforms:

    from filmtools.unreal.boxpaths import BoxPaths
    bp = BoxPaths.current()                 # from film-ue's settings (os, project_dir)
    bp.renders("SQ_Main")                   # /srv/ue/projects/X/Saved/Renders/SQ_Main  or  C:\\UEProjects\\X\\Saved\\Renders\\SQ_Main
    bp.scratch("audio", "L1.wav")           # <project>/Saved/audio/L1.wav
    BoxPaths("windows", r"C:\\UEProjects\\X").token()

Pure: a BoxPaths is (os, project_dir); nothing here reads settings except `current()`. The layout matches what the
bridge uses inside the editor (unreal.Paths.project_saved_dir(), Saved/fmbridge.token, Saved/Bridge/in|out) and what
`film-ue install` writes (Content/Python).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath, PureWindowsPath

OSES = ("linux", "windows")


@dataclass(frozen=True)
class BoxPaths:
    os: str
    project_dir: str

    def __post_init__(self):
        if self.os not in OSES:
            raise ValueError(f"box os {self.os!r} is not one of {', '.join(OSES)}")

    # --- the box's path style -----------------------------------------------------------------------------------
    @property
    def _cls(self) -> type[PurePath]:
        return PurePosixPath if self.os == "linux" else PureWindowsPath

    def join(self, *parts: str) -> str:
        """Parts joined in the box's style (a part may itself hold either separator)."""
        return str(self._cls(*[str(p).replace("\\", "/") if self.os == "linux" else str(p) for p in parts]))

    def basename(self, path: str) -> str:
        return self._cls(path).name

    def parent(self, path: str) -> str:
        return str(self._cls(path).parent)

    def is_abs(self, path: str) -> bool:
        return self._cls(path).is_absolute()

    def name(self) -> str:
        """The project's name (its folder's)."""
        return self.basename(self._project())

    # --- named locations -----------------------------------------------------------------------------------------
    def _project(self) -> str:
        if not self.project_dir:
            raise SystemExit("no project dir set: film-ue set --project-dir /srv/ue/projects/<Name> "
                             "(or C:\\UEProjects\\<Name> on Windows)")
        return self.project_dir

    def project(self, *parts: str) -> str:
        """Inside the project: project("Config", "DefaultEngine.ini")."""
        return self.join(self._project(), *parts)

    def uproject(self) -> str:
        return self.project(f"{self.name()}.uproject")

    def content_python(self, *parts: str) -> str:
        """Where `film-ue install` puts the bridge (Content/Python)."""
        return self.project("Content", "Python", *parts)

    def saved(self, *parts: str) -> str:
        return self.project("Saved", *parts)

    def logs(self, *parts: str) -> str:
        return self.saved("Logs", *parts)

    def token(self) -> str:
        """The bridge's token file (fmbridge.server writes it at start)."""
        return self.saved("fmbridge.token")

    def bridge_in(self, *parts: str) -> str:
        """The inbox transport's drop folder (fmbridge.inbox)."""
        return self.saved("Bridge", "in", *parts)

    def bridge_out(self, *parts: str) -> str:
        return self.saved("Bridge", "out", *parts)

    def renders(self, *parts: str) -> str:
        """Render output: Saved/Renders/<job>/..."""
        return self.saved("Renders", *parts)

    def stills(self, *parts: str) -> str:
        return self.saved("Stills", *parts)

    def scratch(self, area: str, *parts: str) -> str:
        """An area's own working folder on the box: Saved/<area>/... (audio, PoC, ...)."""
        return self.saved(area, *parts)

    def selftest(self, area: str, *parts: str) -> str:
        """A selftest's files: Saved/Selftest/<area>/..."""
        return self.saved("Selftest", area, *parts)

    def audio(self, *parts: str) -> str:
        """WAVs pushed for the audio ops (audio.import / audio.lines / speech.to_face): Saved/Audio/..."""
        return self.saved("Audio", *parts)

    def ddc(self, *parts: str) -> str:
        return self.project("DerivedDataCache", *parts)

    def to_dict(self) -> dict:
        """Every named location, for `film-ue describe`-style output and for checking a box's layout."""
        return {"os": self.os, "project": self.project(), "uproject": self.uproject(), "saved": self.saved(),
                "logs": self.logs(), "token": self.token(), "bridge_in": self.bridge_in(),
                "bridge_out": self.bridge_out(), "renders": self.renders(), "stills": self.stills(),
                "selftest": self.saved("Selftest"), "audio": self.audio(), "content_python": self.content_python(),
                "ddc": self.ddc()}

    @classmethod
    def current(cls) -> "BoxPaths":
        """From film-ue's settings: the box's os ("windows" unless set) and project_dir."""
        from . import workstation as ws
        c = ws.conf()
        return cls("linux" if ws.linux() else "windows", c.get("project_dir") or "")
