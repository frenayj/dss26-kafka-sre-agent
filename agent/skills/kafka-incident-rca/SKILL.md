---
name: kafka-incident-rca
description: Structured root cause analysis for Kafka consumer lag incidents. Use when diagnosing a consumer group lag spike, stall, or CRITICAL alert - ensures schema incompatibility is checked before throughput bottleneck is concluded, metric discrepancies are reconciled with evidence, and all claims are evidence-backed. Do NOT use for proactive topic health checks, schema review in isolation, or performance tuning.
---

# Kafka Incident RCA

Incidents where consumers fall behind can stem from three primary causes: schema breaking changes, throughput saturation, or application faults. The post-mortem discipline: **always check schema registry second**, before concluding throughput - a single wrong root cause can paralyze response.

This skill enforces a decision tree that prioritizes schema checking and requires evidence for every claim. It composes with `kafka-consumer-lag` (for basic lag diagnosis) and `kafka-schema-review` (for schema compatibility deep-dives).

---

## Workflow

- [ ] Step 1: Reconcile metric discrepancy (alert lag vs snapshot lag)
- [ ] Step 2: Query schema registry for breaking changes in consumed topic
- [ ] Step 3: Check message samples for deserialization signals
- [ ] Step 4: Analyze throughput only if schema is clean
- [ ] Step 5: Confirm blast radius (cross-cluster scope)
- [ ] Step 6: Attribute root cause with evidence chain
- [ ] Step 7: Produce structured RCA with decision rationale

---

## Step 1: Reconcile Metric Discrepancy

**Why:** Alert lag and MCP snapshot lag often differ by hours of monitoring sampling. Explaining this gap is a prerequisite to trusting any downstream analysis.

### Action

If `alert_lag ≠ snapshot_lag`:

1. Use `get_dataset_message_metrics` to fetch recent messages from the consumed topic with timestamps
2. Sample at least 5 recent messages across different offsets
3. Compare message timestamps to the alert timestamp (from incident metadata)
4. Classify the discrepancy:
   - **Most recent message is before alert time?** → Consumer stalled at that point; explains why snapshot lag shrinks over time
   - **Most recent message is recent (within 5 min)?** → Consumer has recovered or is recovering; note this as partial recovery
   - **No correlation?** → Acknowledge the gap explicitly; do not speculate

### Evidence format

```
Metric discrepancy reconciliation:
Alert lag (Datadog, 2026-02-11T14:20:41Z): 48,960 messages
Snapshot lag (Lenses API, 2026-02-11T14:30:00Z): 3,207 messages
Most recent message in sample: timestamp=2026-02-11T14:05:09Z
Conclusion: Consumer stalled ~15 min ago; recent recovery underway
```

Do NOT write: "Lag discrepancy likely due to monitoring cache delay." Instead: "Lag discrepancy explained by [message-timestamp evidence]; consumer stalled from 14:05 to ~14:15, now recovering."

---

## Step 2: Query Schema Registry for Breaking Changes

**Why:** This is the mandatory second step. Schema incompatibility is the most common culprit in modern Kafka incidents, yet easiest to miss if you analyze throughput first.

### Action

1. Identify the consumed topic name from Step 1 output (e.g., `orders.placed.v3`)
2. Use `execute_sql` to query the schema registry for recent schema versions on that topic
   - Query pattern: `SELECT version, compatibility_mode, timestamp FROM schema_registry WHERE topic = ? ORDER BY timestamp DESC LIMIT 5`
   - Alternatives: Lenses `GET /api/v1/schemas/subject/{topic-value}/versions` or direct schema registry call
3. For any version changed within the lag window (e.g., last 2 hours):
   - Check compatibility mode: NONE, FORWARD → breaking change confirmed
   - Check if BACKWARD but schema is otherwise modified (field removals, type changes)
4. If breaking change found: proceed to Step 3 (message sample inspection); if clean: skip to Step 4 (throughput analysis)

### Evidence format

```
Schema registry query:
Topic: orders.placed.v3
Version changes in last 2h:
  v1: timestamp=2026-02-11T14:04:03Z, compatibility=BACKWARD
      fields: [quantity: int, gift_wrap: boolean, ...]
  v2: timestamp=2026-02-11T14:04:12Z, compatibility=BACKWARD → NONE
      fields: [quantity: string, ...] (gift_wrap removed)
Verdict: Breaking change confirmed (quantity: int → string, field removal)
```

---

## Step 3: Check Message Samples for Deserialization Signals

**Applies only if Step 2 detected a breaking change.**

### Action

1. Use `get_dataset_message_metrics` to sample 5+ recent messages (offsets spanning the last hour)
2. For each message, inspect the parsed content:
   - **Signal 1 (Data mismatch)**: Do any fields contain empty arrays, nulls, or values inconsistent with the schema definition after the breaking change?
     - Example: `promo_codes: []` (empty) when schema requires a structured object → deserialization likely failed or field is nullable in old schema but required in new
   - **Signal 2 (Offset stall)**: Compare consumer committed offset to producer offset
     - If `consumer_offset << producer_offset` and has not advanced in 10+ minutes → consumer stalled (incompatible message encountered)

3. Tally signals:
   - **Both signals present or one is high-confidence?** → Schema incompatibility is the root cause; skip Step 4
   - **Signal weak (1-2 messages with empty fields, but most parse fine)?** → Escalate to Step 4 throughput analysis; note ambiguity

### Evidence format

```
Message sample inspection (topic: orders.placed.v3):
Sample 1 (offset 1000): quantity="2", gift_wrap=true, promo_codes=[...] ✓
Sample 2 (offset 2000): quantity="1", gift_wrap=null, promo_codes=[] ← empty, inconsistent
Sample 3 (offset 3000): deserialize error (schema mismatch) ← Signal 1 confirmed
Sample 4 (offset 4000): quantity=null, gift_wrap=null ← Signal 2 confirmed (stall)
Sample 5 (offset 5000): quantity="5", gift_wrap=false, promo_codes=[...] ✓

Verdict: Signals 1 and 2 both detected. Root cause: Schema incompatibility.
```

---

## Step 4: Analyze Throughput (Schema-Clean Path Only)

**Applies only if Step 2 found no breaking change AND Step 3 found no deserialization signals.**

### Action

1. Get producer rate (messages/sec) from `get_dataset_message_metrics`:
   - Count messages produced in the last 1 hour
   - Divide by 3600 seconds
   - Compare to per-partition capacity (typically 10-50 MB/s, depending on broker config; estimate ~120 msg/s for moderate message size)

2. Get partition topology from `get_topic_partitions`:
   - Count partitions on the consumed topic
   - Calculate capacity = partition_count × per_partition_throughput_limit

3. Compare producer_rate to capacity:
   - **producer_rate > capacity AND lag monotonically growing over 30 min AND consumer count is fixed?** → Throughput bottleneck
   - **producer_rate > capacity BUT lag fluctuates (up/down)?** → Consumer rebalance, GC pause, or transient issue; investigate consumer logs
   - **producer_rate ≤ capacity?** → Throughput is not the bottleneck; proceed to Step 4b (consumer application)

### Evidence format

```
Throughput analysis (topic: orders.placed.v3):
Producer rate: 120 msg/s (counted from last 1h window)
Partition count: 1
Estimated per-partition capacity: ~120 msg/s (assuming standard broker config)
Calculated cluster capacity: 120 msg/s
Lag trend: 3,207 → 3,215 → 3,221 → 3,230 (monotonic growth over 30 min)

Verdict: producer_rate = capacity; lag monotonically growing. This suggests partition under-provisioning.
Recommendation: Scale to ≥6 partitions to accommodate sustained 120 msg/s + headroom.
```

### Step 4b: Consumer Application Fault (if throughput is clean)

If Steps 2–4 all return clean signals:

1. Check consumer logs (Datadog, ELK, application logs) for:
   - Poison pills (repeated deserialization or parsing errors on the same offset)
   - Infinite retry loops (exception stacktraces repeating, thread hung)
   - Synchronous I/O stalls (consumer blocked on external service: schema registry, cache, database)
2. Note any secondary symptoms: GC pauses, network timeouts, rebalance storms

---

## Step 5: Confirm Blast Radius (Parallel with Steps 1–4)

### Action

1. If `list_environments` returns other clusters (uat, dev), use `list_consumer_groups` on each to check if the consumer group exists elsewhere. With a single environment, skip this and record the scope as production-only.
   - If group absent from non-prod clusters → production-only incident
   - If group present on uat but lag is clean → prod-specific trigger (config, schema version, producer rate)

2. Use `list_consumer_groups_by_topic` and `list_topics` to identify downstream topics:
   - Consumed topic: `orders.placed.v3`
   - Downstream producer: which service publishes to this topic after consuming?
   - Output topic: `orders.invoiced.v1` (or equivalent in this service)
   - Check downstream topic for lag spikes (often lagged by 5–15 minutes from root cause)

3. Note replication factor and compliance tags:
   - RF=1 with no redundancy + production topic + compliance tags → high-risk scenario if a broker fails during the incident

### Evidence format

```
Blast radius:
Consumer group: orders-enricher
Clusters checked: shop-prod-euc1, shop-dev-euc1
Status: Present on prod-euc1 only; absent from dev → PRODUCTION-ONLY INCIDENT

Downstream impact:
Input topic: orders.placed.v3 (RF=1, compliance:gdpr, compliance:sox)
Output topic: orders.invoiced.v1 (RF=1)
Services affected: invoicing, warehouse-allocation
Impact: invoices and warehouse picks delayed by ~10 min
```

---

## Step 6: Attribute Root Cause with Evidence Chain

**Evidence discipline rule:** A root cause label requires at minimum two corroborating signals. Do not attribute based on inference or a single metric.

### Root Cause Labels

**Schema Incompatibility**
- Requires: (a) schema version changed in last lag_window, AND (b) at least one of: compat mode NONE/FORWARD, OR message samples show deser mismatch, OR offset stall detected
- Confidence: high if (a) + (b) both present

**Throughput Bottleneck**
- Requires: (a) producer_rate > partition_capacity, AND (b) lag monotonically growing, AND (c) no schema/deser errors
- Confidence: high only if all three present

**Consumer Application Fault**
- Requires: (a) lag growing while throughput/schema clean, AND (b) consumer logs show poison pill/retry loop/stall
- Confidence: medium if only (a); high if (b) is present

### Output Format

```markdown
## Root Cause Attribution

**Primary root cause:** [Label]
- Signal 1: [Evidence], source: [Tool]
- Signal 2: [Evidence], source: [Tool]
- Rationale: [One sentence explaining why these signals point to this cause]

**Secondary risks (if any):**
- [Risk]: [observation], severity: [low/medium/high]

**Metric discrepancy resolution:**
Alert lag: X | Snapshot lag: Y | Explanation: [evidence-backed reasoning]

**Evidence gaps (if any):**
- Consumer logs unavailable; could not confirm poison pills
- Schema registry query timed out; inferred from code diff instead
```

---

## Step 7: Produce Structured RCA Output

### Mandatory sections (in this order)

```markdown
## Root Cause
**Primary:** [Label] - [one sentence; cites two evidence sources]
**Secondary risks:** [list]

## Evidence Chain
| Signal | Tool | Value | Interpretation |
|--------|------|-------|----------------|
| [metric name] | `[Lenses tool]` | [value] | [what this tells us] |
| ... | ... | ... | ... |

## Metric Discrepancy
Alert lag: `48,960` | Snapshot lag: `3,207` | Timestamp: `2026-02-11T14:05:09Z` | Explanation: [from Step 1]

## Blast Radius
- Scope: [production-only | cross-cluster]
- Downstream topics: [list and lag status]
- Compliance tags: [any compliance:* tags on affected topics]

## Recommended Action
**Verb:** [Rollback | Apply fix | Escalate investigation | Scale partitions]
**Specific action:** [PR #<n> in <repo>, or "investigate consumer logs for X"]
**Why:** [cites evidence from the chain above; must be decisive, not hedged]

## Appendix: Decision Tree Path
[Brief narrative of which steps were taken and why; e.g., "Skipped throughput analysis because schema incompatibility was confirmed in Step 2"]
```

### Success Criteria

- [ ] Every claim in "Root Cause" is backed by at least two evidence signals from the table
- [ ] Metric discrepancy is resolved with timestamps, not speculation
- [ ] Recommended action is a directive (Revert PR #<n>), not a choice ("decide whether to rollback or fix")
- [ ] If evidence is ambiguous, say so explicitly and list both possibilities ranked by confidence
- [ ] No hedging language ("may be", "likely", "possibly") without citing the inference gap

---

## Examples

### Example 1: Schema Incompatibility

**Input:**
- Alert: orders-enricher consumer lag = 48,960 messages at 14:20 UTC
- Service: shop/orders-enricher
- Cluster: shop-prod-euc1

**Workflow:**
1. Reconcile: Snapshot lag = 3,207 at 14:30. Most recent message timestamp = 14:05 (before alert). → Consumer stalled ~15 min ago.
2. Schema check: `orders.placed.v3` gained a version at 14:04: `quantity` int → string, `gift_wrap` removed. Compat mode: FULL → NONE.
3. Message sample: recent messages show `gift_wrap=null` (field removed), `promo_codes=[]` (empty, unusual).
4. Skip throughput: schema incompatibility confirmed.
5. Blast radius: group absent from dev; output topic `orders.invoiced.v1` stopped receiving records at 14:05.
6. Root cause: Schema incompatibility. Signal 1: compat mode NONE + type change + field removal. Signal 2: message samples carry the new shape.

**Output:**
```markdown
## Root Cause
**Primary:** Avro schema breaking change - `orders.placed.v3` changed quantity (int → string) and removed gift_wrap at 2026-02-11T14:04:12Z, breaking deserialization in the orders-enricher consumer.
- Signal 1: Schema registry shows compat mode FULL → NONE, a type change and a field removal, source: schema versions via Lenses
- Signal 2: Message samples show gift_wrap=null, promo_codes=[] (consistent with the new schema), source: `get_dataset_message_metrics`

## Recommended Action
**Revert the producer change** that registered the new version (the PR forensics identified), or fast-track a consumer-side fix that reads quantity as a string.
Why: Two signals confirm schema incompatibility; deserialization is failing on live messages; no throughput bottleneck detected.
```

---

### Example 2: Throughput Bottleneck (Contrasting Case)

**Input:**
- Alert: payments-processor consumer lag = 150,000 messages at 12:00 UTC
- Topic: payments.settled.v2
- Cluster: payments-prod-usw2

**Workflow:**
1. Reconcile: Snapshot lag = 149,500 at 12:05. Most recent message timestamp = 11:55 (10 min old). → Consumer lagging on old messages; not just monitoring lag.
2. Schema check: No version changes in `payments.settled.v2` in last 4 hours.
3. Message sample: All 5 messages parse cleanly; no null/empty fields.
4. Throughput analysis: Producer rate = 200 msg/s, partitions = 1, capacity = ~120 msg/s. Lag trend: growing 500 msg/min for last 30 min (monotonic).
5. Blast radius: group present on all clusters but lag is production-only; downstream topic `payments.ledger.v1` also lagging.
6. Root cause: Throughput bottleneck. Signal 1: producer_rate (200) > capacity (120). Signal 2: lag monotonically growing.

**Output:**
```markdown
## Root Cause
**Primary:** Throughput bottleneck - payments-processor consumer on payments.settled.v2 (1 partition) cannot keep up with producer rate of 200 msg/s (estimated per-partition capacity: ~120 msg/s).
- Signal 1: Producer rate 200 msg/s > partition capacity 120 msg/s, source: `get_dataset_message_metrics` (1h count)
- Signal 2: Consumer lag monotonically growing 500 msg/min for 30 min; offset advancement rate < producer rate, source: `get_dataset_message_metrics` (5-min snapshots)

**Secondary risks:**
- Single partition limits horizontal scaling; requires increasing partition count
- RF=1; broker failure during this incident would cause data loss on compliance:sox topic

## Recommended Action
**Scale topic to 6+ partitions and consumer replicas to match.** Why: Throughput analysis confirms producer rate exceeds single-partition capacity. Horizontal scaling is the only remedy. In parallel, consider rate shedding or circuit-breaking at the producer until scaling completes.
```

---

## Troubleshooting

### "Lag discrepancy is huge; I don't know where to start"

**Cause:** Metric reconciliation step was skipped.

**Fix:** Always run Step 1 first. Fetch 5+ recent messages with timestamps. Compare the most recent message's timestamp to the alert timestamp. This single comparison resolves 90% of discrepancy questions.

### "Schema check returned clean but I still suspect a breaking change"

**Cause:** Schema registry query missed the change (e.g., query used wrong topic name, or schema was changed in the producer code but not registered).

**Fix:** Cross-check with code. Use forensics agent to fetch recent PRs in the producer service and look for schema-changing diffs. If code and registry disagree, flag this explicitly in the RCA.

### "All signals are clean (schema, throughput, logs) but lag still grows"

**Cause:** Consumer application logic is broken (infinite loop, synchronous stall, resource leak).

**Fix:** Inspect consumer logs for repeating errors, thread dumps, or GC pauses. If logs are unavailable, recommend checking consumer CPU/memory metrics and restarting the consumer pod to rule out process-level hangs.

### "I have one strong signal but not two"

**Cause:** Evidence discipline rule requires two signals; single signals can be false positives.

**Fix:** Explicitly note the ambiguity in the RCA. Write: "Single signal detected (e.g., high producer rate); insufficient for confident root cause attribution. Recommend escalating to [next step] and checking [additional evidence source]." Do not speculate.

---

## Output Validation Checklist

Before publishing the RCA, verify:

- [ ] Every claim in "Root Cause" is backed by at least two evidence signals
- [ ] All tool calls (get_dataset_message_metrics, execute_sql, get_topic_partitions, etc.) are cited in the evidence chain
- [ ] Metric discrepancy is resolved with message timestamps, not speculation or cache-delay hand-waving
- [ ] Recommended action uses a directive verb (Rollback, Apply, Scale, Investigate) - not "decide whether to"
- [ ] Decision tree path is documented (which steps were taken, which were skipped and why)
- [ ] Blast radius is confirmed (prod-only? cross-cluster? which downstream topics affected?)
- [ ] No hedging language ("likely", "may be", "possibly") unless explicitly tied to an evidence gap
