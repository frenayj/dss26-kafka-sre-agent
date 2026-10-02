# RCA Decision Tree for Kafka Consumer Lag Incidents

## Overview

This decision tree guides root cause attribution for consumer lag spikes. The key principle: **schema incompatibility must be checked before throughput bottleneck is concluded**. Follow the decision points in order; do not skip steps or reorder.

---

## Decision Flow

```
Consumer lag detected
  │
  ├─► [STEP 1] Metric reconciliation
  │   Alert-lag value ≠ MCP snapshot lag?
  │   │
  │   ├─ YES → Why the gap? Check message timestamps:
  │   │         • Most recent message before alert time? → Consumer stalled (explains shrinking snapshot)
  │   │         • Most recent message is recent? → Partial recovery has begun (note this)
  │   │         • Document the discrepancy with timestamps; never speculate without evidence
  │   │
  │   └─ NO  → Gap is within monitoring sampling error; proceed
  │
  ├─► [STEP 2] Schema registry: breaking changes?
  │   Any schema version change in last 2 hours on the consumed topic?
  │   │
  │   ├─ YES → Check compatibility mode:
  │   │         • Mode = NONE or FORWARD? → Breaking change confirmed
  │   │         • Mode = BACKWARD? → Probe for signal 1: sample messages for deser errors
  │   │         
  │   │         Sample messages show empty/null fields NOT in schema? → SIGNAL 1 DETECTED
  │   │         Consumer committed offset stalled vs producer advanced? → SIGNAL 2 DETECTED
  │   │
  │   │         Both signals or high-confidence one? → ROOT CAUSE: Schema incompatibility
  │   │         One signal weak? → Escalate to throughput analysis
  │   │
  │   └─ NO  → No schema changes; proceed to throughput
  │
  ├─► [STEP 3] Throughput bottleneck?
  │   Is producer rate > (partition count × per-partition throughput capacity)?
  │   AND is consumer lag monotonically growing over the last 30 min?
  │   AND sampled messages show NO deserialization errors?
  │   │
  │   ├─ ALL YES → ROOT CAUSE: Throughput bottleneck / partition under-provisioned
  │   │             Note: requires horizontal scaling (more partitions) or rate shedding
  │   │
  │   ├─ Producer rate high, BUT lag fluctuating (not monotonic) → Consumer side issue
  │   │  (GC pauses, network hiccup, rebalance). Investigate consumer logs.
  │   │
  │   └─ Producer rate normal or low → Proceed to consumer application
  │
  ├─► [STEP 4] Consumer application fault?
  │   Lag is growing but throughput/schema are clean?
  │   │
  │   ├─ Check consumer logs for:
  │   │  • Poison pills (messages that crash every deserialization attempt)
  │   │  • Infinite retry loops (lock contention, external service timeout)
  │   │  • Processing stalls (application logic blocked on I/O)
  │   │
  │   └─ ROOT CAUSE: Consumer application issue (requires code/config fix)
  │
  └─► Cross-cluster blast radius (parallel check)
       Is consumer group absent from dev/UAT clusters? → Production-only impact
       Does impact propagate to downstream topics? → Blast radius = downstream topics
```

---

## Evidence Standards

### Throughput Bottleneck Requires ALL of:
- Producer rate (msg/s) > calculated capacity (partitions × per-partition limit)
- Consumer lag monotonically increasing over 30+ minutes (not fluctuating)
- No schema errors detected in sampled messages
- Partition count < recommended for throughput (e.g., < 6 for 120 msg/s)

### Schema Incompatibility Requires AT LEAST TWO of:
- Schema version changed in consumed topic within lag window
- Compatibility mode is NONE or FORWARD (breaking)
- Sampled messages show empty/null fields inconsistent with schema defaults
- Consumer committed offset is stalled while producer offset advances
- Consumer logs contain Avro deserialization exceptions (if logs are available)

### Metric Discrepancy Resolution Requires:
- Message timestamps (not inferred from error rates)
- Alert timestamp from incident metadata
- Message offset/timestamp correlation to determine if consumer lag represents old or recent messages

---

## Anti-Patterns (What NOT to Do)

❌ Conclude throughput bottleneck from producer rate alone (ignore lag trend, ignore schema)
❌ Explain metric discrepancy as "cache delay" without checking message timestamps
❌ Use single signal (one error in logs, one topology metric) to confirm root cause
❌ Run schema check *after* throughput analysis (reorder; schema check is mandatory second step)
❌ Sample only 1-2 messages and conclude no deserialization problem (need 5+ samples)

---

## Tools to Use at Each Step

| Step | Decision | Lenses Tool | Alternative |
|------|----------|-------------|-------------|
| 1 | Message timestamps | `get_dataset_message_metrics` (sample recent messages with timestamps) | - |
| 2 | Schema registry query | `execute_sql` (query schema versions in MetaStore or catalog) | Read schema diff from code (GitHub) |
| 2 | Compat mode check | `execute_sql` or schema registry API call | Manual registry lookup |
| 3 | Producer rate | `get_dataset_message_metrics` (count messages in last 1h window) | Count topic segment sizes |
| 3 | Partition topology | `get_topic_partitions` | `list_topics` with metadata |
| 4 | Consumer logs | External log system (e.g., Datadog, ELK) | None - logs are primary signal here |
| 5 | Blast radius | `list_topics`, `list_consumer_groups_by_topic` | Grep service code for topic refs |
