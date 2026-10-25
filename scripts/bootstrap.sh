#!/usr/bin/env sh
# Create .env with fresh local secrets. Safe to re-run: an existing .env is kept.
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  echo ".env already exists; leaving it unchanged"
  exit 0
fi
secret() { LC_ALL=C tr -dc "A-Za-z0-9" < /dev/urandom | head -c "$1"; }
cat > .env <<EOF
POSTGRES_PASSWORD=$(secret 24)
SECRET_KEY=$(secret 48)
FUNCTION_RUNNER_TOKEN=$(secret 32)
# Optional: enables the Explain button.
OPENAI_API_KEY=
EOF
echo "Wrote .env."
