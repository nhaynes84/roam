#!/bin/bash
# render.sh — Render all Roam housing STL files
# Requires OpenSCAD installed and on PATH
#
# Usage: ./render.sh [--fast]
#   --fast  Lower resolution for quick preview ($fn=30)

set -euo pipefail
cd "$(dirname "$0")"

FAST_FLAG=""
if [[ "${1:-}" == "--fast" ]]; then
    FAST_FLAG="-D '\$fn=30'"
    echo "Fast mode: reduced resolution"
fi

echo "Rendering roam_case.stl..."
eval openscad -o roam_case.stl roam_case.scad $FAST_FLAG
echo "  Done: $(du -h roam_case.stl | cut -f1)"

echo "Rendering roam_lid.stl..."
eval openscad -o roam_lid.stl roam_lid.scad $FAST_FLAG
echo "  Done: $(du -h roam_lid.stl | cut -f1)"

echo "Rendering roam_button_cap.stl..."
eval openscad -o roam_button_cap.stl roam_button_cap.scad $FAST_FLAG
echo "  Done: $(du -h roam_button_cap.stl | cut -f1)"

echo ""
echo "All STLs rendered:"
ls -lh *.stl
