#!/bin/sh
# Dump key=value pairs (unique) for a service + productFamily
# Usage: ./5_find_all_attribute_key_values.sh "<Service>" "<ProductFamily>" [region] [key=value ...]
set -eu
: "${ENDPOINT:=http://127.0.0.1:4000/graphql}"
: "${REGION:=us-east-1}"

if [ $# -lt 2 ]; then
  echo "Usage: $0 <Service> <ProductFamily> [region] [key=value ...]" >&2
  exit 1
fi

SERVICE="$1"; PRODUCT_FAMILY="$2"; shift 2
if [ $# -gt 0 ] && printf '%s' "$1" | grep -Eq '^[a-z]{2}-'; then REGION="$1"; shift; fi

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
    attributes { key value }
  }
}'
BODY=$(jq -nc --arg q "$QUERY" --arg s "$SERVICE" --arg pf "$PRODUCT_FAMILY" --arg r "$REGION" --argjson attrs "$ATTRS_JSON" \
       '{query:$q, variables:{service:$s, pf:$pf, region:$r, attrs:$attrs}}')
RESP=$(curl -sS -X POST "$ENDPOINT" -H "Content-Type: application/json" -d "$BODY")

if [ "$(echo "$RESP" | jq 'has("errors")')" = "true" ]; then
  echo "GraphQL returned errors:" >&2
  echo "$RESP" | jq '.errors' >&2
  exit 1
fi

echo "$RESP" | jq -r '
  .data.products
  | map(.attributes // [])
  | flatten
  | map("\(.key)=\(.value)")
  | unique
  | sort
  | .[]'
