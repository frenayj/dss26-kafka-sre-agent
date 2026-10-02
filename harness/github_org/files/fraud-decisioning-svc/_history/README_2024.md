# fraud-decisioning-svc

Tier-1 service that approves, sends to review or declines every card
authorisation, and posts the result to the ledger.

- Consumes `cards.authorisation.requested.v1` as consumer group
  `fraud-decisioning-engine` on `cards-prod-euw1`.
- Produces `cards.ledger.posted.v1`, one posting per authorisation, with the
  decision (`APPROVE`, `REVIEW`, `DECLINE`).
- Owner: Cards Platform (`@dss26-org/cards-platform`), Slack `#cards-platform`.

Formerly **fraud-scoring** with consumer group `fraud-scoring-consumer`;
renamed when the service took over approve/decline decisions
([ADR-0011](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979247620/ADR-0011+Rename+fraud-scoring+to+fraud-decisioning)).
`fraud-scoring-consumer` has been deleted.

## How it works

The decisioning loop (`fraud_decisioning/consumer.py`) reads a batch, reads
each record with the pinned reader schema
`schemas/cards_authorisation_requested_v1.avsc`, scores it
(`fraud_decisioning/scoring.py`), produces the ledger postings, waits for every
acknowledgement and then commits once per partition. Offsets are only
committed manually.

## Fail closed

A record that cannot be read with the pinned reader schema is never skipped.
Its partition is paused at that offset and retried every
`BLOCKED_RETRY_SECONDS`; nothing at or after it is committed. Approving or
declining an authorisation we cannot read is not an option, and skipping it
leaves a hole in the ledger. The lag alert pages a human instead.

## Development

```
pip install -r requirements-dev.txt
ruff check .
pytest
```

## Deployment

`main` builds `harbor.dss26.internal/cards-platform/fraud-decisioning-svc:<sha>`.
Values per environment are in `deploy/helm/`; consumer settings live under
`kafka.consumer`. Production changes need a CHG ticket.
