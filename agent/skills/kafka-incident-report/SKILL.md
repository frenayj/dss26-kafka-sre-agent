---
name: kafka-incident-report
description: Write Kafka SRE incident reports, postmortems, and post-incident reviews (PIRs) as Confluence-ready Markdown, using blameless Google SRE conventions and Kafka-specific operational signals (URP, ISR, controller, consumer lag, broker health, GC, disk). Use whenever the user mentions a Kafka incident, outage, broker failure, under-replicated partitions, consumer lag spike, controller flap, unclean leader election, ISR shrink, rebalance storm, or any production Kafka issue they want to document. Also use when asked to write up, document, summarize, or do a postmortem on a Kafka event, fill in incident timelines from raw notes or chat logs, generate action items, or review draft writeups for blameless framing and completeness - including when the user just says "help me write up what happened with Kafka" without the words "incident report".
---

# Kafka Incident Report Writer

This skill produces incident reports for Kafka SRE teams that are (a) fast to fill in during or after an incident, (b) fast to skim during review, and (c) grounded in Kafka-specific operational signals - not generic SRE platitudes.

The output is always a single Markdown file ready to paste into Confluence Cloud (which accepts pasted Markdown natively). The structure puts the most important information first so that a reviewer who reads only the top 60 seconds of the page walks away knowing what happened, who it hit, what was done, and what's being followed up.

## When this skill applies

Reach for this skill whenever the user is documenting something that happened in a Kafka cluster - explicit asks ("write a postmortem", "incident report for the outage"), implicit asks ("help me write up what happened last night", "I need to document the broker-3 thing for the review meeting"), or partial work ("here are my notes from the incident, can you turn this into a report"). Also apply it when reviewing a draft someone else wrote, since blameless framing and Kafka-specific diagnostic completeness are the two things drafts most often get wrong.

If the user is asking for *runbooks*, *on-call training material*, or *general Kafka troubleshooting advice* (i.e., not documenting a specific event that occurred), this skill is not the right fit - answer directly instead.

## The three modes

Figure out which mode the user is in before generating anything. Asking one short clarifying question is fine; making three assumptions and producing the wrong artifact wastes their time.

### Mode 1 - Generate a blank template

The user wants a clean template they can fill in themselves, either right now during an active incident or to keep on hand for the team. Pick the right size:

- **SEV1 / SEV2** → use `references/template-full.md` verbatim as the output. Don't trim sections; this template is deliberately complete so the team can't accidentally skip a section under time pressure.
- **SEV3 / SEV4** → use `references/template-lightweight.md`. The full template is overkill for low-severity events and creates friction that leads to writeups not getting done at all.

If the user hasn't said which severity, ask. Don't guess - the wrong template size is the most common reason a writeup never gets finished.

Output the file to `/mnt/user-data/outputs/` with a clear name (e.g., `kafka-incident-report-template.md` or `kafka-incident-report-INC-2026-05-19-001.md` if they've given an incident ID).

### Mode 2 - Fill from raw notes, logs, or chat scrollback

The user has the messy reality (Slack thread, IC notes, Grafana screenshots, broker logs, a brain dump) and wants a structured writeup. This is the most common real-world ask.

Workflow:

1. **Read everything they gave you first.** Don't start drafting until you've understood the shape of the incident - what broke, when, what was tried, what worked. If critical information is missing, ask for it in one batch rather than drip-feeding questions.
2. **Pick the template** (`template-full.md` or `template-lightweight.md`) based on severity.
3. **Fill top-down, in this order**: page properties → TL;DR → impact → timeline → action items. Stop after the timeline and show the user what you have so far if the incident is complex - they can correct course before you generate sections that depend on accuracy upstream.
4. **For the Diagnostics Snapshot section**, consult `references/diagnostics-checklist.md` and prompt the user for any obviously-missing Kafka-specific signals (e.g., they mentioned "consumer lag" but didn't say what the URP looked like - ask). The whole point of having Kafka context in this skill is that you know what questions to ask.
5. **For Root Cause Analysis**, drive the 5 Whys yourself by asking follow-up questions, rather than writing a shallow RCA from incomplete information. If the user genuinely doesn't know the root cause yet, label it "Under investigation" and put a placeholder action item to come back to it - don't invent causes.
6. **Apply blameless framing throughout.** Before writing any sentence that names a person or describes a decision, read `references/blameless-writing.md` for the rewrite patterns. Common slip: "the on-call didn't notice the alert for 8 minutes" → "the alert fired at 14:11 and was acknowledged at 14:19; the team is investigating why the 8-minute gap occurred (action item #3)".

### Mode 3 - Review an existing draft

The user pastes a draft (theirs or someone else's) and wants feedback. Run it through this checklist and produce a structured review:

- [ ] **Top of page is skimmable**: TL;DR exists and is 2–4 sentences; impact is quantified; status/severity/IC are visible without scrolling
- [ ] **Timeline uses UTC**, has timestamps for trigger / detection / first response / mitigation / resolution, and distinguishes system events from human actions
- [ ] **Detection metrics are at the right layer**: the writeup distinguishes the symptom signal (e.g., URP) from the cause signal (e.g., disk latency). If only symptom-level metrics appear, flag this - it's the most common gap.
- [ ] **Root cause is structural, not behavioral**: "engineer ran the wrong command" is not a root cause; "we had no guardrails preventing the command from being run in prod" is. Push back on RCAs that point at people.
- [ ] **Action items have owners, priorities, due dates, and ticket links.** Action items without all four tend to evaporate.
- [ ] **Action items address the structural cause, not just the trigger.** Replacing the failing disk fixes this incident; adding alerting on disk latency prevents the next one.
- [ ] **"What went well / didn't / got lucky" section is present.** The "got lucky" subsection is the single best predictor of whether the team will catch the next incident - push for it specifically if absent.
- [ ] **Kafka diagnostics snapshot is complete.** Use `references/diagnostics-checklist.md` to identify missing signals.
- [ ] **No blameful language.** Spot-check against `references/blameless-writing.md`.

Deliver the review as a prioritized list of concrete edits, not generic praise. If the user wants, also produce a revised version of the draft incorporating the changes.

## Core principles (apply across all modes)

**Top-down readability.** Most reviewers will only read the top of the page. Sections 1–4 (page properties, TL;DR, impact, timeline + action items summary) must stand alone as a complete executive view. If a senior leader reads only those four sections, they should walk away correctly informed.

**Blameless framing.** Describe what *systems and processes* did, not what *people* failed to do. This isn't softness - it's accuracy. The reason an alert was missed is almost never that the on-call is bad at their job; it's almost always that the alert was noisy, the runbook was wrong, the rotation was overloaded, or the signal was at the wrong layer. Naming the structural cause is what produces durable fixes. See `references/blameless-writing.md` for concrete patterns.

**Kafka-specific depth, not generic SRE filler.** A Kafka incident report that doesn't reference URP, ISR, the controller, consumer lag, broker resource saturation, GC, or disk health is suspicious. These are the layers where Kafka actually fails, and the writeup needs to show evidence at those layers. The diagnostics checklist exists to make sure none of them get skipped.

**Distinguish trigger, root cause, and contributing factors.** The trigger is what kicked it off (a deploy, a disk failure, a traffic spike). The root cause is the underlying condition that allowed the trigger to cause impact (no canary, no rate limiting, no disk alerting). Contributing factors made it worse (low headroom, a stale runbook, a pager rotation gap). Conflating these three produces shallow RCAs.

**Action items must address the root cause.** If every action item is about the trigger ("replace the disk", "roll back the deploy"), the writeup hasn't done its job. The good action items address why the trigger turned into an incident: better signals, better guardrails, better runbooks, better defaults.

## Severity rubric (quick reference)

| Severity | Definition | Kafka examples |
|---|---|---|
| **SEV1** | Critical: data loss risk, cluster-wide outage, or major customer-facing impact | Multiple brokers down simultaneously, unclean leader elections with data loss, controller unavailable, full disk on majority of brokers |
| **SEV2** | High: partial degradation, SLO breach, single-AZ or single-cluster impact | Sustained URP > 0, consumer lag breaching SLO, single broker failure with replication impact, produce error rate above threshold |
| **SEV3** | Medium: minor degradation or risk without immediate customer impact | Elevated GC pauses, capacity headroom concern, single failed canary, isolated topic with stale data |
| **SEV4** | Low: cosmetic or non-urgent | Dashboard error, non-critical alert flapping, minor metric drift |

When severity is ambiguous, the rule of thumb: if customers noticed or could have noticed, it's at least SEV2; if data integrity was at risk, it's SEV1.

## Output conventions

- Always produce a single Markdown file at `/mnt/user-data/outputs/<filename>.md`. After creating it, call `present_files` so the user can download it.
- Use standard Markdown that renders cleanly in Confluence Cloud: pipe tables, fenced code blocks with language tags, task lists, blockquotes for callouts, emoji status indicators (🔴 🟡 🟢) since they render in both Confluence and chat tools.
- Do not wrap the entire report in a code block or fence - the user wants to paste it as content, not view it as source.
- Use UTC for every timestamp, in `YYYY-MM-DD HH:MM` format. Never mix timezones within a single report.
- Use placeholder syntax like `<cluster-name>` or `[link]` for things the user still needs to fill in, so the gaps are visually obvious.
- File naming: if the user has an incident ID, use `kafka-incident-report-<ID>.md`. Otherwise use `kafka-incident-report-<YYYY-MM-DD>.md`. For blank templates, `kafka-incident-report-template.md`.

## Reference files

Load these on demand - they're not needed for every invocation:

- **`references/template-full.md`** - The complete SEV1/SEV2 template. Use this verbatim as the starting point in Modes 1 and 2 for high-severity incidents. Contains all sections including the diagnostic checklist appendix.
- **`references/template-lightweight.md`** - Trimmed template for SEV3/SEV4. Removes appendices and collapses the "what went well/didn't/lucky" trio to a single section. Use when the full template would create more friction than value.
- **`references/diagnostics-checklist.md`** - The full set of Kafka-specific signals organized by layer (cluster, broker, producer, consumer, topic). Consult during Mode 2 to prompt for missing diagnostics, and during Mode 3 to check a draft for gaps.
- **`references/blameless-writing.md`** - Style guide with before/after rewrites for common blameful phrasings. Consult whenever drafting RCA, lessons learned, or any section that describes human decisions or actions.
