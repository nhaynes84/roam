"""bctl -- unit tests for the CLI argument mapping (no browser needed).

The daemon (driver.py) needs Chromium and is exercised manually / in the live smoke;
`build()` is pure and is where the argv-to-command contract lives, so it is worth
locking down here. Run with any python that has pytest:
    ../hub/.venv/bin/python -m pytest test_bctl.py
"""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

# `bctl` has no .py extension, so point importlib at a source loader explicitly.
_loader = SourceFileLoader("bctl", str(Path(__file__).resolve().parent / "bctl"))
_spec = importlib.util.spec_from_loader("bctl", _loader)
bctl = importlib.util.module_from_spec(_spec)
_loader.exec_module(bctl)


def test_goto_and_click():
    assert bctl.build(["goto", "example.com"]) == {"action": "goto", "url": "example.com"}
    assert bctl.build(["click", "#submit"]) == {"action": "click", "selector": "#submit"}


def test_fill_and_type_take_selector_and_text():
    assert bctl.build(["fill", "#q", "hello world"]) == {
        "action": "fill", "selector": "#q", "text": "hello world"}
    assert bctl.build(["type", "#q", "abc"]) == {
        "action": "type", "selector": "#q", "text": "abc"}


def test_press_key_only_vs_selector_and_key():
    assert bctl.build(["press", "Enter"]) == {"action": "press", "key": "Enter"}
    assert bctl.build(["press", "#x", "Tab"]) == {
        "action": "press", "selector": "#x", "key": "Tab"}


def test_wait_numeric_is_ms_else_selector():
    assert bctl.build(["wait", "2000"]) == {"action": "wait", "ms": 2000}
    assert bctl.build(["wait", "#results"]) == {"action": "wait", "selector": "#results"}


def test_text_defaults_to_body():
    assert bctl.build(["text"]) == {"action": "text", "selector": "body"}
    assert bctl.build(["text", "main"]) == {"action": "text", "selector": "main"}


def test_screenshot_path_and_full_flag():
    assert bctl.build(["screenshot"]) == {"action": "screenshot", "path": "", "full": False}
    assert bctl.build(["screenshot", "/tmp/x.png", "--full"]) == {
        "action": "screenshot", "path": "/tmp/x.png", "full": True}


def test_no_arg_verbs():
    for verb in ("snapshot", "where", "back", "forward"):
        assert bctl.build([verb]) == {"action": verb}


def test_eval_carries_the_js():
    assert bctl.build(["eval", "document.title"]) == {
        "action": "eval", "js": "document.title"}


def test_unknown_command_exits():
    with pytest.raises(SystemExit):
        bctl.build(["frobnicate", "x"])
