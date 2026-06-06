#!/bin/bash
# Obtain a Let's Encrypt certificate for the nip.io domain and configure HTTPS.
# Run once on the server after deploying: sudo bash /opt/games/setup-https.sh <domain>
# Example: sudo bash /opt/games/setup-https.sh 34.242.181.49.nip.io

set -e

DOMAIN="${1:-34.242.181.49.nip.io}"
CONFIG="/opt/games/config.json"
SERVICE="games-server"

echo "=== Setting up HTTPS for $DOMAIN ==="

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
    echo "Installing certbot..."
    dnf install -y certbot 2>/dev/null || yum install -y certbot
fi

# Stop the server so certbot can use port 80
echo "Stopping $SERVICE..."
systemctl stop "$SERVICE"

# Obtain certificate
echo "Obtaining certificate..."
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "dickinson.rob@gmail.com" \
    -d "$DOMAIN" \
    --pre-hook "systemctl stop $SERVICE" \
    --post-hook "systemctl start $SERVICE"

CERT_FILE="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_FILE="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

# Update config.json with cert paths
echo "Updating config.json..."
python3 - <<EOF
import json
with open('$CONFIG') as f:
    cfg = json.load(f)
cfg['cert_file'] = '$CERT_FILE'
cfg['key_file'] = '$KEY_FILE'
with open('$CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
print("config.json updated.")
EOF

# Enable and start the service
echo "Starting $SERVICE with HTTPS..."
systemctl start "$SERVICE"
systemctl enable "$SERVICE"

echo ""
echo "=== Done! Site is now available at https://$DOMAIN ==="
echo ""
echo "Certificate auto-renewal is handled by certbot's systemd timer."
echo "Check with: systemctl status certbot.timer"
