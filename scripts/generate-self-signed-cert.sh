#!/usr/bin/env bash
# Generates a self-signed TLS certificate/key pair for native HTTPS
# (NVR_SSL_CERTFILE/NVR_SSL_KEYFILE) - handy for a standalone box with no
# reverse proxy in front of it. Browsers will show a "not private"
# warning to click through (self-signed certs aren't trusted by default),
# which is expected; for a real public domain, prefer a reverse proxy
# with Let's Encrypt instead (see the README's "Regarder depuis le
# telephone" section).
set -euo pipefail

DATA_DIR="${NVR_DATA_DIR:-data}"
OUT_DIR="$DATA_DIR/config/ssl"
DAYS="${1:-825}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl est requis pour generer un certificat (apt install openssl / equivalent)." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
CERT="$OUT_DIR/cert.pem"
KEY="$OUT_DIR/key.pem"

if [[ -f "$CERT" || -f "$KEY" ]]; then
  echo "Un certificat existe deja dans $OUT_DIR - supprimez-le d'abord si vous voulez en regenerer un." >&2
  exit 1
fi

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CERT" -days "$DAYS" \
  -subj "/CN=nvr.local" \
  -addext "subjectAltName=DNS:nvr.local,DNS:localhost,IP:127.0.0.1"

chmod 600 "$KEY"

echo "Certificat genere :"
echo "  $CERT"
echo "  $KEY"
echo
echo "Ajoutez a votre .env (ou variables d'environnement) :"
echo "  NVR_SSL_CERTFILE=$CERT"
echo "  NVR_SSL_KEYFILE=$KEY"
echo
echo "Puis lancez le serveur avec : python -m app.main"
