#!/bin/bash
# Obtain a Let's Encrypt certificate and configure nginx for HTTPS.
# Run once on the server after deploying: sudo bash /opt/games/setup-https.sh <domain>
# Example: sudo bash /opt/games/setup-https.sh 34.242.181.49.nip.io

set -e

DOMAIN="${1:-34.242.181.49.nip.io}"

echo "=== Setting up HTTPS for $DOMAIN ==="

# Install certbot and nginx plugin if needed
if ! command -v certbot &>/dev/null; then
    echo "Installing certbot..."
    dnf install -y certbot python3-certbot-nginx 2>/dev/null || yum install -y certbot python3-certbot-nginx
fi

# Write nginx config for this domain
cat > /etc/nginx/conf.d/combined.conf << EOF
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # MCP server — SSE needs no buffering and long timeouts
    location ~ ^/(sse|messages/|oauth/|authorize|\.well-known/|health) {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        chunked_transfer_encoding on;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Games server — everything else
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Obtain certificate using nginx plugin (no port 80 disruption)
echo "Obtaining certificate..."
certbot certonly \
    --nginx \
    --non-interactive \
    --agree-tos \
    --email "dickinson.rob@gmail.com" \
    -d "$DOMAIN"

# Add deploy hook to reload nginx after renewal
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'HOOK'
#!/bin/bash
systemctl reload nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# Enable auto-renewal timer
systemctl enable --now certbot-renew.timer

# Reload nginx to pick up new config and cert
nginx -t && systemctl reload nginx

echo ""
echo "=== Done! Site is now available at https://$DOMAIN ==="
echo "Certificate auto-renewal is active. Check with: systemctl status certbot-renew.timer"
