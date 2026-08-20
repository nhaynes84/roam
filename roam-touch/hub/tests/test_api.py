"""The HTTP + WebSocket contract in API.md, exercised end to end.

tmux is faked at `channels._run`; the store is real SQLite in a tmp dir.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import hub as hub_mod
from store import EventKind, Store
from transcript import INLINE_BODY_CHARS, MAX_BODY_CHARS
from conftest import TOKEN


def next_frame(ws, want: str, limit: int = 12, where=None) -> dict:
    """Read frames until one of type `want` (and matching `where`) shows up.

    The poller emits `channels` and `activity` frames on its own schedule, and
    a frame published between connecting and acting is a normal race -- a test
    that demands frame #1 be its own would be testing the scheduler.
    """
    for _ in range(limit):
        frame = ws.receive_json()
        if frame["type"] == want and (where is None or where(frame)):
            return frame
    raise AssertionError(f"no matching {want!r} frame in {limit} frames")


def wait_for(predicate, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("condition never became true")


# --------------------------------------------------------------------- auth


def test_health_needs_no_token(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["service"] == "roam-hub"
    assert body["protocol"] == hub_mod.PROTOCOL_VERSION


@pytest.mark.parametrize(
    "path",
    ["/status", "/channels", "/channels/%250/history", "/channels/%250/capture", "/events"],
)
def test_every_data_endpoint_requires_a_token(client, path):
    assert client.get(path).status_code == 401


def test_wrong_token_is_rejected(client):
    resp = client.get("/channels", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_send_requires_a_token(client):
    assert client.post("/channels/0/send", json={"text": "hi"}).status_code == 401


def test_hook_endpoint_requires_a_token(client):
    resp = client.post("/events", json={"pane": "%0", "kind": "receipt"})
    assert resp.status_code == 401


def test_token_file_is_created_private_when_absent(tmp_path):
    settings = hub_mod.Settings(
        token=None, token_file=tmp_path / "t.txt", db_path=tmp_path / "d.sqlite"
    )
    token = hub_mod.resolve_token(settings)
    assert len(token) >= 32
    assert (tmp_path / "t.txt").stat().st_mode & 0o777 == 0o600
    assert hub_mod.resolve_token(settings) == token, "token must be stable"


# ----------------------------------------------------------------- channels


def test_list_channels_merges_live_panes(client, auth):
    body = client.get("/channels", headers=auth).json()
    by_id = {c["pane_id"]: c for c in body["channels"]}
    assert set(by_id) == {"%0", "%1"}
    assert by_id["%0"]["label"] == "◑ Roam Touch rebuild discussion"
    assert by_id["%0"]["live"] is True
    assert by_id["%0"]["status"] == "idle"


def test_a_dead_pane_with_history_is_still_listed_and_marked_dead(
    client, auth, fake_tmux, store
):
    client.post("/channels/1/send", json={"text": "before it died"}, headers=auth)
    fake_tmux.kill_pane("%1")
    body = client.get("/channels", headers=auth).json()
    dead = next(c for c in body["channels"] if c["pane_id"] == "%1")
    assert dead["live"] is False
    assert dead["status"] == "dead"
    assert dead["label"] == "✳ Augment things", "the name must survive the pane"
    assert dead["event_count"] >= 1
    history = client.get("/channels/1/history", headers=auth).json()
    assert any(e["body"] == "before it died" for e in history["events"])


def test_live_channels_sort_above_dead_ones(client, auth, fake_tmux):
    client.get("/channels", headers=auth)
    fake_tmux.kill_pane("%0")
    channels = client.get("/channels", headers=auth).json()["channels"]
    assert [c["live"] for c in channels] == sorted(
        [c["live"] for c in channels], reverse=True
    )


def test_status_becomes_working_after_a_send_and_idle_after_the_outcome(client, auth):
    client.post("/channels/0/send", json={"text": "do the thing"}, headers=auth)
    working = client.get("/channels/0", headers=auth).json()["channel"]
    assert working["status"] == "working"
    client.post("/events", json={"pane": "%0", "kind": "outcome"}, headers=auth)
    idle = client.get("/channels/0", headers=auth).json()["channel"]
    assert idle["status"] == "idle"


def test_unknown_channel_is_404(client, auth):
    assert client.get("/channels/99", headers=auth).status_code == 404


def test_pane_ids_accepted_bare_or_percent_encoded(client, auth):
    bare = client.get("/channels/0", headers=auth).json()["channel"]
    encoded = client.get("/channels/%250", headers=auth).json()["channel"]
    assert bare["pane_id"] == encoded["pane_id"] == "%0"


def test_a_nonsense_pane_id_is_rejected(client, auth):
    resp = client.get("/channels/not-a-pane/history", headers=auth)
    assert resp.status_code == 400
    assert "pane id" in resp.json()["detail"]


def test_archiving_a_channel_hides_it_without_losing_history(client, auth):
    client.post("/channels/1/send", json={"text": "keep me"}, headers=auth)
    client.post("/channels/1/archive", json={"archived": True}, headers=auth)
    visible = client.get("/channels", headers=auth).json()["channels"]
    assert "%1" not in {c["pane_id"] for c in visible}
    everything = client.get(
        "/channels", params={"include_archived": True}, headers=auth
    ).json()["channels"]
    assert "%1" in {c["pane_id"] for c in everything}
    history = client.get("/channels/1/history", headers=auth).json()
    assert [e["body"] for e in history["events"] if e["kind"] == "sent"] == ["keep me"]
    client.post("/channels/1/archive", json={"archived": False}, headers=auth)
    assert "%1" in {
        c["pane_id"] for c in client.get("/channels", headers=auth).json()["channels"]
    }


# --------------------------------------------------------------------- send


def test_send_types_into_the_pane_and_records_it(client, auth, fake_tmux):
    resp = client.post(
        "/channels/0/send", json={"text": "ship it", "origin": "watch"}, headers=auth
    )
    assert resp.status_code == 200
    event = resp.json()["event"]
    assert event["kind"] == "sent"
    assert event["body"] == "ship it"
    assert event["meta"] == {"origin": "watch", "enter": True}
    assert resp.json()["channel"]["status"] == "working"
    assert fake_tmux.argv_for("send-keys")[0] == (
        "send-keys", "-t", "%0", "-l", "--", "ship it",
    )


def test_send_without_enter_is_honoured(client, auth, fake_tmux):
    client.post(
        "/channels/0/send", json={"text": "staged", "enter": False}, headers=auth
    )
    assert fake_tmux.argv_for("send-keys") == [
        ("send-keys", "-t", "%0", "-l", "--", "staged")
    ]


def test_send_to_a_dead_pane_is_404_and_types_nothing(client, auth, fake_tmux):
    fake_tmux.kill_pane("%0")
    resp = client.post("/channels/0/send", json={"text": "hello?"}, headers=auth)
    assert resp.status_code == 404
    assert "not live" in resp.json()["detail"]
    assert fake_tmux.argv_for("send-keys") == []


def test_empty_text_is_rejected_by_validation(client, auth):
    assert client.post("/channels/0/send", json={"text": ""}, headers=auth).status_code == 422


def test_a_tmux_failure_is_502_and_leaves_an_error_event(client, auth, fake_tmux):
    fake_tmux.fail_send_with = "pane is dead"
    resp = client.post("/channels/0/send", json={"text": "boom"}, headers=auth)
    assert resp.status_code == 502
    history = client.get("/channels/0/history", headers=auth).json()["events"]
    error = [e for e in history if e["kind"] == "error"][-1]
    assert error["meta"]["attempted"] == "boom"


# ---------------------------------------------------------------- interrupt


def test_interrupt_sends_escape_as_a_key_not_as_text(client, auth, fake_tmux):
    """`send-keys Escape` (a key press), never `send-keys -l` (typed text)."""
    resp = client.post("/channels/0/interrupt", json={"action": "escape"}, headers=auth)
    assert resp.status_code == 200
    assert fake_tmux.argv_for("send-keys") == [("send-keys", "-t", "%0", "Escape")]


def test_interrupt_defaults_to_escape_with_no_body(client, auth, fake_tmux):
    assert client.post("/channels/0/interrupt", headers=auth).status_code == 200
    assert fake_tmux.argv_for("send-keys")[0][-1] == "Escape"


def test_interrupt_can_send_control_c(client, auth, fake_tmux):
    client.post("/channels/0/interrupt", json={"action": "interrupt"}, headers=auth)
    assert fake_tmux.argv_for("send-keys")[0][-1] == "C-c"


def test_interrupt_records_what_happened_not_the_raw_bytes(client, auth):
    """The old workaround stored a `sent` event holding a control byte, which
    reads as if he typed it and poisons the search index."""
    event = client.post(
        "/channels/0/interrupt", json={"action": "escape"}, headers=auth
    ).json()["event"]
    assert event["kind"] == "control"
    assert event["body"] == "escape"
    assert event["meta"]["key"] == "Escape"
    assert "\x1b" not in event["body"]
    history = client.get("/channels/0/history", headers=auth).json()["events"]
    assert not any(e["kind"] == "sent" for e in history), "no phantom typed message"


def test_an_interrupt_does_not_move_the_conversation(client, auth, store):
    """Stopping a run is not answering it: coverage must not flip to `app`."""
    client.post(
        "/events", json={"pane": "%0", "kind": "receipt", "body": "typed"}, headers=auth
    )
    client.post("/channels/0/interrupt", headers=auth)
    assert store.get_channel("%0").last_input_source == "tmux"


def test_an_unknown_interrupt_action_is_refused(client, auth, fake_tmux):
    resp = client.post("/channels/0/interrupt", json={"action": "rm -rf"}, headers=auth)
    assert resp.status_code == 400
    assert "escape" in resp.json()["detail"]
    assert fake_tmux.argv_for("send-keys") == [], "nothing was pressed"


def test_interrupting_a_dead_pane_is_404(client, auth, fake_tmux):
    fake_tmux.kill_pane("%0")
    assert client.post("/channels/0/interrupt", headers=auth).status_code == 404


def test_interrupt_requires_a_token(client):
    assert client.post("/channels/0/interrupt").status_code == 401


def test_control_events_are_pushed_like_any_other(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        client.post("/channels/0/interrupt", headers=auth)
        frame = next_frame(ws, "event", where=lambda f: f["event"]["kind"] == "control")
        assert frame["event"]["body"] == "escape"


def test_send_refuses_control_characters_and_says_where_to_go(client, auth, fake_tmux):
    """The workaround that polluted the ledger is now closed off."""
    resp = client.post("/channels/0/send", json={"text": "\x1b"}, headers=auth)
    assert resp.status_code == 400
    assert "/interrupt" in resp.json()["detail"]
    assert fake_tmux.argv_for("send-keys") == []
    history = client.get("/channels/0/history", headers=auth).json()["events"]
    assert not any(e["kind"] == "sent" for e in history), "nothing was recorded"


def test_send_still_accepts_newlines_and_tabs(client, auth):
    resp = client.post(
        "/channels/0/send", json={"text": "line one\nline two\tindented"}, headers=auth
    )
    assert resp.status_code == 200


# ------------------------------------------------------------------ history


def test_history_orders_the_full_exchange(client, auth):
    client.post("/channels/0/send", json={"text": "question"}, headers=auth)
    client.post("/events", json={"pane": "%0", "kind": "receipt"}, headers=auth)
    client.post(
        "/events",
        json={"pane": "%0", "kind": "outcome", "body": "answer", "meta": {"ms": 90}},
        headers=auth,
    )
    events = client.get("/channels/0/history", headers=auth).json()["events"]
    kinds = [e["kind"] for e in events if e["kind"] != "opened"]
    assert kinds == ["sent", "receipt", "outcome"]
    assert events[-1]["meta"] == {"ms": 90}


def test_history_since_returns_only_what_the_client_missed(client, auth):
    first = client.post("/channels/0/send", json={"text": "one"}, headers=auth).json()
    client.post("/channels/0/send", json={"text": "two"}, headers=auth)
    body = client.get(
        "/channels/0/history", params={"since": first["event"]["id"]}, headers=auth
    ).json()
    assert [e["body"] for e in body["events"]] == ["two"]


def test_history_limit(client, auth):
    for i in range(5):
        client.post("/channels/0/send", json={"text": f"m{i}"}, headers=auth)
    body = client.get("/channels/0/history", params={"limit": 2}, headers=auth).json()
    assert [e["body"] for e in body["events"]] == ["m3", "m4"]


def test_clearing_history_is_a_soft_delete(client, auth):
    client.post("/channels/0/send", json={"text": "sensitive"}, headers=auth)
    resp = client.delete("/channels/0/history", headers=auth).json()
    assert resp["archived"] >= 1 and resp["deleted"] == 0
    assert client.get("/channels/0/history", headers=auth).json()["events"] == []
    recovered = client.get(
        "/channels/0/history", params={"include_archived": True}, headers=auth
    ).json()["events"]
    assert any(e["body"] == "sensitive" for e in recovered)


def test_global_events_feed_for_wake_up_catchup(client, auth):
    mark = client.get("/status", headers=auth).json()["latest_event_id"]
    client.post("/channels/0/send", json={"text": "a"}, headers=auth)
    client.post("/channels/1/send", json={"text": "b"}, headers=auth)
    body = client.get("/events", params={"since": mark}, headers=auth).json()
    assert [e["body"] for e in body["events"]] == ["a", "b"]


# -------------------------------------------------------------- hook events


def test_hook_posts_receipt_and_outcome_by_tmux_pane(client, auth):
    receipt = client.post(
        "/events",
        json={"pane": "%1", "kind": "receipt", "meta": {"source": "tmux-hook"}},
        headers=auth,
    )
    assert receipt.status_code == 201
    assert receipt.json()["event"]["pane_id"] == "%1"
    assert receipt.json()["event"]["meta"] == {"source": "tmux-hook"}
    outcome = client.post(
        "/events", json={"pane_id": "%1", "kind": "outcome", "body": "done"}, headers=auth
    )
    assert outcome.json()["event"]["kind"] == "outcome"


def test_hook_for_an_unknown_pane_creates_the_channel(client, auth, fake_tmux, store):
    fake_tmux.add_pane("%7", session="side", title="a new session")
    resp = client.post("/events", json={"pane": "%7", "kind": "receipt"}, headers=auth)
    assert resp.status_code == 201
    assert store.get_channel("%7") is not None
    listed = client.get("/channels", headers=auth).json()["channels"]
    assert "%7" in {c["pane_id"] for c in listed}


def test_an_outcome_carries_the_answer_and_a_speakable_summary(client, auth):
    """What the wearer actually needs: the answer, not "it finished"."""
    answer = (
        "## Done\n\nThe suite is **green** — 122 tests.\n\n"
        "```bash\nnpm test -- --watchAll=false\n```\n\nNothing else to do."
    )
    resp = client.post(
        "/events",
        json={"pane": "%0", "kind": "outcome", "body": answer},
        headers=auth,
    )
    event = resp.json()["event"]
    assert event["body"] == answer, "the full text is kept"
    assert event["summary"] == (
        "Done The suite is green — 122 tests. [code, 1 line] Nothing else to do."
    ), "punctuation stays; only markdown and unspeakable symbols go"
    assert "```" not in event["summary"]


def test_a_long_answer_is_kept_whole_and_only_trimmed_in_bulk_payloads(client, auth):
    """Summary first, details expandable -- the details must still be there."""
    answer = "The plan. " + ("detail sentence. " * 2000)
    posted = client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": answer}, headers=auth
    ).json()["event"]
    assert posted["body"] == answer, "the single-event response is never trimmed"
    assert posted["body_chars"] == len(answer)
    assert posted["body_truncated"] is False
    assert posted["summary"].startswith("The plan.")

    listed = client.get("/channels/0/history", headers=auth).json()["events"][-1]
    assert len(listed["body"]) == 4096, "list payloads carry a bounded body"
    assert listed["body_truncated"] is True
    assert listed["body_chars"] == len(answer)
    assert listed["summary"] == posted["summary"]

    whole = client.get(f"/events/{posted['id']}", headers=auth).json()["event"]
    assert whole["body"] == answer, "expanding always returns everything"
    assert whole["body_truncated"] is False


def test_a_pathological_body_is_railed_at_the_storage_limit(client, auth):
    monstrous = "q" * (MAX_BODY_CHARS + 10000)
    event = client.post(
        "/events",
        json={"pane": "%0", "kind": "outcome", "body": monstrous},
        headers=auth,
    ).json()["event"]
    assert event["body_chars"] == MAX_BODY_CHARS
    assert event["meta"]["truncated_from"] == MAX_BODY_CHARS + 10000


def test_an_unknown_event_id_is_404(client, auth):
    assert client.get("/events/999999", headers=auth).status_code == 404


def test_every_event_shape_has_a_summary_field(client, auth):
    client.post("/channels/0/send", json={"text": "**do** the thing"}, headers=auth)
    events = client.get("/channels/0/history", headers=auth).json()["events"]
    assert all("summary" in e for e in events)
    sent = [e for e in events if e["kind"] == "sent"][-1]
    assert sent["summary"] == "do the thing"


def test_hook_rejects_a_bad_pane_id(client, auth):
    resp = client.post("/events", json={"pane": "", "kind": "receipt"}, headers=auth)
    assert resp.status_code == 400


# ------------------------------------------------------------------ capture


def test_capture_returns_pane_output(client, auth, fake_tmux):
    fake_tmux.pane_output["%0"] = "the tail of the pane\n"
    body = client.get(
        "/channels/0/capture", params={"lines": 10}, headers=auth
    ).json()
    assert body["text"] == "the tail of the pane\n"
    assert body["lines"] == 10
    # The liveness poller also runs capture-pane (no -S); find the read-back.
    scrollback = [a for a in fake_tmux.argv_for("capture-pane") if "-S" in a]
    assert scrollback[-1][-1] == "-10"


def test_capture_of_a_dead_pane_is_404(client, auth, fake_tmux):
    fake_tmux.kill_pane("%0")
    assert client.get("/channels/0/capture", headers=auth).status_code == 404


# ---------------------------------------------------------------- websocket


def test_websocket_rejects_a_bad_token(client):
    with client.websocket_connect("/ws?token=wrong") as ws:
        assert ws.receive_json() == {"type": "error", "detail": "unauthorised"}


def test_websocket_hello_carries_the_channel_list(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["protocol"] == hub_mod.PROTOCOL_VERSION
        assert {c["pane_id"] for c in hello["channels"]} >= {"%0", "%1"}
        assert isinstance(hello["latest_event_id"], int)


def test_websocket_accepts_the_token_as_a_query_param(client):
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_websocket_pushes_events_without_polling(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()  # hello
        client.post("/channels/0/send", json={"text": "pushed"}, headers=auth)
        frame = next_frame(ws, "event")
        assert frame["event"]["kind"] == "sent"
        assert frame["event"]["body"] == "pushed"


def test_websocket_pushes_a_hook_outcome_that_lands_later(client, auth):
    """The whole point: the outcome arrives while the wearer is elsewhere."""
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        client.post(
            "/events",
            json={"pane": "%1", "kind": "outcome", "body": "build finished"},
            headers=auth,
        )
        frame = next_frame(ws, "event")
        assert frame["event"]["pane_id"] == "%1"
        assert frame["event"]["body"] == "build finished"


def test_websocket_since_replays_what_was_missed(client, auth):
    mark = client.get("/status", headers=auth).json()["latest_event_id"]
    client.post("/channels/0/send", json={"text": "while you were asleep"}, headers=auth)
    with client.websocket_connect(f"/ws?since={mark}", headers=auth) as ws:
        ws.receive_json()  # hello
        backlog = next_frame(ws, "backlog")
        assert [e["body"] for e in backlog["events"]] == ["while you were asleep"]


def test_websocket_does_not_repeat_backlog_as_a_live_event(client, auth):
    mark = client.get("/status", headers=auth).json()["latest_event_id"]
    sent = client.post("/channels/0/send", json={"text": "once"}, headers=auth).json()
    with client.websocket_connect(f"/ws?since={mark}", headers=auth) as ws:
        ws.receive_json()
        backlog = next_frame(ws, "backlog")
        assert [e["id"] for e in backlog["events"]] == [sent["event"]["id"]]
        client.post("/channels/0/send", json={"text": "twice"}, headers=auth)
        live = next_frame(ws, "event")
        assert live["event"]["body"] == "twice"


def test_websocket_ping_gets_a_pong(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert next_frame(ws, "pong")["t"] > 0


def test_websocket_announces_a_pane_that_appears(client, auth, fake_tmux):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        fake_tmux.add_pane("%5", session="new", title="a fresh claude")
        frame = next_frame(
            ws,
            "channels",
            limit=30,
            where=lambda f: "%5" in {c["pane_id"] for c in f["channels"]},
        )
        assert "%5" in {c["pane_id"] for c in frame["channels"]}


def test_websocket_announces_a_pane_that_dies(client, auth, fake_tmux, store):
    wait_for(lambda: store.get_channel("%1") is not None)
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        fake_tmux.kill_pane("%1")
        frame = next_frame(
            ws,
            "channels",
            limit=30,
            where=lambda f: any(
                c["pane_id"] == "%1" and not c["live"] for c in f["channels"]
            ),
        )
        dead = next(c for c in frame["channels"] if c["pane_id"] == "%1")
        assert dead["live"] is False and dead["status"] == "dead"
    closed = wait_for(
        lambda: [e for e in store.history("%1") if e.kind == EventKind.CLOSED.value]
    )
    assert "channel closed" in closed[-1].body


def test_history_cleared_is_broadcast(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        client.post("/channels/0/send", json={"text": "x"}, headers=auth)
        client.delete("/channels/0/history", headers=auth)
        frame = next_frame(ws, "history_cleared")
        assert frame["pane_id"] == "%0"


# --------------------------------------------------------- liveness heartbeat


def test_a_channel_reports_when_its_output_last_moved(client, auth, store):
    """`working` and `wedged` look identical without this."""
    wait_for(lambda: store.get_channel("%0") is not None)
    channel = wait_for(
        lambda: (
            c := client.get("/channels/0", headers=auth).json()["channel"]
        )
        and c["last_output_at"]
        and c
    )
    assert channel["idle_s"] is not None and channel["idle_s"] >= 0


def test_idle_seconds_grow_while_a_pane_says_nothing(client, auth, fake_tmux):
    wait_for(
        lambda: client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
        is not None
    )
    first = client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
    time.sleep(0.4)
    later = client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
    assert later > first, "a silent pane must look increasingly stale"


def test_output_resets_the_heartbeat(client, auth, fake_tmux):
    wait_for(
        lambda: client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
        is not None
    )
    time.sleep(0.3)
    stale = client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
    fake_tmux.pane_output["%0"] = "the agent printed something new"
    fresher = wait_for(
        lambda: (
            v := client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
        )
        < stale
        and v
    )
    assert fresher < stale


def test_a_dead_pane_reports_no_idle_time(client, auth, fake_tmux):
    wait_for(
        lambda: client.get("/channels/0", headers=auth).json()["channel"]["idle_s"]
        is not None
    )
    fake_tmux.kill_pane("%0")
    dead = wait_for(
        lambda: (
            c := client.get("/channels/0", headers=auth).json()["channel"]
        )
        and not c["live"]
        and c
    )
    assert dead["idle_s"] is None, "a dead pane is not 'idle for 3 seconds'"
    assert dead["last_output_at"] is not None, "but we remember when it last spoke"


def test_activity_is_pushed_over_the_websocket(client, auth, fake_tmux):
    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()
        fake_tmux.pane_output["%1"] = "fresh output on the augment channel"
        frame = next_frame(
            ws, "activity", limit=40, where=lambda f: "%1" in f["panes"]
        )
        assert frame["panes"]["%1"] <= frame["server_time"]


def test_activity_polling_can_be_turned_off(settings, store, fake_tmux, auth):
    quiet = settings.model_copy(update={"activity_polling": False})
    with TestClient(hub_mod.create_app(settings=quiet, store=store)) as c:
        wait_for(lambda: store.get_channel("%0") is not None)
        time.sleep(0.2)
        channel = c.get("/channels/0", headers=auth).json()["channel"]
        assert channel["last_output_at"] is None
        assert channel["idle_s"] is None


# ------------------------------------------- reply where the last message came from


def test_a_prompt_typed_in_tmux_marks_the_channel_as_a_keyboard_conversation(
    client, auth, store
):
    """The UserPromptSubmit hook fired: he is sitting at the keyboard."""
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "run the tests"},
        headers=auth,
    )
    assert store.get_channel("%0").last_input_source == "tmux"
    outcome = client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": "green"}, headers=auth
    ).json()["event"]
    assert outcome["coverage"]["covered"] is True, "he is reading it in tmux"
    assert outcome["coverage"]["by"] == ["tmux-input"]


def test_a_message_sent_from_the_app_moves_the_conversation_to_the_phone(
    client, auth, store
):
    client.post("/channels/0/send", json={"text": "run the tests"}, headers=auth)
    assert store.get_channel("%0").last_input_source == "app"
    outcome = client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": "green"}, headers=auth
    ).json()["event"]
    assert outcome["coverage"]["covered"] is False, "the answer belongs on ROAM"
    assert outcome["coverage"]["known"] is True


def test_the_hook_echo_of_an_app_message_does_not_steal_the_conversation(
    client, auth, store
):
    """Sending from the app types into the pane, which fires the same hook.

    Left alone that echo would flip the channel back to 'keyboard' and silence
    the very answer he is waiting for on the phone.
    """
    client.post("/channels/0/send", json={"text": "deploy it"}, headers=auth)
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "deploy it"},
        headers=auth,
    )
    assert store.get_channel("%0").last_input_source == "app"
    outcome = client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": "done"}, headers=auth
    ).json()["event"]
    assert outcome["coverage"]["covered"] is False


def test_the_echo_receipt_says_which_send_it_duplicates(client, auth):
    """One thing he said, one entry -- so the echo has to name its original.

    The hub already recognises the echo; without saying so on the event, every
    consumer renders the same sentence twice ("YOU" and "PROMPT") and the
    search index carries it twice.
    """
    sent = client.post(
        "/channels/0/send", json={"text": "deploy it"}, headers=auth
    ).json()["event"]
    receipt = client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "deploy it"},
        headers=auth,
    ).json()["event"]
    assert receipt["meta"]["echo_of"] == sent["id"]


def test_a_prompt_typed_at_the_keyboard_is_nobody_s_echo(client, auth):
    """⚠️ The only record that this message exists. It is never an echo."""
    client.post("/channels/0/send", json={"text": "deploy it"}, headers=auth)
    receipt = client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "actually, hold on"},
        headers=auth,
    ).json()["event"]
    assert "echo_of" not in receipt["meta"]


def test_an_echo_outside_the_window_is_a_prompt_he_retyped(client, auth, settings):
    """Same text, but long after the send -- he typed it himself this time."""
    client.post("/channels/0/send", json={"text": "again"}, headers=auth)
    settings.echo_window_s = 0.0
    receipt = client.post(
        "/events", json={"pane": "%0", "kind": "receipt", "body": "again"}, headers=auth
    ).json()["event"]
    assert "echo_of" not in receipt["meta"]


def test_the_echo_mark_survives_into_history(client, auth):
    """The client collapses on a stored field, not on a live stream frame."""
    sent = client.post(
        "/channels/0/send", json={"text": "deploy it"}, headers=auth
    ).json()["event"]
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "deploy it"},
        headers=auth,
    )
    events = client.get("/channels/0/history", headers=auth).json()["events"]
    echo = [e for e in events if e["kind"] == "receipt"][-1]
    assert echo["meta"]["echo_of"] == sent["id"]


def test_a_channel_switches_source_mid_conversation(client, auth, store):
    """He answers from the laptop; the conversation moves back to tmux."""
    client.post("/channels/0/send", json={"text": "from the phone"}, headers=auth)
    assert store.get_channel("%0").last_input_source == "app"
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "actually, do this instead"},
        headers=auth,
    )
    assert store.get_channel("%0").last_input_source == "tmux"
    outcome = client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": "ok"}, headers=auth
    ).json()["event"]
    assert outcome["coverage"]["covered"] is True


def test_no_recorded_source_means_notify(client, auth):
    """An agent that speaks first on a fresh pane. Unknown must never be silence."""
    event = client.post(
        "/events", json={"pane": "%1", "kind": "outcome", "body": "unprompted"},
        headers=auth,
    ).json()["event"]
    assert event["coverage"]["covered"] is False


def test_the_channel_says_where_its_conversation_is(client, auth):
    client.post("/channels/0/send", json={"text": "hello"}, headers=auth)
    channel = client.get("/channels/0", headers=auth).json()["channel"]
    assert channel["last_input_source"] == "app"
    assert channel["last_input_at"] > 0


def test_coverage_never_hides_an_event_from_history(client, auth):
    """Coverage governs notification only -- never storage or display."""
    client.post(
        "/events", json={"pane": "%0", "kind": "receipt", "body": "typed"}, headers=auth
    )
    client.post(
        "/events", json={"pane": "%0", "kind": "outcome", "body": "the answer"},
        headers=auth,
    )
    bodies = [
        e["body"] for e in client.get("/channels/0/history", headers=auth).json()["events"]
    ]
    assert "the answer" in bodies


# ----------------------------------------------------------------- presence


def test_the_app_can_report_itself_foregrounded(client, auth):
    """The one signal last-input cannot express: looking without sending."""
    resp = client.post(
        "/presence",
        json={"source": "roam-app", "kind": "app", "covers_all": True, "ttl_s": 60},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["presence"]["covers_all"] is True

    event = client.post(
        "/events", json={"pane": "%1", "kind": "outcome", "body": "x"}, headers=auth
    ).json()["event"]
    assert event["coverage"]["covered"] is True
    assert "roam-app" in event["coverage"]["by"]

    gone = client.delete("/presence/roam-app", headers=auth)
    assert gone.json()["removed"] is True
    after = client.post(
        "/events", json={"pane": "%1", "kind": "outcome", "body": "y"}, headers=auth
    ).json()["event"]
    assert after["coverage"]["covered"] is False


def test_a_reported_source_can_name_specific_panes(client, auth):
    client.post(
        "/presence", json={"source": "desk-panel", "panes": ["0", "%1"]}, headers=auth
    )
    body = client.get("/presence", headers=auth).json()
    covered = {p for s in body["sources"] if s["id"] == "desk-panel" for p in s["panes"]}
    assert covered == {"%0", "%1"}


def test_presence_requires_a_token(client):
    assert client.get("/presence").status_code == 401
    assert client.post("/presence", json={"source": "x"}).status_code == 401


def test_status_carries_presence(client, auth):
    client.post("/presence", json={"source": "roam-app", "covers_all": True}, headers=auth)
    assert client.get("/status", headers=auth).json()["presence"]["covers_all"] is True


def test_presence_is_pushed_over_the_websocket(client, auth):
    with client.websocket_connect("/ws", headers=auth) as ws:
        hello = ws.receive_json()
        assert "presence" in hello
        client.post(
            "/presence", json={"source": "roam-app", "covers_all": True}, headers=auth
        )
        frame = next_frame(ws, "presence", limit=30, where=lambda f: f["covers_all"])
        assert frame["present"] is True


# ------------------------------------------------------------------- poller


def test_poller_records_channels_it_discovers(client, auth, store):
    wait_for(lambda: store.get_channel("%0") is not None)
    assert store.get_channel("%0").label == "◑ Roam Touch rebuild discussion"
    opened = wait_for(
        lambda: [e for e in store.history("%0") if e.kind == EventKind.OPENED.value]
    )
    assert opened[0].meta["session"] == "main"


def test_poller_tracks_a_retitled_pane(client, auth, fake_tmux, store):
    wait_for(lambda: store.get_channel("%0") is not None)
    fake_tmux.retitle("%0", "◑ Now building the hub")
    wait_for(lambda: store.get_channel("%0").label == "◑ Now building the hub")
    listed = client.get("/channels", headers=auth).json()["channels"]
    assert any(c["label"] == "◑ Now building the hub" for c in listed)


def test_poller_does_not_re_announce_channels_after_a_restart(
    settings, store, fake_tmux
):
    with TestClient(hub_mod.create_app(settings=settings, store=store)):
        wait_for(lambda: store.get_channel("%0") is not None)
    opened_before = store.event_count("%0")
    with TestClient(hub_mod.create_app(settings=settings, store=store)):
        time.sleep(0.3)
    assert store.event_count("%0") == opened_before, "no duplicate opened events"


def test_hub_survives_tmux_going_away(client, auth, fake_tmux):
    fake_tmux.installed = False
    resp = client.get("/channels", headers=auth)
    assert resp.status_code == 503
    fake_tmux.installed = True
    assert client.get("/channels", headers=auth).status_code == 200
    assert client.get("/status", headers=auth).json()["tmux_ok"] is True


# ---------------------------------------------------------------- lifecycle


def test_create_channel_spawns_a_detached_window(client, auth, fake_tmux):
    r = client.post("/channels", json={"label": "TEST spawn", "command": "claude"},
                    headers=auth)
    assert r.status_code == 201
    ch = r.json()["channel"]
    assert ch["live"] is True
    assert ch["label"] == "TEST spawn"
    # A new window, detached, never a split of what the owner is looking at.
    (argv,) = fake_tmux.argv_for("new-window")
    assert "-d" in argv
    # Through an interactive zsh: the tmux client is a launchd daemon whose
    # PATH has no nodenv shims, so a bare exec of `claude` dies instantly.
    assert argv[-3:-1] == ("zsh", "-ic")
    assert argv[-1] == "claude"
    # And in $HOME, not wherever the hub process happens to live.
    import os
    assert argv[argv.index("-c") + 1] == os.path.expanduser("~")
    # Named while we know what it is for -- unnamed panes all read as "talos".
    assert fake_tmux.argv_for("select-pane")


def test_create_channel_records_opened_once(client, auth, fake_tmux):
    r = client.post("/channels", json={"label": "TEST once"}, headers=auth)
    pane_id = r.json()["channel"]["pane_id"]
    import time as _time
    _time.sleep(0.15)  # let the poller run; it must not re-open the channel
    history = client.get(f"/channels/{pane_id.lstrip('%')}/history", headers=auth).json()
    opened = [e for e in history["events"] if e["kind"] == "opened"]
    assert len(opened) == 1
    assert opened[0]["meta"]["spawned"] is True


def test_create_channel_with_no_server_starts_a_session(client, auth, fake_tmux):
    fake_tmux.server_running = False
    fake_tmux.panes = []
    r = client.post("/channels", json={"command": "claude"}, headers=auth)
    assert r.status_code == 201
    assert fake_tmux.argv_for("new-session")
    assert r.json()["channel"]["live"] is True


def test_create_channel_without_tmux_is_502(client, auth, fake_tmux):
    fake_tmux.installed = False
    r = client.post("/channels", json={}, headers=auth)
    assert r.status_code == 502


def test_create_channel_requires_a_token(client):
    assert client.post("/channels", json={}).status_code == 401


def test_kill_ends_the_pane_but_keeps_the_thread(client, auth, fake_tmux):
    r = client.post("/channels/0/kill", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # Recorded as a control action, not as something he "said".
    assert body["event"]["kind"] == "control"
    assert body["event"]["body"] == "kill"
    assert body["channel"]["live"] is False
    assert all(p[0] != "%0" for p in fake_tmux.panes)
    # History is still readable -- the channel outlives the pane.
    history = client.get("/channels/0/history", headers=auth)
    assert history.status_code == 200


def test_kill_a_dead_pane_is_404(client, auth):
    assert client.post("/channels/99/kill", headers=auth).status_code == 404


def test_kill_at_host_is_404(client, auth):
    # @host has no pane; killing it would claim the box was stoppable.
    assert client.post("/channels/@host/kill", headers=auth).status_code == 404
