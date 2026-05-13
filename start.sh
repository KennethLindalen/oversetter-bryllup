#!/bin/bash
set -e
cd "$(dirname "$0")"

# Create .env from example if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  read -rp "Set admin keyphrase: " phrase
  sed -i "s/^ADMIN_KEYPHRASE=.*/ADMIN_KEYPHRASE=${phrase}/" .env
  echo ".env created."
fi

echo ""
echo "Starting with Docker Compose (includes LibreTranslate)..."
echo "First run will download translation models (~500 MB) — this takes a few minutes."
echo ""
echo "  Admin: http://localhost:8000/admin"
echo "  Users: http://localhost:8000/join"
echo ""

docker compose up --build
