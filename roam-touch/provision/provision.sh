#!/usr/bin/env bash
# =============================================================================
# provision.sh — rebuild the ROAM Touch phone from a freshly flashed state.
#
#   ⚠️⚠️ STATUS: DRAFT. Written 2026-08-12. Every read-only precondition and
#   every idempotent skip path has been exercised against the live phone, but
#   NO destructive step has ever been run end-to-end — the phone is a working
#   prototype and reprovisioning it to test the script would have cost the very
#   setup this script exists to protect. The first real end-to-end run will be
#   the first real test. Run it with --dry-run first, then run it attended.
#   Unexercised steps are marked "UNTESTED" in their own comments.
#
# WHAT THIS IS FOR
# ----------------
# The microphone investigation ([[roam-touch-mic]]) has exactly one decisive
# test left: reflash the original 8.0 factory image and try the mic first. The
# objection to doing that was never the flashing — it was losing the setup.
# This script is the answer to that objection. If the setup can be rebuilt in
# ten minutes by running one command, the reflash stops being expensive.
#
# WHAT IT DELIBERATELY DOES NOT DO
# --------------------------------
#   • It does not flash. Flashing is fastboot, it is destructive, and it has a
#     trap that already cost an hour — see FLASH NOTES below. Read those, flash
#     by hand, then run this.
#   • It NEVER signs in to a Google account, and nothing it does can add one.
#     Zero accounts is the precondition for device owner, and device owner is
#     what makes Nexus the home screen and grants RECORD_AUDIO without a dialog.
#     A single sign-in undoes the most important thing on this device.
#   • It never invents a token, a password or a credential. Three things are
#     human steps by nature (Wi-Fi, the Tailscale login, the HA long-lived
#     token). It stops, prints exactly what to do, and waits.
#
# FLASH NOTES — read before the fastboot session, not after
# --------------------------------------------------------
#   ⚠️ sailfish is an A/B device. When it will not boot, read `slot-unbootable`
#      and `slot-retry-count` FIRST. Each failed attempt decrements the retry
#      count; at 0 the slot is marked unbootable and the bootloader falls back
#      to the system_other stub, which looks exactly like a bad flash and is
#      not one. The cure is `fastboot --set-active=b` (re-arms to 3). Do not
#      wipe. This cost an hour once already.
#   ⚠️ UNPLUG USB FOR THE FIRST BOOT AFTER A FLASH. USB confuses a rebooting
#      phone; a 25-minute "boot" that looked like dex2oat was this.
#   ⚠️ Do not complete the Google setup wizard with an account. Skip it. Zero
#      accounts, always.
#
# USAGE
# -----
#   ./stage-apks.sh                 # FIRST, while the phone still works
#   ./provision.sh --dry-run        # read-only: shows every action, changes nothing
#   ./provision.sh                  # the real run, attended (it will stop and ask)
#   ./provision.sh --list           # list step names
#   ./provision.sh --only settings  # re-run one step
#   ./provision.sh --from debloat   # resume from a step
#   ./provision.sh verify           # read-only audit: is the phone fully set up?
#   ./provision.sh restore-debloat  # put every debloated package back
#
# Environment:
#   ROAM_DEVICE   adb serial (default 100.95.196.87:5555, the tailnet address)
# =============================================================================
set -u
# ⚠️ NOT -e: every step checks and reports its own result. `set -e` would abort
#    mid-step with no diagnosis, which is the exact failure mode this script
#    exists to prevent.
#
# ⚠️ NOT -o pipefail, and this one is load-bearing. Nearly every check here is
#    `adb shell dumpsys … | tr -d '\r' | grep -q …`. `grep -q` exits the moment
#    it matches, which SIGPIPEs the upstream `tr`, which under pipefail makes the
#    whole pipeline exit 141 — i.e. "no match" — EVEN THOUGH IT MATCHED. It only
#    bites on outputs too big for the pipe buffer, so small dumpsys reads pass
#    and big ones (bluetooth_manager, package) silently report the opposite of
#    the truth. Caught live 2026-08-12: the paired WH-1000XM6 was reported as
#    not bonded. Do not add pipefail back.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Facts about this specific device. All verified over adb on 2026-08-12 rather
# than copied from notes — if you change one, re-verify it against the phone.
# ---------------------------------------------------------------------------
# ⚠️ Use the TAILNET address, not the LAN one: this device is meant to work away
#    from the house, and 192.168.86.62 is a DHCP lease that will move.
# ⚠️ Two transports can be live at once (tailnet + LAN). ALWAYS pass -s.
DEV="${ROAM_DEVICE:-100.95.196.87:5555}"

EXPECT_DEVICE="sailfish"          # the ORIGINAL 2016 Pixel. Permanent; not a compromise.
EXPECT_SDK="29"                   # Android 10 QP1A.191005.007.A3, the last official build

NEXUS_PKG="com.roam.touch"        # ⚠️ NEVER rename. Renaming the package OR the receiver
NEXUS_RECEIVER=".NexusDeviceAdminReceiver"   # re-provisions the device from scratch.
NEXUS_ADMIN="$NEXUS_PKG/$NEXUS_RECEIVER"
NEXUS_MAIN="$NEXUS_PKG/.MainActivity"
NEXUS_SRC="$(cd "$HERE/../nexus" 2>/dev/null && pwd || echo "$HERE/../nexus")"
NEXUS_BUILT_APK="$NEXUS_SRC/app/build/outputs/apk/debug/app-debug.apk"

# The stock launcher. Kept installed FOREVER as the recovery home screen: if
# Nexus is ever cleared as device owner, `cmd package set-home-activity` needs
# something to point at. Without it, Home is stranded.
STOCK_LAUNCHER="com.google.android.apps.nexuslauncher"
STOCK_LAUNCHER_ACT="$STOCK_LAUNCHER/.NexusLauncherActivity"

TERMUX_PKG="com.termux"
TERMUX_BOOT_PKG="com.termux.boot"
TAILSCALE_PKG="com.tailscale.ipn"
HA_PKG="io.homeassistant.companion.android.minimal"

APK_DIR="$HERE/apks"
LAPTOP_APKS="nicks-macbook-pro:~/pixel/apks"

HUB_HOST="100.67.237.109"   # talos on the tailnet; hub is bound to this only
HUB_PORT="8787"
HA_URL="http://100.67.114.94:8123"   # Home Assistant on argus, tailnet address
HEADSET_NAME="WH-1000XM6"            # the SCO mic that actually works

DRY_RUN=0
ONLY=""
FROM=""
NEXUS_APK_OK=0   # set by step_apks; read by step_install_nexus

# ---------------------------------------------------------------------------
# Output. Loud and specific is the whole point: a silently half-provisioned
# phone is worse than an obvious failure, because it looks finished.
# ---------------------------------------------------------------------------
C_R=$'\033[31m'; C_G=$'\033[32m'; C_Y=$'\033[33m'; C_B=$'\033[36m'; C_0=$'\033[0m'
FAILURES=0
DONE_NOTES=""
TODO_NOTES=""

hdr()  { printf '\n%s== %s %s\n' "$C_B" "$*" "$C_0"; }
ok()   { printf '  %sOK%s    %s\n' "$C_G" "$C_0" "$*"; }
skip() { printf '  %sSKIP%s  %s\n' "$C_B" "$C_0" "$*"; }
warn() { printf '  %sWARN%s  %s\n' "$C_Y" "$C_0" "$*"; }
bad()  { printf '  %sFAIL%s  %s\n' "$C_R" "$C_0" "$*"; FAILURES=$((FAILURES+1)); }
die()  { printf '\n%sFATAL%s %s\n' "$C_R" "$C_0" "$*"; exit 1; }
note_done() { DONE_NOTES="$DONE_NOTES
  • $*"; }
note_todo() { TODO_NOTES="$TODO_NOTES
  • $*"; }

# adb shell, always with -s, always with CR stripped (adb shell line endings
# are CRLF and every string comparison in this script would silently fail).
sh_() { adb -s "$DEV" shell "$@" 2>/dev/null | tr -d '\r'; }

# A mutating command. In --dry-run it is printed and not executed. Everything
# that changes the phone MUST go through this; everything that only reads must
# not, so that --dry-run still verifies real preconditions.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  %sWOULD%s  %s\n' "$C_Y" "$C_0" "$*"
    return 0
  fi
  "$@"
}
run_sh() { run adb -s "$DEV" shell "$@"; }
# Same, but silences the device's own chatter ("Success", "Added: ...") on a
# real run. ⚠️ It must NOT silence the dry-run preview — that is the only output
# a dry run has — so the redirect is applied only when actually executing.
run_sh_q() {
  if [ "$DRY_RUN" -eq 1 ]; then run_sh "$@"; else adb -s "$DEV" shell "$@" >/dev/null 2>&1; fi
}

# A human step. There is no way to automate these and no honest way to fake
# them. Print exactly what to do, wait, then VERIFY — never take "done" on
# faith, because "I did it" and "it worked" are different claims.
#   $1 = short title, $2 = instructions (multi-line ok), $3 = verifier function
gate() {
  local title="$1" body="$2" verify="$3" ans=""
  while :; do
    if $verify >/dev/null 2>&1; then ok "$title — already done"; return 0; fi
    printf '\n%s┌─ HUMAN STEP: %s%s\n' "$C_Y" "$title" "$C_0"
    printf '%s\n' "$body" | sed 's/^/│ /'
    printf '%s└─%s\n' "$C_Y" "$C_0"
    if [ "$DRY_RUN" -eq 1 ]; then
      warn "dry-run: not waiting. This step is NOT satisfied yet."
      note_todo "$title"
      return 0
    fi
    printf 'Press ENTER when done, or type "skip" to leave it for later: '
    read -r ans
    if [ "$ans" = "skip" ]; then
      warn "$title skipped — the device is NOT finished until this is done"
      note_todo "$title"
      return 0
    fi
    if $verify >/dev/null 2>&1; then ok "$title verified"; note_done "$title"; return 0; fi
    warn "still not satisfied. Read the instructions again."
  done
}

# ---------------------------------------------------------------------------
# Small read-only predicates, shared by the steps and by `verify`.
# ---------------------------------------------------------------------------
pkg_installed()   { sh_ "pm list packages --user 0" | grep -qx "package:$1"; }
pkg_known()       { sh_ "pm list packages -u --user 0" | grep -qx "package:$1"; }  # incl. uninstalled-for-user
account_count()   { sh_ "dumpsys account" | grep -c "Account {"; }
is_device_owner() {
  # ⚠️ `dpm list-owners` DOES NOT EXIST on API 29. dumpsys device_policy is the
  #    only way to read this. An agent has already lost time to that.
  # ⚠️ dumpsys prints the receiver FULLY QUALIFIED (com.roam.touch/com.roam.touch.
  #    NexusDeviceAdminReceiver) even though dpm takes the short ".Receiver" form.
  #    Matching the short form here would report "not device owner" on a device
  #    that is one — a false failure that would send someone re-provisioning.
  sh_ "dumpsys device_policy" \
    | grep -qF "admin=ComponentInfo{$NEXUS_PKG/$NEXUS_PKG$NEXUS_RECEIVER}"
}
home_is_nexus()   { sh_ "cmd package resolve-activity -c android.intent.category.HOME -a android.intent.action.MAIN" | grep -q "name=$NEXUS_PKG.MainActivity"; }
mic_granted()     { sh_ "dumpsys package $NEXUS_PKG" | grep -q "android.permission.RECORD_AUDIO: granted=true"; }
perm_granted()    { sh_ "dumpsys package $1" | grep -q "$2: granted=true"; }
doze_whitelisted(){ sh_ "dumpsys deviceidle whitelist" | grep -q "^user,$1,"; }
gset()            { sh_ "settings get $1 $2"; }
# ⚠️ "Wi-Fi is on" is not "Wi-Fi is joined" — wifi_on=1 is true while sitting on
#    the network picker. Check the actual NetworkAgent state instead.
wifi_connected()  { sh_ "dumpsys connectivity" | grep -q "type: WIFI.*state: CONNECTED"; }
# Reaching talos's TAILNET address proves Tailscale is up and authenticated;
# the LAN address would still answer with Tailscale logged out.
tailscale_up()    { sh_ "ping -c1 -W2 $HUB_HOST" | grep -q "1 received"; }
headset_bonded()  { sh_ "dumpsys bluetooth_manager" | grep -q "$HEADSET_NAME"; }
ha_token_set()    { grep -qE '^[[:space:]]*roam\.ha\.token=.+' "$NEXUS_SRC/local.properties" 2>/dev/null; }

debloat_list() { grep -vE '^[[:space:]]*(#|$)' "$HERE/debloat.txt"; }

# =============================================================================
# STEPS
# =============================================================================

# ---------------------------------------------------------------------------
step_preflight() {
  hdr "preflight — is this the right phone, and can we reach it?"

  command -v adb >/dev/null || die "adb not on PATH."
  [ -f "$HERE/debloat.txt" ] || die "debloat.txt missing next to this script."

  if ! adb -s "$DEV" get-state >/dev/null 2>&1; then
    bad "no adb device at '$DEV'"
    cat <<EOF

  ⚠️ adb over Wi-Fi DOES NOT SURVIVE A REBOOT on this phone. Setting
     persist.adb.tcp.port needs root (verified: it does not stick), and
     adb_wifi_enabled is an Android 11+ feature. sailfish has neither, and
     there is no sshd in Termux to get back in another way.
     After ANY reboot — including the one at the end of a flash:
         plug the phone into a USB port, then:
         adb devices           # accept the RSA prompt ON THE PHONE
         adb tcpip 5555
         adb connect $DEV

  ⚠️ Endless 'unauthorized'? Two adb servers are fighting over one device.
     Kill the other one (adb kill-server on the other machine), or copy an
     already-authorized ~/.android/adbkey across.
EOF
    die "cannot continue without a device."
  fi
  ok "adb reachable at $DEV"

  local d s b
  d="$(sh_ getprop ro.product.device)"
  s="$(sh_ getprop ro.build.version.sdk)"
  b="$(sh_ getprop ro.build.id)"
  [ "$d" = "$EXPECT_DEVICE" ] || die "this is '$d', not '$EXPECT_DEVICE'. Wrong phone — refusing to touch it."
  ok "device = $d, build = $b, API = $s"
  if [ "$s" != "$EXPECT_SDK" ]; then
    # Not fatal: the whole point of the mic investigation is a reflash to 8.0,
    # and this script should still be runnable there. But most of what follows
    # was only ever verified on API 29, so say so out loud.
    warn "API $s, expected $EXPECT_SDK. Everything below was verified on API $EXPECT_SDK only."
    warn "In particular: dpm flags, settings keys and the debloat list may differ."
  fi

  local n; n="$(sh_ "pm list users" | grep -c 'UserInfo{')"
  [ "$n" = "1" ] || warn "$n users on the device. Device owner requires a single user; expected 1."
}

# ---------------------------------------------------------------------------
gate_wifi() {
  hdr "Wi-Fi — human step"
  # This has to be a human step: joining a WPA2 network needs the passphrase,
  # and there is no adb path to it that does not involve typing the secret into
  # a command line (and therefore into shell history and this repo). Not worth it.
  gate "Join Wi-Fi" \
"On the phone: Settings → Network & internet → Wi-Fi → BlueSun-5G, enter the
passphrase. (This is the only network the hub and Home Assistant are reachable
from until Tailscale is up.)

⚠️ Do NOT let the setup wizard sign in to a Google account at any point. Zero
   accounts is what makes device owner possible, and device owner is what makes
   Nexus the home screen and grants the mic without a dialog." \
    wifi_connected
}

# ---------------------------------------------------------------------------
step_adb_wifi() {
  hdr "adb over Wi-Fi"
  # If we are already talking to the phone over TCP, this is done by definition.
  case "$DEV" in
    *:*) ok "already connected over TCP ($DEV) — adb tcpip is in effect"
         warn "reminder: this dies on the next reboot. Re-do it with USB + 'adb tcpip 5555'."
         return 0 ;;
  esac
  # Reached only when running over a USB serial.
  # UNTESTED: never exercised, because the working device has been on TCP the
  # whole time.
  run adb -s "$DEV" tcpip 5555 || bad "adb tcpip 5555 failed"
  sleep 2
  run adb connect "100.95.196.87:5555" || bad "adb connect failed"
  ok "adb over Wi-Fi enabled (⚠️ does not survive a reboot)"
}

# ---------------------------------------------------------------------------
step_apks() {
  hdr "APKs — make sure we have the bytes before we need them"
  mkdir -p "$APK_DIR"
  # ⚠️ Track "will be available at install time", not "is on disk right now":
  #    during a dry run the copies have not happened, and an -f test would
  #    report a false missing for every APK the real run would have fetched.
  local f any=0
  NEXUS_APK_OK=0
  for f in termux.apk termux-boot.apk tailscale.apk ha-minimal.apk nexus.apk; do
    if [ -f "$APK_DIR/$f" ]; then
      ok "$f staged locally"; any=1
      [ "$f" = "nexus.apk" ] && NEXUS_APK_OK=1
      continue
    fi

    # Nexus is built on talos, never downloaded — prefer the gradle output over
    # a network round trip.
    if [ "$f" = "nexus.apk" ] && [ -f "$NEXUS_BUILT_APK" ]; then
      run cp "$NEXUS_BUILT_APK" "$APK_DIR/nexus.apk"
      ok "nexus.apk available from the last gradle build ($NEXUS_BUILT_APK)"
      any=1; NEXUS_APK_OK=1; continue
    fi

    # Fall back to the laptop stage. Only termux + termux-boot were ever put
    # there by hand; Tailscale and HA were installed from downloads that are
    # not stored anywhere, which is exactly why stage-apks.sh exists.
    # ⚠️ Never fetch during --dry-run: termux.apk alone is 118 MB, and a dry run
    #    that pulls 118 MB over ssh is not a dry run.
    if [ "$DRY_RUN" -eq 1 ]; then
      if ssh -o BatchMode=yes -o ConnectTimeout=8 nicks-macbook-pro "test -f ~/pixel/apks/$f" 2>/dev/null; then
        printf '  %sWOULD%s  scp %s/%s -> %s\n' "$C_Y" "$C_0" "$LAPTOP_APKS" "$f" "$APK_DIR"
        any=1; [ "$f" = "nexus.apk" ] && NEXUS_APK_OK=1
      else
        warn "$f NOT staged locally and NOT on the laptop — run ./stage-apks.sh"
      fi
      continue
    fi
    if scp -q "$LAPTOP_APKS/$f" "$APK_DIR/$f" 2>/dev/null; then
      ok "$f fetched from $LAPTOP_APKS"; any=1
      [ "$f" = "nexus.apk" ] && NEXUS_APK_OK=1
      continue
    fi
    warn "$f NOT available locally or on the laptop"
  done
  [ "$any" = "1" ] || warn "no APKs staged at all — run ./stage-apks.sh against a working phone first"

  # ⚠️ Termux and its add-ons must come from the SAME signing source (GitHub vs
  #    F-Droid); a mismatched pair fails to install with a signature error.
  #    Staging both off a working device is the only way to be sure they match.
  if [ -f "$APK_DIR/termux.apk" ] && [ ! -f "$APK_DIR/termux-boot.apk" ]; then
    warn "termux.apk present but termux-boot.apk missing — do NOT download the add-on"
    warn "separately; get the matched pair from the same source or from stage-apks.sh"
  fi

  if [ "$NEXUS_APK_OK" -eq 0 ]; then
    cat <<EOF
  Nexus is built on talos, not downloaded. To build it:
      export JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
      export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
      (cd $NEXUS_SRC && ./gradlew assembleDebug)
  ⚠️ JAVA_HOME is not on PATH by default on talos — exporting it is required.
  ⚠️ The hub token and (later) the HA token are baked in at BUILD time from
     $NEXUS_SRC/local.properties. A build without them produces an app that
     shows "HUB REFUSED TOKEN". Check local.properties before building.
EOF
    bad "nexus.apk unavailable — cannot proceed to device owner without it"
  fi
}

# ---------------------------------------------------------------------------
step_install_nexus() {
  hdr "install Nexus (first, because device owner needs the package present)"
  if pkg_installed "$NEXUS_PKG"; then
    local v; v="$(sh_ "dumpsys package $NEXUS_PKG" | sed -n 's/.*versionName=\([^ ]*\).*/\1/p' | head -1)"
    skip "$NEXUS_PKG already installed (versionName=$v)"
    return 0
  fi
  if [ ! -f "$APK_DIR/nexus.apk" ] && [ "$DRY_RUN" -eq 0 ]; then
    bad "no nexus.apk to install"; return 1
  fi
  run adb -s "$DEV" install -r "$APK_DIR/nexus.apk" || { bad "nexus install failed"; return 1; }
  if [ "$DRY_RUN" -eq 0 ]; then
    pkg_installed "$NEXUS_PKG" || { bad "installed but $NEXUS_PKG is not present — refusing to continue"; return 1; }
  fi
  ok "$NEXUS_PKG installed"
  note_done "Nexus installed"
}

# ---------------------------------------------------------------------------
step_device_owner() {
  hdr "DEVICE OWNER — the gated, irreversible-ish step. It goes first."
  # WHY THIS IS EARLY: dpm set-device-owner is refused the moment ANY account
  # exists on the device. Everything after this point (installing apps, poking
  # settings, handing the phone back) is an opportunity for an account to appear.
  # So it happens as early as the package being present allows.
  #
  # ★ device_provisioned=1 does NOT block this. An earlier note claimed it did;
  #   it was wrong — it worked first try on an already-set-up device. The ONLY
  #   rule that actually bites is zero accounts.

  if is_device_owner; then
    skip "device owner already set to $NEXUS_ADMIN"
    ok "verified via dumpsys device_policy (⚠️ 'dpm list-owners' does not exist on API 29)"
    return 0
  fi

  local n; n="$(account_count)"
  if [ "${n:-0}" -ne 0 ]; then
    bad "$n account(s) on the device — dpm set-device-owner WILL be refused"
    cat <<EOF
  Remove every account before continuing:
      Settings → Accounts → (each one) → Remove account
  Then re-check with:
      adb -s $DEV shell dumpsys account | grep -c "Account {"
  ⚠️ This IS recoverable — removing the account restores the 0-account state and
     Tailscale survives it. But device owner cannot be set while one exists.
EOF
    return 1
  fi
  ok "0 accounts — the precondition holds"

  pkg_installed "$NEXUS_PKG" || { bad "$NEXUS_PKG not installed; cannot set device owner"; return 1; }

  # UNTESTED against a fresh device: on the live phone this is already set, so
  # only the skip path above has ever run here.
  run_sh "dpm set-device-owner $NEXUS_ADMIN" || { bad "dpm set-device-owner failed"; return 1; }

  if [ "$DRY_RUN" -eq 0 ]; then
    is_device_owner || { bad "dpm reported success but dumpsys device_policy does not show it"; return 1; }
  fi
  ok "device owner set to $NEXUS_ADMIN"
  note_done "device owner set"

  cat <<EOF
  ★ Escape hatch, tested 4x, in case this ever has to be undone (otherwise a
    device owner is factory-reset-only):
        adb -s $DEV shell am start -n $NEXUS_MAIN --ez clear_device_owner true
        adb -s $DEV shell cmd package set-home-activity $STOCK_LAUNCHER_ACT
    ⚠️ Re-test the hatch after ANY change to MainActivity or the receiver.
    ⚠️ A device-owner package is immune to 'am force-stop': the pid survives and
       'am start' only re-fronts the task. singleTop + onNewIntent in
       MainActivity are load-bearing for the hatch; the v1 hatch silently
       no-opped for exactly this reason.
EOF
}

# ---------------------------------------------------------------------------
step_nexus_home() {
  hdr "Nexus as the persistent home activity + RECORD_AUDIO by policy"
  # Nexus does both of these ITSELF on launch, when it finds it is device owner:
  # addPersistentPreferredActivity(HOME) and setPermissionGrantState(RECORD_AUDIO).
  # Both are device-owner-only calls. So the automation here is simply "start it
  # once and then check that it did its job" — not a reimplementation.

  if ! pkg_installed "$STOCK_LAUNCHER"; then
    # This is a real hazard, not a nitpick: without the stock launcher there is
    # no target for `cmd package set-home-activity`, and the escape hatch has
    # nowhere to send Home.
    bad "$STOCK_LAUNCHER is NOT installed — the recovery home screen is gone"
    warn "restore it before going further:  adb -s $DEV shell cmd package install-existing $STOCK_LAUNCHER"
  else
    ok "$STOCK_LAUNCHER present (recovery home screen)"
  fi

  if home_is_nexus && mic_granted; then
    skip "Home already resolves to Nexus and RECORD_AUDIO is granted"
    return 0
  fi

  run_sh "am start -n $NEXUS_MAIN" || bad "could not start $NEXUS_MAIN"
  [ "$DRY_RUN" -eq 0 ] && sleep 3

  if [ "$DRY_RUN" -eq 0 ]; then
    if home_is_nexus; then ok "Home resolves to $NEXUS_PKG.MainActivity (no picker)"
    else bad "Home does NOT resolve to Nexus — check 'adb logcat -s RoamNexus' for addPersistentPreferredActivity errors"; fi
    if mic_granted; then ok "RECORD_AUDIO granted (device-owner policy, POLICY_FIXED)"
    else bad "RECORD_AUDIO not granted — PTT will pop a permission dialog mid-press"; fi
  fi
  note_done "Nexus is home; mic permission granted by policy"
}

# ---------------------------------------------------------------------------
step_install_apps() {
  hdr "the other three sideloaded apps"
  # ⚠️ There is NO Play Store on this device (removed by design, see debloat.txt).
  #    adb install is the only install path that exists. That is deliberate: the
  #    store is the likeliest route to an accidental Google account.
  local pairs="$TERMUX_PKG:termux.apk $TERMUX_BOOT_PKG:termux-boot.apk $TAILSCALE_PKG:tailscale.apk $HA_PKG:ha-minimal.apk"
  local p pkg file
  for p in $pairs; do
    pkg="${p%%:*}"; file="${p##*:}"
    if pkg_installed "$pkg"; then skip "$pkg already installed"; continue; fi
    if [ ! -f "$APK_DIR/$file" ] && [ "$DRY_RUN" -eq 0 ]; then
      bad "$file missing — cannot install $pkg"; continue
    fi
    if run adb -s "$DEV" install -r "$APK_DIR/$file"; then
      if [ "$DRY_RUN" -eq 0 ] && ! pkg_installed "$pkg"; then
        bad "install of $file reported success but $pkg is not present"
      else
        ok "$pkg installed"; note_done "$pkg installed"
      fi
    else
      bad "install of $file failed"
      case "$pkg" in
        "$TERMUX_BOOT_PKG"|"$TERMUX_PKG")
          warn "⚠️ if this is a signature error: Termux and termux-boot must come from the"
          warn "   SAME source (GitHub-signed ≠ F-Droid-signed). Get a matched pair." ;;
      esac
    fi
  done

  # Home Assistant is installed but is NOT expected to render. Say so here so
  # nobody re-debugs it after a rebuild and concludes the provisioning failed.
  cat <<EOF
  ⚠️ The HA companion app installs and runs but shows a BLANK WHITE SCREEN, and
     that is expected, not a provisioning failure. This phone's WebView and
     Chrome are frozen at 74.0.3729.186 (2019) — they shipped with the Android 10
     factory image and can only update through the Play Store, which is gone.
     Proved by loading the HA URL in Chrome directly: also blank. Sideloading a
     WebView provider is not possible (the allowed providers are signature-pinned).
     The working path is Nexus's native REST client against $HA_URL. Do not burn
     time on this again.
EOF
}

# ---------------------------------------------------------------------------
step_debloat() {
  hdr "debloat — $(debloat_list | wc -l | tr -d ' ') packages, all reversible"
  local pkg removed=0 already=0 failed=0
  for pkg in $(debloat_list); do
    if ! pkg_known "$pkg"; then
      # Not on this build at all. Not an error — factory images differ.
      warn "$pkg not present on this build, nothing to remove"
      continue
    fi
    if ! pkg_installed "$pkg"; then already=$((already+1)); continue; fi
    if run_sh_q "pm uninstall --user 0 $pkg" || [ "$DRY_RUN" -eq 1 ]; then
      if [ "$DRY_RUN" -eq 0 ] && pkg_installed "$pkg"; then
        bad "$pkg: pm uninstall returned success but it is still installed"; failed=$((failed+1))
      else
        removed=$((removed+1))
      fi
    else
      bad "$pkg: pm uninstall --user 0 failed"; failed=$((failed+1))
    fi
  done
  if [ "$DRY_RUN" -eq 1 ]; then
    ok "would remove $removed, already gone $already"
  else
    ok "removed $removed, already gone $already, failed $failed"
  fi
  [ "$failed" -eq 0 ] || bad "$failed package(s) could not be removed"
  # Guard the one package that must never leave.
  pkg_installed "$STOCK_LAUNCHER" || bad "$STOCK_LAUNCHER was removed — restore it NOW, it is the recovery home screen"
  note_done "debloat applied (undo: ./provision.sh restore-debloat)"
}

cmd_restore_debloat() {
  hdr "restore-debloat — putting every debloated package back"
  # `pm uninstall --user 0` never deleted the APKs, so this always works and
  # never needs a reflash. This is the whole reason the debloat is safe.
  local pkg n=0
  for pkg in $(debloat_list); do
    pkg_installed "$pkg" && { skip "$pkg already installed"; continue; }
    pkg_known "$pkg" || { warn "$pkg not on this build"; continue; }
    if run_sh_q "cmd package install-existing $pkg" || [ "$DRY_RUN" -eq 1 ]; then
      if [ "$DRY_RUN" -eq 1 ]; then ok "$pkg would be restored"; else ok "$pkg restored"; fi
      n=$((n+1))
    else
      bad "$pkg could not be restored"
    fi
  done
  ok "$n package(s) restored"
}

# ---------------------------------------------------------------------------
step_settings() {
  hdr "settings"
  # Each of these is set, then read back. `settings put` is silent on failure —
  # a typo'd key succeeds and stores nothing, which is exactly the kind of quiet
  # half-provisioning this script is supposed to make impossible.
  set_global() {
    local key="$1" want="$2" why="$3" cur
    cur="$(gset global "$key")"
    if [ "$cur" = "$want" ]; then skip "global.$key = $want already  ($why)"; return 0; fi
    run_sh_q "settings put global $key $want"
    if [ "$DRY_RUN" -eq 0 ]; then
      cur="$(gset global "$key")"
      [ "$cur" = "$want" ] && ok "global.$key = $want  ($why)" || bad "global.$key is '$cur', wanted '$want'"
    fi
  }
  set_system() {
    local key="$1" want="$2" why="$3" cur
    cur="$(gset system "$key")"
    if [ "$cur" = "$want" ]; then skip "system.$key = $want already  ($why)"; return 0; fi
    run_sh_q "settings put system $key $want"
    if [ "$DRY_RUN" -eq 0 ]; then
      cur="$(gset system "$key")"
      [ "$cur" = "$want" ] && ok "system.$key = $want  ($why)" || bad "system.$key is '$cur', wanted '$want'"
    fi
  }

  # 7 = AC | USB | wireless. The device is a wrist display driven from talos; a
  # screen that sleeps mid-session while it is on the charger is a nuisance, and
  # a sleeping screen also drops the hub websocket connection sooner.
  set_global stay_on_while_plugged_in 7 "stay awake on any charger"

  # 2 = never sleep Wi-Fi. The hub pushes events over a websocket and the phone
  # must be reachable by adb. Wi-Fi sleeping on screen-off breaks both.
  # ⚠️ Deprecated key on API 29+, but it still reads and writes on this build.
  set_global wifi_sleep_policy 2 "never sleep Wi-Fi (keeps hub WS + adb alive)"

  # 0 = radio off. The SIM is dead. A modem hunting for a network it will never
  # find is pure battery drain on a 2016 cell, and every telephony service on
  # the device wakes up alongside it.
  set_global cell_on 0 "cellular radio OFF — dead SIM, nothing to connect to"

  # 30 minutes. Long enough to read a channel without the screen dying; not
  # infinite, because the bracer will get bumped and left face-up.
  set_system screen_off_timeout 1800000 "30 min screen timeout"

  # ★★ LOCK THE WHOLE DEVICE TO reverseLandscape. Nexus locks its own activity
  # (screenOrientation="reverseLandscape" in the manifest), but that only holds while
  # you are IN Nexus — the moment a tile launches Chrome or Settings, the accelerometer
  # takes over and a device strapped to a forearm ends up sideways. Found 2026-08-14
  # when the app-tray tiles shipped: "chrome works, same issue, need locked to landscape
  # for everything".
  # ⚠️ This is a DEVICE setting, not something the app enforces — so if the orientation
  # ever comes unstuck, the cause is here and not in Kotlin. 3 = ROTATION_270, which is
  # what reverseLandscape resolves to; it must match the manifest or the device and the
  # app will disagree by 180 degrees.
  set_system accelerometer_rotation 0 "no auto-rotate: it is worn, not held"
  set_system user_rotation 3 "reverseLandscape (270), matching Nexus's manifest"

  # Sanity, not configuration: these should already be true and it costs nothing
  # to notice if a reflash left them otherwise.
  [ "$(gset global adb_enabled)" = "1" ] || bad "adb_enabled is not 1 (how are we even talking?)"
  [ "$(gset global development_settings_enabled)" = "1" ] || warn "developer options not enabled"
  note_done "settings applied (stay-awake, Wi-Fi never sleeps, radio off, 30min timeout)"
}

# ---------------------------------------------------------------------------
step_doze() {
  hdr "doze whitelist"
  # Doze will otherwise defer the very things this device exists to do: the hub
  # websocket (Nexus), the tailnet (Tailscale) and HA polling. These three are
  # exactly what is whitelisted on the live device — verified 2026-08-12.
  # ⚠️ Termux and termux-boot are deliberately NOT whitelisted: they run nothing
  #    resident today (there is no sshd), so whitelisting them would only cost
  #    battery. Add them here if that ever changes.
  local pkg
  for pkg in "$NEXUS_PKG" "$TAILSCALE_PKG" "$HA_PKG"; do
    if doze_whitelisted "$pkg"; then skip "$pkg already doze-whitelisted"; continue; fi
    if ! pkg_installed "$pkg"; then warn "$pkg not installed, skipping whitelist"; continue; fi
    run_sh_q "dumpsys deviceidle whitelist +$pkg"
    if [ "$DRY_RUN" -eq 0 ]; then
      doze_whitelisted "$pkg" && ok "$pkg whitelisted" || bad "$pkg whitelist did not take"
    fi
  done
  note_done "doze whitelist: Nexus, Tailscale, Home Assistant"
}

# ---------------------------------------------------------------------------
step_permissions() {
  hdr "runtime permissions"
  # RECORD_AUDIO for Nexus is granted by DEVICE-OWNER POLICY, not by `pm grant`
  # — see step_nexus_home. It lands POLICY_FIXED, which is what stops a runtime
  # dialog appearing after the thumb is already down on the PTT button.
  if mic_granted; then
    ok "$NEXUS_PKG RECORD_AUDIO granted (by policy, from Nexus itself)"
  else
    bad "$NEXUS_PKG RECORD_AUDIO NOT granted"
    warn "the policy grant happens when Nexus starts as device owner; re-run --only nexus_home"
    warn "last-resort manual grant: adb -s $DEV shell pm grant $NEXUS_PKG android.permission.RECORD_AUDIO"
  fi

  # Tailscale holds storage permissions on the live device (it uses them for
  # taildrop / log export). Reproduced here so a rebuilt phone matches.
  local perm
  for perm in android.permission.READ_EXTERNAL_STORAGE android.permission.WRITE_EXTERNAL_STORAGE; do
    if ! pkg_installed "$TAILSCALE_PKG"; then warn "Tailscale not installed"; break; fi
    if perm_granted "$TAILSCALE_PKG" "$perm"; then skip "$TAILSCALE_PKG $perm already granted"; continue; fi
    run_sh_q "pm grant $TAILSCALE_PKG $perm"
    if [ "$DRY_RUN" -eq 0 ]; then
      perm_granted "$TAILSCALE_PKG" "$perm" && ok "$TAILSCALE_PKG $perm granted" || bad "$TAILSCALE_PKG $perm grant failed"
    fi
  done

  # ⚠️ Home Assistant's location/phone/camera/mic permissions are all DENIED on
  #    the live device and are left that way on purpose: the app cannot render
  #    anything anyway (WebView 74), and Nexus talks to HA over REST instead.
  ok "HA permissions intentionally left ungranted (the app is a dead end here)"
}

# ---------------------------------------------------------------------------
gate_tailscale() {
  hdr "Tailscale — human step"
  # No automation is possible or desirable: it is an OAuth/SSO login in a
  # browser, and the auth key would be a credential this script must never hold.
  gate "Tailscale login" \
"On the phone: open Tailscale → Log in → complete the sign-in → allow the VPN
profile when Android asks.

Then confirm the machine comes back as \"pixel\" at 100.95.196.87 in the
tailnet admin panel. If it registers under a new name or address, update
ROAM_DEVICE and the notes — everything on talos points at that address.

⚠️ This is a Tailscale account, not a Google account. Do not sign into Google." \
    tailscale_up
}

# ---------------------------------------------------------------------------
gate_headset() {
  hdr "Bluetooth headset — human step"
  # The built-in analog mic delivers nothing (all-zero samples, pcm_prepare -1
  # on every source/rate/buffer). A BT headset over SCO is the only working
  # capture path today. Pairing needs the headset physically in pairing mode
  # and a tap on the phone's screen; there is no adb path.
  gate "Pair $HEADSET_NAME" \
"Put the $HEADSET_NAME in pairing mode, then on the phone:
   Settings → Connected devices → Pair new device → $HEADSET_NAME

Why this matters: the phone's own analog mic captures NOTHING (all-zero
samples, pcm_prepare -1 on every source/rate/buffer combination tried). SCO
from a headset is the only capture path that works, and only with audio source
VOICE_RECOGNITION — MIC / VOICE_COMMUNICATION / DEFAULT silently fall back to
the dead built-in mic on this Qualcomm HAL.

(Skip this if the point of the current rebuild is to test the built-in mic on a
different firmware — in that case test the built-in mic FIRST, before pairing
anything, so there is no doubt about which path is being measured.)" \
    headset_bonded
}

# ---------------------------------------------------------------------------
gate_ha_token() {
  hdr "Home Assistant token — human step (on talos, not the phone)"
  # The token is baked into the app at BUILD time from local.properties. It is
  # a credential only Nick can mint, and this script will never invent one.
  gate "HA long-lived access token" \
"In Home Assistant ($HA_URL):
    Profile → Security → Long-lived access tokens → Create Token

Then on talos, add it to $NEXUS_SRC/local.properties:
    roam.ha.token=eyJhbGciOi…
and rebuild + reinstall Nexus:
    export JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
    export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
    (cd $NEXUS_SRC && ./gradlew assembleDebug)
    adb -s $DEV install -r $NEXUS_BUILT_APK

⚠️ Nothing can create this token but you, and nothing here will fake one.
⚠️ local.properties is gitignored and holds the hub token too — it lives on
   talos and is NOT affected by reflashing the phone, so this step is only
   needed if the token itself was never set." \
    ha_token_set
}

# ---------------------------------------------------------------------------
step_verify() {
  hdr "verify — full read-only audit"
  local n
  n="$(account_count)"
  [ "${n:-0}" -eq 0 ] && ok "accounts = 0 (device owner stays possible)" || bad "accounts = $n — device owner cannot be re-established without removing them"
  is_device_owner && ok "device owner = $NEXUS_ADMIN" || bad "device owner NOT set"
  home_is_nexus && ok "Home resolves to Nexus" || bad "Home does not resolve to Nexus"
  mic_granted && ok "Nexus RECORD_AUDIO granted" || bad "Nexus RECORD_AUDIO not granted"
  pkg_installed "$STOCK_LAUNCHER" && ok "stock launcher present (recovery target)" || bad "stock launcher missing"

  local p
  for p in "$NEXUS_PKG" "$TERMUX_PKG" "$TERMUX_BOOT_PKG" "$TAILSCALE_PKG" "$HA_PKG"; do
    pkg_installed "$p" && ok "installed: $p" || bad "missing: $p"
  done

  local left; left=0
  for p in $(debloat_list); do pkg_installed "$p" && left=$((left+1)); done
  [ "$left" -eq 0 ] && ok "debloat complete ($(debloat_list | wc -l | tr -d ' ') packages removed)" || warn "$left debloat-list package(s) still installed"

  [ "$(gset global stay_on_while_plugged_in)" = "7" ] && ok "stay_on_while_plugged_in = 7" || bad "stay_on_while_plugged_in = $(gset global stay_on_while_plugged_in)"
  [ "$(gset global wifi_sleep_policy)" = "2" ] && ok "wifi_sleep_policy = 2" || bad "wifi_sleep_policy = $(gset global wifi_sleep_policy)"
  [ "$(gset global cell_on)" = "0" ] && ok "cell_on = 0 (radio off)" || bad "cell_on = $(gset global cell_on)"

  for p in "$NEXUS_PKG" "$TAILSCALE_PKG" "$HA_PKG"; do
    doze_whitelisted "$p" && ok "doze whitelist: $p" || bad "not doze-whitelisted: $p"
  done

  tailscale_up && ok "tailnet reachable (talos $HUB_HOST answers)" || warn "cannot reach talos over the tailnet — Tailscale logged in?"
  headset_bonded && ok "$HEADSET_NAME bonded (the only working mic path)" || warn "$HEADSET_NAME not bonded — no working microphone"
  ha_token_set && ok "roam.ha.token present in nexus/local.properties" || warn "roam.ha.token not set — HA tiles will not authenticate"
}

# ---------------------------------------------------------------------------
step_summary() {
  hdr "summary"
  printf '%sIN PLACE — handled automatically (done this run, or already correct):%s%s\n' "$C_G" "$C_0" "${DONE_NOTES:-
  (nothing — dry run, or everything was already in place)}"

  printf '\n%sYOURS TO DO — nothing else can:%s%s\n' "$C_Y" "$C_0" "${TODO_NOTES:-
  (none outstanding)}"

  cat <<EOF

${C_Y}Standing reminders${C_0}
  • ⚠️ adb over Wi-Fi dies at every reboot. USB + 'adb tcpip 5555' to get it back.
  • ⚠️ Never sign in to a Google account. Zero accounts is what device owner needs.
  • ⚠️ The HA companion app's blank screen is expected (WebView 74). Not a bug to fix.
  • The escape hatch, if Nexus-as-home ever has to be undone:
        adb -s $DEV shell am start -n $NEXUS_MAIN --ez clear_device_owner true
        adb -s $DEV shell cmd package set-home-activity $STOCK_LAUNCHER_ACT
  • Undo the debloat with: ./provision.sh restore-debloat

Re-audit any time with:  ./provision.sh verify
EOF

  if [ "$FAILURES" -gt 0 ]; then
    printf '\n%s%d FAILURE(S) above. The phone is NOT fully provisioned.%s\n' "$C_R" "$FAILURES" "$C_0"
    return 1
  fi
  printf '\n%sNo failures.%s\n' "$C_G" "$C_0"
  return 0
}

# =============================================================================
# Driver
# =============================================================================
# Ordered so the gated and hard-to-undo things happen while the device is still
# pristine: device owner before anything can add an account, and the human gates
# that need a logged-in service last.
STEPS="preflight wifi adb_wifi apks install_nexus device_owner nexus_home install_apps debloat settings doze permissions tailscale headset ha_token verify"

step_fn() {
  case "$1" in
    preflight)     step_preflight ;;
    wifi)          gate_wifi ;;
    adb_wifi)      step_adb_wifi ;;
    apks)          step_apks ;;
    install_nexus) step_install_nexus ;;
    device_owner)  step_device_owner ;;
    nexus_home)    step_nexus_home ;;
    install_apps)  step_install_apps ;;
    debloat)       step_debloat ;;
    settings)      step_settings ;;
    doze)          step_doze ;;
    permissions)   step_permissions ;;
    tailscale)     gate_tailscale ;;
    headset)       gate_headset ;;
    ha_token)      gate_ha_token ;;
    verify)        step_verify ;;
    *) die "unknown step '$1'" ;;
  esac
}

CMD="provision"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|-n) DRY_RUN=1; shift ;;
    -s|--device)  DEV="$2"; shift 2 ;;
    --only)       ONLY="$2"; shift 2 ;;
    --from)       FROM="$2"; shift 2 ;;
    --list)       echo "$STEPS" | tr ' ' '\n'; exit 0 ;;
    -h|--help)    sed -n '2,70p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    verify|restore-debloat|provision) CMD="$1"; shift ;;
    *) die "unknown argument '$1' (try --help)" ;;
  esac
done

valid_step() {
  local s
  for s in $STEPS; do [ "$s" = "$1" ] && return 0; done
  return 1
}
[ -n "$ONLY" ] && ! valid_step "$ONLY" && die "--only '$ONLY' is not a step. See --list."
[ -n "$FROM" ] && ! valid_step "$FROM" && die "--from '$FROM' is not a step. See --list."

[ "$DRY_RUN" -eq 1 ] && printf '%s*** DRY RUN — nothing on the phone will be changed ***%s\n' "$C_Y" "$C_0"
printf 'device: %s\n' "$DEV"

case "$CMD" in
  verify)
    step_preflight || exit 1
    step_verify
    [ "$FAILURES" -eq 0 ] || { printf '\n%s%d problem(s).%s\n' "$C_R" "$FAILURES" "$C_0"; exit 1; }
    printf '\n%sFully provisioned.%s\n' "$C_G" "$C_0"
    ;;
  restore-debloat)
    step_preflight || exit 1
    cmd_restore_debloat
    ;;
  provision)
    started=0
    [ -n "$FROM" ] || started=1
    for s in $STEPS; do
      if [ -n "$ONLY" ]; then [ "$s" = "$ONLY" ] || continue; fi
      if [ "$started" -eq 0 ]; then [ "$s" = "$FROM" ] && started=1 || continue; fi
      step_fn "$s"
    done
    [ -n "$ONLY" ] || step_summary
    ;;
esac
exit $(( FAILURES > 0 ? 1 : 0 ))
