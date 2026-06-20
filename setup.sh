#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$ROOT/scripts/release/rehome_bundle.sh" ]]; then
  bash "$ROOT/scripts/release/rehome_bundle.sh" "$ROOT" || true
fi

if [[ "${1:-}" == "--ci" ]]; then
  echo "JARVIS V3 — setup --ci (mode non-interactif)"

  mkdir -p memory_data/sessions \
           memory_data/topics \
           memory_data/conso \
           memory_data/initiatives \
           memory_data/curator_reports \
           vision_data/faces \
           skills_data/installed \
           skills_data/candidates \
           workspace/projects
  echo "  Disposition creee"

  if [[ ! -f .env ]]; then
    cat > .env <<'EOF'
LLM_PROVIDER=api
API_BACKEND=anthropic
ANTHROPIC_API_KEY=unused-in-fake-llm-mode
ANTHROPIC_MODEL=claude-sonnet-4-6
VOICE_ANTHROPIC_MODEL=claude-haiku-4-5-20251001
USER_FIRSTNAME=B9
HOME_CITY=Paris
MEMORY_DIR=memory_data
PORT=8000
EOF
    echo "  .env minimal genere"
  fi

  if command -v uv > /dev/null 2>&1; then
    uv sync --frozen --group dev --extra vision
    echo "  uv sync termine"
  else
    echo "  uv absent du PATH"
    exit 1
  fi

  echo "setup --ci OK"
  exit 0
fi

resolve_python() {
  if [[ -x bundle/.venv/bin/python ]]; then
    echo bundle/.venv/bin/python
  elif [[ -x .venv/bin/python ]]; then
    echo .venv/bin/python
  fi
}

PYTHON_BIN="$(resolve_python || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -f bundle/manifest.json ]]; then
    echo "Bundle detecte mais bundle/.venv manquant. Lance scripts/release/build_bundle.sh"
    exit 1
  fi
  echo ""
  echo "JARVIS — aucun runtime pre-packaged detecte."
  echo "  A) Telecharge une release Jarvis avec bundle offline"
  echo "  B) bash scripts/release/build_bundle.sh (une fois, avec reseau)"
  echo "  C) uv sync puis relance ./setup.sh"
  echo ""
  read -r -p "Construire le bundle offline maintenant ? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    bash scripts/release/build_bundle.sh
    PYTHON_BIN="$(resolve_python || true)"
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv introuvable — installe-le depuis https://docs.astral.sh/uv/"
    exit 1
  fi
  uv sync --extra vision
  PYTHON_BIN="$(resolve_python || true)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Impossible de demarrer l'assistant de configuration."
  exit 1
fi

if ! "$PYTHON_BIN" -c "import jarvis.setup_app" 2>/dev/null; then
  UV_CMD="uv"
  [[ -x bundle/bin/uv ]] && UV_CMD="bundle/bin/uv"
  # Bundle case: deps already installed, only the editable link needs
  # (re)registering -> --no-deps avoids any network call.
  "$UV_CMD" pip install --python "$PYTHON_BIN" --no-deps -e . \
    || "$UV_CMD" pip install --python "$PYTHON_BIN" -e .
fi

echo ""
echo "Ouverture de http://127.0.0.1:8765/setup"
echo "Ctrl-C pour arreter l'assistant."
echo ""
exec "$PYTHON_BIN" -m jarvis.setup_app
