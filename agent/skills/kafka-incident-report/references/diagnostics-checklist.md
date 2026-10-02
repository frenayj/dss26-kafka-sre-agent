# Kafka diagnostics checklist

This is the list of signals a Kafka incident report should reference when describing what was happening in the cluster. It serves two purposes:

1. **During Mode 2 (fill from notes)** - when the user gives raw notes, scan this checklist and ask follow-up questions about any signal that's relevant to the symptom but not mentioned. Example: if they describe "consumer lag" but never say what the URP looked like, ask. Replication health is almost always relevant to consumer lag.
2. **During Mode 3 (review a draft)** - use this to check whether the diagnostics snapshot in the draft is complete. Most drafts cover one or two layers (e.g., consumer-side) and skip the others. Flag the gaps.

The checklist is organized by **layer of the stack**. The single most common quality problem with Kafka incident reports is that they describe symptoms at one layer (e.g., consumer lag) without evidence from the layer where the cause actually lived (e.g., broker disk, JVM, network). The point of organizing by layer is to make those gaps visible.

---

## Cluster-level signals

These are the first-pass signals that tell you "is the cluster healthy". Almost every Kafka incident report should reference at least the first three.

- `UnderReplicatedPartitions` per broker - non-zero means some partitions aren't fully replicated. The most fundamental "something is wrong" signal.
- `OfflinePartitionsCount` - non-zero means partitions are unavailable for reads/writes. Always a major incident.
- `ActiveControllerCount` - should be exactly 1 across the cluster. 0 means no controller; >1 means split-brain.
- `UncleanLeaderElectionsPerSec` - non-zero means leadership was promoted to a replica that wasn't in the ISR. This implies **potential data loss**. Always call this out explicitly.
- `PreferredReplicaImbalanceCount` - leadership skew across brokers. Causes hot-spotting.
- `GlobalTopicCount`, `GlobalPartitionCount` - useful for context, especially if topic creation/deletion was involved.
- `LeaderElectionRateAndTimeMs` - elevated rate indicates instability.

## Per-broker signals

When something is wrong, the next question is "which broker(s)?" These signals isolate it.

### Request handling
- `RequestHandlerAvgIdlePercent` - < 20% indicates the broker's request handler threads are saturated. A leading indicator of broker degradation.
- `NetworkProcessorAvgIdlePercent` - < 20% indicates network thread saturation. Often correlates with high client connection counts or large request sizes.
- Request queue size and time-in-queue per request type (Produce, Fetch, Metadata)

### Replication
- `IsrShrinksPerSec` / `IsrExpandsPerSec` per broker - churn indicates instability. A single broker repeatedly leaving and rejoining the ISR is a classic "degraded but not dead" pattern.
- `ReplicaFetcherManager` lag per follower
- `LogFlushRateAndTimeMs` - high flush time is almost always a disk problem.

### JVM & memory
- Heap usage (G1 young/old, or whichever collector), trend over time
- GC pause time (P50, P99, max) - sustained pauses > 200ms cause replication and client timeouts
- GC frequency - frequent short GCs are often more disruptive than infrequent long ones
- Off-heap memory (page cache pressure)

### Disk
- Filesystem free space per data directory
- Disk %util, await, IOPS, throughput
- SMART status / hardware errors
- This is the layer most often missed in postmortems. A broker that's "alive but slow" is almost always disk or GC. If the report doesn't reference disk metrics, ask.

### Network
- Packets per second, errors, retransmits
- Inter-broker bandwidth utilization
- Connection count (especially if approaching ulimits)
- File descriptor count vs limit

### OS
- CPU utilization, load average, run queue depth
- Memory pressure, swap usage (Kafka brokers should not swap)
- `dmesg` for hardware-level errors

## Producer-side signals

When the symptom is on the producer side ("our app can't write"), these are the signals.

- `record-send-rate`, `record-error-rate`, `record-retry-rate` - the trio that tells you whether producers are succeeding, failing, or struggling
- `request-latency-avg`, `request-latency-p99` - end-to-end produce latency from the client
- `buffer-available-bytes`, `buffer-exhausted-records` - if the producer buffer is full, the app is producing faster than the cluster can absorb (or the cluster has slowed)
- `acks` setting and `min.insync.replicas` interaction - with `acks=all`, produce latency is bounded by the slowest in-sync replica. A single slow broker can stall all producers.
- `linger.ms`, `batch.size`, compression - relevant if batching behavior changed
- Idempotence / transactions enabled? (changes failure semantics significantly)

## Consumer-side signals

When the symptom is on the consumer side ("we're behind"), these are the signals.

- `records-lag-max` per consumer group, per partition - the headline consumer-health metric
- `records-consumed-rate`, `bytes-consumed-rate` - is the consumer processing at all?
- `fetch-latency-avg`, `fetch-latency-p99` - broker-side fetch performance
- Rebalance frequency - frequent rebalances often mask the real cause; if a group is rebalancing repeatedly, that's usually the proximate problem
- `commit-rate`, `commit-latency-avg` - slow commits can cascade into rebalances
- `poll-idle-ratio-avg` - low values mean the consumer is processing-bound, not fetch-bound (the application is slow, not Kafka)
- Session timeout, heartbeat interval, max poll interval - misconfiguration of these causes most spurious rebalances

## Topic-level signals

When isolating to a topic or set of topics:

- Replication factor (RF), `min.insync.replicas` (min ISR)
- Partition count and distribution across brokers
- Retention (`retention.ms`, `retention.bytes`) - relevant to disk pressure
- Cleanup policy (`delete` vs `compact`) - compaction issues have their own failure modes
- Segment size, segment age - compaction can stall on stuck segments
- Any recent config changes (use `kafka-configs.sh --describe`)

## Connect / Streams / Schema Registry signals (if applicable)

If the incident involves the broader Kafka ecosystem:

- **Kafka Connect:** task state per connector, restart counts, dead-letter queue depth, source/sink lag
- **Kafka Streams:** state store status, RocksDB metrics, processing lag, repartition topic health
- **Schema Registry:** request rate and error rate, subject/version growth, leader status
- **MirrorMaker 2 / Replicator:** replication lag, consumer offset translation health, heartbeat topic freshness

## Cross-cluster / multi-region (if applicable)

- Inter-cluster replication lag
- Consumer offset sync state
- Network latency between regions
- Failover state and recency of last successful failover test

---

## Common incident patterns and where to look first

| Pattern | Typical headline signal | Layers most likely to reveal the cause |
|---|---|---|
| Under-replicated partitions | `UnderReplicatedPartitions > 0` | Broker disk, GC, network; sometimes broker overload |
| Consumer lag spike | `records-lag-max` rising | Consumer app performance, broker fetch latency, partition hot-spotting, rebalance churn |
| Controller flap | `ActiveControllerCount` toggling | ZK/KRaft latency, network partition, controller JVM |
| Unclean leader election | `UncleanLeaderElectionsPerSec > 0` | Multi-broker failure preceded it; check for correlated broker incidents |
| Produce timeouts / errors | `record-error-rate` up, `request-latency-p99` up | ISR shrink, broker overload, `acks=all` + slow replica, network |
| Disk full | `LogFlushRateAndTimeMs` rising, write failures | Retention misconfig, traffic spike, log compaction stuck |
| Rebalance storm | Consumer group rebalances repeatedly | `max.poll.interval.ms` misconfig, slow consumer processing, deploy churn |
| Hot partition | One partition lagging while others are fine | Key skew at producer, partitioner choice, downstream consumer bottleneck |
| Slow broker (alive but degraded) | `RequestHandlerAvgIdlePercent` low on one broker | Disk, GC, file descriptor pressure, noisy neighbor |

When you see a pattern in the user's notes, prompt for evidence at the layers in the right-hand column. Without that evidence, the RCA section will be shallow.
