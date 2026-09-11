"""ptyrun -- integration tests against a REAL tmux on the isolated roampty socket.

These drive actual processes on real ptys (that is the whole point of the tool), so
they are integration, not unit, tests. Each cleans the roampty server around itself.
Run with any python that has pytest, e.g. the hub venv:
    ../hub/.venv/bin/python -m pytest test_ptyrun.py
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

PTY = str(Path(__file__).resolve().parent / "ptyrun")


def run(*args):
    return subprocess.run([PTY, *args], capture_output=True, text=True)


def runj(*args):
    return json.loads(run(*args).stdout)


@pytest.fixture(autouse=True)
def clean_server():
    run("clean")
    yield
    run("clean")


def test_start_captures_output_and_exit_code():
    pid = runj("start", "--", "sh", "-c", "echo HELLO_PTY; exit 7")["id"]
    assert runj("wait", pid, "HELLO_PTY", "--timeout", "5")["matched"] is True
    time.sleep(0.4)  # let the process finish exiting
    d = runj("dead", pid)
    assert d["dead"] is True
    assert d["status"] == 7


def test_screen_reads_the_terminal():
    pid = runj("start", "--", "sh", "-c", "echo alpha; echo beta; sleep 3")["id"]
    runj("wait", pid, "beta", "--timeout", "5")
    screen = run("screen", pid).stdout
    assert "alpha" in screen and "beta" in screen


def test_interactive_send_reaches_the_program():
    # `cat` echoes stdin -- a minimal program that only works with a real tty.
    pid = runj("start", "--", "cat")["id"]
    runj("send", pid, "ping-pong", "--enter")
    assert runj("wait", pid, "ping-pong", "--timeout", "5")["matched"] is True
    runj("key", pid, "C-d")  # EOF -> cat exits cleanly


def test_list_shows_the_job_and_hides_the_anchor():
    pid = runj("start", "--name", "job1", "--", "sleep", "5")["id"]
    sessions = runj("list")["sessions"]
    assert pid in [s["id"] for s in sessions]
    assert all(s["name"] != "__anchor__" for s in sessions)  # anchor excluded


def test_kill_removes_a_session():
    pid = runj("start", "--", "sleep", "5")["id"]
    runj("kill", pid)
    assert pid not in [s["id"] for s in runj("list")["sessions"]]


def test_wait_times_out_cleanly():
    pid = runj("start", "--", "sleep", "5")["id"]
    r = run("wait", pid, "NEVER_APPEARS", "--timeout", "1")
    assert r.returncode == 3
    assert json.loads(r.stdout)["matched"] is False
