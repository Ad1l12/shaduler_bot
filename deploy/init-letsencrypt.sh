#!/usr/bin/env bash
# Obtain a Let's Encrypt TLS certificate for the first time.
#
# Run once on a fresh server BEFORE starting the full production stack:
#   chmod +x deploy/init-letsencrypt.sh
#   sudo ./deploy/init-letsencrypt.sh
#
# Prerequisites:
#   - Docker and docker-compose-plugin installed
#   - DNS A-record for DOMAIN already pointing to this server's IP
#   - Ports 80 and 443 open in the firewall
#   - .env file present in the repo root with all required variables

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-your-domain.com}"        # Override with: DOMAIN=example.com ./init-letsencrypt.sh
EMAIL="${EMAIL:-admin@your-domain.com}"    # Let's Encrypt expiry notifications
COMPOSE_FILE="$(dirname "$0")/docker-compose.yml"
CERTBOT_DIR="$(dirname "$0")/certbot"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { echo "[INFO]  $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || error "docker is not installed"
[[ -f "$COMPOSE_FILE" ]] || error "docker-compose.yml not found at $COMPOSE_FILE"

info "Domain  : $DOMAIN"
info "Email   : $EMAIL"

# ── Create directory structure Certbot expects ────────────────────────────────
mkdir -p "$CERTBOT_DIR/conf/live/$DOMAIN"
mkdir -p "$CERTBOT_DIR/www"

# ── Create a temporary self-signed cert so nginx can start on 443 ─────────────
# nginx refuses to start if ssl_certificate files are missing.
if [[ ! -f "$CERTBOT_DIR/conf/live/$DOMAIN/fullchain.pem" ]]; then
    info "Creating temporary self-signed certificate …"
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "$CERTBOT_DIR/conf/live/$DOMAIN/privkey.pem" \
        -out    "$CERTBOT_DIR/conf/live/$DOMAIN/fullchain.pem" \
        -subj   "/CN=$DOMAIN" 2>/dev/null
fi

# ── Start nginx only (app + db not needed for the ACME challenge) ─────────────
info "Starting nginx …"
docker compose -f "$COMPOSE_FILE" up -d nginx

# Give nginx a moment to bind the ports.
sleep 3

# ── Request the real certificate ──────────────────────────────────────────────
info "Requesting Let's Encrypt certificate for $DOMAIN …"
docker compose -f "$COMPOSE_FILE" run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d "$DOMAIN"

# ── Reload nginx with the real certificate ────────────────────────────────────
info "Reloading nginx …"
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload

info "Done. Start the full stack with:"
info "  docker compose -f $COMPOSE_FILE up -d"
