#!/bin/bash
# Pflegeplanung - Unraid Setup Script
#
# Verwendung:
#   1. Projektordner nach /mnt/user/appdata/pflegeplanung/ kopieren
#   2. Dieses Script ausführen: bash /mnt/user/appdata/pflegeplanung/unraid-setup.sh

APPDATA="/mnt/user/appdata/pflegeplanung"
SWAG_PROXY="/mnt/user/appdata/swag/nginx/proxy-confs"

echo "=== Pflegeplanung Setup für Unraid ==="

# 1. Verzeichnisse erstellen
echo "1. Erstelle Verzeichnisse..."
mkdir -p "$APPDATA/instance"

# 2. Berechtigungen setzen (für nobody:users wie Unraid es mag)
echo "2. Setze Berechtigungen..."
chown -R nobody:users "$APPDATA"
chmod -R 755 "$APPDATA"
chmod 777 "$APPDATA/instance"  # DB braucht Schreibrechte

# 3. SWAG Proxy-Config kopieren (falls SWAG vorhanden)
if [ -d "$SWAG_PROXY" ]; then
    echo "3. Kopiere SWAG Proxy-Config..."
    cp "$APPDATA/swag-pflegeplanung.subdomain.conf" "$SWAG_PROXY/pflegeplanung.subdomain.conf"
    echo "   -> Vergiss nicht: docker exec -it swag htpasswd -c /config/nginx/.htpasswd DEINUSER"
else
    echo "3. SWAG nicht gefunden, überspringe Proxy-Config"
fi

# 4. Docker Image bauen
echo "4. Baue Docker Image..."
cd "$APPDATA"
docker-compose build

# 5. Container starten
echo "5. Starte Container..."
docker-compose up -d

# 6. Status prüfen
echo ""
echo "=== Setup abgeschlossen ==="
docker-compose ps

echo ""
echo "Nächste Schritte:"
echo "  1. SWAG htpasswd erstellen: docker exec -it swag htpasswd -c /config/nginx/.htpasswd DEINUSER"
echo "  2. SWAG neustarten: docker restart swag"
echo "  3. Zugriff lokal: http://UNRAID-IP:9500"
echo "  4. Zugriff extern: https://pflegeplanung.deinedomain.de"
echo ""
echo "Logs anzeigen: docker-compose -f $APPDATA/docker-compose.yml logs -f"
