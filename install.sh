#!/usr/bin/env bash
# ============================================================
# Jarvis V3 — Script d'installation
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[jarvis]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── 1. Vérification Python ────────────────────────────────────
info "Vérification de Python 3.11+..."
if ! command -v python3 &>/dev/null; then
    error "Python 3.11+ requis. Installe-le depuis https://python.org"
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
    error "Python $PY_VERSION détecté. Jarvis nécessite Python 3.11+."
fi
success "Python $PY_VERSION OK"

# ── 2. Installation / mise à jour de uv ───────────────────────
info "Vérification de uv..."
if ! command -v uv &>/dev/null; then
    info "uv non trouvé — installation..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    success "uv installé"
else
    success "uv $(uv --version | cut -d' ' -f2) OK"
fi

# ── 3. Environnement virtuel + dépendances ────────────────────
info "Installation des dépendances Python (pyproject.toml)..."
uv sync
success "Dépendances installées dans .venv/"

# ── 4. Fichier .env ───────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    warn ".env créé depuis .env.example — remplis tes clés API avant de lancer Jarvis."
else
    success ".env déjà présent"
fi

# ── 5. Modèle YOLOv8 (vision) ─────────────────────────────────
if [[ ! -f "yolov8n.pt" ]]; then
    info "Téléchargement du modèle YOLOv8n (vision)..."
    if command -v uv &>/dev/null; then
        uv run python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
    else
        python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
    fi
    success "yolov8n.pt téléchargé"
else
    success "yolov8n.pt déjà présent"
fi

# ── 6. Modèle Piper TTS français (optionnel) ──────────────────
PIPER_MODEL="models/piper/fr_FR-upmc-medium.onnx"
if [[ ! -f "$PIPER_MODEL" ]]; then
    info "Téléchargement du modèle Piper TTS français (≈73 Mo)..."
    mkdir -p models/piper
    BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium"
    curl -L --progress-bar -o "$PIPER_MODEL" "${BASE_URL}/fr_FR-upmc-medium.onnx"
    curl -L --progress-bar -o "${PIPER_MODEL}.json" "${BASE_URL}/fr_FR-upmc-medium.onnx.json"
    success "Modèle Piper téléchargé dans models/piper/"
else
    success "Modèle Piper déjà présent"
fi

# ── 7. nowplaying-cli (lecture locale macOS) ─────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    if ! command -v nowplaying-cli &>/dev/null; then
        if command -v brew &>/dev/null; then
            info "Installation de nowplaying-cli (lecture locale macOS)..."
            brew install nowplaying-cli
            success "nowplaying-cli installé"
        else
            warn "Homebrew non trouvé — nowplaying-cli non installé (optionnel pour la lecture locale)."
        fi
    else
        success "nowplaying-cli $(nowplaying-cli --version 2>/dev/null || echo '') déjà présent"
    fi
fi

# ── 8. Dossiers runtime ───────────────────────────────────────
mkdir -p memory_data/sessions memory_data/topics memory_data/conso memory_data/initiatives
mkdir -p workspace/projects
success "Dossiers memory_data/ et workspace/ créés"

# ── Résumé ────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Jarvis V3 — Installation terminée !${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Prochaines étapes :"
echo "  1. Édite .env avec tes clés API"
echo "  2. Lance le serveur principal :"
echo "       uv run python main.py"
echo "  3. (Optionnel) Lance le voice agent LiveKit :"
echo "       uv run python voice_agent.py dev"
echo ""
