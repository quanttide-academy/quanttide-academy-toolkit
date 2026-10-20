#!/usr/bin/env bash
set -euo pipefail
git commit "$@"
out="$(git status --short)"
if [ -n "$out" ]; then
  echo "error: working tree not clean after commit:" >&2
  echo "$out" >&2
  exit 1
fi
