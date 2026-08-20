#!/bin/sh
# Build dist/Nexus.app from the SwiftPM release binary. No Xcode required.
set -e
cd "$(dirname "$0")/.."
swift build -c release
APP=dist/Nexus.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/Nexus "$APP/Contents/MacOS/Nexus"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Nexus</string>
    <key>CFBundleDisplayName</key><string>Nexus</string>
    <key>CFBundleIdentifier</key><string>com.roam.nexus</string>
    <key>CFBundleVersion</key><string>7</string>
    <key>CFBundleShortVersionString</key><string>0.3.1</string>
    <key>CFBundleExecutable</key><string>Nexus</string>
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
