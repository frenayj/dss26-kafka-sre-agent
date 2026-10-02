# Lightweight template (SEV3 / SEV4)

For lower-severity incidents - minor degradations, near-misses, single-canary failures, things that didn't reach customer impact but the team still wants to document. The full template is overkill here, and friction kills writeups: if the form is too long, it doesn't get filled in, and the institutional learning is lost.

This version drops the SLO impact table, the full diagnostics matrix, the trio of "what went well / didn't / lucky" sections (collapsed into a single "Reflections" section), and the appendix. It keeps the parts that actually drive learning: what happened, what we did, what we'll change.

Output everything from the `# Incident Report:` line down. Remove the `> **ℹ️ ...**` guidance blockquotes before publishing.

---

# Incident Report: [INC-YYYY-MM-DD-###] - <Short, descriptive title>

## 📌 Page Properties

| | |
|---|---|
| **Incident ID** | INC-YYYY-MM-DD-### |
| **Severity** | SEV3 / SEV4 |
| **Status** | 🟢 Resolved |
| **When (UTC)** | YYYY-MM-DD HH:MM – HH:MM |
| **Duration** | Xm |
| **Author** | @name |
| **Affected clusters** | `<cluster>` |
| **Affected topics / consumer groups** | `<topics>` |
| **Tags** | `kafka`, `<other>` |
| **Related tickets** | JIRA-#### |

---

## 1. Summary

> **ℹ️ Two sentences. What happened, what we did about it. No customer impact for SEV3/SEV4, so no need to dwell on impact framing.**

`<What happened in plain language, plus the resolution.>`

---

## 2. Timeline (UTC)

| Time | Event |
|---|---|
| HH:MM | `<Trigger>` |
| HH:MM | `<Detection>` |
| HH:MM | `<Response>` |
| HH:MM | `<Resolution>` |

---

## 3. Root cause

> **ℹ️ One paragraph. Distinguish the trigger from the underlying cause. If unknown, say "Under investigation" and add an action item to follow up - don't invent.**

`<The underlying reason this happened, in 2–4 sentences.>`

---

## 4. What we did

> **ℹ️ The actions taken to resolve. Include commands or links to PRs where useful.**

- `<Action 1>`
- `<Action 2>`

---

## 5. Reflections

> **ℹ️ One short list. What surprised us, what could have been worse, what we want to remember. This is the section that pays for the cost of writing this report - be honest, not exhaustive.**

- `<Reflection 1>`
- `<Reflection 2>`

---

## 6. Action items

| # | Action | Owner | Priority | Due | Ticket |
|---|---|---|---|---|---|
| 1 | `<action>` | @name | P2 | YYYY-MM-DD | JIRA-#### |
| 2 | `<action>` | @name | P3 | YYYY-MM-DD | JIRA-#### |

---

## 7. Links

- Dashboards: [link]
- Runbook used: [link]
- Slack thread: [link]
