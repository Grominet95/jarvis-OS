#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BUNDLE_ROOT="$ROOT/bundle"
VENV_PATH="$BUNDLE_ROOT/.venv"
PYTHON_DIR="$BUNDLE_ROOT/python"
MODELS_DIR="$BUNDLE_ROOT/models"
PIPER_DIR="$MODELS_DIR/piper"
BIN_DIR="$BUNDLE_ROOT/bin"

echo "Jarvis — build offline bundle"
echo "This script downloads Python deps and models once."
echo ""

if ! command -v uv >/dev/null 2>&1; then
  echo "uv missing — install from https://docs.astral.sh/uv/"
  exit 1
fi

mkdir -p "$BUNDLE_ROOT" "$MODELS_DIR" "$PIPER_DIR" "$BIN_DIR"

# A standalone Python is embedded and the venv is created with the std `venv`
# module (--copies). uv's own venv bakes the base interpreter path into its
# python trampoline, which is NOT relocatable across machines. The std venv
# reads `home` from pyvenv.cfg, so it can be re-homed on the target machine
# (see scripts/release/rehome_bundle.sh).
echo "[1/6] Embed relocatable Python into bundle/python"
rm -rf "$PYTHON_DIR"
PY_INSTALL_CACHE="$BUNDLE_ROOT/.python-install"
rm -rf "$PY_INSTALL_CACHE"
export UV_PYTHON_INSTALL_DIR="$PY_INSTALL_CACHE"
uv python install 3.11
MANAGED_PYTHON="$(find "$PY_INSTALL_CACHE" -name 'python3.11' -type f | head -n 1)"
if [[ -z "$MANAGED_PYTHON" ]]; then
  MANAGED_PYTHON="$(find "$PY_INSTALL_CACHE" -name 'python3' -type f | head -n 1)"
fi
if [[ -z "$MANAGED_PYTHON" ]]; then
  echo "managed python not found after install"
  exit 1
fi
MANAGED_ROOT="$(cd "$(dirname "$MANAGED_PYTHON")/.." && pwd)"
mkdir -p "$PYTHON_DIR"
cp -a "$MANAGED_ROOT/." "$PYTHON_DIR/"
rm -rf "$PY_INSTALL_CACHE"
BUNDLE_BASE_PYTHON="$PYTHON_DIR/bin/python3.11"
[[ -x "$BUNDLE_BASE_PYTHON" ]] || BUNDLE_BASE_PYTHON="$PYTHON_DIR/bin/python3"
if [[ ! -x "$BUNDLE_BASE_PYTHON" ]]; then
  echo "bundle base python missing"
  exit 1
fi

echo "[2/6] Create relocatable venv (std venv --copies)"
rm -rf "$VENV_PATH"
"$BUNDLE_BASE_PYTHON" -m venv --copies "$VENV_PATH"
BUNDLE_PYTHON="$VENV_PATH/bin/python"
if [[ ! -x "$BUNDLE_PYTHON" ]]; then
  echo "bundle venv python missing"
  exit 1
fi

echo "[3/6] Install deps + jarvis into venv"
uv pip install --python "$BUNDLE_PYTHON" -e ".[vision]"
"$BUNDLE_PYTHON" -c "import jarvis.setup_app"

echo "[4/6] Copy uv binary"
cp "$(command -v uv)" "$BIN_DIR/uv"
chmod +x "$BIN_DIR/uv"

echo "[5/6] Download ML models"
if [[ ! -f yolov8n.pt ]]; then
  uv run --python "$BUNDLE_PYTHON" python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
fi
cp yolov8n.pt "$MODELS_DIR/yolov8n.pt"

PIPER_ONNX="$PIPER_DIR/fr_FR-upmc-medium.onnx"
PIPER_JSON="${PIPER_ONNX}.json"
if [[ ! -f "$PIPER_ONNX" ]]; then
  BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium"
  curl -L --silent -o "$PIPER_ONNX" "${BASE_URL}/fr_FR-upmc-medium.onnx"
  curl -L --silent -o "$PIPER_JSON" "${BASE_URL}/fr_FR-upmc-medium.onnx.json"
fi

echo "[6/6] Download livekit-server"
OS="$(uname -s)"
ARCH="$(uname -m)"
LK_TARGET="$BIN_DIR/livekit-server"
if [[ ! -x "$LK_TARGET" ]]; then
  RELEASE_JSON="$(curl -fsSL -H "User-Agent: jarvis-bundle" "https://api.github.com/repos/livekit/livekit/releases/latest")"
  case "$OS" in
    Darwin)
      if [[ "$ARCH" == "arm64" ]]; then
        PATTERN='livekit_.*_darwin_arm64\.tar\.gz'
      else
        PATTERN='livekit_.*_darwin_amd64\.tar\.gz'
      fi
      ;;
    Linux)
      if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        PATTERN='livekit_.*_linux_arm64\.tar\.gz'
      else
        PATTERN='livekit_.*_linux_amd64\.tar\.gz'
      fi
      ;;
    *)
      echo "Unsupported OS for bundled livekit-server"
      PATTERN=""
      ;;
  esac
  if [[ -n "$PATTERN" ]]; then
    URL="$(python3 -c "import json,re,sys; r=json.load(sys.stdin); a=next(x for x in r['assets'] if re.search(sys.argv[1], x['name'])); print(a['browser_download_url'])" "$PATTERN" <<< "$RELEASE_JSON")"
    TMP_ARCHIVE="$(mktemp)"
    curl -fL --retry 3 -o "$TMP_ARCHIVE" "$URL"
    EXTRACT_DIR="$(mktemp -d)"
    tar -xzf "$TMP_ARCHIVE" -C "$EXTRACT_DIR"
    EXTRACTED="$(find "$EXTRACT_DIR" -name 'livekit-server' -type f | head -n 1)"
    if [[ -z "$EXTRACTED" ]]; then
      echo "livekit-server binary not found in archive"
      exit 1
    fi
    cp "$EXTRACTED" "$LK_TARGET"
    chmod +x "$LK_TARGET"
    rm -f "$TMP_ARCHIVE"
    rm -rf "$EXTRACT_DIR"
  fi
fi

echo "Write manifest"
cat > "$BUNDLE_ROOT/manifest.json" <<EOF
{
  "version": "2",
  "platform": "$(echo "$OS" | tr '[:upper:]' '[:lower:]')",
  "python": "3.11",
  "venv": ".venv",
  "python_home": "python",
  "relocatable": true,
  "models": {
    "yolo": "models/yolov8n.pt",
    "piper_onnx": "models/piper/fr_FR-upmc-medium.onnx",
    "piper_json": "models/piper/fr_FR-upmc-medium.onnx.json"
  },
  "bin": {
    "uv": "bin/uv",
    "livekit": "bin/livekit-server"
  }
}
EOF

echo ""
echo "Bundle ready: $BUNDLE_ROOT"
echo "Next: ./jarvis eclosion"
