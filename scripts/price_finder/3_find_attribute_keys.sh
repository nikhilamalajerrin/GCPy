#!/bin/sh
# List attribute KEYS for a service + productFamily in a region.
# Usage: ./3_find_attribute_keys.sh "<Service>" "<ProductFamily>" [key=value ...]
set -eu
: "${ENDPOINT:=http://127.0.0.1:4000/graphql}"
: "${REGION:=us-east-1}"

if [ $# -lt 2 ]; then
  echo "Usage: $0 <Service> <ProductFamily> [key=value ...]" >&2
  exit 1
fi
SERVICE="$1"; PRODUCT_FAMILY="$2"; shift 2

need(){ command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }
need jq

ATTRS_JSON='[]'
while [ $# -gt 0 ]; do
  kv="$1"; shift
  k="${kv%%=*}"; v="${kv#*=}"
  [ "$k" != "$kv" ] && ATTRS_JSON=$(printf '%s' "$ATTRS_JSON" | jq --arg k "$k" --arg v "$v" '. + [{key:$k, value:$v}]')
done

QUERY='query ($service: String!, $pf: String!, $region: String!, $attrs: [AttributeFilter!]) {
  products(filter:{
    vendorName:"aws",
    region:$region,
    service:$service,
    productFamily:$pf,
    attributeFilters:$attrs
  }){
    productHash
    attributes { key value }
  }
}'
BODY=$(jq -nc --arg q "$QUERY" --arg s "$SERVICE" --arg pf "$PRODUCT_FAMILY" --arg r "$REGION" --argjson attrs "$ATTRS_JSON" \
       '{query:$q, variables:{service:$s, pf:$pf, region:$r, attrs:$attrs}}')
RESP=$(curl -sS -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY")

# Errors?
if [ "$(echo "$RESP" | jq 'has("errors")')" = "true" ]; then
  echo "GraphQL returned errors:" >&2
  echo "$RESP" | jq '.errors' >&2
  exit 1
fi

echo "$RESP" | jq -r '
  .data.products as $p
  | if ($p|length)==0 then "No products matched your filters." else
      ($p|map(.attributes)|flatten|map(.key)|unique|sort[]) end'
