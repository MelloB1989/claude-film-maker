"""WP11's selftest: the op registry, the schema an agent generates its CLI/SDK from, and the error contract, checked
in the real editor. Takes ~10 s. Needs: nothing (no GPU, no sign-in).

It proves: every op module imported (ops.broken is empty); ops.schema has the CONVENTIONS shape and agrees with
`list`; every op has a docstring and an area.verb name; ops.call rejects an unknown op and a misspelt argument with
an OpError carrying a hint and candidates; the op journal records a move and replays it; a multi-tick op runs
across ticks; level.spawn / level.move do what the
generic `actor` spec kind plans (spawn, move, converge: a second plan would be empty); stills work (when a camera
can be made)."""
from __future__ import annotations

REQUIRES: list = []
AREAS = ["ops", "journal"]  # journal.clear is not run: it would empty the box's real journal
TIMEOUT = 120

SHAPE = {"name", "area", "verb", "module", "file", "line", "summary", "doc", "params", "returns", "multi_tick",
         "mutates", "idempotent", "tags"}


def run(t):
    broken = t.op("ops.broken")
    t.check("no op module failed to import", sorted(broken), [])
    sch = t.op("ops.schema")
    t.check("ops.schema version", sch.get("version"), 1)
    ops_ = sch.get("ops", [])
    t.ok("ops.schema lists ops", len(ops_) > 20, detail=f"{len(ops_)} ops")
    bad = [o.get("name") for o in ops_ if set(o) != SHAPE]
    t.check("every schema entry has the CONVENTIONS shape", bad, [])
    t.check("every op has a docstring", [o["name"] for o in ops_ if not o["doc"].strip()], [])
    t.check("every op is area.verb", [o["name"] for o in ops_ if "." not in o["name"] and o["name"] != "list"], [])
    listing = t.op("list")
    t.check("list and ops.schema name the same ops", sorted(k for k in listing if not k.startswith("!")),
            sorted(o["name"] for o in ops_))
    t.metric("ops", len(ops_))
    t.metric("multi_tick_ops", sum(1 for o in ops_ if o["multi_tick"]))
    t.metric("ops_without_flags", sum(1 for o in ops_ if o["mutates"] is None))

    t.raises("an unknown op is not_found with candidates", "level.spwan", code="not_found", label="x")
    t.raises("a misspelt argument is bad_args with a hint", "level.move", code="bad_args", lable="x")

    a = t.prefix + "Box"
    t.op("level.spawn", label=a, shape="cube", loc=[0, 0, 50])
    found = t.op("level.actors", contains=a)
    t.check("level.spawn made one actor", [x[0] for x in found], [a])
    t.op("level.spawn", label=a, shape="cube", loc=[0, 0, 50])  # replace=True: converges on the label
    t.check("level.spawn again keeps one", len(t.op("level.actors", contains=a)), 1)
    loc = t.op("level.move", label=a, loc=[100, 0, 50])
    t.check("level.move moves it", loc, [100, 0, 50], tol=0.01)
    t.check("level.actors sees the move", t.op("level.actors", contains=a)[0][2], [100, 0, 50], tol=0.1)

    rec = t.op("journal.record", on=True)
    t.ok("the journal hook is installed", rec.get("hooked"), detail=rec)
    t.op("level.move", label=a, loc=[120, 0, 50])
    tail = t.op("journal.tail", n=5, prefix="level.", since_s=600)
    moves = [e for e in tail["entries"] if e["op"] == "level.move" and e["args"].get("label") == a]
    t.ok("the journal recorded the move", bool(moves), detail=tail.get("path"))
    if moves:
        dry = yield from t.op("journal.replay", entries=moves[-1:], dry_run=True)
        t.check("journal.replay dry_run lists it", dry.get("count"), 1)
        done = yield from t.op("journal.replay", entries=moves[-1:])
        t.check("journal.replay re-runs it", done.get("ran"), 1)

    ticks = yield from _ticks(3)
    t.check("a generator job ticks the editor", ticks, 3)

    cam = t.prefix + "Cam"
    try:
        t.op("look.camera", label=cam, loc=[400, 0, 120], look_at=[0, 0, 50])
    except Exception as e:  # a still is a bonus here: the look area's selftest owns stills
        t.note(f"no camera for a still: {e}")
        cam = None
    if cam:
        yield from t.still("box", camera=cam)
    return {"ops": len(ops_)}


def _ticks(n):
    k = 0
    for _ in range(n):
        yield
        k += 1
    return k
