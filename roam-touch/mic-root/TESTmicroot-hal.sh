#!/system/bin/sh
#
# TESTmicroot-hal.sh — capture what the KERNEL says while the audio HAL tries to record.
#
# The HAL-side failure (`start_input_stream: pcm_prepare returned -1`) is already documented from
# userspace. What has never been seen is the kernel log underneath it, because dmesg needs root.
# Run this under the same temporary Magisk boot, then make the phone record (hold PTT in Nexus,
# or drive it over adb) inside the listening window.
#
# Usage:  TESTmicroot-hal.sh [seconds]     (default 12)
#
# PRIVACY: this script records nothing. It only reads log buffers.
set -u

DIR=/data/local/tmp/TESTmicroot
BB=$DIR/busybox
WIN=${1:-12}

[ "$(id -u)" = "0" ] || { echo "!! not root"; exit 1; }

echo "== clearing kernel + audio logs =="
dmesg -c >/dev/null 2>&1
logcat -b all -c 2>/dev/null

echo "== LISTENING FOR ${WIN}s — make the phone record now (hold PTT) =="
i=0
while [ "$i" -lt "$WIN" ]; do sleep 1; i=$((i + 1)); printf '.'; done
echo

echo
echo "=========== KERNEL LOG (audio-related) ==========="
dmesg | "$BB" grep -iE 'wcd|tasha|slim|adsp|q6|apr|afe|asm|adm|pcm|snd|audio|dai|dsp' | tail -80

echo
echo "=========== HAL / AUDIOSERVER LOG ==========="
logcat -b all -d 2>/dev/null | "$BB" grep -iE 'audio_hw|audio_hal|select_devices|enable_snd_device|pcm_open|pcm_prepare|start_input_stream|ACDB|AudioFlinger|AudioRecord|audioserver|msm8996|platform_' | tail -120

echo
echo "=========== MIXER STATE THE HAL LEFT BEHIND ==========="
for c in "MultiMedia1 Mixer SLIM_0_TX" "MultiMedia8 Mixer SLIM_0_TX" "AIF1_CAP Mixer SLIM TX7" \
         "SLIM TX7 MUX" "ADC MUX7" "DMIC MUX7" "DEC7 Volume" "SLIM_0_TX Channels"; do
  printf '  %-32s = %s\n' "$c" "$(tinymix "$c" 2>&1 | tail -1)"
done

echo
echo "=========== ACTIVE PCM STREAMS ==========="
cat /proc/asound/pcm | "$BB" grep -i capture
for s in /proc/asound/card0/pcm*c/sub0/status; do
  st=$(cat "$s" 2>/dev/null | head -1)
  [ "$st" = "closed" ] || echo "  $s -> $st"
done
echo "DONE"
