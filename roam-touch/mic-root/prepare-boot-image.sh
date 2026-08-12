#!/usr/bin/env bash
#
# prepare-boot-image.sh — build the Magisk-patched boot image used for the TEMPORARY root test.
#
# Nothing here writes to the phone's boot partition. The output is meant for `fastboot boot`
# (RAM only), never `fastboot flash`.
#
# Why patching happens ON THE PHONE: magiskboot is an arm64 Android binary, there is no macOS
# build, and Magisk's GUI "patch a file" flow is exactly this script (assets/boot_patch.sh) with
# the environment flags the app computes. We compute the same flags ourselves, from the device:
#
#   KEEPVERITY=true        SYSTEM_AS_ROOT (`/dev/root / ext4` in /proc/mounts)  -> keep dm-verity
#   KEEPFORCEENCRYPT=true  ro.crypto.state=encrypted (file-based)
#   PATCHVBMETAFLAG=true   sailfish has NO vbmeta partition (AVB 1.0)
#   RECOVERYMODE=false     we want a normal Android boot, not recovery
#   LEGACYSAR=true         legacy system-as-root: this is the load-bearing one. It makes
#                          magiskboot hex-patch the kernel `skip_initramfs` -> `want_initramfs`,
#                          so the bootloader's cmdline flag no longer matches and the ramdisk
#                          (whose /init is now magiskinit) actually runs. Without it the patched
#                          image boots stock and unrooted.
#
set -euo pipefail

SERIAL=${SERIAL:-100.95.196.87:5555}
T=/data/local/tmp/TESTmicroot
WORK=${WORK:-$(mktemp -d)}
MAGISK_VER=${MAGISK_VER:-v30.7}

echo "work dir: $WORK"
cd "$WORK"

# 1. stock boot.img for the running build, straight out of the staged factory image
ssh nicks-macbook-pro \
  "cd ~/pixel/sailfish-qp1a.191005.007.a3 && unzip -p image-sailfish-qp1a.191005.007.a3.zip boot.img" > boot.img
echo "stock boot.img: $(shasum -a 256 boot.img)"

# 2. Magisk APK -> the patch toolkit
curl -sL -o "Magisk-$MAGISK_VER.apk" \
  "https://github.com/topjohnwu/Magisk/releases/download/$MAGISK_VER/Magisk-$MAGISK_VER.apk"
mkdir -p apk stage && (cd apk && unzip -oq "../Magisk-$MAGISK_VER.apk" 'assets/*' 'lib/arm64-v8a/*')
cp apk/assets/boot_patch.sh apk/assets/util_functions.sh apk/assets/stub.apk stage/
cp apk/lib/arm64-v8a/libmagiskboot.so stage/magiskboot
cp apk/lib/arm64-v8a/libmagiskinit.so stage/magiskinit
cp apk/lib/arm64-v8a/libmagisk.so     stage/magisk
cp apk/lib/arm64-v8a/libinit-ld.so    stage/init-ld
cp apk/lib/arm64-v8a/libbusybox.so    stage/busybox

# 3. stage on the phone and patch there
adb -s "$SERIAL" shell "rm -rf $T; mkdir -p $T"
adb -s "$SERIAL" push stage/. "$T/"
adb -s "$SERIAL" push boot.img "$T/boot.img"
adb -s "$SERIAL" shell "chmod 755 $T/*"
adb -s "$SERIAL" shell "cd $T && KEEPVERITY=true KEEPFORCEENCRYPT=true PATCHVBMETAFLAG=true \
  RECOVERYMODE=false LEGACYSAR=true ./busybox sh ./boot_patch.sh boot.img"

# 4. verify BEFORE anyone reboots anything
adb -s "$SERIAL" shell "cd $T && rm -rf verify && mkdir verify && cp magiskboot new-boot.img verify/ \
  && cd verify && ./magiskboot unpack new-boot.img >/dev/null 2>&1 \
  && echo -n 'ramdisk magisk-patched (want 1): ' && (./magiskboot cpio ramdisk.cpio test; echo \$?) \
  && echo -n 'kernel want_initramfs (want 1): ' && ../busybox grep -c want_initramfs kernel \
  && echo -n 'kernel skip_initramfs (want 0): ' && ../busybox grep -c skip_initramfs kernel"

# 5. bring the patched image back to the host that will run fastboot
adb -s "$SERIAL" pull "$T/new-boot.img" ./TESTmagisk-boot-sailfish-QP1A.191005.007.A3.img
echo "patched image: $WORK/TESTmagisk-boot-sailfish-QP1A.191005.007.A3.img"
echo "USE WITH: fastboot boot <that file>    — NEVER fastboot flash"
