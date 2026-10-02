# fraud-scoring

Scores every card authorisation request in real time and posts the score to
the ledger. Replaces the nightly batch scoring job.

- Consumes `cards.authorisation.requested.v1` as consumer group
  `fraud-scoring-consumer`.
- Produces `cards.ledger.posted.v1` (one posting per authorisation).
- Records are JSON.

## Scoring

`fraud_scoring/scoring.py` adds a base rate per channel and a weight per risk
signal attached by the merchant gateway, capped at 1.0. Scores of 0.5 and
above are flagged for review, 0.8 and above as a recommended decline. The
issuer host makes the final decision.

## Running

```
pip install -r requirements-dev.txt
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 python -m fraud_scoring
```

## Owners

Cards Platform (`@dss26-org/cards-platform`), Slack `#cards-platform`.
