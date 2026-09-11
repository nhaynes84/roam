"""`POST /notify` -- "tell the wearer this", from a shell.

Every agent on this box is told to push status to the arm. Before this
endpoint existed, `roam-msg` shelled straight to `adb` and the phone rang while
he sat at the keyboard: the one policy the hub owns -- **reply where the last
message came from** -- was applied to outcomes and bypassed by everything else.

So a notice is an event like any other: stored, stamped with the coverage in
force when it landed, searchable in the ledger afterwards, and delivered (or
not) by the bridge. What is under test here is that a notice behaves like a
first-class event *without* pretending to be a conversation: it must never make
a channel look like it owes an answer, and it must never move the conversation
to the keyboard or to the phone.
"""

from __future__ import annotations

import pytest

from store import HOST_CHANNEL_ID, EventKind


def notify(client, auth, text: str, **body):
    return client.post("/notify", json={"text": text, **body}, headers=auth)


# ------------------------------------------------------------ the basics


def test_notify_requires_a_token(client):
    assert client.post("/notify", json={"text": "hi"}).status_code == 401


def test_empty_text_is_rejected(client, auth):
    assert notify(client, auth, "").status_code == 422


def test_a_notice_lands_in_the_channel_it_names(client, auth):
    body = notify(client, auth, "build finished", pane="0").json()
    assert body["event"]["kind"] == EventKind.NOTICE.value
    assert body["event"]["pane_id"] == "%0"
    assert body["event"]["body"] == "build finished"
    assert body["event"]["summary"] == "build finished"

    history = client.get("/channels/0/history", headers=auth).json()["events"]
    assert [e["body"] for e in history if e["kind"] == "notice"] == ["build finished"]


def test_a_notice_is_not_a_prompt_the_channel_owes_an_answer_to(client, auth):
    notify(client, auth, "still going", pane="0")
    channel = client.get("/channels/0", headers=auth).json()["channel"]
    assert channel["status"] == "idle"


def test_a_notice_does_not_move_the_conversation(client, auth, store):
    """A status line is not somebody talking. `last_input_source` decides where
    real answers go; a notice must not be able to redirect them."""
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "run the tests"},
        headers=auth,
    )
    before = store.get_channel("%0").last_input_source
    notify(client, auth, "tests running", pane="0")
    assert store.get_channel("%0").last_input_source == before


# ------------------------------------------------------- the whole point


def test_a_notice_from_the_keyboard_channel_is_not_pushed(client, auth):
    """He typed the prompt in tmux, so he is watching that pane. The agent's
    own status lines are the loudest thing on the box -- they must obey the
    same rule as the answer they are about."""
    client.post(
        "/events",
        json={"pane": "%0", "kind": "receipt", "body": "fix the bug"},
        headers=auth,
    )
    body = notify(client, auth, "found it", pane="0").json()
    assert body["push"] is False
    assert "tmux-input" in body["reason"]
    assert body["event"]["coverage"]["covered"] is True


def test_a_notice_on_a_channel_he_is_talking_to_from_roam_is_pushed(client, auth, store):
    store.set_channel_input("%0", "app")
    body = notify(client, auth, "done", pane="0").json()
    assert body["push"] is True
    assert body["event"]["coverage"]["covered"] is False


def test_a_notice_is_suppressed_while_the_panel_is_foregrounded(client, auth):
    client.post(
        "/presence",
        json={"source": "roam-app", "covers_all": True, "ttl_s": 60},
        headers=auth,
    )
    body = notify(client, auth, "done", pane="0").json()
    assert body["push"] is False
    assert "roam-app" in body["reason"]


def test_an_unheard_of_channel_still_pushes(client, auth):
    """Unknown means push. A missed message is worse than a redundant one."""
    body = notify(client, auth, "hello", pane="0").json()
    assert body["push"] is True
    assert body["event"]["coverage"]["known"] is False


# --------------------------------------------------- when there is no pane


def test_a_notice_with_no_pane_lands_on_the_host_channel(client, auth):
    """Agents run from launchd and cron too, with no `$TMUX_PANE` to claim.
    Such a message still belongs in the ledger, and it belongs somewhere the
    panel can show it -- not attributed to a pane that did not send it."""
    body = notify(client, auth, "nightly backup failed").json()
    assert body["event"]["pane_id"] == HOST_CHANNEL_ID
    assert body["push"] is True  # nothing covers a channel nobody talks to

    history = client.get(
        f"/channels/{HOST_CHANNEL_ID}/history", headers=auth
    ).json()["events"]
    assert history[-1]["body"] == "nightly backup failed"


def test_the_host_channel_is_hidden_from_every_users_list(client, auth):
    """★ Owner: "i don't need that shit ... keep it for YOU to monitor, and if shit
    does go there, that's a bug we should fix." The @host dead-letter is hidden from
    the channel list -- but it still EXISTS and still catches pane-less notices
    (verified in test_a_notice_with_no_pane_lands_on_the_host_channel), which the box
    side watches."""
    notify(client, auth, "from cron")
    channels = client.get("/channels", headers=auth).json()["channels"]
    assert all(c["pane_id"] != HOST_CHANNEL_ID for c in channels)


def test_nothing_can_be_typed_into_the_host_channel(client, auth):
    """It is a noticeboard, not a terminal."""
    assert client.post(
        f"/channels/{HOST_CHANNEL_ID}/send", json={"text": "ls"}, headers=auth
    ).status_code == 404
    assert client.post(
        f"/channels/{HOST_CHANNEL_ID}/interrupt", json={}, headers=auth
    ).status_code == 404


def test_a_nonsense_pane_is_still_rejected(client, auth):
    """The host channel is one exact literal, not a hole in the pane check."""
    assert notify(client, auth, "hi", pane="; rm -rf /").status_code == 400
    assert notify(client, auth, "hi", pane="@anything-else").status_code == 400


# ------------------------------------------------------------- the ledger


def test_a_notice_is_pushed_to_websocket_clients_like_any_event(client, auth):
    from test_api import next_frame

    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()  # hello
        notify(client, auth, "deploy done", pane="1")
        frame = next_frame(ws, "event", where=lambda f: f["event"]["kind"] == "notice")
    assert frame["event"]["body"] == "deploy done"


def test_a_channel_nobody_has_heard_of_is_announced_before_its_first_notice(
    client, auth, fake_tmux
):
    """The bridge labels a notification with the channel name -- which it only
    has if it has been told about the channel. Without this, the first message
    from a new channel reads `@host: …` instead of `⌁ talos: …`, and the first
    one is the one that most needs to say who is speaking."""
    from test_api import next_frame

    with client.websocket_connect("/ws", headers=auth) as ws:
        ws.receive_json()  # hello
        notify(client, auth, "from cron")
        frame = next_frame(
            ws, "channel", where=lambda f: f["channel"]["pane_id"] == HOST_CHANNEL_ID
        )
        assert frame["channel"]["label"]
        event = next_frame(ws, "event", where=lambda f: f["event"]["kind"] == "notice")
        assert event["event"]["pane_id"] == HOST_CHANNEL_ID


def test_who_sent_it_is_recorded(client, auth):
    body = notify(client, auth, "hi", pane="0", source="roam-msg", meta={"host": "talos"}).json()
    assert body["event"]["meta"]["source"] == "roam-msg"
    assert body["event"]["meta"]["host"] == "talos"


def test_notices_show_up_in_the_global_events_feed(client, auth):
    notify(client, auth, "one", pane="0")
    events = client.get("/events", headers=auth).json()["events"]
    assert any(e["kind"] == "notice" and e["body"] == "one" for e in events)
