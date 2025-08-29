#!/usr/bin/env bash
set -e

# Resolve repo root relative to this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}/frontend"

# Try to ensure npm is available (support nvm installations)
if ! command -v npm >/dev/null 2>&1; then
  # Load nvm if present
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    . "$HOME/.nvm/nvm.sh"
    # Use default or latest installed version silently
    if command -v nvm >/dev/null 2>&1; then
      nvm use --silent >/dev/null 2>&1 || true
    fi
  fi
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "⚠️  npm is not available. Install Node.js (brew install node) or load nvm in your shell init."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "▶️  Running: npm run dev in ${REPO_ROOT}/frontend"

# Ensure dependencies are installed if missing (supports clean machines)
if [ ! -d node_modules ] || [ ! -f node_modules/.bin/vite ]; then
  echo "🔧 Installing frontend dependencies (this may take a minute)…"
  if [ -f package-lock.json ]; then
    npm ci || npm install
  else
    npm install
  fi
fi

npm run dev
