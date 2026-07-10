#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ ! -d ".venv" ]; then
  echo "First-time setup is required. Running mac_install.sh..."
  chmod +x mac_install.sh || true
  ./mac_install.sh
  exit 0
fi

source .venv/bin/activate
python app.py
