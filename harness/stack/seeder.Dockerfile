# One-shot demo seeder - runs the idempotent seed scripts against the running
# stack, then exits, so a plain `docker compose up` needs no Python venv.
#
# Based on docker:cli because creating topics needs `docker exec` into the
# broker container (`kafka-topics --create`), which has no network-only
# equivalent. The compose service mounts the Docker socket for this.
# Everything else is plain HTTP to the internal Schema Registry / Kafka
# Connect / Lenses HQ endpoints (set via env).
FROM docker:27-cli

# python3 + requests (the scripts' only third-party dep).
RUN apk add --no-cache python3 py3-requests

WORKDIR /app
COPY harness/seed/ harness/seed/
# The auth schema, pre-registered before the datagen connector starts.
COPY harness/stack/schemas/ harness/stack/schemas/

# Not `&&`-chained: each step is idempotent and independent, so a slow step
# never blocks the next. Re-running the whole seeder is always safe.
CMD ["sh", "-c", "python3 harness/seed/seed_demo_topics.py; python3 harness/seed/apply_topic_metadata.py; python3 harness/seed/seed_datagen.py seed"]
