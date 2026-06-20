#!/usr/bin/env bash
set -euo pipefail

# Re-home the bundled relocatable venv to the current machine.
# The bundle ships a standalone Python (bundle/python) and a std venv
# (bundle/.venv) whose pyvenv.cfg `home` and the editable .pth point to the
# build machine's absolute paths. This rewrites them to the local paths so the
# venv works after the bundle is moved/extracted anywhere.

ROOT="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"

VENV_CFG="$ROOT/bundle/.venv/pyvenv.cfg"
PY_HOME="$ROOT/bundle/python"
PY_BIN="$PY_HOME/bin/python3.11"
[[ -x "$PY_BIN" ]] || PY_BIN="$PY_HOME/bin/python3"

# Nothing to do for dev installs (no bundle) or legacy bundles without an
# embedded Python — those can't be re-homed offline.
[[ -f "$VENV_CFG" ]] || exit 0
[[ -x "$PY_BIN" ]] || exit 0

VENV_PATH="$ROOT/bundle/.venv"
TMP_CFG="$(mktemp)"
while IFS= read -r line; do
  case "$line" in
    home\ =*|home=*) echo "home = $PY_HOME" ;;
    executable\ =*|executable=*) echo "executable = $PY_BIN" ;;
    command\ =*|command=*) echo "command = $PY_BIN -m venv $VENV_PATH" ;;
    *) echo "$line" ;;
  esac
done < "$VENV_CFG" > "$TMP_CFG"
mv "$TMP_CFG" "$VENV_CFG"

SRC_PATH="$ROOT/src"
SITE_PACKAGES="$(find "$VENV_PATH/lib" -maxdepth 1 -type d -name 'python*' 2>/dev/null | head -n 1)/site-packages"
if [[ -d "$SITE_PACKAGES" ]]; then
  for pth in "$SITE_PACKAGES"/*editable*jarvis*.pth; do
    [[ -f "$pth" ]] || continue
    echo "$SRC_PATH" > "$pth"
  done
fi
