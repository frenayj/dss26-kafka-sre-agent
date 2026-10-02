# clearing-settlement-svc runbook

## Settlement run did not finish

The job is transactional: either every merchant batch for the day is posted,
or none is.

1. Logs: `Settlement <date>: <n> merchant batches posted` means it finished.
   No such line: look for the exception in the same pod.
2. If it failed, fix the cause and run the cut-off again with
   `POST /admin/settlement/run` on any one pod (internal ingress only,
   `clearing-ops` role). It only picks up records that are not settled yet.
3. Funding leaves at 06:00. If the run cannot complete by 05:00, call
   Treasury operations so they hold the payment file.

## Unmatched queue growing

1. Datadog: is the match rate down for one network or both?
2. One network: check the presentment file of the last cycle for a format
   change (the scheme gateway team owns the normalisation).
3. Both: check that `issuer_auth_log` replication is current
   (`SELECT max(authorised_at) FROM issuer_auth_log`). A stale replica means
   every presentment looks unmatched.
4. Once the cause is fixed, re-drive the queue: reset
   `clearing-settlement-matcher` to the start of the cycle. The matcher skips
   presentments that already have a match.
