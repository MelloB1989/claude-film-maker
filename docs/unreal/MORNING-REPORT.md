# ue-helpers: morning report (draft, the lead updates it through the night)

Branch: `ue-helpers`. Start from [CONVENTIONS.md](CONVENTIONS.md), [DECISIONS.md](DECISIONS.md) and
[BACKLOG.md](BACKLOG.md).

## Status by work package

| WP | owner | branch | merged | state |
|---|---|---|---|---|
| WP0 lead | agent-10 | ue-helpers | yes | runtime (auto-discovery, ops.schema, OpError), fakeunreal, conventions |
| WP1 platform | agent-07 | ue-platform | f6ddfe4 | job registry, transport, editor/bridge/jobs ops; box lifecycle in progress |
| WP2 assets | agent-02 | ue-assets | no | in progress |
| WP3 MetaHuman | agent-04 | ue-metahuman | no | in progress |
| WP4 animation | agent-01 | ue-anim | no | in progress |
| WP5 look | agent-08 | none | no | no branch yet (asked 21:22 UTC) |
| WP6 layout | agent-10 (agent-12 stopped) | ue-layout | yes | level.*, layout.*, scene spec, selftest, docs |
| WP7 cameras | agent-11 | ue-cameras | e7f3d29 | cam.*, shot.*, camkit |
| WP8 Sequencer | agent-06 | ue-sequencer | no | in progress |
| WP9 render | agent-05 | ue-render | no | in progress |
| WP10 QA | agent-09 | ue-qa | 7ae757a | view.*, qa.* |
| WP11 DX | agent-13 | ue-dx | no | in progress |
| WP12 audio/post | agent-03 | ue-post | 035c086 | audio.*, film-post, selftest, docs |

## Tests

`cd tools && python -m pytest -q tests/test_ue_*.py tests/test_unreal_*.py tests/test_fmbridge_jobs.py`

## GPU-box selftest plan

The plan is filled in as the selftests land. The order is foundations first, so a failure early on explains the
failures after it.

## Risks and open decisions for the operator

The lead fills these in from the night's DECISIONS.
