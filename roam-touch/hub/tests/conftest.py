"""Shared fixtures. tmux is mocked at exactly one boundary: `channels._run`,
the single place the channel layer shells out. Everything above it -- argument
construction, output parsing, error mapping -- runs for real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import channels as channels_mod
import hub as hub_mod
from store import Store

TOKEN = "test-token-not-a-secret"


class FakeTmux:
    """A tmux server that exists only in memory.

    Holds panes as (pane_id, session, window, index, command, title) and
    records every argv the channel layer builds, so tests can assert on the
    exact flags used (`-l --`, bracketed paste, capture ranges).
    """

    def __init__(self) -> None:
        self.panes: list[tuple[str, str, int, int, str, str]] = [
            ("%0", "main", 0, 0, "node", "◑ Roam Touch rebuild discussion"),
            ("%1", "augment", 1, 0, "node", "✳ Augment things"),
        ]
        self.pane_options: dict[str, dict[str, str]] = {}
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self.pane_output: dict[str, str] = {}
        self.server_running = True
        self.installed = True
        self.fail_send_with: str | None = None

    # -- test helpers ----------------------------------------------------
    def add_pane(self, pane_id, session="main", window=0, index=1, command="node",
                 title="new pane") -> None:
        self.panes.append((pane_id, session, window, index, command, title))

    def kill_pane(self, pane_id: str) -> None:
        self.panes = [p for p in self.panes if p[0] != pane_id]

    def retitle(self, pane_id: str, title: str) -> None:
        self.panes = [
            (p[0], p[1], p[2], p[3], p[4], title) if p[0] == pane_id else p
            for p in self.panes
        ]

    def _next_pane_id(self) -> str:
        highest = max((int(p[0].lstrip("%")) for p in self.panes), default=-1)
        return f"%{highest + 1}"

    def argv_for(self, subcommand: str) -> list[tuple[str, ...]]:
        return [args for args, _ in self.calls if args and args[0] == subcommand]

    # -- the mocked boundary ---------------------------------------------
    def __call__(self, args, stdin=None, check=True):
        args = tuple(args)
        self.calls.append((args, stdin))
        if not self.installed:
            raise channels_mod.TmuxError("tmux is not installed")
        sub = args[0] if args else ""
        if sub == "list-panes":
            if not self.server_running:
                raise channels_mod.TmuxError("no server running on /tmp/tmux-501/default")
            return "".join(
                "\t".join((
                    pid, sess, str(win), str(idx), cmd, title,
                    self.pane_options.get(pid, {}).get("@roam_label", ""),
                )) + "\n"
                for pid, sess, win, idx, cmd, title in self.panes
            )
        if sub == "capture-pane":
            pane_id = args[args.index("-t") + 1]
            return self.pane_output.get(pane_id, f"output of {pane_id}\n")
        if sub in ("send-keys", "load-buffer", "paste-buffer"):
            if self.fail_send_with:
                raise channels_mod.TmuxError(self.fail_send_with)
            return ""
        if sub == "new-window":
            if not self.server_running:
                raise channels_mod.TmuxError("no server running on /tmp/tmux-501/default")
            target = args[args.index("-t") + 1].rstrip(":") if "-t" in args else "main"
            new_id = self._next_pane_id()
            self.add_pane(new_id, session=target, window=len(self.panes), index=0,
                          command=args[-1], title="")
            return f"{new_id}\n"
        if sub == "new-session":
            self.server_running = True
            session = args[args.index("-s") + 1] if "-s" in args else "agents"
            new_id = self._next_pane_id()
            self.add_pane(new_id, session=session, window=0, index=0,
                          command=args[-1], title="")
            return f"{new_id}\n"
        if sub == "kill-pane":
            self.kill_pane(args[args.index("-t") + 1])
            return ""
        if sub == "set-option":
            pane_id = args[args.index("-t") + 1]
            self.pane_options.setdefault(pane_id, {})[args[-2]] = args[-1]
            return ""
        if sub == "select-pane":
            if "-T" in args:
                self.retitle(args[args.index("-t") + 1], args[args.index("-T") + 1])
            return ""
        return ""


@pytest.fixture
def fake_tmux(monkeypatch) -> FakeTmux:
    fake = FakeTmux()
    monkeypatch.setattr(channels_mod, "_run", fake)
    return fake


@pytest.fixture
def store(tmp_path) -> Store:
    st = Store(tmp_path / "hub.sqlite")
    yield st
    st.close()


@pytest.fixture
def settings(tmp_path) -> hub_mod.Settings:
    return hub_mod.Settings(
        token=TOKEN,
        db_path=tmp_path / "hub.sqlite",
        token_file=tmp_path / "token.txt",
        poll_interval=0.05,
    )


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(settings, store, fake_tmux):
    """TestClient with the lifespan (and therefore the poller) running."""
    app = hub_mod.create_app(settings=settings, store=store)
    with TestClient(app) as c:
        yield c
