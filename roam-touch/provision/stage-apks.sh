#!/usr/bin/env bash
# ============================================================================
# stage-apks.sh — snapshot the APKs that are ON THE PHONE RIGHT NOW.
#
# READ-ONLY against the device. It installs nothing, changes nothing, and is
# safe to run against the live prototype at any time.
#
# WHY THIS EXISTS, AND WHY IT RUNS *BEFORE* A REFLASH
# ---------------------------------------------------
# A reflash wipes /data. Everything sideloaded goes with it. The laptop stage
# (`ssh nicks-macbook-pro:~/pixel/apks/`) only ever held termux + termux-boot —
# Tailscale and the Home Assistant minimal build were installed from downloads
# that are not stored anywhere. Re-finding "the version that worked" after the
# fact means hunting release pages for an EOL 2016 phone.
#
# Pulling the installed APKs off the device sidesteps all of that AND fixes the
# one trap that has already bitten here:
#
#   ⚠️ Termux add-ons must be signed by the SAME source as the Termux app
#      (GitHub-signed ≠ F-Droid-signed) or `adb install` fails with
#      INSTALL_FAILED_UPDATE_INCOMPATIBLE / signature mismatch. Pulling the pair
#      that is currently installed and working guarantees a matched set. Never
#      re-download them individually from two different places.
#
# Run this FIRST. Then provision.sh can rebuild the phone with byte-identical
# packages instead of "whatever is on the download page today".
#
# Usage:  ./stage-apks.sh [-s <serial>] [--out <dir>] [--push-to-laptop]
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The tailnet address, because this device is supposed to work away from the
# house and the LAN address is a DHCP lease. See [[roam-touch-phone-2]].
DEV="${ROAM_DEVICE:-100.95.196.87:5555}"
OUT="$HERE/apks"
PUSH_LAPTOP=0
LAPTOP_DEST="nicks-macbook-pro:~/pixel/apks/"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s) DEV="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --push-to-laptop) PUSH_LAPTOP=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The packages that make up the device, and the filename each is staged under.
# Keep these filenames in sync with APK_* in provision.sh — that script looks
# them up here by name.
PKGS=(
  "com.termux:termux.apk"
  "com.termux.boot:termux-boot.apk"
  "com.tailscale.ipn:tailscale.apk"
  "io.homeassistant.companion.android.minimal:ha-minimal.apk"
  "com.roam.touch:nexus.apk"
)

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }

if ! adb -s "$DEV" get-state >/dev/null 2>&1; then
  red "FAIL: no adb device at '$DEV'."
  echo "  ⚠️ adb over Wi-Fi does NOT survive a reboot on this phone (setting"
  echo "     persist.adb.tcp.port needs root; adb_wifi_enabled is Android 11+)."
  echo "     If the phone has rebooted: plug in USB and run  adb tcpip 5555"
  echo "  ⚠️ If you get endless 'unauthorized': a second adb server somewhere else"
  echo "     is fighting for the device. Kill it (adb kill-server there) first."
  exit 1
fi

mkdir -p "$OUT"
echo "device : $DEV"
echo "out    : $OUT"
echo

manifest="$OUT/MANIFEST.txt"
: > "$manifest"
printf '# staged %s from %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$DEV" >> "$manifest"

missing=0
for entry in "${PKGS[@]}"; do
  pkg="${entry%%:*}"; file="${entry##*:}"

  # `pm path` prints one "package:/path" line per split. These five are all
  # single-APK installs (verified on-device 2026-08-12); a split app would need
  # `adb install-multiple` instead, so fail loudly rather than stage half of one.
  # (No mapfile / no arrays-from-process-substitution: macOS ships bash 3.2.)
  paths="$(adb -s "$DEV" shell "pm path $pkg" 2>/dev/null | tr -d '\r' | sed -n 's/^package://p')"
  npaths="$(printf '%s' "$paths" | grep -c . || true)"

  if [ "$npaths" -eq 0 ]; then
    ylw "MISS  $pkg — not installed on the device, nothing to stage"
    missing=$((missing+1))
    continue
  fi
  if [ "$npaths" -gt 1 ]; then
    red "FAIL  $pkg is a SPLIT install ($npaths apks). provision.sh assumes"
    red "      single-APK installs and would install a broken subset. Stage by hand."
    exit 1
  fi
  apkpath="$(printf '%s' "$paths" | head -1)"

  ver="$(adb -s "$DEV" shell "dumpsys package $pkg" 2>/dev/null | tr -d '\r' \
         | sed -n 's/.*versionName=\([^ ]*\).*/\1/p' | head -1)"

  adb -s "$DEV" pull "$apkpath" "$OUT/$file" >/dev/null
  sum="$(shasum -a 256 "$OUT/$file" | cut -d' ' -f1)"
  grn "OK    $file  ($pkg $ver)"
  printf '%s  %s  %s  %s\n' "$file" "$pkg" "${ver:-?}" "$sum" >> "$manifest"
done

echo
if [[ $PUSH_LAPTOP -eq 1 ]]; then
  # Second copy on the laptop, because talos and the phone can both die in the
  # same accident (same desk, same power strip) and the laptop is where the
  # factory image already lives.
  echo "mirroring to $LAPTOP_DEST ..."
  ssh nicks-macbook-pro 'mkdir -p ~/pixel/apks'
  scp -q "$OUT"/*.apk "$OUT/MANIFEST.txt" "$LAPTOP_DEST"
  grn "mirrored to $LAPTOP_DEST"
fi

cat "$manifest"
echo
if [[ $missing -gt 0 ]]; then
  ylw "$missing package(s) were not installed and could not be staged."
  ylw "provision.sh will fall back to ~/pixel/apks on the laptop for those."
fi
grn "staged. These are the exact bytes now running — provision.sh will reinstall these."
