#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BUNDLE_ROOT="$ROOT/bundle"
VENV_PATH="$BUNDLE_ROOT/.venv"
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

echo "[1/5] Sync Python env into bundle/.venv"
rm -rf "$VENV_PATH"
uv venv "$VENV_PATH" --python 3.11
uv sync --python "$VENV_PATH" --extra vision

BUNDLE_PYTHON="$VENV_PATH/bin/python"
if [[ ! -x "$BUNDLE_PYTHON" ]]; then
  echo "bundle python missing"
  exit 1
fi

echo "[2/5] Copy uv binary"
cp "$(command -v uv)" "$BIN_DIR/uv"
chmod +x "$BIN_DIR/uv"

echo "[3/5] Download ML models"
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

echo "[4/5] Download livekit-server"
OS="$(uname -s)"
ARCH="$(uname -m)"
LK_TARGET="$BIN_DIR/livekit-server"
if [[ ! -x "$LK_TARGET" ]]; then
  case "$OS" in
    Darwin)
      if [[ "$ARCH" == "arm64" ]]; then
        URL="https://github.com/livekit/livekit/releases/latest/download/livekit-server_darwin_arm64.zip"
      else
        URL="https://github.com/livekit/livekit/releases/latest/download/livekit-server_darwin_amd64.zip"
      fi
      ;;
    Linux)
      URL="https://github.com/livekit/livekit/releases/latest/download/livekit-server_linux_amd64.zip"
      ;;
    *)
      echo "Unsupported OS for bundled livekit-server"
      URL=""
      ;;
  esac
  if [[ -n "$URL" ]]; then
    TMP_ZIP="$(mktemp).zip"
    curl -L --silent -o "$TMP_ZIP" "$URL"
    unzip -o "$TMP_ZIP" -d "$BIN_DIR"
    chmod +x "$BIN_DIR"/livekit-server*
    mv "$BIN_DIR"/livekit-server* "$LK_TARGET" 2>/dev/null || true
    rm -f "$TMP_ZIP"
  fi
fi

echo "[5/5] Write manifest"
cat > "$BUNDLE_ROOT/manifest.json" <<EOF
{
  "version": "1",
  "platform": "$(echo "$OS" | tr '[:upper:]' '[:lower:]')",
  "python": "3.11",
  "venv": ".venv",
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
