# DAY1-REPORT: the Unreal helpers on a real GPU box

Box: i-0f7a6ac044b75e922 (g6.4xlarge, 1x L4 24 GB, Ubuntu 22.04, ap-south-1b), UE 5.8.4 source build, project
HostStudio, from `main` 31c57577. Runs: `film-ue selftest` in the planned order (`film-ue selftest plan`), then the
demo (examples/unreal/demo). Fixes go to `fleet/agent-13/day1-<area>` off main, merged by agent-10.

Live table (newest result per area; times are wall clock on the box):

| # | area | result | time | failures | fix (branch / commit) | rerun | stills |
|---|---|---|---|---|---|---|---|
| 0 | first-run (agent-07) | pending | | | | | |
| 1 | platform | pending | | | | | |
| 2 | dx | pending | | | | | |
| 3 | assets | pending | | | | | |
| 4 | layout | pending | | | | | |
| 5 | mh | pending | | | | | |
| 6 | anim | pending | | | | | |
| 7 | seq | pending | | | | | |
| 8 | cam | pending | | | | | |
| 9 | render | pending | | | | | |
| 10 | qa | pending | | | | | |
| 11 | audio | pending | | | | | |
| 12 | env | pending | | | | | |
| 13 | foliage | pending | | | | | |
| 14 | pose | pending | | | | | |
| 15 | wp | pending | | | | | |
| D | demo | pending | | | | | |

## Log

(each run: when, what, the report folder, what was learned)
