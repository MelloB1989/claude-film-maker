"""How film-ue reaches a box: one interface, three ways, for Windows or Linux boxes alike.

    t = transport.get()                 # from the current box's settings (workstation.conf())
    t.run("ls /srv", timeout=60)        # the box's own shell: bash on Linux (as the editor's user, or root=True),
                                        # PowerShell on Windows
    t.put("/srv/x/a.txt", b"...")       # a small file (big folders: push_dir / pull_dir)
    t.get("/srv/x/a.txt") -> bytes|None
    t.forward(18765, 18766)             # a local port to the box's 127.0.0.1:18765 (the bridge), a Popen or None
    t.push_dir(local, remote) / t.pull_dir(remote, local)

  ssm    AWS Systems Manager: commands with AWS-RunShellScript / AWS-RunPowerShellScript, the bridge through an SSM
         port-forward (Session Manager plugin), folders through the box's S3 bucket. No inbound port on the box.
  ssh    OpenSSH to a box someone else owns (a fleet EC2 box, a machine on the LAN): bash with sudo, or PowerShell on
         Windows' OpenSSH server; the bridge through ssh -L; folders by rsync (Linux) or scp (Windows).
  local  The editor runs on this machine: commands in a local shell, files and folders copied directly, the bridge on
         its own port (no forward).

A transport never decides what to run; it only runs it, and every failure is a SystemExit with the box's own error
text (the CLI prints it as is). The AWS calls go through `aws_cli` / `ssm_cmd`, which tests replace with fakes."""
from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

KINDS = ("ssm", "ssh", "local")


class Transport:
    kind = ""

    def __init__(self, conf: dict):
        self.conf = conf
        self.os = conf.get("os", "windows")

    # --------------------------------------------------------------------------------------------- the interface
    def run(self, script: str, timeout: int = 600, root: bool = False) -> str:
        raise NotImplementedError

    def forward(self, remote_port: int, local_port: int, log_path: Path | None = None):
        raise NotImplementedError

    def push_dir(self, local_dir: str, remote_dir: str) -> int:
        raise NotImplementedError

    def pull_dir(self, remote_dir: str, local_dir: str) -> int:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"transport": self.kind, "os": self.os}

    # --------------------------------------------------------------------------------- shared on top of run()
    @property
    def linux(self) -> bool:
        return self.os == "linux"

    def path(self, *parts: str) -> str:
        """A path on the box, joined in its own style (boxpaths.BoxPaths.join)."""
        from .boxpaths import BoxPaths
        return BoxPaths("linux" if self.linux else "windows", "").join(*parts)

    def as_user(self, script: str) -> str:
        """A bash script run as the editor's user (files it writes belong to the editor) instead of root."""
        return f"runuser -u {shlex.quote(self.conf.get('user') or 'ubuntu')} -- bash -c {shlex.quote(script)}"

    PART = 60_000  # base64 characters per command: SSM caps a command near 100 KB
    GET_PART = 15_000  # bytes per command on the way back (20,000 base64 characters: SSM keeps 24,000 of an output)

    def put(self, path: str, data: bytes) -> None:
        """A file onto the box through the command channel. Above ~45 KB it goes in parts (each one command) that the
        last command joins and moves into place, so a half-sent file never appears at `path`. Folders and big
        files: push_dir."""
        b64 = base64.b64encode(data).decode()
        parts = [b64[i:i + self.PART] for i in range(0, len(b64), self.PART)] or [""]
        if self.linux:
            q, tmp = shlex.quote(path), shlex.quote(path + ".fmpart")
            if len(parts) == 1:
                self.run(f"mkdir -p \"$(dirname {q})\" && echo {b64} | base64 -d > {q}")
                return
            self.run(f"mkdir -p \"$(dirname {q})\" && : > {tmp}")
            for part in parts:
                self.run(f"printf '%s' {part} >> {tmp}")
            self.run(f"base64 -d < {tmp} > {q}.fmnew && mv -f {q}.fmnew {q} && rm -f {tmp}")
        else:
            if len(parts) == 1:
                self.run(f"New-Item -ItemType Directory -Force -Path (Split-Path {_ps(path)}) | Out-Null; "
                         f"[IO.File]::WriteAllBytes({_ps(path)}, [Convert]::FromBase64String('{b64}'))")
                return
            tmp = path + ".fmpart"
            self.run(f"New-Item -ItemType Directory -Force -Path (Split-Path {_ps(path)}) | Out-Null; "
                     f"Set-Content -NoNewline -Path {_ps(tmp)} -Value ''")
            for part in parts:
                self.run(f"Add-Content -NoNewline -Path {_ps(tmp)} -Value '{part}'")
            self.run(f"[IO.File]::WriteAllBytes({_ps(path)}, [Convert]::FromBase64String((Get-Content -Raw {_ps(tmp)}))); "
                     f"Remove-Item {_ps(tmp)}")

    def get(self, path: str) -> bytes | None:
        """A file from the box, or None when it is not there. In parts of GET_PART bytes, one command each: SSM keeps
        only the first 24,000 characters of a command's output (day 1: a 150 KB file came back cut)."""
        n = self.GET_PART
        if self.linux:
            q = shlex.quote(path)
            out = self.run(f"if [ -f {q} ]; then echo FMFILE $(stat -c %s {q}); head -c {n} {q} | base64 -w0; echo; fi")
        else:
            out = self.run(f"if (Test-Path {_ps(path)}) {{ $b = [IO.File]::ReadAllBytes({_ps(path)}); "
                           f"'FMFILE ' + $b.Length; [Convert]::ToBase64String($b, 0, [Math]::Min({n}, $b.Length)) }}")
        lines = [x.strip() for x in out.splitlines()]
        head = next((i for i, x in enumerate(lines) if x.startswith("FMFILE")), None)
        if head is None:
            return None
        size = int(lines[head].split()[1]) if len(lines[head].split()) > 1 else 0
        chunks = [base64.b64decode(lines[head + 1]) if head + 1 < len(lines) else b""]
        for off in range(n, size, n):
            if self.linux:
                out = self.run(f"tail -c +{off + 1} {q} | head -c {n} | base64 -w0; echo")
            else:
                out = self.run(f"$b = [IO.File]::ReadAllBytes({_ps(path)}); "
                               f"[Convert]::ToBase64String($b, {off}, [Math]::Min({n}, $b.Length - {off}))")
            chunks.append(base64.b64decode(next((x.strip() for x in reversed(out.splitlines()) if x.strip()), "")))
        data = b"".join(chunks)
        if len(data) != size:
            raise SystemExit(f"get {path}: {len(data)} of {size} bytes came back")
        return data

    def exists(self, path: str) -> bool:
        if self.linux:
            return "yes" in self.run(f"[ -e {shlex.quote(path)} ] && echo yes || echo no")
        return "True" in self.run(f"Test-Path {_ps(path)}")


def _ps(s: str) -> str:
    """A PowerShell single-quoted literal."""
    return "'" + s.replace("'", "''") + "'"


# ------------------------------------------------------------------------------------------------------- AWS
def aws_cli(conf: dict, *args: str, check: bool = True):
    """The AWS CLI in the box's region, JSON out (tests replace this)."""
    r = subprocess.run(["aws", *args, "--region", conf.get("region", ""), "--output", "json"], capture_output=True,
                       text=True)
    if check and r.returncode:
        raise SystemExit(f"aws {' '.join(args[:2])}: {r.stderr.strip()[-500:]}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        return r.stdout


def ssm_cmd(conf: dict, document: str, script: str, timeout: int, aws=None) -> str:
    """Run one SSM command document on the box and wait for its output (tests replace this)."""
    if not conf.get("instance"):
        raise SystemExit("no instance set for this box: film-ue set --instance i-... (or film-ue box up)")
    aws = aws or (lambda *a, **k: aws_cli(conf, *a, **k))
    params = json.dumps({"commands": [script], "executionTimeout": [str(timeout)]})
    cid = aws("ssm", "send-command", "--instance-ids", conf["instance"], "--document-name", document,
              "--parameters", params)["Command"]["CommandId"]
    end = time.time() + timeout + 30
    while time.time() < end:
        time.sleep(2)
        r = aws("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", conf["instance"], check=False)
        if isinstance(r, dict) and r.get("Status") in ("Success", "Failed", "TimedOut", "Cancelled"):
            if r["Status"] != "Success":
                err = (r.get("StandardErrorContent", "") or r.get("StandardOutputContent", ""))[-800:]
                raise SystemExit(f"workstation command {r['Status']}: {err}")
            return r.get("StandardOutputContent", "")
    raise SystemExit("workstation command timed out")


class SSM(Transport):
    kind = "ssm"

    def __init__(self, conf: dict, ssm=None, aws=None):
        super().__init__(conf)
        self._ssm = ssm or (lambda document, script, timeout: ssm_cmd(conf, document, script, timeout))
        self._aws = aws or (lambda *a, **k: aws_cli(conf, *a, **k))

    def run(self, script: str, timeout: int = 600, root: bool = False) -> str:
        if self.linux:
            return self._ssm("AWS-RunShellScript", "set -e\n" + (script if root else self.as_user(script)), timeout)
        return self._ssm("AWS-RunPowerShellScript", script, timeout)

    def forward(self, remote_port: int, local_port: int, log_path: Path | None = None):
        if not shutil.which("session-manager-plugin"):
            raise SystemExit("the AWS Session Manager plugin is needed for a tunnel (or film-ue set --bridge ssm): "
                             "https://docs.aws.amazon.com/systems-manager/latest/userguide/"
                             "session-manager-working-with-install-plugin.html")
        out = open(log_path, "w") if log_path else subprocess.DEVNULL
        cmd = ["aws", "ssm", "start-session", "--region", self.conf["region"], "--target", self.conf["instance"],
               "--document-name", "AWS-StartPortForwardingSession", "--parameters",
               json.dumps({"portNumber": [str(remote_port)], "localPortNumber": [str(local_port)]})]
        return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)

    def _bucket(self) -> str:
        b = self.conf.get("bucket")
        if not b:
            raise SystemExit("no bucket set: film-ue set --bucket NAME (one the box's role can read and write)")
        return b

    def _local_s3(self, *args: str) -> None:
        r = subprocess.run(["aws", "s3", *args, "--only-show-errors", "--region", self.conf["region"]],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"aws s3 {args[0]}: {r.stderr.strip()[-500:]}")

    def push_dir(self, local_dir: str, remote_dir: str) -> int:
        """Up through the bucket (far faster than the tunnel), then the bucket copy is removed."""
        s3 = f"s3://{self._bucket()}/film-ue/up-{Path(local_dir).name}-{int(time.time())}"
        self._local_s3("sync", local_dir, s3)
        try:
            if self.linux:
                self.run(f"mkdir -p {shlex.quote(remote_dir)} && aws s3 sync --only-show-errors {s3} "
                         f"{shlex.quote(remote_dir)} --region {self.conf['region']}", timeout=3600)
            else:
                prefix = s3.split("/", 3)[3]
                self.run(f"New-Item -ItemType Directory -Force -Path {_ps(remote_dir)} | Out-Null; "
                         f"Read-S3Object -BucketName {self._bucket()} -KeyPrefix {prefix} -Folder {_ps(remote_dir)} "
                         f"-Region {self.conf['region']} | Out-Null", timeout=3600)
        finally:
            self._local_s3("rm", "--recursive", s3)
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())

    def pull_dir(self, remote_dir: str, local_dir: str) -> int:
        """Down through the bucket, then the bucket copy is removed."""
        s3 = f"s3://{self._bucket()}/film-ue/{Path(remote_dir.replace(chr(92), '/')).name}-{int(time.time())}"
        if self.linux:
            self.run(f"aws s3 sync --only-show-errors {shlex.quote(remote_dir)} {s3} --region {self.conf['region']}",
                     timeout=3600)
        else:
            prefix = s3.split("/", 3)[3]
            self.run(f"Write-S3Object -BucketName {self._bucket()} -KeyPrefix {prefix} -Folder {_ps(remote_dir)} "
                     f"-Recurse -Region {self.conf['region']}", timeout=3600)
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        try:
            self._local_s3("sync", s3, local_dir)
        finally:
            self._local_s3("rm", "--recursive", s3)
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())

    def describe(self) -> dict:
        return {**super().describe(), "instance": self.conf.get("instance"), "region": self.conf.get("region")}


class SSH(Transport):
    kind = "ssh"
    GET_PART = 64 * 2**20  # no output cap over ssh: one command

    def __init__(self, conf: dict, runner=None):
        super().__init__(conf)
        self._runner = runner or (lambda *a, **k: subprocess.run(*a, **k))  # looked up per call: tests patch it
        if not conf.get("ssh"):
            raise SystemExit("no ssh target set: film-ue set --transport ssh --ssh ubuntu@<host> --ssh-key <path>")

    def base(self) -> list:
        opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
                "-o", "ConnectTimeout=20"]
        key = self.conf.get("ssh_key")
        return ["ssh", *(["-i", key] if key else []), *opts]

    def run(self, script: str, timeout: int = 600, root: bool = False) -> str:
        if self.linux:  # bash as root (the login user has passwordless sudo); as the editor's user unless root
            cmd, stdin = [*self.base(), self.conf["ssh"], "sudo", "bash", "-s"], "set -e\n" + (script if root else self.as_user(script))
        else:  # Windows OpenSSH: PowerShell reads the script on stdin
            cmd, stdin = [*self.base(), self.conf["ssh"], "powershell", "-NoProfile", "-NonInteractive", "-Command", "-"], script
        try:
            r = self._runner(cmd, input=stdin, capture_output=True, text=True, timeout=timeout + 30)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"workstation command timed out after {timeout}s")
        if r.returncode:
            raise SystemExit(f"workstation command failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return r.stdout

    def forward(self, remote_port: int, local_port: int, log_path: Path | None = None):
        out = open(log_path, "w") if log_path else subprocess.DEVNULL
        cmd = [*self.base(), "-N", "-o", "ExitOnForwardFailure=yes",
               "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}", self.conf["ssh"]]
        return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)

    def _copy(self, src: str, dst: str) -> None:
        if self.linux:
            ssh = " ".join(shlex.quote(x) for x in self.base())
            user = self.conf.get("user") or "ubuntu"
            cmd = ["rsync", "-a", "--mkpath", "-e", ssh, f"--rsync-path=sudo -u {user} rsync", src, dst]
        else:
            cmd = ["scp", "-r", *self.base()[1:], src, dst]
        r = self._runner(cmd, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"copy failed ({r.returncode}): {(r.stderr or r.stdout)[-500:]}")

    def push_dir(self, local_dir: str, remote_dir: str) -> int:
        self._copy(local_dir.rstrip("/") + "/", f"{self.conf['ssh']}:{remote_dir.rstrip('/')}/")
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())

    def pull_dir(self, remote_dir: str, local_dir: str) -> int:
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        self._copy(f"{self.conf['ssh']}:{remote_dir.rstrip('/')}/", local_dir.rstrip("/") + "/")
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())

    def describe(self) -> dict:
        return {**super().describe(), "ssh": self.conf.get("ssh")}


class Local(Transport):
    """The editor on this very machine (a workstation someone sits at, or a GPU box running film-ue itself)."""
    kind = "local"

    def __init__(self, conf: dict, runner=None):
        super().__init__(conf)
        self._runner = runner or (lambda *a, **k: subprocess.run(*a, **k))

    def run(self, script: str, timeout: int = 600, root: bool = False) -> str:
        if self.linux:
            cmd = (["sudo", "-n", "bash", "-c", script] if root and os.geteuid() != 0 else ["bash", "-c", script])
        else:
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        try:
            r = self._runner(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"command timed out after {timeout}s")
        if r.returncode:
            raise SystemExit(f"command failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return r.stdout

    def put(self, path: str, data: bytes) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)

    def get(self, path: str) -> bytes | None:
        return Path(path).read_bytes() if Path(path).is_file() else None

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def forward(self, remote_port: int, local_port: int, log_path: Path | None = None):
        if remote_port != local_port:
            raise SystemExit(f"a local box needs no tunnel: set --local-port {remote_port} (the bridge's own port)")
        return None

    def push_dir(self, local_dir: str, remote_dir: str) -> int:
        shutil.copytree(local_dir, remote_dir, dirs_exist_ok=True)
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())

    def pull_dir(self, remote_dir: str, local_dir: str) -> int:
        shutil.copytree(remote_dir, local_dir, dirs_exist_ok=True)
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())


def get(conf: dict | None = None, **kw) -> Transport:
    """The transport for a box's settings (default: the current box's)."""
    if conf is None:
        from . import workstation
        conf = workstation.conf()
    kind = conf.get("transport") or "ssm"
    if kind not in KINDS:
        raise SystemExit(f"transport {kind!r}: one of {', '.join(KINDS)} (film-ue set --transport ...)")
    return {"ssm": SSM, "ssh": SSH, "local": Local}[kind](conf, **kw)


def tempdir(prefix: str = "film-ue-") -> str:
    return tempfile.mkdtemp(prefix=prefix)
