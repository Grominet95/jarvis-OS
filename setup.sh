#!/usr/bin/env bash
# ================================================================
#  JARVIS V3 — Setup interactif
# ================================================================
set -euo pipefail

# ── Couleurs & styles ────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

BLACK='\033[30m'
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
BLUE='\033[94m'
MAGENTA='\033[95m'
CYAN='\033[96m'
WHITE='\033[97m'

BG_BLACK='\033[40m'

# True color
TC_CYAN='\033[38;2;0;212;255m'
TC_BLUE='\033[38;2;0;100;255m'
TC_TEAL='\033[38;2;0;255;180m'
TC_GRAY='\033[38;2;120;130;150m'
TC_DIMGRAY='\033[38;2;70;80;95m'
TC_WHITE='\033[38;2;220;230;255m'

# ── Compteur de steps ─────────────────────────────────────────────
STEP_CURRENT=0
STEP_TOTAL=8

# ── Utilitaires visuels ──────────────────────────────────────────
nl()  { echo ""; }
sep() { echo -e "${TC_DIMGRAY}$(printf '─%.0s' {1..60})${RESET}"; }

badge_ok()   { echo -e "  ${TC_TEAL}${BOLD}✓${RESET}  $*"; }
badge_warn() { echo -e "  ${YELLOW}${BOLD}!${RESET}  $*"; }
badge_err()  { echo -e "  ${RED}${BOLD}✗${RESET}  $*"; }
badge_info() { echo -e "  ${TC_CYAN}${BOLD}›${RESET}  $*"; }
badge_skip() { echo -e "  ${TC_GRAY}${BOLD}–${RESET}  ${TC_GRAY}$*${RESET}"; }

step() {
  STEP_CURRENT=$((STEP_CURRENT + 1))
  nl
  echo -e "${TC_DIMGRAY}$(printf '─%.0s' {1..60})${RESET}"
  echo -e "  ${TC_CYAN}${BOLD}[ ${STEP_CURRENT}/${STEP_TOTAL} ]${RESET}  ${WHITE}${BOLD}$*${RESET}"
  echo -e "${TC_DIMGRAY}$(printf '─%.0s' {1..60})${RESET}"
}

# ── Spinner ───────────────────────────────────────────────────────
SPINNER_PID=""
spinner_start() {
  local msg="$1"
  local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  (
    i=0
    while true; do
      printf "\r  ${TC_CYAN}${frames[$((i % 10))]}${RESET}  ${TC_GRAY}%s${RESET}   " "$msg"
      i=$((i + 1))
      sleep 0.08
    done
  ) &
  SPINNER_PID=$!
}

spinner_stop() {
  if [[ -n "$SPINNER_PID" ]]; then
    kill "$SPINNER_PID" 2>/dev/null || true
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
    printf "\r\033[2K"
  fi
}

run_task() {
  local msg="$1"
  shift
  spinner_start "$msg"
  if "$@" > /tmp/jarvis_setup_out.log 2>&1; then
    spinner_stop
    badge_ok "$msg"
  else
    spinner_stop
    badge_err "$msg"
    echo ""
    echo -e "${TC_GRAY}$(tail -5 /tmp/jarvis_setup_out.log)${RESET}"
    echo ""
    exit 1
  fi
}

# ── Lecture sécurisée ─────────────────────────────────────────────
ask() {
  # ask "Label" VAR_NAME [default]
  local label="$1" varname="$2" default="${3:-}"
  local hint=""
  [[ -n "$default" ]] && hint=" ${TC_GRAY}(défaut : $default)${RESET}"
  printf "  ${TC_WHITE}${BOLD}%s${RESET}%s\n  ${TC_DIMGRAY}›${RESET} " "$label" "$hint"
  read -r "$varname"
  if [[ -z "${!varname}" && -n "$default" ]]; then
    printf -v "$varname" '%s' "$default"
  fi
}

ask_secret() {
  local label="$1" varname="$2"
  printf "  ${TC_WHITE}${BOLD}%s${RESET}\n  ${TC_DIMGRAY}›${RESET} " "$label"
  read -rs "$varname"
  echo ""
}

ask_yesno() {
  # returns 0 (yes) or 1 (no)
  local label="$1" default="${2:-n}"
  local opts
  [[ "$default" == "y" ]] && opts="${TC_TEAL}o${RESET}/${TC_GRAY}n${RESET}" || opts="${TC_GRAY}o${RESET}/${TC_TEAL}n${RESET}"
  printf "  ${TC_WHITE}${BOLD}%s${RESET}  [%b] " "$label" "$opts"
  read -r _yn
  _yn="${_yn:-$default}"
  [[ "$_yn" =~ ^[oOyY] ]]
}

# ── Logo JARVIS ───────────────────────────────────────────────────
print_logo() {
  clear
  echo ""
  echo -e "${TC_BLUE}${BOLD}    ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗${RESET}"
  echo -e "${TC_CYAN}${BOLD}    ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝${RESET}"
  echo -e "${TC_CYAN}${BOLD}    ██║███████║██████╔╝██║   ██║██║███████╗${RESET}"
  echo -e "${TC_TEAL}${BOLD}██  ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║${RESET}"
  echo -e "${TC_TEAL}${BOLD}╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║${RESET}"
  echo -e "${TC_GRAY}${BOLD} ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝${RESET}"
  echo ""
  echo -e "  ${TC_GRAY}Assistant IA temps réel  ·  v3.0  ·  Setup interactif${RESET}"
  echo ""
  echo -e "${TC_DIMGRAY}$(printf '═%.0s' {1..60})${RESET}"
  echo ""
}

# ── Abort propre ──────────────────────────────────────────────────
abort() {
  spinner_stop
  nl
  echo -e "${RED}${BOLD}  Annulé.${RESET}"
  nl
  exit 1
}
trap abort INT TERM

# ════════════════════════════════════════════════════════════════
#  DÉBUT
# ════════════════════════════════════════════════════════════════

print_logo

echo -e "  ${TC_WHITE}${BOLD}Bienvenue dans le wizard de configuration de JARVIS.${RESET}"
echo -e "  ${TC_GRAY}Ce script va installer les dépendances, configurer tes clés${RESET}"
echo -e "  ${TC_GRAY}API et préparer l'environnement en quelques minutes.${RESET}"
nl

# ── STEP 1 — Prérequis ───────────────────────────────────────────
step "Vérification des prérequis"

# Python
if ! command -v python3 &>/dev/null; then
  badge_err "Python 3.11+ introuvable — installe-le sur https://python.org"
  exit 1
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
  badge_err "Python $PY_VERSION détecté — JARVIS nécessite Python 3.11+"
  exit 1
fi
badge_ok "Python $PY_VERSION"

# uv
if ! command -v uv &>/dev/null; then
  badge_info "uv introuvable — installation automatique..."
  run_task "Installation de uv" bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi
badge_ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"

# curl
if ! command -v curl &>/dev/null; then
  badge_err "curl introuvable — requis pour les téléchargements"
  exit 1
fi
badge_ok "curl"

# ── STEP 2 — Dépendances Python ──────────────────────────────────
step "Installation des dépendances Python"

run_task "uv sync (pyproject.toml)" uv sync
badge_info ".venv/ prêt"

# ── STEP 3 — LLM principal ───────────────────────────────────────
step "Configuration — LLM principal (obligatoire)"

nl
echo -e "  ${TC_CYAN}${BOLD}Choisis ton backend API principal${RESET}"
echo -e "  ${TC_GRAY}Anthropic (Claude) ou OpenAI.${RESET}"
nl

API_BACKEND="anthropic"
ANTHROPIC_API_KEY=""
ANTHROPIC_MODEL="claude-sonnet-4-6"
OPENAI_API_KEY=""
OPENAI_MODEL="gpt-4o-mini"
if ask_yesno "Utiliser OpenAI comme LLM principal ?" "n"; then
  API_BACKEND="openai"
  while [[ -z "$OPENAI_API_KEY" ]]; do
    ask_secret "Clé API OpenAI  (sk-...)" OPENAI_API_KEY
    if [[ -z "$OPENAI_API_KEY" ]]; then
      badge_warn "La clé OpenAI est obligatoire avec ce backend."
    fi
  done
  badge_ok "Backend principal → OpenAI"
else
  while [[ -z "$ANTHROPIC_API_KEY" ]]; do
    ask_secret "Clé API Anthropic  (sk-ant-...)" ANTHROPIC_API_KEY
    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
      badge_warn "La clé Anthropic est obligatoire avec ce backend."
    fi
  done
  badge_ok "Backend principal → Anthropic"
fi

# ── STEP 4 — Identité utilisateur ───────────────────────────────
step "Ton identité"

nl
echo -e "  ${TC_GRAY}Utilisée pour personnaliser la séquence de démarrage et le scan biométrique.${RESET}"
nl

USER_FIRSTNAME=""
while [[ -z "$USER_FIRSTNAME" ]]; do
  ask "Ton prénom" USER_FIRSTNAME ""
  if [[ -z "$USER_FIRSTNAME" ]]; then
    badge_warn "Le prénom est requis pour personnaliser JARVIS."
  fi
done

badge_ok "Bonjour, ${USER_FIRSTNAME} !"

nl
echo -e "  ${TC_CYAN}${BOLD}Photo de référence (reconnaissance faciale)${RESET}"
echo -e "  ${TC_GRAY}Si tu veux activer la séquence de scan biométrique, place une photo de toi${RESET}"
echo -e "  ${TC_GRAY}(format JPG, visage bien visible) dans :${RESET}"
nl
echo -e "  ${TC_WHITE}    vision/faces/référence.jpg${RESET}"
nl
echo -e "  ${TC_GRAY}Sans cette photo, le scan s'exécutera mais ne pourra pas t'identifier.${RESET}"
badge_info "Tu peux ajouter la photo après l'installation."

nl

# ── STEP 5 — Localisation (météo proactive) ─────────────────────
step "Localisation (moteur proactif)"

nl
echo -e "  ${TC_GRAY}Utilisée pour les alertes météo et contexte local.${RESET}"
nl

ask "Ville" PROACTIVE_CITY "Paris"
ask "Latitude" PROACTIVE_LAT "48.85"
ask "Longitude" PROACTIVE_LON "2.35"

badge_ok "Localisation : $PROACTIVE_CITY ($PROACTIVE_LAT, $PROACTIVE_LON)"

# ── STEP 6 — Modules optionnels ──────────────────────────────────
step "Modules optionnels"

nl
echo -e "  ${TC_GRAY}Active uniquement ce dont tu as besoin maintenant.${RESET}"
echo -e "  ${TC_GRAY}Tu pourras compléter le .env plus tard.${RESET}"
nl

# TTS
TTS_PROVIDER="piper"
ELEVENLABS_API_KEY=""
ELEVENLABS_VOICE_ID=""
ELEVENLABS_MODEL="eleven_flash_v2_5"

echo -e "  ${TC_CYAN}${BOLD}Synthèse vocale (TTS)${RESET}"
echo -e "  ${TC_GRAY}  Piper = local, gratuit / ElevenLabs = cloud, voix naturelles${RESET}"
nl
if ask_yesno "Utiliser ElevenLabs (cloud) plutôt que Piper (local) ?" "n"; then
  TTS_PROVIDER="elevenlabs"
  ask_secret "Clé ElevenLabs  (sk_...)" ELEVENLABS_API_KEY
  ask "Voice ID ElevenLabs" ELEVENLABS_VOICE_ID ""
  badge_ok "TTS → ElevenLabs"
else
  badge_ok "TTS → Piper (local)"
fi

nl
# LiveKit voice pipeline
LIVEKIT_URL=""
LIVEKIT_API_KEY=""
LIVEKIT_API_SECRET=""
DEEPGRAM_API_KEY=""

echo -e "  ${TC_CYAN}${BOLD}Pipeline vocal temps réel (LiveKit + Deepgram)${RESET}"
echo -e "  ${TC_GRAY}  Requis pour parler à voix haute avec JARVIS.${RESET}"
echo -e "  ${TC_GRAY}  LiveKit : cloud.livekit.io  ·  Deepgram : deepgram.com (gratuit 200h/mois)${RESET}"
nl
if ask_yesno "Activer le pipeline vocal ?" "n"; then
  ask "LiveKit URL  (wss://...)" LIVEKIT_URL ""
  ask_secret "LiveKit API Key" LIVEKIT_API_KEY
  ask_secret "LiveKit API Secret" LIVEKIT_API_SECRET
  ask_secret "Deepgram API Key" DEEPGRAM_API_KEY
  badge_ok "Pipeline vocal configuré"
else
  badge_skip "Pipeline vocal ignoré"
fi

nl
# AISstream (navires)
AISSTREAM_KEY=""
echo -e "  ${TC_CYAN}${BOLD}AISstream${RESET} ${TC_GRAY}— tracking navires temps réel (globe 3D)${RESET}"
echo -e "  ${TC_GRAY}  Clé gratuite sur aisstream.io${RESET}"
nl
if ask_yesno "Configurer AISstream ?" "n"; then
  ask_secret "Clé AISstream" AISSTREAM_KEY
  badge_ok "AISstream configuré"
else
  badge_skip "AISstream ignoré"
fi

# ── STEP 7 — Modèles ML ──────────────────────────────────────────
step "Téléchargement des modèles ML"

# YOLOv8
if [[ ! -f "yolov8n.pt" ]]; then
  run_task "YOLOv8n (~6 Mo) — vision objet" \
    uv run python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
else
  badge_ok "YOLOv8n déjà présent"
fi

# Piper TTS
PIPER_MODEL="models/piper/fr_FR-upmc-medium.onnx"
if [[ ! -f "$PIPER_MODEL" ]]; then
  mkdir -p models/piper
  BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium"
  run_task "Piper TTS français (~73 Mo)" \
    bash -c "curl -L --silent -o '$PIPER_MODEL' '${BASE_URL}/fr_FR-upmc-medium.onnx' && curl -L --silent -o '${PIPER_MODEL}.json' '${BASE_URL}/fr_FR-upmc-medium.onnx.json'"
else
  badge_ok "Modèle Piper déjà présent"
fi

# ── STEP 8 — Génération .env + dossiers ──────────────────────────
step "Génération de l'environnement"

mkdir -p memory_data/sessions memory_data/topics memory_data/conso memory_data/initiatives
mkdir -p workspace/projects
mkdir -p vision/faces
badge_ok "Dossiers runtime créés"

# Écriture du .env
ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
  badge_info ".env existant sauvegardé"
fi

cat > "$ENV_FILE" <<EOF
# ================================================================
# JARVIS V3 — Configuration  (généré par setup.sh)
# ================================================================

# ── Identité ─────────────────────────────────────────────────────
USER_FIRSTNAME=${USER_FIRSTNAME}

# ── LLM ──────────────────────────────────────────────────────────
LLM_PROVIDER=api
API_BACKEND=${API_BACKEND}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=${ANTHROPIC_MODEL}
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}

# ── Serveur ───────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO

# ── Localisation ──────────────────────────────────────────────────
PROACTIVE_LAT=${PROACTIVE_LAT}
PROACTIVE_LON=${PROACTIVE_LON}
PROACTIVE_CITY=${PROACTIVE_CITY}

# ── TTS ───────────────────────────────────────────────────────────
TTS_PROVIDER=${TTS_PROVIDER}
ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID}
ELEVENLABS_MODEL=${ELEVENLABS_MODEL}
WHISPER_MODEL=tiny

# ── LiveKit ───────────────────────────────────────────────────────
LIVEKIT_URL=${LIVEKIT_URL}
LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}

# ── Deepgram ──────────────────────────────────────────────────────
DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}

# ── AISstream ─────────────────────────────────────────────────────
AISSTREAM_KEY=${AISSTREAM_KEY}

# ── Providers LLM alternatifs ─────────────────────────────────────
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-large-latest
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
GOOGLE_API_KEY=
EOF

badge_ok ".env généré"

# ── Installation commande globale ────────────────────────────────
JARVIS_BIN="/usr/local/bin/jarvis"
JARVIS_SRC="$(cd "$(dirname "$0")" && pwd)/jarvis"
if [[ ! -f "$JARVIS_BIN" ]]; then
  nl
  echo -e "  ${TC_GRAY}Installation de la commande ${TC_WHITE}jarvis${TC_GRAY} dans /usr/local/bin...${RESET}"
  if sudo ln -sf "$JARVIS_SRC" "$JARVIS_BIN" 2>/dev/null; then
    badge_ok "Commande \`jarvis\` disponible globalement"
  else
    badge_skip "Symlink ignoré — utilise ./jarvis depuis le repo"
  fi
else
  badge_ok "Commande \`jarvis\` déjà installée"
fi

# ── Résumé final ─────────────────────────────────────────────────
nl
echo -e "${TC_DIMGRAY}$(printf '═%.0s' {1..60})${RESET}"
nl
echo -e "  ${TC_TEAL}${BOLD}Système prêt.${RESET}"
nl
echo -e "  ${TC_GRAY}Noyau principal :${RESET}"
nl
echo -e "  ${TC_CYAN}  jarvis run${RESET}"
echo -e "  ${TC_GRAY}  ↳ ${TC_WHITE}localhost:8000/admin${RESET}"
nl
if [[ -n "$LIVEKIT_URL" ]]; then
  echo -e "  ${TC_GRAY}Interface vocale :${RESET}"
  nl
  echo -e "  ${TC_CYAN}  jarvis voice${RESET}"
  nl
fi
echo -e "  ${TC_DIMGRAY}Config  →  .env${RESET}"
nl
echo -e "${TC_DIMGRAY}$(printf '═%.0s' {1..60})${RESET}"
nl
