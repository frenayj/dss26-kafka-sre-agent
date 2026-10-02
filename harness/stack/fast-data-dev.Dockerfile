# fast-data-dev + kafka-connect-datagen.
#
# The base lensesio/fast-data-dev image bundles Stream Reactor + the Apache
# file/mirror connectors, but NOT Confluent's kafka-connect-datagen. We add it
# so the demo can generate baseline card-auth traffic through Kafka Connect.
# See harness/seed/seed_datagen.py.
#
# kafka-connect-datagen is Apache-2.0. We take the packaged component out of
# Confluent's published image and drop it into fast-data-dev's third-party
# plugin dir - the same place the bundled file/debezium connectors live, so it
# is already on the Connect plugin path.
#
# Why the image and not the Confluent Hub archive: the Hub archive endpoint
# (api.hub.confluent.io/.../archive) proved unreliable from some networks -
# large transfers are terminated part-way with curl exit 92, which fails the
# build on the very first step and blocks the whole stack. Docker Hub pulls are
# already on the critical path for every other image here, so sourcing it this
# way removes an independent, flakier dependency rather than adding one.
#
# The image tag is <datagen-version>-<confluent-platform-version>. It is only
# ever used as a COPY source in a build stage - never run - so its amd64
# platform is irrelevant on arm64 hosts (the payload is plain Java jars);
# --platform is pinned to keep BuildKit from emitting a spurious warning.

ARG DATAGEN_IMAGE=cnfldemos/kafka-connect-datagen:0.6.7-8.0.0

# --- source the connector from Confluent's published image ---
FROM --platform=linux/amd64 ${DATAGEN_IMAGE} AS datagen

# --- bake it into fast-data-dev ---
FROM lensesio/fast-data-dev:3.9.0
COPY --from=datagen \
     /usr/share/confluent-hub-components/confluentinc-kafka-connect-datagen/ \
     /opt/lensesio/connectors/third-party/kafka-connect-datagen/

# Bake the datagen generation schema so the Connect worker can load it via
# `schema.filename` (the `schema.string` path drops arg.properties off
# primitive types). Baking rather than writing it at seed time keeps the
# connector working across broker restarts without a reseed.
COPY harness/stack/datagen/cards_authorisation_requested_v1.datagen.avsc \
     /opt/lensesio/datagen/cards_auth_prod.avsc
