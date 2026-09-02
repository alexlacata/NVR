#!/usr/bin/env bash
# Turns a fresh Raspberry Pi OS Lite (64-bit) boot - flashed directly onto
# an SSD/HDD with Raspberry Pi Imager, see README "Creer une image prete a
# flasher" - into a running NVR that comes back up on every reboot.
#
# Usage (on the Pi, over SSH, as the user created by Raspberry Pi Imager):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/pi-image/firstboot.sh | bash -s -- <repo-url>
# or, with the repo already cloned:
#   bash pi-image/firstboot.sh
#
# Idempotent: safe to re-run (e.g. after `git pull`) to pick up changes.
set -euo pipefail

REPO_URL="${1:-}"
INSTALL_DIR="${NVR_INSTALL_DIR:-$HOME/nvr}"

log() { echo -e "\n== $* =="; }

if [ "$(id -u)" = "0" ]; then
  echo "Ne lancez pas ce script en root - lancez-le en tant qu'utilisateur normal (il utilisera sudo lui-meme)." >&2
  exit 1
fi

log "Verification de ffmpeg / Docker"
if ! command -v docker >/dev/null 2>&1; then
  log "Installation de Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
if ! docker compose version >/dev/null 2>&1; then
  log "Installation du plugin docker compose"
  sudo apt-get update -y
  sudo apt-get install -y docker-compose-plugin
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  if [ -z "$REPO_URL" ]; then
    echo "Depot introuvable dans $INSTALL_DIR et aucune URL de depot fournie." >&2
    echo "Usage: bash firstboot.sh <url-du-depot-git>" >&2
    exit 1
  fi
  log "Clonage du depot dans $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  log "Depot deja present dans $INSTALL_DIR, mise a jour"
  git -C "$INSTALL_DIR" pull --ff-only
fi

cd "$INSTALL_DIR"

if [ ! -f .env ]; then
  log "Creation de .env (a completer/verifier - mot de passe admin notamment)"
  cp .env.example .env
  SECRET=$(openssl rand -hex 32)
  sed -i "s#^NVR_SECRET_KEY=.*#NVR_SECRET_KEY=${SECRET}#" .env
  echo "  -> Pensez a changer NVR_ADMIN_PASSWORD dans $INSTALL_DIR/.env avant de continuer."
fi

DISK_MOUNT="${NVR_DISK_MOUNT:-$(grep '^NVR_DISK_PATH=' .env 2>/dev/null | head -n1 | cut -d= -f2- || true)}"
DISK_MOUNT="${DISK_MOUNT:-/mnt/disque-nvr}"
if ! grep -q "^NVR_DISK_PATH=" .env 2>/dev/null; then
  echo "NVR_DISK_PATH=${DISK_MOUNT}" >> .env
else
  sed -i "s#^NVR_DISK_PATH=.*#NVR_DISK_PATH=${DISK_MOUNT}#" .env
fi
if [ ! -d "$DISK_MOUNT" ]; then
  log "Creation du point de montage $DISK_MOUNT (montez-y votre disque d'enregistrement si ce n'est pas deja fait, via /etc/fstab)"
  sudo mkdir -p "$DISK_MOUNT"
  sudo chown "$USER":"$USER" "$DISK_MOUNT"
fi

log "Activation du service systemd (demarrage automatique au boot)"
SERVICE_FILE=/etc/systemd/system/nvr.service
sudo tee "$SERVICE_FILE" >/dev/null <<UNIT
[Unit]
Description=NVR (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable nvr.service

log "Demarrage du NVR"
sudo systemctl restart nvr.service

IP=$(hostname -I | awk '{print $1}')
cat <<EOF

Termine. Le NVR redemarrera automatiquement avec le systeme.
Interface : http://${IP}:8000
(si vous venez d'ajouter votre utilisateur au groupe docker, deconnectez-vous/reconnectez-vous avant de relancer ce script une deuxieme fois)
EOF
