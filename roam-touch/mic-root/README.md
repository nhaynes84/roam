# mic-root — temporary-root test for the ROAM Touch built-in microphone

The built-in mic returns pure digital silence and the HAL logs
`start_input_stream: pcm_prepare returned -1` on every configuration. A Bluetooth headset mic
works, which proves AudioFlinger, the HAL framework, tinyalsa and the app are fine — and proves
**nothing** about the codec driver, the ADSP audio firmware or the ACDB calibration, because SCO
bypasses all three. Those three live in the vendor partition that the 8.0 → 10 flash replaced, so
"we broke it in software" and "the hardware is dead" are both still live.

`tinycap` is on the device but `shell` is not in group `audio` (1005), so there is no root-free way
to reach ALSA. This directory is the root-free-of-consequences way to get there.

## Files

| file | what it is |
|---|---|
| `PROCEDURE.md` | the numbered checklist for the owner, plus the recovery path |
| `prepare-boot-image.sh` | host-side: builds the Magisk-patched boot image (already run) |
| `TESTmicroot.sh` | on-device, as root: the capture ladder |
| `TESTmicroot-hal.sh` | on-device, as root: the kernel log under a HAL capture attempt |

The patched image is **not** in git (34 MB binary). It is staged at
`~/pixel/TESTmagisk-boot-sailfish-QP1A.191005.007.A3.img` on both `nicks-macbook-pro` and talos,
sha256 `234c1186c2e05a3c0bbe75b35e5361593b0a340d84d4ec5d0f115f4ed4105c43`.
It is for `fastboot boot` only. Rebuild it with `prepare-boot-image.sh`.

## Verified before anyone touched the phone

- Stock `boot.img` taken from the staged factory image for the exact running build
  (`QP1A.191005.007.A3`), sha256 `b020dba9…b445`.
- Patched on-device with Magisk v30.7's own `boot_patch.sh`, with the flags the Magisk app would
  have computed for this device: `KEEPVERITY=true KEEPFORCEENCRYPT=true PATCHVBMETAFLAG=true
  RECOVERYMODE=false LEGACYSAR=true`.
- `LEGACYSAR=true` is load-bearing. sailfish is a legacy system-as-root A/B device: the boot image
  carries the *recovery* ramdisk and the bootloader passes `skip_initramfs` on a normal boot, so
  the ramdisk is skipped. magiskboot hex-patches the kernel `skip_initramfs` → `want_initramfs`
  so the flag no longer matches and magiskinit (now `/init` in that ramdisk) runs and performs the
  system-as-root mount itself. Confirmed in the patch log:
  `Patch @ 0x017853F6 [736B69705F696E697472616D667300] -> [77616E745F696E697472616D667300]`.
- Re-verified on the finished image: ramdisk `cpio test` → 1 (Magisk-patched), `init` is 200 KB
  (magiskinit), kernel contains `want_initramfs` ×1 and `skip_initramfs` ×0.

## The route the test drives

sailfish's mics are **digital MEMS mics on the WCD9335 (Tasha) DMIC ports**, not analog inputs.
From `/vendor/etc/mixer_paths.xml`, `handset-mic` = `dmic1` + `DEC7 Volume 88`, i.e.

```
MultiMedia1 Mixer SLIM_0_TX = 1      front-end -> SLIMBUS_0_TX backend
AIF1_CAP Mixer SLIM TX7     = 1      codec TX port 7 into the SLIMbus capture stream
SLIM_0_TX Channels          = One
SLIM TX7 MUX                = DEC7
ADC MUX7                    = DMIC
DMIC MUX7                   = DMIC0  bottom mic
IIR0 INP0 MUX               = DEC7
DEC7 Volume                 = 88
```

The other two physical mics ride different decimators and different TX ports: back mic =
`dmic3` (DMIC2 / DEC6 / TX6), top mic = `dmic6` (DMIC5 / DEC5 / TX5). Testing all three separates
"one dead mic" from "the whole capture chain is down".

## Reading the result — what it does and does not prove

| observed | supports | still does NOT prove |
|---|---|---|
| Rung A already fails (front-end alone, no backend) | the ADSP audio session cannot start at all — a firmware/DSP-level fault, not a microphone | which side put the ADSP in that state |
| A/B pass, C onward fail | the fault is on the SLIMbus link to the WCD9335 or in the codec's own bring-up | codec silicon vs codec firmware/driver — both sit behind that boundary |
| A–C pass, D/E/F all fail to **prepare** | the codec is reachable but the DMIC capture chain will not start | that the mics themselves are dead. A cracked mic joint cannot make `pcm_prepare` fail |
| D/E/F **prepare and deliver samples** | the kernel driver, the codec and the ADSP can all bring the capture path up — the failure is above them, in the HAL / ACDB / vendor config, i.e. plausibly ours | that a specific config file is the culprit; that has to be found separately |
| samples arrive but are all-zero on all three mics | the digital chain runs and no acoustic energy reaches it | dead elements vs a DMIC clock that is never driven vs calibration zeroing the decimator |
| samples arrive at a real noise floor (≈ −60 dBFS) and rise on speech | that mic works below the HAL, full stop | nothing further is needed for that mic |

**The honest framing:** a `pcm_prepare` failure is a *session-start* failure. A cracked solder
joint on a mic, or a dead MEMS element, does not make a session fail to start — it makes a session
start cleanly and deliver silence. So this test is a strong discriminator between
"session cannot start" (driver / ADSP firmware / codec bring-up) and "session starts, no sound"
(the mic itself, its clock, or calibration). It is **not** a silicon test. If every rung fails
identically, that points hard away from a single cracked joint and toward the vendor stack, but
the only thing that would settle "we broke it" outright is reflashing the original 8.0 image and
testing the mic first — which costs the whole current setup.
