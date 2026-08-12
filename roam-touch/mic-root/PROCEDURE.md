# Temporary-root mic test — ROAM Touch (sailfish, QP1A.191005.007.A3)

**Nothing is flashed.** The patched boot image is loaded into RAM with `fastboot boot`.
The boot partition, both slots, `/data`, the device owner and the home activity are untouched,
and the phone is back to stock-unrooted on the next reboot.

Everything is already built and verified. What is left is the part that needs hands and a cable.

---

## Your part — 9 steps

Run these on the laptop (`nicks-macbook-pro`). Everything is staged there already.

```sh
FB=/opt/homebrew/bin/fastboot
ADB=~/Library/Android/sdk/platform-tools/adb
IMG=~/pixel/TESTmagisk-boot-sailfish-QP1A.191005.007.A3.img
```

1. **Plug the phone into the laptop by USB.** Leave it plugged for the whole test — after a
   reboot there is no adb-over-Wi-Fi until step 8.
2. `$ADB devices` — must say `device`. If it says `unauthorized`, tap **Allow** on the phone.
3. `$ADB reboot bootloader`
4. `$FB devices` — must list the phone. Then `$FB getvar current-slot` — must print **`b`**.
   (Read-only. If it prints `a`, stop and tell me.)
5. **`$FB boot $IMG`** — ⚠️ `boot`, **never** `flash`. It should print `Sending`/`Booting`/`OKAY`.
6. Wait for the phone to boot normally and unlock it. Expect 1–3 min. It will look completely
   normal: same launcher, same Nexus home screen, same apps.
7. `$ADB shell su -c id` — the phone pops a **Magisk** prompt. Tap **Grant** (choose *Forever* if
   offered). The command should then print `uid=0(root)`.
8. `$ADB tcpip 5555`
9. Tell me. I drive the rest from talos over the tailnet; you can put the phone down.

Expected total: about five minutes of your attention, then it is mine.

---

## If a step misbehaves

| symptom | do this |
|---|---|
| `fastboot boot` returns `FAILED` / `unknown command` | Nothing happened. `$FB reboot`, phone comes back stock. Tell me. |
| Stuck on the boot animation > 5 min | Hold **Power ~10 s** to force off, then power on normally. The boot partition was never written, so it boots stock. |
| **Lands in recovery, or loops** | ⚠️ Do **not** wipe and do **not** re-flash. This is the A/B retry-count trap: `$FB --set-active=b` (re-arms the counter to 3), then `$FB reboot`. |
| `su` prompt never appears / denied | Open the Magisk app once, then retry step 7. |
| `adb` says `unauthorized` and tapping Allow does not stick | Another adb server owns the device. On talos: `adb kill-server`, then retry on the laptop. |

**Never**, at any point: `fastboot flash`, `fastboot -w`, `fastboot format`,
`fastboot flashing lock`, or `fastboot --set-active=a`.

---

## Getting back to normal (I do this, or you can)

1. `$ADB reboot` — this alone removes root. The phone comes up on the stock boot image.
2. Replug USB once and `$ADB tcpip 5555` (this never survives a reboot on Android 10).
3. `$ADB uninstall com.topjohnwu.magisk` and `$ADB shell rm -rf /data/local/tmp/TESTmicroot`.

The only disk changes the whole exercise makes are the Magisk **app** (an APK, uninstallable),
`/data/adb/magisk/` (~15 MB, deleted in cleanup), and the staged test files under
`/data/local/tmp/TESTmicroot`. Device owner, 0 accounts, the Nexus home activity and
`nexuslauncher` are all unaffected — I snapshot them before and check them after.

---

## What actually runs, once I have root

`TESTmicroot.sh` walks a ladder that adds **one component at a time** and reports, for each rung,
whether the PCM can be prepared and what the samples look like:

| rung | adds | what a failure here means |
|---|---|---|
| A | ADSP front-end only, no backend | the ADSP audio session itself is down |
| B | `AUX_PCM_UL_TX` (no WCD9335 involved) | AFE / DSP-side routing is broken, not the codec |
| C | `SLIMBUS_0_TX` (codec link up, no mic) | the SLIMbus link to the codec is the problem |
| D | `dmic1` → DMIC0, bottom mic — **the exact route the HAL uses for `handset-mic`** | |
| E | `dmic3` → DMIC2, back mic, different decimator | |
| F | `dmic6` → DMIC5, top mic, different decimator | |

Then `TESTmicroot-hal.sh` records what the **kernel** says while the HAL makes its own attempt —
that log has never been seen, because `dmesg` needs root.

**Privacy:** each rung opens the mic for 2 seconds, the level statistics are computed on the phone,
and the raw capture is deleted immediately — including on error, via a shell trap. No audio file is
pulled off the phone, kept, or transcribed. Only sample counts and dBFS numbers come back.

---

## Why this route and not TWRP

A TWRP `fastboot boot` is a faster way to a root shell, and it is the wrong tool here. In recovery
the vendor audio HAL never runs, so nothing ever pushes the ACDB calibration into the ADSP and no
mixer path is ever applied. A capture failure there would be indistinguishable from "recovery does
not set up audio", which is exactly the ambiguity this test exists to remove. Booting a
Magisk-patched *normal* boot image keeps the entire stock vendor stack — same ADSP firmware, same
ACDB blobs, same HAL — and only adds a root shell alongside it. That makes `tinycap`'s result a
statement about the same system the HAL is failing in.
