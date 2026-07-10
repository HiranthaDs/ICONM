#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "ICON MOBILE ERP - macOS setup"
echo "Project: $APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed."
  echo "Install Python 3 from https://www.python.org/downloads/macos/ then run this again."
  exit 1
fi

PY_VERSION="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
echo "Python: $PY_VERSION"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

python diagnose.py

echo ""
echo "Setup complete."
echo "To run the app later, double-click RUN_MAC_APP.command or run:"
echo "  ./RUN_MAC_APP.command"
echo ""
python app.py
