#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
tmp=$(mktemp)
trap 'rm -f "$tmp" "$tmp.clean"' EXIT
if [ -n "${DENYLIST:-}" ]; then
  printf '%s\n' "$DENYLIST" > "$tmp"
elif [ -f scripts/denylist.txt ]; then
  cp scripts/denylist.txt "$tmp"
else
  echo "error: no DENYLIST secret and no scripts/denylist.txt. Add the DENYLIST secret in CI, or create scripts/denylist.txt locally (one entry per line)."
  exit 1
fi
tr -d '\r' < "$tmp" | sed 's/[[:space:]]*$//; /^$/d' > "$tmp.clean"
if [ ! -s "$tmp.clean" ]; then
  echo "error: the denylist is empty. Fill the DENYLIST secret or scripts/denylist.txt with one entry per line."
  exit 1
fi
hits=$(grep -rilwF -f "$tmp.clean" . \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
  --exclude-dir=.next --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache \
  --exclude-dir=.pytest_cache --exclude-dir=.hypothesis --exclude-dir=__pycache__ \
  --exclude=denylist.txt || true)
if [ -n "$hits" ]; then
  echo "denylist match in:"
  echo "$hits"
  exit 1
fi
echo "denylist clean"
