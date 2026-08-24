#!/bin/sh
# Build dist/Nexus.app from the SwiftPM release binary. No Xcode required.
set -e
cd "$(dirname "$0")/.."
swift build -c release
APP=dist/Nexus.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/Nexus "$APP/Contents/MacOS/Nexus"

# The mark: convergence / connection / redundancy / adaptability. Generated from
# scratch (see the project's makeicon.py) rather than a stock glyph, and shipped as
# a real .icns so the Dock, Finder and ⌘-Tab all get the right size instead of
# scaling one bitmap.
mkdir -p "$APP/Contents/Resources"
cp Resources/Nexus.icns "$APP/Contents/Resources/Nexus.icns"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Nexus</string>
    <key>CFBundleDisplayName</key><string>Nexus</string>
    <key>CFBundleIdentifier</key><string>com.roam.nexus</string>
    <key>CFBundleVersion</key><string>9</string>
    <key>CFBundleShortVersionString</key><string>0.3.3</string>
    <key>CFBundleExecutable</key><string>Nexus</string>
    <key>CFBundleIconFile</key><string>Nexus</string>
    <!-- Stream captures audio. macOS refuses the mic outright without this string,
         and the refusal is silent from the app's side — the engine just returns
         empty buffers, which looks exactly like a broken microphone. -->
    <!-- ⚠️ Without this macOS refuses the camera SILENTLY — no frames, no error,
         which is indistinguishable from a broken camera. Exactly the trap the
         microphone had. -->
    <key>NSCameraUsageDescription</key><string>Stream uses the camera to show your room on the open channel, when you or another device turns it on.</string>
    <key>NSMicrophoneUsageDescription</key><string>Stream uses the microphone to open an audio channel to your other devices, and to talk back on push-to-talk.</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <!-- The hub is plain HTTP bound to the tailnet only; WireGuard is the
             encryption layer (hub/API.md §1). ATS would block it otherwise. -->
        <key>NSAllowsArbitraryLoads</key><true/>
    </dict>
</dict>
</plist>
PLIST
codesign --force -s - "$APP"
echo "built $APP"
