from farm_rows import rows


def job(i, ok=True, seams=True, lead=1, strays=()):
    return {"id": f"shot{i:02d}", "verify": {"ok": ok}, "continuity": {"ok": seams, "flagged": [] if seams else [500]},
            "guards": [{"leaders_ok": lead, "strays": list(strays)}, {"leaders_ok": 1, "strays": []}]}


def test_clean_run_and_each_failure():
    r = rows({"jobs": [job(1), job(2)]})
    assert all(v["value"] == 1 for k, v in r.items() if k != "shot.farm_state_parity")
    assert rows({"jobs": [job(1), job(2, ok=False)]})["shot.farm_frames_ok"]["value"] == 0
    assert rows({"jobs": [job(1, seams=False)]})["shot.chunk_seams_ok"]["value"] == 0
    assert rows({"jobs": [job(1, lead=0)]})["garment.leaders_ok"]["value"] == 0
    assert rows({"jobs": [job(1, strays=["Test_perf_x"])]})["set.strays_ok"]["value"] == 0
    assert rows({"jobs": []})["shot.farm_frames_ok"]["value"] is None


def test_state_parity():
    j = job(1)
    for g in j["guards"]:
        g["state"] = "sync-42"
    assert rows({"jobs": [j], "expected_state": "sync-42"})["shot.farm_state_parity"]["value"] == 1
    j["guards"][1]["state"] = "sync-41"
    assert rows({"jobs": [j], "expected_state": "sync-42"})["shot.farm_state_parity"]["value"] == 0
    assert rows({"jobs": [job(2)]})["shot.farm_state_parity"]["value"] is None
