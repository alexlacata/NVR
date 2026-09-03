#!/usr/bin/env bash
# Turns a fresh Raspberry Pi OS Lite (64-bit) boot - flashed directly onto
# an SSD/HDD with Raspberry Pi Imager, see README "Creer une image prete a
# flasher" - into a running NVR that comes back up on every reboot.
#
# Usage (on the Pi, over SSH, as the user created by Raspberry Pi Imager) -
# no arguments needed, the repo/branch below are baked in:
#   curl -fsSL https://raw.githubusercontent.com/alexlacata/NVR/claude/nvr-multi-stream-gateway-fzb8xm/pi-image/firstboot.sh | bash
# To point at a different fork/branch, pass them explicitly instead:
#   bash firstboot.sh <repo-url> <branch>
#
# Idempotent: safe to re-run (e.g. to pick up an update) - just run the
# same command again.
set -euo pipefail

DEFAULT_REPO_URL="https://github.com/alexlacata/NVR.git"
DEFAULT_BRANCH="claude/nvr-multi-stream-gateway-fzb8xm"
REPO_URL="${1:-$DEFAULT_REPO_URL}"
BRANCH="${2:-$DEFAULT_BRANCH}"
INSTALL_DIR="${NVR_INSTALL_DIR:-$HOME/nvr}"
USER="${USER:-$(whoami)}"
TOTAL_STEPS=6

log() { echo -e "\n[etape $1/$TOTAL_STEPS] $2"; }

if [ "$(id -u)" = "0" ]; then
  echo "Ne lancez pas ce script en root - lancez-le en tant qu'utilisateur normal (il utilisera sudo lui-meme)." >&2
  exit 1
fi

cat <<'BANNER'

============================================================
 Installation du NVR - cette etape ne se fait qu'une fois.
 Ca prend quelques minutes, laissez faire sans interrompre.
============================================================
BANNER

log 1 "Verification de Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker n'est pas installe, installation en cours (1-2 minutes)..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
else
  echo "Deja installe, rien a faire."
fi
if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y docker-compose-plugin
fi

log 2 "Recuperation du logiciel NVR"
if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "Telechargement dans $INSTALL_DIR..."
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
else
  echo "Deja telecharge dans $INSTALL_DIR, mise a jour..."
  git -C "$INSTALL_DIR" pull --ff-only
fi

cd "$INSTALL_DIR"

log 3 "Configuration"
NEW_ENV=0
if [ ! -f .env ]; then
  NEW_ENV=1
  cp .env.example .env
  SECRET=$(openssl rand -hex 32)
  sed -i "s#^NVR_SECRET_KEY=.*#NVR_SECRET_KEY=${SECRET}#" .env
  echo "Fichier de configuration cree."
else
  echo "Deja configure, rien a faire."
fi

log 4 "Preparation du disque de stockage"
DISK_MOUNT="${NVR_DISK_MOUNT:-$(grep '^NVR_DISK_PATH=' .env 2>/dev/null | head -n1 | cut -d= -f2- || true)}"
DISK_MOUNT="${DISK_MOUNT:-/mnt/disque-nvr}"
if ! grep -q "^NVR_DISK_PATH=" .env 2>/dev/null; then
  echo "NVR_DISK_PATH=${DISK_MOUNT}" >> .env
else
  sed -i "s#^NVR_DISK_PATH=.*#NVR_DISK_PATH=${DISK_MOUNT}#" .env
fi
if [ ! -d "$DISK_MOUNT" ]; then
  echo "Creation du dossier $DISK_MOUNT."
  sudo mkdir -p "$DISK_MOUNT"
  sudo chown "$USER":"$USER" "$DISK_MOUNT"
  echo "  -> Si vos enregistrements doivent vivre sur un disque separe,"
  echo "     montez-le sur ce dossier (/etc/fstab) puis relancez ce script."
else
  echo "Deja pret."
fi

log 5 "Demarrage automatique au redemarrage"
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
echo "Fait : le NVR redemarrera tout seul avec le Raspberry Pi."

log 6 "Demarrage du NVR"
sudo systemctl restart nvr.service
echo "En cours de demarrage (peut prendre 10-20 secondes la premiere fois)..."

IP=$(hostname -I | awk '{print $1}')
if [ "$NEW_ENV" = "1" ]; then
  ADMIN_NOTE="
IMPORTANT - a faire maintenant :
  Le mot de passe administrateur par defaut est celui du fichier .env
  (NVR_ADMIN_PASSWORD, valeur \"changez-ce-mot-de-passe\" par defaut).
  Changez-le tout de suite :
    nano ${INSTALL_DIR}/.env
  puis relancez : cd ${INSTALL_DIR} && docker compose up -d
  (ou changez-le depuis l'interface une fois connecte, dans Parametres)."
else
  ADMIN_NOTE=""
fi

cat <<EOF

============================================================
 Termine ! Le NVR est installe et demarre tout seul desormais.
============================================================

Ouvrez cette adresse depuis un telephone ou ordinateur sur le
meme reseau :

    http://${IP}:8000
${ADMIN_NOTE}
(Astuce : relancer cette meme commande a tout moment est sans
risque, ca met juste a jour l'installation existante.)
EOF
