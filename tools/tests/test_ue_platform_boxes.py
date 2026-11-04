"""Temporary boxes (filmtools.unreal.boxes) with a fake AWS: launch arguments (TTL tag, terminate on shutdown, spot,
user-data with the watchdog and the backstop), the profile it makes, idempotent up, ls, extend, status, down."""
from __future__ import annotations

import base64
import gzip
import json
import time

import pytest

from filmtools.unreal import boxes
from filmtools.unreal import workstation as ws


class FakeAWS:
    def __init__(self):
        self.calls = []
        self.instances = {}

    def __call__(self, *args, check=True):
        self.calls.append(args)
        svc, verb = args[0], args[1]
        if (svc, verb) == ("ssm", "get-parameter"):
            return {"Parameter": {"Value": "ami-ubuntu"}}
        if (svc, verb) == ("ec2", "run-instances"):
            iid = f"i-{len(self.instances):04d}"
            tags = json.loads(args[args.index("--tag-specifications") + 1])[0]["Tags"]
            self.instances[iid] = {"InstanceId": iid, "InstanceType": args[args.index("--instance-type") + 1],
                                   "State": {"Name": "running"}, "Tags": tags,
                                   **({"InstanceLifecycle": "spot"} if "--instance-market-options" in args else {})}
            return {"Instances": [self.instances[iid]]}
        if (svc, verb) == ("ec2", "describe-instances"):
            flt = [a for a in args if a.startswith("Name=tag:")]
            want = flt[0].split("Values=")[1] if flt else None
            out = [i for i in self.instances.values() if i["State"]["Name"] in boxes.LIVE and (
                want is None or any(t["Key"] == boxes.TAG and t["Value"] == want for t in i["Tags"]))]
            return {"Reservations": [{"Instances": out}]}
        if (svc, verb) == ("ssm", "describe-instance-information"):
            return {"InstanceInformationList": [{"PingStatus": "Online"}]}
        if (svc, verb) == ("ec2", "terminate-instances"):
            self.instances[args[3]]["State"]["Name"] = "shutting-down"
            return {}
        return {}

    def made(self, verb):
        return [c for c in self.calls if c[1] == verb]


@pytest.fixture
def conf(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.delenv("FILM_UE_BOX", raising=False)
    return tmp_path


def test_durations():
    assert [boxes.parse_duration(x) for x in ("4h", "90m", "1h30m", "2d", "45", 30)] == \
        [14400, 5400, 5400, 172800, 2700, 1800]
    with pytest.raises(SystemExit, match="like 4h"):
        boxes.parse_duration("soon")


def test_up_launches_a_terminating_tagged_box_with_the_watchdog(conf, monkeypatch):
    aws = FakeAWS()
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo", bucket="b", epic_s3="s3://b/k", region="ap-south-1")
    monkeypatch.delenv("FILM_UE_BOX")
    r = boxes.up("gpu1", ttl="3h", idle="25m", spot=True, like="linux", aws=aws, sleep=lambda s: None, log=lambda m: None)
    run = aws.made("run-instances")[0]
    assert run[run.index("--image-id") + 1] == "ami-ubuntu" and "--instance-market-options" in run
    assert run[run.index("--instance-initiated-shutdown-behavior") + 1] == "terminate"
    tags = {t["Key"]: t["Value"] for t in json.loads(run[run.index("--tag-specifications") + 1])[0]["Tags"]}
    assert tags["film-ue:box"] == "gpu1" and abs(int(tags["film-ue:ttl-until"]) - (time.time() + 3 * 3600)) < 5
    ud = run[run.index("--user-data") + 1]
    assert "systemctl enable --now ue-watchdog.timer" in ud and "--on-active=" in ud and "poweroff" in ud
    blob = ud.split("echo ", 1)[1].split(" |", 1)[0]
    assert b"def decide(" in gzip.decompress(base64.b64decode(blob))
    cfg = json.loads(ud.split("watchdog.json <<'FMEOF'\n", 1)[1].split("\nFMEOF", 1)[0])
    assert cfg["idle_min"] == 25 and cfg["token"] == "/srv/ue/projects/Demo/Saved/fmbridge.token"
    prof = json.loads((conf / "film-ue.gpu1.json").read_text())
    assert prof["instance"] == r["id"] and prof["temporary"] and prof["epic_s3"] == "s3://b/k" and prof["spot"]
    assert prof["project_dir"] == "/srv/ue/projects/Demo" and "local_port" not in prof
    # again: the same box, nothing launched
    again = boxes.up("gpu1", aws=aws, log=lambda m: None)
    assert again["id"] == r["id"] and len(aws.made("run-instances")) == 1


def test_up_refuses_nonsense(conf):
    with pytest.raises(SystemExit, match="ttl under 10 minutes"):
        boxes.up("gpu1", ttl="5m", aws=FakeAWS())
    with pytest.raises(SystemExit, match="box name"):
        boxes.up("../x", aws=FakeAWS())
    with pytest.raises(SystemExit, match="no profile 'nope'"):
        boxes.up("gpu1", like="nope", aws=FakeAWS())


def test_ls_extend_status_down(conf):
    aws = FakeAWS()
    boxes.up("gpu1", aws=aws, wait=False, log=lambda m: None)
    rows = boxes.ls(aws=aws)
    assert [(r["name"], r["state"], r["profile"]) for r in rows] == [("gpu1", "running", True)]
    assert 230 <= rows[0]["ttl_left_min"] <= 240
    ran = []
    e = boxes.extend("gpu1", "2h", aws=aws, run=ran.append)
    assert e["ttl_left_min"] == 120 and "film-ue-ttl" in ran[0] and str(e["ttl_until"]) in ran[0]
    assert aws.made("create-tags")
    st = boxes.status("gpu1", aws=aws, read=lambda p: b'{"last_decision": {"busy": ["gpu 80%"]}}')
    assert st["watchdog"]["last_decision"]["busy"] == ["gpu 80%"]
    d = boxes.down("gpu1", aws=aws, log=lambda m: None)
    assert d["state"] == "shutting-down" and json.loads((conf / "film-ue.gpu1.json").read_text())["instance"] == ""
    assert boxes.ls(aws=aws) == []
    with pytest.raises(SystemExit, match="not running"):
        boxes.extend("gpu1", "1h", aws=aws, run=ran.append)


def test_down_never_terminates_a_permanent_workstation(conf, monkeypatch):
    aws = FakeAWS()
    monkeypatch.setenv("FILM_UE_BOX", "ws")
    ws.save(os="windows", instance="i-perm")
    monkeypatch.delenv("FILM_UE_BOX")
    with pytest.raises(SystemExit, match="permanent workstation"):
        boxes.down("ws", aws=aws)
    assert not aws.made("terminate-instances")


def test_user_data_fits_and_the_backstop_is_at_least_a_minute():
    ud = boxes.user_data(int(time.time()) + 5, 20, 15)
    assert len(ud.encode()) < 16000 and "--on-active=60s" in ud


def test_save_ddc_on_exit_puts_the_ddc_save_in_the_watchdog(conf, monkeypatch):
    aws = FakeAWS()
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo", bucket="bkt", region="ap-south-1")
    monkeypatch.delenv("FILM_UE_BOX")
    boxes.up("gpu1", like="linux", save_ddc_on_exit=True, aws=aws, wait=False, log=lambda m: None)
    run = aws.made("run-instances")[0]
    ud = run[run.index("--user-data") + 1]
    cfg = json.loads(ud.split("watchdog.json <<'FMEOF'\n", 1)[1].split("\nFMEOF", 1)[0])
    assert len(cfg["on_exit"]) == 1 and "runuser -u ubuntu" in cfg["on_exit"][0]
    assert "s3://bkt/ue-linux/ddc/5.8.4/zen-data" in cfg["on_exit"][0]
    assert ws.conf()["os"] in ("windows", "linux")  # the temporary conf is gone
    with pytest.raises(SystemExit, match="needs --like"):
        boxes.up("gpu2", save_ddc_on_exit=True, aws=aws, wait=False, log=lambda m: None)
