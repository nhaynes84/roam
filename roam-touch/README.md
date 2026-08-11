# ROAM Touch — a forearm terminal for the AI stack

Spec locked 2026-08-11. **Nothing built.**

> ⚠️ **This supersedes the 2026-08-10 revision of this file**, which specified an
> ESP32-3248S035C ("CYD") desk console. None of that survives — not the board, the form factor,
> the power model, or the audio plan. See [Why the CYD died](#why-the-cyd-died).

★ **This absorbs the wrist Roam.** They are no longer complementary devices. One arm-mounted unit
does target selection, push-to-talk, and display.

## THE THESIS

> **"A functional arm-strapped computer, voice-controlled predominantly, that frees me from
> sitting at a computer. NOT a phone strapped to my arm."** — owner, 2026-08-11

Voice is the input. The screen reads output and confirms input — you never *drive* from it. This is
not an aesthetic project; function first. Read this before proposing any UI.

## WHAT IT IS

A forearm bracer with a flip-up AMOLED panel, running Linux, that acts as a control
surface for every Claude session on every box you own — at home over WiFi, or anywhere over
Tailscale.

Think Slack, for AI tools, on your arm. **N devices × N targets; each target is one channel with
one call/response thread.** For V1, a channel is a tmux pane running Claude.

The interaction loop:

1. Pick the target channel on the touchscreen.
2. Push to talk. Whisper (already running on talos) transcribes it.
3. Panel shows **"send «transcript» to «channel»?"** → Send / Redo / Cancel.
   One confirmation covers both the words *and* the routing, so a good command can't land in the
   wrong session.
4. **Receipt** comes back immediately — it got there.
5. **Outcome** arrives whenever it's done, into that channel's thread, to read or hear.

## WHY LINUX, NOT AN MCU

★ **An ESP32 cannot run Tailscale.** That single fact drove the entire redesign.

Every earlier version of this document contorted itself around that limitation — BLE tethering to
a phone that *could* reach the tailnet, two transport paths, a protocol written twice. Moving to
Linux deletes all of it: the device is just a tailnet node, and "local" and "remote" become the
same code path with no phone in the loop.

It also hands back, for free: a native UI instead of LVGL partial buffers on 520 KB of SRAM,
working audio through ALSA, and a real application platform.

## LAYOUT

| where | contains |
|---|---|
| **Panel** (moves) | CM4 + 3.92" AMOLED 1080×1240, **married** so DSI never crosses the hinge · aluminium backplate · memory-LCD status strip on the outer face |
| **Base** (fixed) | BBQ20KBD keyboard, 5000 mAh cell stacked beneath it |
| **Band** | ESP32-C6 companion. The strap is a partial cuff, not a full wrap. |
| **Across the hinge** | power + keyboard I2C/USB **only** — nothing fast, nothing fragile |

Lid position is sensed by a **magnet in the panel and a hall sensor in the base**, so *zero*
conductors cross the hinge for sensing, and there's no switch to wear out.

## COMPUTE — Raspberry Pi CM4 (2 GB, eMMC, external antenna)

- ⚠️ **Pi Zero 2 W has no DSI at all** (CSI only). It cannot take this panel natively.
- **Radxa Zero 3W** is tempting — 65×30 mm, WiFi 6 — but RK3566 mainline support lags Raspberry
  Pi's by a wide margin, which means writing the panel driver inside a vendor BSP kernel.
- **CM4 wins on display stack**, which is the scarce resource here. Not CPU.
- **eMMC, not SD** — boot speed is load-bearing (see power states) and SD cards corrupt under the
  abrupt power cuts the companion performs.
- **External antenna** — a body absorbs 2.4 GHz. Mount it on the outer face, away from the arm.

## ⚠️⚠️ HARD GATE: NO PANEL WITHOUT A DATASHEET

The AMOLED is not a Pi-supported display. Its timings and init sequence get written by hand from
the manufacturer's documentation.

**No datasheet → DSI is impossible.** The fallback is an HDMI→MIPI driver board, which works
precisely because it contains a controller that already knows the panel. Plenty of sellers ship
these modules with nothing but a wiring photo. **Never buy on specs alone.**

## POWER — three states

| state | on | draw | wake |
|---|---|---|---|
| open / active | Linux + AMOLED | 1–2 W | — |
| closed, **warm** (recent use) | Linux idling, screen off | ~300 mA | instant |
| closed, **cold** (>30 min idle) | companion only, Linux **power-gated** | ~110 µA | boot |

At 5000 mAh: hours active, 2–3 days of instant-on standby, months truly stowed. The warm→cold timer
means you never eat a boot mid-use, only when returning hours later.

### ⚠️ Do not chase suspend-to-RAM

ARM Linux suspend is a swamp. PinePhone Pro draws **1250 mW in s2idle**; most postmarketOS mainline
devices lack runtime power management entirely; where it exists it fails intermittently (suspend
breaking on certain kernels, or when the charger is connected).

The one platform that does it well — PinePhone, ~100 h idle — gets there via **crust**, firmware
running on a *separate co-processor* whose only job is babysitting power. The mobile-Linux world
independently invented our companion architecture.

**So: power-gate instead.** Boot time is tractable engineering; suspend is an open-ended bug hunt.

## COMPANION — ESP32-C6

Owns the WebSocket to the hub, the hall sensor, the haptic motor, the status strip, and the CM4's
power rail.

- **C6 specifically, for WiFi 6 TWT**: ~110 µA while associated, versus 2–5 mA on legacy DTIM.
  ⚠️ TWT requires a WiFi 6 AP *and* is optional in 802.11ax — verify per router. "WiFi 6" on the
  box is not sufficient.
- ⚠️ **nRF52840 / XIAO is disqualified: no WiFi.** It could only reach the hub via the phone,
  reinstating the dependency Linux just removed. Its excellent idle draw is real and irrelevant.
- ★ **Don't poll while closed.** An idle WebSocket with DTIM-aligned keepalives costs less than
  repeated wake/handshake/teardown, *and* delivers instantly.
- Message lands while stowed → status strip shows it, haptic buzzes → flip open and it's already
  there. Boot latency hides behind reading you'd be doing anyway.

## HUB AND CHANNELS

The hub is **talos** — always-on, on the tailnet. Channels have history: an outcome may land
minutes after the command while you're looking at something else. **The hub holds state; the panel
is only a view.** The ESP32 could never hold this itself, and doesn't have to.

Per device: discover with `tmux list-panes -a -F`, route with `send-keys -t %3`, read back with
`capture-pane`. Every box runs the same small agent and advertises its panes.

- ⚠️ **Key channels on tmux pane IDs (`%3`), never `session:window.pane` indices.** Indices
  renumber when panes close, so channels would silently re-point at the wrong pane — the worst
  possible failure for a device whose entire job is "send this to exactly that."
- ★ **The receipt and outcome signals already exist.** The "Sent" and "Ready" hooks described in
  `../CLAUDE.md` fire on prompt-submit and response-finish. They need to POST to the hub tagged
  with `$TMUX_PANE` instead of pushing straight to BLE.

## SOFTWARE SPLIT

STT and the hub link are **system services**, so one global PTT gives every application voice input.

★ **The channel client is app #1, and V1 ships only it.** "Run network diag", "ssh to argus" are
things you *say to a channel*, not separate apps you open — a launcher would be phone thinking.
More apps when they earn it: **Home Assistant is the obvious second**, and it closes the loop on
the original "00s smart-home controller" idea. It also reuses the same Whisper/Piper services the
HA satellites already share. **Lean, not closed** — it's Linux, so don't design against other uses;
just don't build for needs that don't exist yet.

Useful test for anything proposed later: if it fits *pick target → speak → confirm → read result*,
it belongs. If it needs you poking at the screen, it's the phone-on-your-arm thing.

- **Native toolkit, not Chromium.** A browser at 1080×1240 is exactly what would force CM5-class
  compute and a thermal problem. A native UI runs comfortably on far less.
- ⚠️ Keep a minimal text-entry path. **You cannot voice-type a password** — you'd say it out loud
  and Whisper would mangle it anyway. That is what the keyboard is for, not general typing.

Voice services already live on talos under launchd:

| leg | service | endpoint |
|---|---|---|
| speech → text | Wyoming faster-whisper `small-int8` | `talos.local:10300` |
| text → speech | Wyoming Piper `en_US-lessac-medium` | `talos.local:10200` |

## THERMAL — the plastic does not conduct, the metal does

PLA/PETG is ~0.13–0.25 W/m·K. Aluminium is ~167. Through-thickness conduction through a 2 mm wall is
fine; ★ **lateral spreading is what dies.** Heat from a ~15 mm chip punches straight through in a
hot spot and 95% of the panel contributes nothing. A metal spreader on the hot path is not optional.

- ★ **Thermals match the duty cycle.** Panel **open** = CM4 working = both faces in free air, the
  best-ventilated surface on the device. Panel **closed** = CM4 power-gated = no heat to dump.
  Compute belongs in the panel; the battery — the heavy part — stays in the base.
- ⚠️ Don't sit the CM4 behind the emissive area. OLEDs age faster hot. Offset it toward the hinge.
- Fans are unnecessary for a bursty 1–2 W load. If one is ever added, **seal it inside** and trigger
  on temperature — on a body-worn device **sweat ingress is the real killer, not heat.** Never open
  a vent to the outside.

## MATERIALS — per function, not one choice

| part | material | why |
|---|---|---|
| hinge, structure | **PA-CF** | stiff, HDT >100 °C. ⚠️ hygroscopic — keep off skin and sweat |
| skin contact, cosmetic shell | **PETG / PCTG** | no moisture uptake, adequate UV. PCTG buys *toughness*, **not** heat — same ~85 °C Tg |
| panel backplate, hot path | **aluminium** ★ LOCKED | ~167 W/m·K at 2.7 g/cm³ — better conductor *and* 1/3 the weight of brass |

⚠️ **Never PLA.** Glass transition 55–60 °C; it will deform behind the board and in a hot car.

### Backplate sourcing — aluminium, 1 mm

**SendCutSend** takes DXF/DWG/EPS/AI/STEP with instant pricing and no minimums, and offers laser
engraving as an add-on. 2–4 day lead, free US shipping.

A 100×70×1 mm plate is **~19 g in aluminium**. The plate hangs off the hinge, so its mass is
cantilevered, not carried.

⚠️ **Brass was considered and rejected (2026-08-11).** It was an *aesthetic* pick presented as a
thermal one — thermally fine at ~120 W/m·K, but 3× the density (~60 g for the same plate) for zero
functional gain, on a device with no aesthetic brief. Noted so it doesn't get re-proposed.

Reference, if a copper alloy is ever revisited: **CO2 lasers cannot cut brass or copper** — too
reflective at 10.6 µm, and the reflection can damage the tube. Those need a fiber laser (1.06 µm)
or waterjet. Aluminium is unaffected.

## WHY THE CYD DIED

The 2026-08-10 concept was an ESP32-3248S035C desk console. Every constraint that shaped it turned
out to be soft, except one:

- **"The board is what I own."** It's a wall/desk board: no PMU, no charger, no fuel gauge, no
  battery connector, 5 V input, 101×55 mm of rigid bare-backed PCB. Wrong for worn-and-battery.
- **"480×320 is the screen size available."** That was a catalog limit, not a physical one. Phone
  AMOLED panels and HDMI→MIPI driver boards exist; the ESP32 dev-board ceiling was irrelevant.
- **"307 KB framebuffer against 520 KB SRAM."** An artifact of using an MCU at all.
- **"Echo is the hard problem."** It was the hard problem *for an always-listening single-mic
  panel*. Push-to-talk plus a hinged, stowable device makes it mostly moot.
- **⚠️ "An ESP32 cannot run Tailscale."** This one was real, and it is the reason for every change
  above.

## OPEN

- Bracer internal volume (drives final battery and board fit)
- Exact ESP32 placement on the band
- Where the status strip sits, which determines whether SPI crosses the hinge
- Which SSID talos lives on — TWT needs the WiFi 6 network, and moving talos there also unthrottles
  its 6E radio (it currently negotiates 11ac). Note it would need a fresh DHCP reservation.
