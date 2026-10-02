#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
if [ -n "${DENYLIST:-}" ]; then
  printf '%s\n' "$DENYLIST" > "$tmp"
elif [ -f scripts/denylist.txt ]; then
  cp scripts/denylist.txt "$tmp"
else
  if [ -n "${CI:-}" ]; then
    echo "::warning::DENYLIST secret is missing, the denylist check did not scan anything"
  fi
  echo "warning: no DENYLIST secret and no scripts/denylist.txt, skipping the denylist check"
  exit 0
fi
tr -d '\r' < "$tmp" | sed 's/[[:space:]]*$//; /^$/d' > "$tmp.clean"
mv "$tmp.clean" "$tmp"
if [ ! -s "$tmp" ]; then
  if [ -n "${CI:-}" ]; then
    echo "::warning::the denylist is empty, the denylist check did not scan anything"
  fi
  echo "warning: the denylist is empty, skipping the denylist check"
  exit 0
fi
hits=$(grep -rilwF -f "$tmp" . \
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
