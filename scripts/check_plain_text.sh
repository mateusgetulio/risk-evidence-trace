#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
dash=$(printf '\342\200\224')
hits=$(grep -rln "$dash" README.md docs apps/web/app apps/web/components apps/web/lib services/api/app fixtures 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "em dash found in:"
  echo "$hits"
  exit 1
fi
echo "no em dashes"
