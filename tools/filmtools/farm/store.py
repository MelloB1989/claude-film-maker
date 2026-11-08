"""The farm's one shared place: an S3 bucket, used through conditional writes so two workers can never both win.

    put(key, body, if_none_match=True)   create only if absent (claim a lease, write done.json once)
    put(key, body, if_match=etag)        replace only if unchanged since read (heartbeat, steal an expired lease)

Both fail with PreconditionFailed when another writer got there first. S3 has had both since 2024 (PutObject
If-None-Match / If-Match), so no SQS or DynamoDB is needed and the box role's s3:PutObject is enough.

AwsStore runs the aws CLI (on kali with a profile, on a worker with the box role); MemStore is the same thing in
memory for the tests. Python 3.10, stdlib only: it runs on the workers.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading


class PreconditionFailed(Exception):
    """Another writer changed (or created) the object first."""


class StoreError(RuntimeError):
    pass


class Store:
    bucket = ""

    def get(self, key: str):
        """(bytes, etag), or None if there is no such object."""
        raise NotImplementedError

    def put(self, key: str, body: bytes, *, if_none_match: bool = False, if_match: str | None = None,
            sse_kms: bool = False, metadata: dict | None = None) -> str:
        """Write an object; returns its new etag. PreconditionFailed if the condition does not hold."""
        raise NotImplementedError

    def list(self, prefix: str) -> list[dict]:
        """[{"key", "size", "etag"}] under prefix (every page)."""
        raise NotImplementedError

    def upload(self, key: str, path: str, *, sse_kms: bool = False, metadata: dict | None = None) -> None:
        with open(path, "rb") as f:
            self.put(key, f.read(), sse_kms=sse_kms, metadata=metadata)

    def download(self, key: str, path: str) -> None:
        got = self.get(key)
        if got is None:
            raise StoreError(f"no object {key}")
        with open(path, "wb") as f:
            f.write(got[0])

    # JSON helpers ---------------------------------------------------------------------------------------------------
    def get_json(self, key: str):
        """(doc, etag) or (None, None)."""
        got = self.get(key)
        if got is None:
            return None, None
        return json.loads(got[0].decode()), got[1]

    def put_json(self, key: str, doc, **kw) -> str:
        return self.put(key, (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode(), **kw)


class MemStore(Store):
    """An in-memory bucket with S3's conditional-write rules (for the tests, and for a dry run)."""

    def __init__(self, bucket: str = "test-bucket"):
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str, dict]] = {}
        self._n = 0
        self._lock = threading.Lock()

    def get(self, key):
        o = self.objects.get(key)
        return (o[0], o[1]) if o else None

    def put(self, key, body, *, if_none_match=False, if_match=None, sse_kms=False, metadata=None):
        with self._lock:
            cur = self.objects.get(key)
            if if_none_match and cur is not None:
                raise PreconditionFailed(key)
            if if_match is not None and (cur is None or cur[1] != if_match):
                raise PreconditionFailed(key)
            self._n += 1
            etag = f'"e{self._n}"'
            self.objects[key] = (bytes(body), etag, {"sse_kms": sse_kms, **(metadata or {})})
            return etag

    def list(self, prefix):
        return [{"key": k, "size": len(v[0]), "etag": v[1]} for k, v in sorted(self.objects.items())
                if k.startswith(prefix)]

    def meta(self, key) -> dict:
        return self.objects[key][2]


def _clean_env(profile: str) -> dict:
    """With a profile, ambient key variables must not override it (they point at another identity on kali)."""
    env = dict(os.environ)
    if profile:
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            env.pop(k, None)
        env["AWS_PROFILE"] = profile
    return env


class AwsStore(Store):
    """The aws CLI against one bucket. `profile` on kali (nani); empty on a worker (the instance role)."""

    def __init__(self, bucket: str, region: str, profile: str = "", run=subprocess.run):
        self.bucket, self.region, self.profile, self._run = bucket, region, profile, run

    def _aws(self, *args: str, check: bool = True):
        cmd = ["aws", "--region", self.region, "--output", "json", *args]
        r = self._run(cmd, capture_output=True, text=True, env=_clean_env(self.profile))
        if r.returncode != 0 and check:
            err = (r.stderr or "").strip()
            if "PreconditionFailed" in err or "(412)" in err or "ConditionalRequestConflict" in err or "(409)" in err:
                raise PreconditionFailed(err[-300:])
            raise StoreError(f"aws {' '.join(args[:2])}: {err[-500:]}")
        return r

    def get(self, key):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o")
            r = self._aws("s3api", "get-object", "--bucket", self.bucket, "--key", key, p, check=False)
            if r.returncode != 0:
                if "NoSuchKey" in r.stderr or "(404)" in r.stderr or "Not Found" in r.stderr:
                    return None
                raise StoreError(f"get {key}: {r.stderr.strip()[-500:]}")
            with open(p, "rb") as f:
                return f.read(), json.loads(r.stdout).get("ETag", "")

    def put(self, key, body, *, if_none_match=False, if_match=None, sse_kms=False, metadata=None):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o")
            with open(p, "wb") as f:
                f.write(body)
            return self._put_file(key, p, if_none_match=if_none_match, if_match=if_match, sse_kms=sse_kms,
                                  metadata=metadata)

    def _put_file(self, key, path, *, if_none_match=False, if_match=None, sse_kms=False, metadata=None):
        a = ["s3api", "put-object", "--bucket", self.bucket, "--key", key, "--body", path]
        if if_none_match:
            a += ["--if-none-match", "*"]
        if if_match is not None:
            a += ["--if-match", if_match]
        if sse_kms:
            a += ["--server-side-encryption", "aws:kms"]
        if metadata:
            a += ["--metadata", json.dumps({k: str(v) for k, v in metadata.items()})]
        return json.loads(self._aws(*a).stdout or "{}").get("ETag", "")

    def upload(self, key, path, *, sse_kms=False, metadata=None):
        if os.path.getsize(path) < 4_500_000_000:  # put-object's own limit is 5 GB
            self._put_file(key, path, sse_kms=sse_kms, metadata=metadata)
            return
        a = ["s3", "cp", "--only-show-errors", "--no-progress", path, f"s3://{self.bucket}/{key}"]
        if sse_kms:
            a += ["--sse", "aws:kms"]
        self._aws(*a)

    def download(self, key, path):
        self._aws("s3", "cp", "--only-show-errors", "--no-progress", f"s3://{self.bucket}/{key}", path)

    def list(self, prefix):
        out, token = [], None
        while True:
            a = ["s3api", "list-objects-v2", "--bucket", self.bucket, "--prefix", prefix, "--max-items", "100000"]
            if token:
                a += ["--starting-token", token]
            doc = json.loads(self._aws(*a).stdout or "{}")
            out += [{"key": o["Key"], "size": o["Size"], "etag": o.get("ETag", "")} for o in doc.get("Contents") or []]
            token = doc.get("NextToken")
            if not token:
                return out
