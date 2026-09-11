"""The scheduler: schedule math, the cron store, and the /cron API.

A firing rides the ordinary send path (a held `sent` event + the queue), so these
tests assert the ledger effect, not tmux keystrokes -- the send layer is tested in
test_channels."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import cron


# ----------------------------------------------------------- schedule math

def test_parse_interval_units():
    assert cron.parse_interval("30s") == 30
    assert cron.parse_interval("10m") == 600
    assert cron.parse_interval("1h") == 3600
    assert cron.parse_interval("2d") == 172800
    with pytest.raises(ValueError):
        cron.parse_interval("soon")


def test_first_run_every_and_relative_at():
    now = 1_000_000.0
    assert cron.first_run("every", "10m", "", now) == now + 600
    assert cron.first_run("at", "20m", "", now) == now + 1200


def test_first_run_at_absolute_iso():
    exp = datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()
    assert cron.first_run("at", "2030-01-01T00:00:00Z", "", 0) == exp
    # a naive timestamp is treated as UTC
    assert cron.first_run("at", "2030-01-01T00:00:00", "", 0) == exp


def test_first_run_cron_lands_within_the_hour():
    now = 1_000_000.0
    nxt = cron.first_run("cron", "*/5 * * * *", "", now)
    assert 0 < nxt - now <= 300


def test_first_run_honours_timezone():
    # 9am in two zones is not the same instant.
    la = cron.first_run("cron", "0 9 * * *", "America/Los_Angeles", 1_000_000.0)
    ny = cron.first_run("cron", "0 9 * * *", "America/New_York", 1_000_000.0)
    assert la != ny


def test_first_run_rejects_garbage():
    with pytest.raises(ValueError):
        cron.first_run("cron", "not a cron", "", 0)
    with pytest.raises(ValueError):
        cron.first_run("bogus", "x", "", 0)
    with pytest.raises(ValueError):
        cron.first_run("cron", "* * * * *", "Not/AZone", 0)


def test_advance_one_shot_vs_recurring():
    now = 1_000_000.0
    assert cron.advance("at", "20m", "", now) is None      # one-shot is spent
    assert cron.advance("every", "1h", "", now) == now + 3600
    assert cron.advance("cron", "*/5 * * * *", "", now) > now


def test_describe_reads_as_english():
    assert cron.describe({"kind": "every", "expr": "1h"}) == "every 1h"
    assert cron.describe({"kind": "at", "expr": "20m"}) == "once at 20m"
    assert "cron" in cron.describe({"kind": "cron", "expr": "0 9 * * *", "tz": "UTC"})


# ------------------------------------------------------------- cron store

def _job(store, **over):
    fields = {"kind": "every", "expr": "1h", "pane_id": "%0",
              "prompt": "go", "next_run_at": 100.0}
    fields.update(over)
    return store.create_job(fields)


def test_create_and_get(store):
    job = _job(store, name="nightly")
    assert job["id"] and job["enabled"] is True and job["kind"] == "every"
    assert store.get_job(job["id"])["prompt"] == "go"
    assert store.get_job(9999) is None


def test_create_requires_kind_and_expr(store):
    with pytest.raises(ValueError):
        store.create_job({"kind": "every"})       # no expr
    with pytest.raises(ValueError):
        store.create_job({"expr": "1h"})           # no kind


def test_list_orders_by_soonest_next_run(store):
    a = _job(store, next_run_at=300.0)
    b = _job(store, next_run_at=100.0)
    assert [j["id"] for j in store.list_jobs()] == [b["id"], a["id"]]


def test_due_jobs_respects_time_and_enabled(store):
    j = _job(store, next_run_at=100.0)
    assert store.due_jobs(50.0) == []                               # not yet
    assert [x["id"] for x in store.due_jobs(150.0)] == [j["id"]]    # arrived
    store.update_job(j["id"], {"enabled": False})
    assert store.due_jobs(150.0) == []                             # disabled never fires


def test_mark_ran_advances_counts_and_stamps(store):
    j = _job(store, next_run_at=100.0)
    store.mark_job_ran(j["id"], 100.0, 3700.0)
    g = store.get_job(j["id"])
    assert g["run_count"] == 1
    assert g["last_run_at"] == 100.0
    assert g["next_run_at"] == 3700.0


def test_runs_are_recorded_and_listed_newest_first(store):
    j = _job(store)
    r1 = store.record_run(j["id"], 1.0, "fired")
    store.finish_run(r1, "ok", "queued", 42)
    store.record_run(j["id"], 2.0, "fired")
    runs = store.list_runs(j["id"])
    assert len(runs) == 2
    assert runs[0]["started_at"] == 2.0                # newest first
    done = next(r for r in runs if r["id"] == r1)
    assert done["status"] == "ok" and done["event_id"] == 42


def test_delete_removes_job_and_its_runs(store):
    j = _job(store)
    store.record_run(j["id"], 1.0)
    assert store.delete_job(j["id"]) is True
    assert store.get_job(j["id"]) is None
    assert store.list_runs(j["id"]) == []
    assert store.delete_job(j["id"]) is False          # already gone


# --------------------------------------------------------------- /cron API

def test_create_list_get_delete(client, auth):
    r = client.post("/cron", json={"name": "daily", "kind": "every", "expr": "1h",
                                    "pane_id": "%0", "prompt": "go"}, headers=auth)
    assert r.status_code == 201
    jid = r.json()["id"]
    assert r.json()["schedule"] == "every 1h"
    assert any(j["id"] == jid for j in client.get("/cron", headers=auth).json()["jobs"])
    got = client.get(f"/cron/{jid}", headers=auth).json()
    assert got["prompt"] == "go" and got["runs"] == []
    assert client.delete(f"/cron/{jid}", headers=auth).status_code == 200
    assert client.get(f"/cron/{jid}", headers=auth).status_code == 404


def test_create_rejects_a_bad_schedule(client, auth):
    assert client.post("/cron", json={"kind": "cron", "expr": "nope", "prompt": "x"},
                       headers=auth).status_code == 400
    assert client.post("/cron", json={"kind": "bogus", "expr": "1h"},
                       headers=auth).status_code == 400


def test_patch_recomputes_the_next_run(client, auth):
    jid = client.post("/cron", json={"kind": "every", "expr": "1d",
                                     "pane_id": "%0", "prompt": "go"},
                      headers=auth).json()["id"]
    before = client.get(f"/cron/{jid}", headers=auth).json()["next_run_at"]
    r = client.patch(f"/cron/{jid}", json={"expr": "1h"}, headers=auth)
    assert r.status_code == 200 and r.json()["expr"] == "1h"
    assert r.json()["next_run_at"] < before            # 1h is sooner than 1d


def test_patch_and_delete_unknown_are_404(client, auth):
    assert client.patch("/cron/999", json={"expr": "1h"}, headers=auth).status_code == 404
    assert client.delete("/cron/999", headers=auth).status_code == 404


def test_run_now_fires_into_the_channel_and_records_a_run(client, auth, fake_tmux):
    jid = client.post("/cron", json={"kind": "every", "expr": "1h", "pane_id": "%0",
                                     "prompt": "scheduled hello"},
                      headers=auth).json()["id"]
    r = client.post(f"/cron/{jid}/run", headers=auth)
    assert r.json()["fired"] is True

    events = client.get("/channels/0/history", headers=auth).json()["events"]
    sent = [e for e in events if e["kind"] == "sent" and e["body"] == "scheduled hello"]
    assert sent, "the prompt should land in the channel as a sent event"
    assert sent[-1]["meta"]["origin"] == "cron"

    runs = client.get(f"/cron/{jid}", headers=auth).json()["runs"]
    assert runs and runs[0]["status"] == "ok"


def test_run_now_into_a_dead_channel_is_skipped(client, auth, fake_tmux):
    jid = client.post("/cron", json={"kind": "every", "expr": "1h", "pane_id": "%0",
                                     "prompt": "x"}, headers=auth).json()["id"]
    fake_tmux.kill_pane("%0")
    r = client.post(f"/cron/{jid}/run", headers=auth)
    assert r.json()["fired"] is False
    assert client.get(f"/cron/{jid}", headers=auth).json()["runs"][0]["status"] == "skipped"


def test_cron_requires_a_token(client):
    assert client.get("/cron").status_code == 401
    assert client.post("/cron", json={"kind": "every", "expr": "1h"}).status_code == 401
