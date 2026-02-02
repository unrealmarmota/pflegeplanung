#!/bin/bash
# Pflegeplanung - Update Script
#
# Verwendung: Neue Projektdaten kopieren, dann dieses Script ausführen

APPDATA="/mnt/user/appdata/pflegeplanung"

echo "=== Pflegeplanung Update ==="

cd "$APPDATA"

# Container stoppen
echo "1. Stoppe Container..."
docker-compose down

# Image neu bauen (falls sich requirements.txt geändert hat)
echo "2. Baue Image neu..."
docker-compose build --no-cache

# Container starten
echo "3. Starte Container..."
docker-compose up -d

# Status
echo ""
echo "=== Update abgeschlossen ==="
docker-compose ps
