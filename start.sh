#!/bin/bash

# Load .env if present
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

# Install dependencies if missing
if [ ! -d node_modules ] || [ ! -f node_modules/.bin/vite ]; then
  echo "Installing Node.js dependencies..."
  pnpm install 2>/dev/null || npm install --legacy-peer-deps
fi

echo "Starting AKKI AI — Express + Vite on port 5000..."
exec pnpm dev
