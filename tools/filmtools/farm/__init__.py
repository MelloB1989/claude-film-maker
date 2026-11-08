"""film-farm: Blender and Unreal (MRQ) renders across several GPU boxes, from a queue in S3 (docs/FARM.md).

model (jobs, chunks, pre-roll), store (S3 with conditional writes), queue (leases, heartbeats, requeue), worker (the
box side), engines/ (blender, ue), verify (frames once each, hashes, continuity, assemble), provision (EC2: quotas,
spot-first launch, tags, teardown, cost), cli (film-farm). Everything a worker imports is stdlib-only Python 3.10.
"""
