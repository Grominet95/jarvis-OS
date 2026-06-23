#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Garantit la présence du binaire `livekit-server` (serveur WebRTC du pipeline
# vocal LiveKit). Appelé par le launcher `jarvis` avant de démarrer le serveur.
#
#   - no-op s'il est déjà sur le PATH (cas nominal)
#   - sinon installation automatique : Homebrew (macOS) puis repli sur le
#     script d'installation officiel get.livekit.io (macOS sans brew + Linux)
#
# Sortie 0 si `livekit-server` est disponible après coup, 1 sinon (avec des
# instructions manuelles affichées sur stderr).
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

log() { printf "  %s\n" "$1" >&2; }

# 1) Déjà disponible → rien à faire.
if command -v livekit-server >/dev/null 2>&1; then
  exit 0
fi

OS="$(uname -s)"
log "livekit-server introuvable — installation automatique…"

# 2) macOS + Homebrew : voie la plus propre (binaire posé sur le PATH brew).
if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
  log "→ brew install livekit"
  if brew install livekit >&2; then
    command -v livekit-server >/dev/null 2>&1 && exit 0
  fi
  log "brew a échoué — repli sur le script officiel."
fi

# 3) Script d'installation officiel (macOS sans brew + Linux). Installe le
#    binaire dans /usr/local/bin (peut demander sudo selon la plateforme).
if command -v curl >/dev/null 2>&1; then
  log "→ curl -sSL https://get.livekit.io | bash"
  curl -sSL https://get.livekit.io | bash >&2 || true
  command -v livekit-server >/dev/null 2>&1 && exit 0
fi

# 4) Échec : instructions manuelles selon la plateforme.
log ""
log "Installation automatique impossible. Installe livekit-server manuellement :"
if [ "$OS" = "Darwin" ]; then
  log "  brew install livekit"
else
  log "  curl -sSL https://get.livekit.io | bash"
fi
log "Puis relance « jarvis run »."
exit 1
