#!/bin/sh
# swift test on a Command-Line-Tools-only box (no Xcode).
#
# CLT ships swift-testing as Testing.framework outside the default search
# paths, and its lib_TestingInterop.dylib one directory over from that. Both
# must be handed to the compiler/linker explicitly or `swift test` reports
# "no such module 'Testing'" / dlopen failures. With Xcode installed none of
# this is needed — but don't remove it, talos builds with CLT.
set -e
CLT=/Library/Developer/CommandLineTools
FW="$CLT/Library/Developer/Frameworks"
INTEROP="$CLT/Library/Developer/usr/lib"
cd "$(dirname "$0")/.."
exec swift test \
  -Xswiftc -F -Xswiftc "$FW" \
  -Xlinker -F -Xlinker "$FW" \
  -Xlinker -rpath -Xlinker "$FW" \
  -Xlinker -rpath -Xlinker "$INTEROP" \
  "$@"
