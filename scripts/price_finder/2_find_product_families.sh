#!/bin/sh
# Usage: ./2_find_product_families.sh "<AWS Service Name>"
# Example: ./2_find_product_families.sh "AmazonRDS"
# Requires: gq (GraphQL CLI) and jq
#
# Env overrides:
#   ENDPOINT=https://pricing.infracost.io/graphql
#   REGION=us-east-1

set -eu

: "${ENDPOINT:=https://pricing.infracost.io/graphql}"
: "${REGION:=us-east-1}"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <AWS Service Name>" >&2
  exit 1
fi

SERVICE="$1"

gq "$ENDPOINT" -q '
query ($service: String!, $region: String!) {
  products(filter: {
    vendorName: "aws"
    region: $region
    service: $service
  }) {
    productFamily
  }
}
' -v service="$SERVICE" -v region="$REGION" \
| jq -r '
  .data.products
  | map(.productFamily)         # collect families (may include nulls)
  | map(select(. != null))      # drop nulls
  | unique
  | sort
  | .[]
' | {
  # capture output to detect empty result
  had_output=false
  while IFS= read -r line; do
    had_output=true
    printf "%s\n" "$line"
  done
  if [ "$had_output" = false ]; then
    echo "No product families found for service \"$SERVICE\" in region \"$REGION\"." >&2
    exit 2
  fi
}
