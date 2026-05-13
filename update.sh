#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Rebuilding app container..."
docker compose up --build -d app
echo ""
echo "Done. Logs:"
docker compose logs -f app
