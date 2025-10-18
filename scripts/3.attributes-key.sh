#!/bin/sh
# Compare a specific attribute across the first two AWS products for a given
# service + productFamily in us-east-1.
#
# Usage:
#   ./3.attributes-key.sh "<Service>" "<ProductFamily>" "<AttributeKey>"
# Example:
#   ./3.attributes-key.sh "AmazonEC2" "Compute Instance" "instanceType"
#
# Requirements: jq, and either gq or curl.
# Optional: set PRICING_ENDPOINT (defaults to https://pricing.infracost.io/graphql)

set -eu

# ---- args ----
if [ $# -lt 3 ]; then
  echo "Usage: $0 <Service> <ProductFamily> <AttributeKey>" >&2
  exit 1
fi
SERVICE="$1"
PRODUCT_FAMILY="$2"
ATTR_KEY="$3"

ENDPOINT="${PRICING_ENDPOINT:-https://pricing.infracost.io/graphql}"

# ---- deps ----
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }
}
need jq
# gq OR curl is fine

# ---- base64 decode portable helper (GNU/macOS) ----
b64d() {
  if base64 --help >/dev/null 2>&1; then
    base64 --decode
  else
    base64 -D
  fi
}

# ---- temp files & cleanup ----
TMP0="$(mktemp -t attrib0.XXXXXX)"
TMP1="$(mktemp -t attrib1.XXXXXX)"
trap 'rm -f "$TMP0" "$TMP1"' EXIT

# ---- fetch function: uses gq if present, otherwise curl ----
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

# ---- run query ----
RESP="$(fetch)"

# Bail early on GraphQL errors
ERRS=$(echo "$RESP" | jq '.errors // empty')
if [ -n "$ERRS" ]; then
  echo "GraphQL returned errors:" >&2
  echo "$ERRS" | jq >&2
  exit 1
fi

# Select first two products and encode them so we can loop safely
attribs=$(
  echo "$RESP" \
  | jq -r '.data.products[:2][] | @base64'
)

# Extract the requested attribute from attributes[] into tmp files
i=0
for x in $attribs; do
  echo "$x" \
  | b64d \
  | jq --arg k "$ATTR_KEY" '
      . as $p
      | {
          productHash: ($p.productHash // ""),
          attrsObj: ( ($p.attributes // [])
                      | map({( .key // "" ): (.value // "")})
                      | add )
        }
      | {productHash, value: (.attrsObj[$k] // null)}' \
  | tee "$( [ $i -eq 0 ] && echo "$TMP0" || echo "$TMP1" )" >/dev/null
  i=$((i + 1))
done

echo "Found $i product(s) for:"
echo "  service       = $SERVICE"
echo "  productFamily = $PRODUCT_FAMILY"
echo "  attributeKey  = $ATTR_KEY"
echo ""
echo "#####################################"
echo ""

# If fewer than 2, just print what we found
if [ "$i" -lt 2 ]; then
  cat "$TMP0"
  exit 0
fi

# Show both values and a diff (excluding noisy fields)
echo "Product 1:"
cat "$TMP0" | jq
echo ""
echo "Product 2:"
cat "$TMP1" | jq
echo ""
echo "Diff (value only):"
diff -U1 \
  <(jq -r '.value' "$TMP0") \
  <(jq -r '.value' "$TMP1") \
  || true
