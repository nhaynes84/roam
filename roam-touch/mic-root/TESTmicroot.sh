#!/system/bin/sh
#
# TESTmicroot.sh — ROAM Touch: can the built-in mic capture path be brought up BELOW the audio HAL?
#
# Runs as ROOT under a TEMPORARY Magisk boot (`fastboot boot`, nothing is flashed).
# Everything it writes lives under /data/local/tmp/TESTmicroot and is deleted on the next reboot
# anyway; the boot partition is never touched.
#
# PRIVACY: each case opens the mic for at most $SECS seconds, computes level statistics ON DEVICE,
# and deletes the raw capture immediately. No capture file is ever pulled off the phone, kept, or
# transcribed. Only sample counts and dBFS levels leave this script.
#
# The ladder below adds one component at a time, so a failure localises itself:
#   A  front-end only          ADSP + ASM session, no backend at all
#   B  + AUX_PCM_UL_TX         adds an AFE port that does NOT involve the WCD9335 codec
#   C  + SLIMBUS_0_TX          adds the SLIMbus link to the codec, but no mic routed
#   D  + dmic1 (DMIC0, bottom) the real `handset-mic` path the HAL uses
#   E  + dmic3 (DMIC2, back)   second physical mic, different decimator (DEC6/TX6)
#   F  + dmic6 (DMIC5, top)    third physical mic, different decimator (DEC5/TX5)
#
set -u

DIR=/data/local/tmp/TESTmicroot
BB=$DIR/busybox
WAV=$DIR/TESTcap.wav
SECS=2
CARD=0

trap 'rm -f "$WAV"' EXIT INT TERM HUP

[ "$(id -u)" = "0" ] || { echo "!! not root — this must run under the temporary Magisk boot"; exit 1; }
[ -x "$BB" ] || { echo "!! $BB missing"; exit 1; }

say() { echo; echo "=================================================================="; echo "$@"; echo "=================================================================="; }

# ---------------------------------------------------------------- 0. environment
say "0. ENVIRONMENT"
date
echo "id: $(id)"
getprop ro.build.fingerprint
echo "slot: $(getprop ro.boot.slot_suffix)   bootloader: $(getprop ro.boot.verifiedbootstate)"
uname -a
echo "-- magisk --"
magisk -v 2>/dev/null || echo "(magisk binary not on PATH)"

say "0b. SOUND CARD"
cat /proc/asound/cards
echo "-- capture PCMs --"
cat /proc/asound/pcm | "$BB" grep -i capture

# Locate the front-end the HAL uses for USECASE_AUDIO_RECORD (MultiMedia1).
PDEV=$(cat /proc/asound/pcm | "$BB" awk -F: '/MultiMedia1/ && /capture/ {split($1,a,"-"); print a[2]+0; exit}')
[ -n "${PDEV:-}" ] || PDEV=0
echo "MultiMedia1 capture front-end -> card $CARD device $PDEV"

say "0c. CODEC / SLIMBUS / ADSP AT BOOT (kernel log)"
dmesg | "$BB" grep -iE 'wcd9335|tasha|slim|adsp|q6afe|q6asm|q6adm|apr|msm-dai|asoc|snd_soc|audio' | tail -60
echo "-- slimbus devices --"
ls -l /sys/bus/slimbus/devices/ 2>&1 | head -20
echo "-- subsystem states --"
for d in /sys/bus/msm_subsys/devices/*; do
  [ -e "$d/name" ] && echo "  $(cat $d/name 2>/dev/null) = $(cat $d/state 2>/dev/null)"
done 2>/dev/null

say "0d. MIXER SNAPSHOT (controls this test touches, before any change)"
for c in "MultiMedia1 Mixer SLIM_0_TX" "MultiMedia1 Mixer AUX_PCM_UL_TX" "MultiMedia1 Mixer TERT_MI2S_TX" \
         "AIF1_CAP Mixer SLIM TX5" "AIF1_CAP Mixer SLIM TX6" "AIF1_CAP Mixer SLIM TX7" \
         "SLIM_0_TX Channels" "SLIM TX5 MUX" "SLIM TX6 MUX" "SLIM TX7 MUX" \
         "ADC MUX5" "ADC MUX6" "ADC MUX7" "DMIC MUX5" "DMIC MUX6" "DMIC MUX7" \
         "IIR0 INP0 MUX" "DEC5 Volume" "DEC6 Volume" "DEC7 Volume"; do
  printf '  %-32s = %s\n' "$c" "$(tinymix "$c" 2>&1 | tail -1)"
done

# ---------------------------------------------------------------- helpers
mix() {
  if ! tinymix "$1" "$2" >/dev/null 2>&1; then
    echo "  !! tinymix FAILED to set [$1] = [$2]"
  fi
}

readback() {
  printf '  readback %-28s = %s\n' "$1" "$(tinymix "$1" 2>&1 | tail -1)"
}

reset_all() {
  mix "MultiMedia1 Mixer SLIM_0_TX" 0
  mix "MultiMedia1 Mixer AUX_PCM_UL_TX" 0
  mix "MultiMedia1 Mixer TERT_MI2S_TX" 0
  mix "AIF1_CAP Mixer SLIM TX5" 0
  mix "AIF1_CAP Mixer SLIM TX6" 0
  mix "AIF1_CAP Mixer SLIM TX7" 0
  mix "ADC MUX5" ZERO
  mix "ADC MUX6" ZERO
  mix "ADC MUX7" ZERO
  mix "SLIM TX5 MUX" ZERO
  mix "SLIM TX6 MUX" ZERO
  mix "SLIM TX7 MUX" ZERO
}

# Level statistics, computed on device. Reports counts and dBFS only; never the audio.
stats() {
  sz=$("$BB" stat -c %s "$WAV" 2>/dev/null || echo 0)
  echo "  wav_bytes=$sz  header=44  frames=$(( (sz - 44) / 2 ))"
  if [ "$sz" -le 44 ]; then echo "  NO SAMPLES CAPTURED"; return; fi
  "$BB" od -A n -t d2 -v -j 44 "$WAV" | "$BB" awk '
    { for (i = 1; i <= NF; i++) { v = $i + 0; n++; if (v != 0) nz++; a = (v < 0 ? -v : v); if (a > peak) peak = a; s += v * v; sum += v } }
    END {
      if (n == 0) { print "  n=0"; exit }
      rms = sqrt(s / n)
      pk = (peak > 0) ? sprintf("%.1f", 20 * log(peak / 32768) / log(10)) : "-inf"
      rm = (rms  > 0) ? sprintf("%.1f", 20 * log(rms  / 32768) / log(10)) : "-inf"
      printf "  samples=%d  nonzero=%d (%.3f%%)  peak=%d (%s dBFS)  rms=%.2f (%s dBFS)  dc_mean=%.3f\n", n, nz, 100.0 * nz / n, peak, pk, rms, rm, sum / n
    }'
}

run_case() {
  label="$1"
  say "CASE $label"
  shift
  echo "  route:"
  for kv in "$@"; do echo "    $kv"; done
  dmesg -c >/dev/null 2>&1
  rm -f "$WAV"
  echo "  -- tinycap card $CARD device $PDEV, 1ch 48000Hz S16, ${SECS}s --"
  out=$(tinycap "$WAV" -D "$CARD" -d "$PDEV" -c 1 -r 48000 -b 16 -T "$SECS" 2>&1)
  rc=$?
  echo "  tinycap exit=$rc"
  echo "$out" | while IFS= read -r l; do echo "  | $l"; done
  stats
  rm -f "$WAV"
  echo "  -- kernel log emitted during this case --"
  dmesg | "$BB" grep -iE 'wcd|tasha|slim|adsp|q6|apr|afe|asm|adm|pcm|snd|audio|dai|dsp' | tail -40 | while IFS= read -r l; do echo "  k| $l"; done
  echo "  (end of case $label)"
}

# ---------------------------------------------------------------- the ladder
reset_all

run_case "A — front-end only, NO backend routed" \
  "(no mixer controls set)"

mix "MultiMedia1 Mixer AUX_PCM_UL_TX" 1
readback "MultiMedia1 Mixer AUX_PCM_UL_TX"
run_case "B — + AUX_PCM_UL_TX (AFE port, WCD9335 codec NOT involved)" \
  "MultiMedia1 Mixer AUX_PCM_UL_TX = 1"
mix "MultiMedia1 Mixer AUX_PCM_UL_TX" 0

mix "MultiMedia1 Mixer SLIM_0_TX" 1
mix "SLIM_0_TX Channels" One
readback "MultiMedia1 Mixer SLIM_0_TX"
run_case "C — + SLIMBUS_0_TX backend, no mic routed inside the codec" \
  "MultiMedia1 Mixer SLIM_0_TX = 1" "SLIM_0_TX Channels = One"

# D: handset-mic == dmic1 + DEC7 Volume 88   (bottom mic, DMIC0, decimator 7, SLIM TX7)
mix "AIF1_CAP Mixer SLIM TX7" 1
mix "SLIM TX7 MUX" DEC7
mix "ADC MUX7" DMIC
mix "DMIC MUX7" DMIC0
mix "IIR0 INP0 MUX" DEC7
mix "DEC7 Volume" 88
for c in "AIF1_CAP Mixer SLIM TX7" "SLIM TX7 MUX" "ADC MUX7" "DMIC MUX7" "DEC7 Volume"; do readback "$c"; done
run_case "D — handset-mic: dmic1 = DMIC0 (bottom mic) via DEC7/SLIM TX7  << the path the HAL uses" \
  "AIF1_CAP Mixer SLIM TX7 = 1" "SLIM TX7 MUX = DEC7" "ADC MUX7 = DMIC" "DMIC MUX7 = DMIC0" "DEC7 Volume = 88"
mix "AIF1_CAP Mixer SLIM TX7" 0
mix "ADC MUX7" ZERO
mix "SLIM TX7 MUX" ZERO

# E: camcorder-mic == dmic3   (back mic, DMIC2, decimator 6, SLIM TX6)
mix "AIF1_CAP Mixer SLIM TX6" 1
mix "SLIM TX6 MUX" DEC6
mix "ADC MUX6" DMIC
mix "DMIC MUX6" DMIC2
mix "IIR0 INP0 MUX" DEC6
mix "DEC6 Volume" 84
run_case "E — dmic3 = DMIC2 (back mic) via DEC6/SLIM TX6 — different mic, different decimator" \
  "AIF1_CAP Mixer SLIM TX6 = 1" "SLIM TX6 MUX = DEC6" "ADC MUX6 = DMIC" "DMIC MUX6 = DMIC2" "DEC6 Volume = 84"
mix "AIF1_CAP Mixer SLIM TX6" 0
mix "ADC MUX6" ZERO
mix "SLIM TX6 MUX" ZERO

# F: speaker-mic == dmic6    (top mic, DMIC5, decimator 5, SLIM TX5)
mix "AIF1_CAP Mixer SLIM TX5" 1
mix "SLIM TX5 MUX" DEC5
mix "ADC MUX5" DMIC
mix "DMIC MUX5" DMIC5
mix "IIR0 INP0 MUX" DEC5
mix "DEC5 Volume" 84
run_case "F — dmic6 = DMIC5 (top mic) via DEC5/SLIM TX5 — third mic, third decimator" \
  "AIF1_CAP Mixer SLIM TX5 = 1" "SLIM TX5 MUX = DEC5" "ADC MUX5 = DMIC" "DMIC MUX5 = DMIC5" "DEC5 Volume = 84"

say "TEARDOWN — returning the mixer to the state the HAL expects"
reset_all
rm -f "$WAV"
ls -l "$DIR"/*.wav 2>/dev/null && echo "!! a capture file survived — delete it" || echo "  no capture files remain"

say "DONE"
echo "Read the ladder: the first case that fails names the deepest component that is still broken."
