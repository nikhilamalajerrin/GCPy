#!/usr/bin/env sh
set -eu

# Path to the AWS pricing index (override with INDEX env var)
INDEX="${INDEX:-index.json}"

if [ ! -f "$INDEX" ]; then
  echo "Error: $INDEX not found. Set INDEX=/path/to/index.json or run in the folder containing it." >&2
  exit 1
fi

have_jq=0
if command -v jq >/dev/null 2>&1; then
  have_jq=1
fi

print_all_services() {
  if [ "$have_jq" -eq 1 ]; then
    # The AWS pricing index.json structure has an "offers" object with keys like "AmazonRDS", "AmazonEC2", etc.
    jq -r '.offers | keys[]' "$INDEX" | sort
  else
    # Fallback: grep the "offerCode" fields and extract the value
    grep -o '"offerCode":[[:space:]]*"[^"]*"' "$INDEX" \
      | sed -E 's/.*"offerCode":[[:space:]]*"([^"]*)".*/\1/' \
      | sort -u
  fi
}

search_services() {
  q="$1"
  if [ "$have_jq" -eq 1 ]; then
    # Match query against the offer keys (case-insensitive)
    jq -r --arg q "$q" '.offers | to_entries[] | select(.key | test($q; "i")) | .key' "$INDEX" | sort
  else
    # Fallback grep (case-insensitive, quoted)
    grep -i -- "$q" "$INDEX" \
      | grep -o '"offerCode":[[:space:]]*"[^"]*"' \
      | sed -E 's/.*"offerCode":[[:space:]]*"([^"]*)".*/\1/' \
      | sort -u
  fi
}

if [ "${1:-}" = "" ]; then
  echo "Listing all AWS services (offer codes):"
  print_all_services
else
  echo "Matches for \"$1\":"
  search_services "$1"
fi
