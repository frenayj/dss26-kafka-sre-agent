# Blameless writing for Kafka incident reports

The single most important property of a good incident report is that it describes what *systems and processes* did, not what *people* failed to do. This isn't softness or political correctness - it's accuracy. The reason an alert was missed is almost never that the on-call is bad at their job; it's almost always that the alert was noisy, the runbook was wrong, the rotation was overloaded, or the signal was at the wrong layer. Writing those structural causes down is what produces durable fixes. Writing "Alice should have noticed sooner" produces nothing.

This guide gives concrete rewrite patterns. Apply them when drafting Mode 2 reports, and use them as the checklist when reviewing drafts in Mode 3.

---

## The core test

Before any sentence that describes a human action or decision, ask:

> If the same person had a different name and were equally competent, well-rested, and well-intentioned, would the sentence still describe the same problem?

If yes, the sentence is structural. If no - if it only makes sense because of who that specific person is - rewrite it. The structural version is almost always more useful.

---

## Common rewrite patterns

### Pattern 1: "X didn't notice" → "the signal was at the wrong layer / the alert was missing"

**Before:** "The on-call engineer didn't notice the broker disk was failing for 8 minutes."

**After:** "Disk write latency began climbing at 14:02 but no alert existed for that signal. The first page fired at 14:11 when the symptom propagated up to `UnderReplicatedPartitions`. The 9-minute gap is a detection-layer problem - see action item #2 (add disk latency alerting)."

The first version blames a person for not noticing something that wasn't being shown to them. The second version locates the actual problem (no alert for the cause-layer signal) and produces a concrete fix.

### Pattern 2: "X ran the wrong command" → "the tooling allowed a foot-gun"

**Before:** "The on-call accidentally ran the partition reassignment against the wrong cluster."

**After:** "The partition reassignment was executed against `prod-kafka-eu-1` instead of the intended `staging-kafka-eu-1`. `kafka-reassign-partitions.sh` does not visually distinguish prod from staging clusters at invocation time, and the two cluster names differ by only one segment. Action item #4 adds a confirmation prompt for production clusters."

If the system makes a mistake easy to make, the mistake will eventually be made by someone. Naming the system property is what fixes it.

### Pattern 3: "X should have escalated sooner" → "the escalation policy was unclear"

**Before:** "The IC should have escalated to the platform team sooner."

**After:** "The runbook does not specify when to engage the platform team during a broker-degradation incident. The IC made a reasonable judgment call but engagement was 22 minutes later than ideal. Action item #5 adds explicit escalation triggers to the runbook (e.g., 'engage platform team within 10 minutes if URP > 0 sustained for 5 minutes')."

"Should have" is almost always a sign that an unwritten expectation existed. Write it down.

### Pattern 4: "X misconfigured Y" → "the default was wrong / the config wasn't validated"

**Before:** "The engineer set `min.insync.replicas=1` on the new topic by mistake."

**After:** "The new topic was created with `min.insync.replicas=1`. Our durability policy requires `min.insync.replicas=2` for production topics, but this is enforced only by convention - there is no automated check at topic creation time. Action item #3 adds policy-as-code validation via a custom AdminClient interceptor."

A configuration that can be wrong, will be wrong. The fix is at the validation layer, not at the human layer.

### Pattern 5: "X panicked / made a mistake under pressure" → "the runbook didn't cover this"

**Before:** "Under time pressure, the responder ran `kafka-leader-election.sh` with the wrong flag, which prolonged the incident by 6 minutes."

**After:** "The responder used `--election-type UNCLEAN` instead of `PREFERRED`. The runbook for 'demote a single broker' exists but does not include the explicit `kafka-leader-election.sh` invocation, leaving the operator to construct it from memory during an active SEV2. Action item #6 adds the exact command to the runbook with a 'copy-paste verified' note."

Stress is not a failing of the responder; it's a fact of incidents. Treat it as a given and design around it.

### Pattern 6: "X forgot to" → "the process didn't prompt for"

**Before:** "We forgot to update the status page until 30 minutes in."

**After:** "Status page updates are a manual responsibility of the IC. During a fast-moving SEV2 with one IC handling both technical response and comms, the comms update slipped to 30 minutes. Action item #7 adds an auto-generated reminder to the IC checklist 10 minutes after incident declaration."

Memory and attention are limited resources during an incident. The fix is to offload them to the system.

---

## Phrases to watch for

When reviewing a draft, search (literally or mentally) for these phrases. They almost always indicate a blame-shaped sentence that needs rewriting:

- "should have" - implies an unwritten expectation
- "forgot to" - implies memory was load-bearing
- "didn't notice" - implies attention was load-bearing
- "made a mistake" - implies the system permitted the mistake
- "by mistake" / "accidentally" - same
- "human error" - almost never a useful root cause on its own
- "lack of attention" - same
- "should be more careful" - same, and additionally not actionable

None of these phrases are forbidden in absolute terms - sometimes a human did genuinely make a mistake, and naming that is honest. But each one is a flag to **also** ask: "what was it about the system that made this mistake possible?" The answer to that question goes in the report.

---

## What blameless does NOT mean

Blameless does not mean evasive. It does not mean refusing to describe what happened. It does not mean pretending the responders performed perfectly. A blameless writeup is often *more* specific about decisions, choices, and timing than a blameful one, because it's safe to be honest when the framing is structural.

Compare:

- **Blameful and vague:** "Mistakes were made during the response."
- **Blameless and specific:** "The responder chose to attempt a rolling restart before isolating broker-3. This added 14 minutes before mitigation. Retrospectively, isolation should have come first; the runbook does not currently rank these two options, and the responder reasonably tried the more conservative action first."

The second version names the decision, names its cost, and names the structural reason it happened. That's the version that produces a better runbook.

---

## When the user is reviewing their own incident

A subtle case: the person you're helping write the report was sometimes also the IC or first responder. They often write more blamefully about themselves than they would about a colleague. Watch for this and gently rewrite. The same standard applies: describe what happened, not who failed.

If the user pushes back ("but I really did mess that up"), acknowledge the feeling without removing the structural framing. The report is not a confessional; it's a document that future on-calls will read to do their job better. The structural version serves them; the self-blaming version doesn't.
