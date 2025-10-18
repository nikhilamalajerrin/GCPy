#!/bin/sh
# Usage: ./2.productFamily.sh "AmazonRDS"
# Requires: gq (GraphQL CLI) and jq

set -eu

if [ $# -lt 1 ]; then
  echo "Usage: $0 <AWS Service Name>" >&2
  exit 1
fi

SERVICE="$1"
ENDPOINT="https://pricing.infracost.io/graphql"

gq "$ENDPOINT" -q "
query (\$service: String!) {
  products(filter: {
    vendorName: \"aws\"
    region: \"us-east-1\"
    service: \$service
  }) {
    productFamily
  }
}" -v service="$SERVICE" \
| jq -r '.data.products[].productFamily' \
| sort -u
