# Full template (SEV1 / SEV2)

This is the canonical full template for high-severity Kafka incidents. Use it verbatim as the starting point. The example data filled in below (the "broker-3 failing SSD" scenario) is there to show the **expected level of detail** for each section - replace it with the actual incident's data, don't strip the structure.

Output everything from the `# Incident Report:` line down. The guidance blockquotes (lines starting with `> **ℹ️ ...**`) should be kept while drafting and removed before publishing - they're prompts for the author, not content for the reader.

---

# Incident Report: [INC-YYYY-MM-DD-###] - <Short, descriptive title>

> **ℹ️ How to use this template**
> Fill in top-down during and after the incident. Sections 1–4 should be readable in under 60 seconds - that's what most reviewers will read. Everything below is for the post-incident review (PIR). Keep it **blameless**: describe what systems and processes did, not who failed. Remove these guidance blockquotes before publishing.

---

## 📌 Page Properties

| | |
|---|---|
| **Incident ID** | INC-YYYY-MM-DD-### |
| **Severity** | SEV1 / SEV2 / SEV3 / SEV4 |
| **Status** | 🔴 Active / 🟡 Mitigated / 🟢 Resolved / 📘 Postmortem Complete |
| **Start time (UTC)** | YYYY-MM-DD HH:MM |
| **Detection time (UTC)** | YYYY-MM-DD HH:MM |
| **Mitigation time (UTC)** | YYYY-MM-DD HH:MM |
| **Resolution time (UTC)** | YYYY-MM-DD HH:MM |
| **Total duration** | Xh Ym (detection → resolution) |
| **Customer impact duration** | Xh Ym |
| **Incident Commander** | @name |
| **Author(s)** | @name, @name |
| **Reviewers** | @name (SRE lead), @name (Platform lead) |
| **Affected clusters** | `prod-kafka-eu-1`, `prod-kafka-us-1` |
| **Affected topics / consumer groups** | `orders.events`, `payments-consumer-group` |
| **Tags** | `kafka`, `replication`, `disk`, `controller`, `consumer-lag` |
| **Related tickets** | JIRA-5821, JIRA-5822 |

---

## 1. TL;DR

> **ℹ️ Two to four sentences. What broke, who was impacted, what we did, current state. A reviewer should be able to read only this section and know whether to read further.**

On `<date>` between `<start>` and `<end>` UTC, the `<cluster>` Kafka cluster experienced `<symptom>` caused by `<trigger>`. This resulted in `<customer impact>` affecting `<X>` consumers / `<Y>` topics. The incident was mitigated by `<action>` and fully resolved by `<action>`. No data loss occurred / `<N>` messages were lost.

---

## 2. Impact

### Customer-facing impact
- **Users affected:** `<number / %>` of `<service>` users
- **Services degraded:** `<list>`
- **User-visible symptoms:** `<e.g., delayed order confirmations, failed payment notifications>`
- **Data loss:** None / `<N>` messages on `<topic>` (partition `<P>`, offsets `<X>`–`<Y>`)
- **Data correctness:** No correctness issues / `<details>`

### SLO impact

| SLO | Target | Observed | Error budget consumed |
|---|---|---|---|
| Producer P99 end-to-end latency | < 500ms | 4.2s peak | 18% of monthly budget |
| Consumer freshness (lag < 30s) | 99.9% | 97.4% during incident | 22% of monthly budget |
| Message delivery (durability) | 99.999% | 99.9998% | 4% of monthly budget |

### Business impact
- **Revenue / cost:** `<$ estimate or "negligible">`
- **Contractual / regulatory:** `<e.g., breached <X> contract SLA, customer credits owed>`
- **Reputation:** `<e.g., 12 support tickets, 3 customer escalations, social media mentions>`

---

## 3. Timeline (UTC)

> **ℹ️ Use 24h UTC for all timestamps. Include events from the system, humans, and external dependencies. Tag each row with type for easy scanning.**

| Time (UTC) | Type | Event |
|---|---|---|
| 14:02 | 🟢 Trigger | Broker-3 disk write latency starts climbing (background, not yet alerted) |
| 14:11 | 🔴 Symptom | `UnderReplicatedPartitions` crosses 0 → 47 on `prod-kafka-eu-1` |
| 14:12 | 🚨 Alert | PagerDuty: `kafka_under_replicated_partitions > 0` fires |
| 14:13 | 👤 Response | On-call SRE @alice acknowledges page |
| 14:18 | 👤 Response | Incident declared SEV2; @bob joins as IC |
| 14:22 | 🔎 Diagnosis | ISR shrink on `orders.events` partitions traced to broker-3 |
| 14:25 | 🔎 Diagnosis | `iostat` shows broker-3 disk await > 800ms; suspect failing disk |
| 14:31 | 🛠️ Action | `kafka-reassign-partitions` initiated to move leadership off broker-3 |
| 14:38 | 🟡 Mitigation | Broker-3 demoted; URP returns to 0; consumer lag begins draining |
| 14:42 | 💬 Comms | Status page updated; customer comms drafted |
| 15:05 | 🟢 Resolution | Consumer lag back within SLO; broker-3 gracefully stopped |
| 15:30 | 📋 Wrap | Incident closed; PIR scheduled |

---

## 4. Status & Action Items Summary

| # | Action | Owner | Priority | Due | Status | Ticket |
|---|---|---|---|---|---|---|
| 1 | Replace failing disk on broker-3 | @carol | P0 | 2026-05-20 | 🟢 Done | JIRA-5821 |
| 2 | Add alert on disk write latency P99 > 100ms | @alice | P1 | 2026-05-26 | 🟡 In progress | JIRA-1235 |
| 3 | Auto-quarantine brokers with sustained high disk latency | @bob | P2 | 2026-06-10 | ⚪ Todo | JIRA-1236 |
| 4 | Runbook: leadership migration off a degraded broker | @alice | P1 | 2026-05-28 | ⚪ Todo | JIRA-1237 |
| 5 | Tabletop exercise: silent disk degradation scenario | @dan | P2 | 2026-06-15 | ⚪ Todo | JIRA-1238 |

---

## 5. Detection

- **How detected:** `<Alert / Customer report / Dashboard / Synthetic check>`
- **Detecting signal:** `kafka_under_replicated_partitions` Prometheus alert
- **Time to detect (TTD):** `<incident start → first alert>` - `9 minutes`
- **Was this the right signal?** `<Yes / No - explain>`
- **Could we have detected earlier?** Yes. Disk write latency began degrading at 14:02 but no alert existed for that metric. **→ Action Item #2**

---

## 6. Response

- **Time to acknowledge (TTA):** 1 minute
- **Time to engage IC:** 6 minutes
- **Escalations needed:** None / `<list>`
- **External vendor engagement:** None / `<vendor + ticket>`
- **Communication channels used:** `#incident-2026-05-19`, status page, customer email
- **Customer comms sent:** Status page update at 14:42, follow-up at 15:30

---

## 7. Root Cause Analysis

### Trigger
The proximate event that started the incident.

> Broker-3's data disk (`/var/lib/kafka/data`) began experiencing elevated write latency due to a developing hardware fault on a single SSD in the RAID array.

### Root cause(s)
The underlying conditions that allowed the trigger to cause impact.

> 1. The RAID controller did not eject the degraded disk; it remained in service with high error-correction overhead, causing per-write latency to climb without triggering hardware alerts.
> 2. Kafka's `replica.lag.time.max.ms` was set to the default (30s), but our SLO requires faster ISR shrink detection. The broker remained in the ISR for too long, masking the issue.
> 3. We had no alert on disk-level latency, only on Kafka-level symptoms (URP), which lag the underlying cause by several minutes.

### 5 Whys
1. **Why did consumers experience lag?** Replication to broker-3 stalled, causing producers with `acks=all` to slow.
2. **Why did replication stall?** Broker-3 could not flush log segments fast enough.
3. **Why couldn't it flush?** Disk write latency was >800ms, far above the normal <5ms.
4. **Why was disk latency so high?** A failing SSD in the RAID-10 array was performing repeated error correction.
5. **Why didn't we catch the failing SSD earlier?** No proactive monitoring of disk-level latency or SMART attributes feeding into our alerting; we relied on Kafka-level symptoms only.

### Contributing factors
- Recent capacity changes had pushed broker-3 to ~75% disk utilization, making it more sensitive to per-IO latency.
- The runbook for "degraded broker" assumed full broker failure, not a slow-but-alive broker.
- `min.insync.replicas=2` with RF=3 meant one slow broker stalled producers using `acks=all`.

---

## 8. Kafka Diagnostics Snapshot

> **ℹ️ Capture the cluster state at the time of the incident. Paste graph screenshots and link to dashboards. Future-you will thank present-you.**

### Cluster state
- **Cluster:** `prod-kafka-eu-1`
- **Version:** Kafka 3.7.0, KRaft mode
- **Brokers:** 9 (3 controller-eligible)
- **Topics affected:** `orders.events` (60 partitions, RF=3), `payments.events` (30 partitions, RF=3)

### Key metrics during incident

| Metric | Normal | At incident peak | Notes |
|---|---|---|---|
| `UnderReplicatedPartitions` | 0 | 47 | All on broker-3 |
| `OfflinePartitionsCount` | 0 | 0 | No partitions went offline |
| `ActiveControllerCount` | 1 | 1 | No controller flapping |
| `UncleanLeaderElectionsPerSec` | 0 | 0 | Durability preserved |
| `IsrShrinksPerSec` | ~0 | 12 | Concentrated on broker-3 |
| `RequestHandlerAvgIdlePercent` (broker-3) | >70% | <5% | Handler exhaustion |
| `NetworkProcessorAvgIdlePercent` (broker-3) | >80% | 60% | OK |
| Produce P99 latency | 45ms | 4,200ms | `acks=all` callers worst-hit |
| Consumer max lag (records) | <10k | 2.3M | `payments-consumer-group` |
| Disk write await (broker-3) | <5ms | 870ms | Hardware-level signal |
| Disk %util (broker-3) | <40% | 99% | Saturated |
| GC pause (broker-3, G1 old) | <100ms | 180ms | Within tolerance |

### Logs & evidence
- **Broker-3 server.log excerpt:** [link]
- **Controller log:** [link]
- **GC log:** [link]
- **`iostat`, `dmesg`, RAID controller log:** [link]
- **Grafana snapshot:** [link]

---

## 9. Mitigation & Resolution

### Mitigation (what stopped the bleeding)
1. Triggered preferred-leader election to move partition leadership off broker-3:
   ```bash
   kafka-leader-election.sh --bootstrap-server <...> \
     --election-type PREFERRED --all-topic-partitions
   ```
2. Initiated partition reassignment to move replicas off broker-3:
   ```bash
   kafka-reassign-partitions.sh --bootstrap-server <...> \
     --reassignment-json-file move-off-broker3.json --execute
   ```
3. Gracefully stopped broker-3 once URP returned to 0.

### Permanent fix
- Replaced failing SSD; rebuilt RAID array; reintroduced broker-3 after a clean replay.
- Tuned `replica.lag.time.max.ms` from 30s to 10s on this cluster (see ADR-0042).
- Added disk-latency alerting (see action item #2).

### Verification
- `UnderReplicatedPartitions = 0` sustained for 1 hour post-resolution.
- Consumer lag for `payments-consumer-group` back under 5s.
- Synthetic producer/consumer canary green for 24h.
- No `acks=all` produce errors in the following 24h window.

---

## 10. What Went Well

- TTA was 1 minute; on-call rotation worked as designed.
- IC role was assumed quickly and incident communication was clean.
- No data loss; durability guarantees held end-to-end.
- The `kafka-reassign-partitions` runbook was accurate and got us to mitigation fast.

## 11. What Didn't Go Well

- TTD was 9 minutes; we detected at the symptom layer, not the cause layer.
- Customer comms went out 30 minutes after detection - too slow for SEV2.
- The on-call had to manually craft the reassignment JSON; this should be tooled.
- The Slack incident channel was created reactively; not auto-created on page.

## 12. Where We Got Lucky

- Only one broker was affected. Had the same SSD model been failing across multiple brokers, we'd have hit `OfflinePartitionsCount > 0` and likely a SEV1.
- The incident happened during business hours in EU; the team was already online.
- `min.insync.replicas=2` held; if `acks=all` producers had not been retrying, we'd have seen produce failures, not just latency.

---

## 13. Lessons Learned

1. **Detect at the cause layer, not just the symptom layer.** Kafka-level metrics (URP, ISR) tell us *something is wrong*, but disk-, network-, and JVM-level metrics tell us *what is wrong*. We need both, with the lower-level alerts feeding the same paging system.
2. **"Slow" is a failure mode.** Our runbooks treated brokers as binary (up/down). A slow broker can be worse than a down one because the cluster keeps trying to use it. We need a "degraded broker" playbook.
3. **`acks=all` + `min.insync.replicas=2` couples producer latency to the slowest in-sync replica.** This is the right durability choice, but it means slow brokers are tail-latency amplifiers. Documented as a known trade-off in our platform docs.
4. **Auto-create the incident channel on page.** Manual channel creation cost us ~5 minutes of coordination overhead.

---

## 14. Appendix

### References & further reading
- Google SRE Book - Chapter 15: Postmortem Culture
- Atlassian Incident Management Handbook
- PagerDuty Incident Response Documentation
- Confluent: "Optimizing Kafka for Reliability"
- Internal runbooks: [link to runbook index]
- Internal SLO definitions: [link]

---

*This template is maintained by the Kafka SRE team. Suggest improvements via PR to `<repo>/templates/incident-report.md`.*
