"""The Apps shelf: who sees which tile, and where a client is told to point.

The two failure modes worth a test are both quiet ones. A visibility rule that leaks
puts one person's app on another person's home screen; a URL built from the wrong host
produces a tile that works on talos and is dead on every device that matters.
"""

from __future__ import annotations

import apps


class TestVisibility:
    def test_shared_apps_are_on_everyones_shelf(self):
        for who in apps.KNOWN_USERS:
            ids = [a.id for a in apps.visible_for(who)]
            assert "stream" in ids
            assert "encountable" in ids, "owner: 'encountable is shared'"

    def test_a_private_app_is_only_on_its_owners_shelf(self):
        registry = apps.REGISTRY + (
            apps.App(id="ledger", label="Ledger", subtitle="", icon="x",
                     port=9999, scope=apps.PRIVATE, owner="nick"),
        )
        assert "ledger" in [a.id for a in apps.visible_for("nick", registry)]
        assert "ledger" not in [a.id for a in apps.visible_for("jeanne", registry)]

    def test_an_unknown_name_gets_shared_only_not_the_owners_shelf(self):
        """⚠️ The tempting fallback is 'unknown means the owner', because his was the
        only shelf for months. That hands his private apps to anyone who fat-fingers
        the header. Showing too little is the correct direction to fail."""
        registry = apps.REGISTRY + (
            apps.App(id="ledger", label="Ledger", subtitle="", icon="x",
                     port=9999, scope=apps.PRIVATE, owner="nick"),
        )
        ids = [a.id for a in apps.visible_for("nobody", registry)]
        assert "ledger" not in ids
        assert "stream" in ids

    def test_no_name_means_the_owner(self):
        assert [a.id for a in apps.visible_for(None)] == \
               [a.id for a in apps.visible_for("nick")]

    def test_case_and_padding_do_not_change_who_you_are(self):
        assert [a.id for a in apps.visible_for("  Jeanne ")] == \
               [a.id for a in apps.visible_for("jeanne")]


class TestUrls:
    def test_the_url_uses_the_host_the_client_reached_us_on(self):
        """★★ The phone loading 127.0.0.1:3456 gets the phone, not talos."""
        enc = apps.find("encountable")
        assert apps.url_for(enc, "100.67.237.109") == \
            "http://100.67.237.109:3456/pick-user"
        assert apps.url_for(enc, "127.0.0.1") == "http://127.0.0.1:3456/pick-user"

    def test_an_internal_app_has_no_url_to_open(self):
        assert apps.url_for(apps.find("stream"), "100.67.237.109") is None
        assert apps.find("stream").hosted is False


class TestWireShape:
    def test_a_hosted_tile_reports_its_liveness_and_that_it_can_be_started(self):
        row = apps.to_json(apps.find("encountable"), "talos", live=False)
        assert row["startable"] is True
        assert row["live"] is False
        assert row["shared"] is True

    def test_an_internal_tile_reports_unknown_liveness_not_dead(self):
        """`false` would dim Stream, which works perfectly and has no port to ask."""
        row = apps.to_json(apps.find("stream"), "talos")
        assert row["live"] is None
        assert row["startable"] is False
        assert row["url"] is None


class TestRegistry:
    def test_ids_are_unique(self):
        ids = [a.id for a in apps.REGISTRY]
        assert len(ids) == len(set(ids))

    def test_every_hosted_app_can_be_started(self):
        """⚠️ A hosted tile with no service is the exact thing he complained about:
        a link that lands on a dead port and cannot do anything about it."""
        for app in apps.REGISTRY:
            # ★ A self-hosted tile (served by the hub on its own port) is exempt:
            #   there is no separate service to start, and it is never a dead port
            #   while the hub is answering. Every OTHER hosted tile must be startable.
            if app.hosted and not app.self_hosted:
                assert app.service, f"{app.id} is hosted but has no launchd label"

    def test_internal_apps_carry_neither_port_nor_service(self):
        for app in apps.REGISTRY:
            if app.internal:
                assert app.port is None and app.service is None

    def test_find_misses_cleanly(self):
        assert apps.find("nope") is None


class TestRoutes:
    """The two things the shelf needs from the machine."""

    def test_the_shelf_needs_the_token(self, client):
        assert client.get("/apps").status_code == 401

    def test_the_shelf_lists_tiles_with_urls_the_caller_can_reach(self, client, auth):
        body = client.get("/apps", headers=auth).json()
        by_id = {a["id"]: a for a in body["apps"]}
        assert "stream" in by_id and "encountable" in by_id
        # TestClient reaches us on "testserver"; the URL must come back addressed
        # there rather than at a hard-coded loopback.
        assert by_id["encountable"]["url"].startswith("http://testserver:3456")
        assert by_id["stream"]["url"] is None

    def test_a_hosted_tile_reports_whether_it_is_answering(self, client, auth):
        body = client.get("/apps", headers=auth).json()
        enc = next(a for a in body["apps"] if a["id"] == "encountable")
        assert enc["live"] in (True, False), "a hosted tile always has a verdict"
        assert enc["startable"] is True

    def test_an_internal_tile_is_never_reported_dead(self, client, auth):
        body = client.get("/apps", headers=auth).json()
        stream = next(a for a in body["apps"] if a["id"] == "stream")
        assert stream["live"] is None

    def test_the_shelf_is_drawn_for_the_named_user(self, client, auth):
        shared_only = client.get("/apps?user=nobody", headers=auth).json()["apps"]
        assert all(a["shared"] for a in shared_only)

    def test_starting_something_that_is_not_an_app_is_a_404(self, client, auth):
        assert client.post("/apps/nope/start", headers=auth).status_code == 404

    def test_an_internal_app_cannot_be_started(self, client, auth):
        """⚠️ Stream has no service; a start route that accepted it would reach
        launchctl with `gui/501/None`."""
        assert client.post("/apps/stream/start", headers=auth).status_code == 404


class TestTheShelfAsShipped:
    """The tiles that actually exist, and the two rules they encode."""

    def test_the_household_apps_are_shared_and_the_kanban_is_not(self):
        hers = [a.id for a in apps.visible_for("jeanne")]
        assert {"stream", "files", "encountable"} <= set(hers)
        assert "vikunja" not in hers, "his operating picture, not a household app"
        assert "vikunja" in [a.id for a in apps.visible_for("nick")]


class TestCredentialHandling:
    """⚠️ Which apps may be handed the hub's bearer token.

    Notes was unauthenticated on the tailnet until a second person joined it, and
    marking the TILE private only decided which shelf it appeared on. It now requires
    the token — but that privilege must never spread by default.
    """

    def test_our_own_service_may_receive_the_token(self):
        assert apps.find("notes").authed is True

    def test_third_party_services_never_do(self):
        """EnCountAble and Vikunja run their own auth. Handing them the hub token
        would give them the keys to everything else."""
        for app_id in ("encountable", "vikunja"):
            assert apps.find(app_id).authed is False

    def test_authed_defaults_to_false(self):
        probe = apps.App(id="x", label="X", subtitle="", icon="x", port=1, service="s")
        assert probe.authed is False

    def test_the_wire_tells_the_client_which_is_which(self):
        row = apps.to_json(apps.find("notes"), "talos", live=True)
        assert row["authed"] is True
