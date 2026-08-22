# Nexus Voice

Speak to the ROAM Touch channels through Home Assistant. Wake word, then
*"Nexus, add the OPV result to the espresso notes"* — it finds the right
channel, sends it, and speaks the answer back on the device you asked from.

## Why HA is in the middle

The hub binds to the **tailnet address only** (`100.67.237.109:8787`); the LAN
gets connection refused. An ESP32 cannot run Tailscale — the fact that killed
the MCU version of ROAM Touch. So a satellite can never reach the hub directly.

`argus` is the only box on both networks. HA is therefore not a convenience
here, it is the bridge, and the integration lives *inside* it — which also
means it calls `tts.speak` through the service registry and needs no
long-lived access token.

## The loop

```
ESP32-S3 / Sonos ──wake word──▶ HA (argus)
                                  │  Whisper @ talos:10300
                                  ▼
                          local intents first  ──▶ lights, scenes  (<1s)
                                  │ "Nexus, …"
                                  ▼
                          nexus_voice agent ──▶ hub /send ──▶ tmux pane
                                  │
                          "Sent to Gaggia Build."   ◀── spoken immediately
                                  ⋮
                          outcome event ──▶ tts.speak ──▶ same device
```

**Nothing here waits for Claude.** Assist is synchronous and wants an answer in
about a second; a Claude turn takes minutes. The agent acknowledges, and the
answer arrives later as an announcement. That is the hub's own shape — receipt
now, outcome later.

## How a channel is chosen

Three layers, cheapest and most certain first:

1. **String** — exact label, then subset of content words. Free and certain.
2. **Embedding** — `nomic-embed-text` on talos, over the channel's *label plus
   recent history*.
3. **Neither** — spawn a new channel.

Two candidates within `AMBIGUITY_DELTA` produce a question rather than a guess.
Misfiling a note corrupts two threads; one extra second of conversation is
cheaper.

### ⚠️ What the measurements actually said (2026-08-21)

Embedding the **label alone does not work**. "the espresso notes" scored 0.365
against "Gaggia Build", while an unrelated "jeep brake booster" scored 0.504
against the same channel. Short proper nouns carry almost no signal.

Embedding **label + history** fixed the ranking but not the scale — the useful
signal is the **margin between #1 and #2**, not the absolute score:

| utterance | #1 | #2 | margin | correct |
|---|---|---|---|---|
| the espresso notes | 0.508 | 0.435 | 0.073 | ✓ Gaggia Build |
| wrist display font | 0.431 | 0.367 | 0.064 | ✓ Roam Touch |
| the augment board | 0.425 | 0.375 | 0.050 | ✓ Augment |
| jeep brake booster | 0.422 | 0.418 | **0.004** | ✓ spawn |

When nothing fits, the scores go **flat**. That is the only reliable "none of
these" signal available. ⚠️ **n=5** — the threshold fits the measurements, it
is not validated by them. Re-run `tools/probe_routing.py` against real traffic
before trusting it further.

`cwd` is kept but is **not load-bearing**: every live channel on the hub reports
`/Users/talos`, because panes spawn in `$HOME` unless someone passes `cwd`. It
breaks ties and decides nothing.

## Laws this obeys

* **Nothing ever speaks on its own.** Audio fires only for an answer he asked
  for by voice, on the device he asked from. Auto-speak was built into the
  Channels app once and killed within the hour.
* **Speak the `summary`, never the `body`.** Capped at 280 chars, markdown
  stripped — and short enough for a satellite with no echo cancellation, which
  cannot hear you interrupt it.
* **Reply where the last message came from.** A satellite is one more place
  that rule applies to; HA hands us `satellite_id` so it needs no identity
  scheme of its own.

## Layout

| file | what |
|---|---|
| `matcher.py` | which channel — pure, no HA, no network |
| `phrasing.py` | trigger stripping, channel naming — pure |
| `runtime.py` | channel index, embedding cache, hub WS, delivery map |
| `hub.py` · `embeddings.py` | clients |
| `conversation.py` · `__init__.py` · `config_flow.py` | HA glue, decides nothing |

Tests: `.venv/bin/python -m pytest tests/ -q` (53). The HA-facing modules are
verified by importing them against real HA on argus, since HA is not installed
on talos.

## Deployed

`/home/homeassistant/.homeassistant/custom_components/nexus_voice` on **argus**.
Restart HA after changing it: `sudo systemctl restart home-assistant@homeassistant`.
