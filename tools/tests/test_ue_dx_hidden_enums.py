"""Live-only enum names, held: every TraceTypeQueryN / ObjectTypeQueryN is UMETA(Hidden) in C++ (EngineTypes.h:1276),
so Python exports them only as deprecated aliases of the names the collision profile gives them at editor start
(ECC_<channel>, CollisionProfile.cpp:499-512). The fake accepts the old names, so only this test sees a new use.
Use fmbridge.ops._util.visibility_channel() (B57)."""
import ast
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2] / "unreal" / "fmbridge"
HELPER = "ops/_util.py"                      # the one place allowed to name the fallback
PENDING = {"ops/qa.py"}                      # agent-09's switch (ca9b8e0) not merged yet: delete once it is


def uses() -> dict:
    out: dict = {}
    for p in sorted(BRIDGE.rglob("*.py")):
        rel = p.relative_to(BRIDGE).as_posix()
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute) and n.attr.startswith(("TRACE_TYPE_QUERY", "OBJECT_TYPE_QUERY")):
                out.setdefault(rel, []).append(n.lineno)
    return out


def test_no_hidden_trace_or_object_type_names():
    bad = {f: lines for f, lines in uses().items() if f != HELPER and f not in PENDING}
    assert not bad, (f"hidden-enum channel names used directly (live they are deprecated aliases): {bad}; "
                     "use fmbridge.ops._util.visibility_channel()")
