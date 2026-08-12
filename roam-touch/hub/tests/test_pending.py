"""What happens to a message written while the hub process is not running.

★ There is no file. Owner, on the dead-letter spool this replaced: *"you have a
DB for messages, why would we use a DL file and not a table or column flag in
the existing table"* -- a second store of record for the same data, with none of
the ledger's properties: no ids, no query, not in the search index, invisible to
every client.

The hub is a **local** service and `hub.sqlite` is a local file in WAL mode, so
`roam-msg` can always reach the ledger even when the service is down (owner:
*"if talos is down, how the fuck am i talking to you, lol"* -- Claude, the
agents, the hub and the bridge are all this one box). So the message goes
straight into the ledger flagged `pending`: it never reached the push path, and
the hub adopts it the moment it is running again.

`pending` is therefore transient state with a defined lifetime, not a second
history. In steady state nothing is pending.
"""

from __future__ import annotations

import pytest

from store import EventKind, Store


def test_an_event_is_not_pending_by_default(store):
    event = store.append("%0", EventKind.OUTCOME, "done")
    assert event.pending is False
    assert store.pending_count() == 0


def test_a_pending_event_is_a_normal_event_in_every_other_way(store):
    """It is in the thread, in the feed and in the search index. The flag says
    how it got in, not whether it counts."""
    store.append("%0", EventKind.NOTICE, "written while the hub was down", pending=True)
    assert [e.body for e in store.history("%0")] == ["written while the hub was down"]
    assert store.pending_count() == 1


def test_claiming_pending_events_returns_them_once(store):
    store.append("%0", EventKind.NOTICE, "one", pending=True)
    store.append("%0", EventKind.NOTICE, "two", pending=True)
    claimed = store.claim_pending()
    assert [e.body for e in claimed] == ["one", "two"]
    assert all(e.pending for e in claimed)
    assert store.pending_count() == 0
    assert store.claim_pending() == []  # nothing is ever adopted twice


def test_claiming_is_bounded(store):
    for i in range(5):
        store.append("%0", EventKind.NOTICE, str(i), pending=True)
    assert len(store.claim_pending(limit=2)) == 2
    assert store.pending_count() == 3


def test_the_flag_survives_a_reopen(tmp_path):
    """It has to outlive the crash that caused it."""
    path = tmp_path / "hub.sqlite"
    with Store(path) as first:
        first.append("%0", EventKind.NOTICE, "hi", pending=True)
    with Store(path) as second:
        assert second.pending_count() == 1


# ------------------------------------------------------- the hub adopts them


def test_the_hub_adopts_pending_events_and_pushes_them(client, auth, store):
    """The bridge delivers what the hub publishes. A message that went around
    the hub while it was down must still reach his arm when it comes back --
    otherwise the ledger row is just a nicer-looking dropped message."""
    from test_api import next_frame, wait_for

    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()  # hello
        # Written after the socket is up: the poller adopts within one tick,
        # and a subscriber that connected first must see it as a live event.
        store.append("%0", EventKind.NOTICE, "from while you were down", pending=True)
        frame = next_frame(
            ws,
            "event",
            limit=30,
            where=lambda f: f["event"]["body"] == "from while you were down",
        )
    assert frame["event"]["kind"] == "notice"
    wait_for(lambda: store.pending_count() == 0)


def test_status_reports_how_many_never_reached_the_push_path(client, auth, store):
    """A count nobody reads is the same failure as a file nobody reads."""
    store.append("%0", EventKind.NOTICE, "orphan", pending=True)
    assert "pending_events" in client.get("/status", headers=auth).json()


def test_notify_tells_the_caller_what_is_still_pending(client, auth, store):
    """`roam-msg`'s next successful call is the moment he is most likely to be
    told that an earlier one went around the hub."""
    store.append("%0", EventKind.NOTICE, "orphan", pending=True)
    body = client.post(
        "/notify", json={"text": "back up"}, headers=auth
    ).json()
    assert body["pending"] >= 1
