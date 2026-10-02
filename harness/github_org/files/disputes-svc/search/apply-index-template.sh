#!/usr/bin/env bash
# Apply the chargeback index template to one disputes-search cluster.
#   ES_URL=https://disputes-search.uat.dss26.internal:9200 ES_USER=... ES_PASSWORD=... ./search/apply-index-template.sh
# Templates only apply to new indices: after a mapping change, roll the index
# over (or reindex) - see README "Search index".
set -euo pipefail

: "${ES_URL:?set ES_URL}"
: "${ES_USER:?set ES_USER}"
: "${ES_PASSWORD:?set ES_PASSWORD}"

here="$(cd "$(dirname "$0")" && pwd)"

curl --fail --silent --show-error \
  -u "${ES_USER}:${ES_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -X PUT "${ES_URL}/_index_template/cards-chargeback" \
  --data-binary @"${here}/index-template.json"
echo
