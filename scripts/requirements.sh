#!/usr/bin/env bash
# Setup helper deps for the pricing discovery scripts.
# - Installs jq + (optionally) Node + graphqurl on macOS via Homebrew
# - Falls back to existing installs if present
# - Downloads AWS pricing index.json next to this script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX_JSON="$SCRIPT_DIR/index.json"

have() { command -v "$1" >/dev/null 2>&1; }

echo "==> Checking jq"
if have jq; then
  echo "jq already installed ✔"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  if ! have brew; then
    echo "Homebrew not found. Install from https://brew.sh/ and re-run." >&2
    exit 1
  fi
  brew install jq
else
  echo "Please install jq with your package manager (apt/dnf/yum/etc) and re-run." >&2
  exit 1
fi

echo "==> Checking Node (for graphqurl)"
if ! have node; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    brew install node
  else
    echo "Node not found; skipping graphqurl install (scripts will use curl if available)." >&2
  fi
fi

echo "==> Checking graphqurl (gq)"
if ! have gq; then
  if have npm; then
    npm install -g graphqurl
  else
    echo "npm not found; skipping graphqurl install (scripts will use curl if available)." >&2
  fi
else
  echo "graphqurl already installed ✔"
fi

echo "==> Downloading AWS pricing index.json"
if [[ -f "$INDEX_JSON" ]]; then
  echo "index.json already exists at $INDEX_JSON (skipping download) ✔"
else
  if have curl; then
    curl -fsSL -o "$INDEX_JSON" "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
  elif have wget; then
    wget -O "$INDEX_JSON" "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
  else
    echo "Need curl or wget to download index.json." >&2
    exit 1
  fi
  echo "Saved to $INDEX_JSON ✔"
fi

echo "All set! You can run the scripts now."
