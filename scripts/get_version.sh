#!/usr/bin/env bash
set -euo pipefail

COMMITISH=${1:-HEAD}
SUFFIX=""


git update-index -q --refresh || true
if ! git diff-files --quiet -- . ':!**/go.mod' ':!**/go.sum'; then
  SUFFIX="-dirty"
fi
if ! git diff-index --quiet --cached HEAD -- . ':!**/go.mod' ':!**/go.sum'; then
  SUFFIX="-dirty"
fi

# Ensure we have tags (handle shallow clones gracefully)
# If this fails (no remote), we just proceed with whatever tags exist locally.
git fetch --tags --quiet || true

TAG=""
if git describe --tags --exact-match "${COMMITISH}" >/dev/null 2>&1; then
  TAG=$(git describe --tags --exact-match "${COMMITISH}")
elif git describe --tags "${COMMITISH}" >/dev/null 2>&1; then
  TAG=$(git describe --tags "${COMMITISH}")
else
  # Fallback: short commit hash so we never return empty
  TAG=$(git rev-parse --short "${COMMITISH}")
fi

printf '%s%s\n' "$TAG" "$SUFFIX"
