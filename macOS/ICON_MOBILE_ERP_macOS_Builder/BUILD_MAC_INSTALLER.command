#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

chmod +x BUILD_MAC_APP.sh
./BUILD_MAC_APP.sh

echo ""
echo "The macOS installer is ready in the dist folder."
echo "Press Return to open it."
read -r _
open "$SCRIPT_DIR/dist"
