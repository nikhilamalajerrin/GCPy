#!/usr/bin/env sh
# List unique values for a given attribute key across AWS products
# filtered by service + productFamily (default region us-east-1).
#
# Usage:
#   ./4.attributes-value.sh "<Service>" "<ProductFamily>" "<AttributeKey>"
# Example:
#   ./4.attributes-value.sh "AmazonEC2" "Compute Instance" "instanceType"
#
# Env overrides:
#   PRICING_ENDPOINT (default: https://pricing.infracost.io/graphql)
#   REGION          (default: us-east-1)

set -eu
IFS=$(printf '\n\t')

if [ $# -lt 3 ]; then
  echo "Usage: $0 <Service> <ProductFamily> <AttributeKey>" >&2
  exit 1
fi

SERVICE="$1"
PRODUCT_FAMILY="$2"
ATTR_KEY="$3"

ENDPOINT="${PRICING_ENDPOINT:-https://pricing.infracost.io/graphql}"
REGION="${REGION:-us-east-1}"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }
}
need jq
# gq OR curl is fine

fetch() {
  if command -v gq >/dev/null 2>&1; then
    gq "$ENDPOINT" -q '
      query($service: String!, $pf: String!, $region: String!) {
        products(filter: {
          vendorName: "aws"
          region: $region
          service: $service
          productFamily: $pf
        }) {
          attributes { key, value }
        }
      }' \
      -v service="$SERVICE" -v pf="$PRODUCT_FAMILY" -v region="$REGION"
  else
    need curl
    QUERY='query($service: String!, $pf: String!, $region: String!) {
      products(filter: {
        vendorName: "aws"
        region: $region
        service: $service
        productFamily: $pf
      }) { attributes { key, value } }
    }'
    BODY=$(jq -nc \
      --arg q "$QUERY" \
      --arg s "$SERVICE" \
      --arg pf "$PRODUCT_FAMILY" \
      --arg r "$REGION" \
      '{query:$q, variables:{service:$s, pf:$pf, region:$r}}')
    curl -sS -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY"
  fi
}

RESP="$(fetch)"

# Fail loudly on GraphQL errors
if [ "$(echo "$RESP" | jq 'has("errors")')" = "true" ]; then
  echo "GraphQL returned errors:" >&2
  echo "$RESP" | jq '.errors' >&2
  exit 1
fi

# Print unique values for the requested attribute key, one per line (non-empty)
echo "$RESP" \
  | jq -r --arg k "$ATTR_KEY" '
      .data.products[]
      | ( (.attributes // [])
          | map(select(.key == $k) | .value)
          | .[]? )
    ' \
  | awk 'length>0' \
  | sort -u
