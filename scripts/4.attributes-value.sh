#!/bin/sh
# List unique values for a given attribute key across AWS products
# filtered by service + productFamily (region fixed to us-east-1).
#
# Usage:
#   ./4.attributes-value.sh "<Service>" "<ProductFamily>" "<AttributeKey>"
# Example:
#   ./4.attributes-value.sh "AmazonEC2" "Compute Instance" "instanceType"
#
# Requirements: jq, and either gq or curl.
# Optional: set PRICING_ENDPOINT (defaults to https://pricing.infracost.io/graphql)

set -eu

if [ $# -lt 3 ]; then
  echo "Usage: $0 <Service> <ProductFamily> <AttributeKey>" >&2
  exit 1
fi

SERVICE="$1"
PRODUCT_FAMILY="$2"
ATTR_KEY="$3"
ENDPOINT="${PRICING_ENDPOINT:-https://pricing.infracost.io/graphql}"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }
}
need jq
# gq OR curl is fine

fetch() {
  if command -v gq >/dev/null 2>&1; then
    gq "$ENDPOINT" -q "
      query(\$service: String!, \$pf: String!) {
        products(filter: {
          vendorName: \"aws\"
          region: \"us-east-1\"
          service: \$service
          productFamily: \$pf
        }) {
          productHash
          attributes { key, value }
        }
      }" -v service="$SERVICE" -v pf="$PRODUCT_FAMILY"
  else
    need curl
    QUERY='query($service: String!, $pf: String!) {
      products(filter: {
        vendorName: "aws"
        region: "us-east-1"
        service: $service
        productFamily: $pf
      }) {
        productHash
        attributes { key, value }
      }
    }'
    BODY=$(jq -nc --arg q "$QUERY" --arg s "$SERVICE" --arg pf "$PRODUCT_FAMILY" \
      '{query:$q, variables:{service:$s, pf:$pf}}')
    curl -sS -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY"
  fi
}

RESP="$(fetch)"

# Fail loudly on GraphQL errors
ERRS=$(echo "$RESP" | jq '.errors // empty')
if [ -n "$ERRS" ]; then
  echo "GraphQL returned errors:" >&2
  echo "$ERRS" | jq >&2
  exit 1
fi

# Print unique values for the requested attribute key, one per line.
# Filters out null/empty entries.
echo "$RESP" \
| jq -r --arg k "$ATTR_KEY" '
    .data.products[]
    | ( (.attributes // [])
        | map({( .key // "" ): (.value // "")})
        | add
        | .[$k] ) // empty
  ' \
| awk 'length>0' \
| sort | uniq
