"""roam-browser -- a headless Chromium the agent can drive over web pages.

★ The capability ported (in design) from openclaw's `extensions/browser`: give the
  agent real web interaction -- navigate, click, type, read, screenshot -- not just
  fetch. Headless on talos, NOT the owner's Mac Chrome (his ruling: "drive headless
  to do things you can't now that require web interactions").

Why a DAEMON and not a one-shot CLI: an agent drives interactively -- goto, read,
decide, click, read again. A one-shot process would lose the live page (and its
in-memory JS state) between every step; only cookies would persist. So a long-lived
process holds ONE Chromium + one live page, and `bctl` sends it commands.

⚠️ Sync Playwright is single-threaded: every call must run on the thread that
   started it. The server is deliberately single-threaded (`HTTPServer`, not
   threading) so every command lands on that one thread and nothing needs locking.
   Commands serialise, which is exactly right for one agent driving one page.

Bind: 127.0.0.1 only. This drives a browser as the talos user; it is not for the
tailnet.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from playwright.sync_api import Error as PWError
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("ROAM_BROWSER_PORT", "8791"))
#: Cookies, localStorage and logins live here, so a login survives a daemon
#: restart -- the whole point of a persistent context.
PROFILE_DIR = Path(os.environ.get("ROAM_BROWSER_PROFILE", HERE / "profile"))
SHOTS_DIR = Path(os.environ.get("ROAM_BROWSER_SHOTS", HERE / "shots"))
DEFAULT_TIMEOUT_MS = 15000


class Browser:
    """The one live Chromium + page. All methods run on the server thread."""

    def __init__(self) -> None:
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    # -- each returns a JSON-able dict; exceptions are caught by the handler --

    def goto(self, url: str, **_) -> dict:
        if "://" not in url:
            url = "https://" + url
        self.page.goto(url, wait_until="domcontentloaded")
        return {"url": self.page.url, "title": self.page.title()}

    def click(self, selector: str, **_) -> dict:
        self.page.click(selector)
        return {"clicked": selector, "url": self.page.url}

    def fill(self, selector: str, text: str = "", **_) -> dict:
        self.page.fill(selector, text)
        return {"filled": selector}

    def type(self, selector: str, text: str = "", **_) -> dict:
        self.page.press_sequentially(selector, text) if hasattr(
            self.page, "press_sequentially") else self.page.type(selector, text)
        return {"typed": selector}

    def press(self, selector: str = "body", key: str = "Enter", **_) -> dict:
        self.page.press(selector, key)
        return {"pressed": key, "url": self.page.url}

    def select(self, selector: str, value: str = "", **_) -> dict:
        self.page.select_option(selector, value)
        return {"selected": value}

    def wait(self, selector: str = "", ms: int = 0, **_) -> dict:
        if selector:
            self.page.wait_for_selector(selector)
            return {"waited_for": selector}
        self.page.wait_for_timeout(int(ms) or 500)
        return {"waited_ms": int(ms) or 500}

    def text(self, selector: str = "body", **_) -> dict:
        body = self.page.inner_text(selector)
        return {"text": body[:20000], "chars": len(body)}

    def html(self, selector: str = "", **_) -> dict:
        html = self.page.inner_html(selector) if selector else self.page.content()
        return {"html": html[:40000], "chars": len(html)}

    def snapshot(self, **_) -> dict:
        """A compact list of the visible, interactive things on the page -- what an
        agent needs to decide what to click, far cheaper than the whole DOM."""
        js = """() => {
          const vis = el => { const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight * 1.5; };
          const label = el => (el.innerText || el.value || el.getAttribute('aria-label')
            || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().slice(0, 80);
          const sel = el => {
            if (el.id) return '#' + CSS.escape(el.id);
            if (el.getAttribute('name')) return el.tagName.toLowerCase()+'[name="'+el.getAttribute('name')+'"]';
            return null;
          };
          const out = [];
          for (const el of document.querySelectorAll('a,button,input,textarea,select,[role=button],[onclick]')) {
            if (!vis(el)) continue;
            const t = label(el); if (!t && el.tagName !== 'INPUT') continue;
            out.push({ tag: el.tagName.toLowerCase(), type: el.type || '', text: t, selector: sel(el),
                       href: el.getAttribute('href') || undefined });
            if (out.length >= 120) break;
          }
          return { title: document.title, url: location.href, items: out };
        }"""
        return self.page.evaluate(js)

    def eval(self, js: str = "", **_) -> dict:
        return {"result": self.page.evaluate(js)}

    def screenshot(self, path: str = "", full: bool = False, **_) -> dict:
        # The agent Reads the PNG path directly (the Read tool renders images), so
        # there is no need to shovel base64 through the CLI on every shot.
        target = Path(path) if path else SHOTS_DIR / "shot.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(target), full_page=bool(full))
        return {"path": str(target), "bytes": target.stat().st_size}

    def back(self, **_) -> dict:
        self.page.go_back()
        return {"url": self.page.url}

    def forward(self, **_) -> dict:
        self.page.go_forward()
        return {"url": self.page.url}

    def where(self, **_) -> dict:
        return {"url": self.page.url, "title": self.page.title()}

    def close(self) -> None:
        try:
            self.ctx.close()
        finally:
            self._pw.stop()


def make_handler(browser: Browser):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # quiet
            pass

        def _send(self, code: int, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/ping":
                self._send(200, {"ok": True, **browser.where()})
            else:
                self._send(404, {"ok": False, "error": "GET only /ping"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"ok": False, "error": "bad json"})
            action = req.pop("action", "")
            if action == "shutdown":
                self._send(200, {"ok": True, "bye": True})
                browser.close()
                # stop serve_forever from this thread's request
                raise SystemExit(0)
            fn = getattr(browser, action, None)
            if fn is None or action.startswith("_"):
                return self._send(400, {"ok": False, "error": f"unknown action {action!r}"})
            try:
                result = fn(**req) or {}
                self._send(200, {"ok": True, **result})
            except PWError as exc:
                self._send(200, {"ok": False, "error": str(exc).splitlines()[0]})
            except Exception as exc:  # never take the daemon down on one bad command
                self._send(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return Handler


def main() -> int:
    browser = Browser()
    server = HTTPServer((HOST, PORT), make_handler(browser))
    sys.stderr.write(f"roam-browser on {HOST}:{PORT} (profile {PROFILE_DIR})\n")
    sys.stderr.flush()
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
