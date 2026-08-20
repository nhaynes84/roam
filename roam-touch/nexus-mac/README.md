# Nexus for macOS

Native SwiftUI client for the ROAM Touch hub (`../hub`, contract in `../hub/API.md`).
Same hub, same channels, same rules as the Android Nexus — this is the desk view.

- Build: `swift build` (Command Line Tools are enough; no Xcode required)
- Test: `swift test`
- Run (dev): `swift run`
- App bundle: `tools/bundle.sh` → `dist/Nexus.app` (ad-hoc signed)

Config resolution order:
1. `ROAM_HUB_URL` / `ROAM_HUB_TOKEN` environment variables
2. `~/.config/roam-nexus/config.json` — `{"base_url": "http://talos:8787", "token": "…"}`
3. On talos itself: `../hub/hub-token.txt` with the default base URL

House rules carried over from the Android client (see `hub/API.md` and the
roam-touch-channels memory before changing behaviour):
- Summary first, body on demand. Never re-derive summaries client-side.
- Nothing speaks or notifies on its own. Coverage/push is the hub+bridge's job.
- Presence covers ONLY the channel on screen. `covers_all` from a client with a
  screen once silenced the wearer's arm for a day.
- Interrupts go through `POST /channels/{pane}/interrupt`, never control bytes
  through `/send`.
