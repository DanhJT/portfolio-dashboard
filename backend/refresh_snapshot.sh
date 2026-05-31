#!/usr/bin/env bash
#
# Local snapshot refresh — the reliable fallback when GitHub Actions gets
# rate-limited by Yahoo (your home/residential IP rarely is).
#
# Regenerates frontend/public/snapshot.json from live market data and pushes
# the change, which triggers Vercel's auto-deploy.
#
# Usage:
#   ./backend/refresh_snapshot.sh
#
set -euo pipefail

# Resolve repo paths relative to this script so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer the project venv; fall back to whatever python3 is on PATH.
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

echo "==> Generating snapshot with $PYTHON"
( cd "$SCRIPT_DIR" && "$PYTHON" generate_snapshot.py )

SNAPSHOT="$REPO_ROOT/frontend/public/snapshot.json"

if git -C "$REPO_ROOT" diff --quiet -- "$SNAPSHOT"; then
  echo "==> No snapshot changes — nothing to push."
  exit 0
fi

echo "==> Committing and pushing updated snapshot"
git -C "$REPO_ROOT" add "$SNAPSHOT"
git -C "$REPO_ROOT" commit -m "chore: refresh data snapshot (local)"
git -C "$REPO_ROOT" push
echo "==> Done. Vercel will redeploy shortly."
