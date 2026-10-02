# The DSS26 Bank GitHub org

The forensics agent investigates the engineering estate of a fictional
European retail bank: about twenty repos across four tribes, with history
backdated to 2022 by a cast of engineers who also wrote the Confluence
knowledge base (same people, ADRs, postmortems and dates). Everything is
declared in [`harness/github_org/`](../harness/github_org) and reproducible.

You don't need GitHub access to use it. In stub mode (the default) the agent
reads a snapshot of the org,
[`harness/stubs/data/github-dss26-org.json`](../harness/stubs/data), generated
from the same declarations. The live org used in the talk, `dss26-org`, is
private; to run against real GitHub, seed your own copy (below).

| Tribe | Squads (GitHub teams) | Repos |
|---|---|---|
| Cards & Payments | payments-edge, cards-platform, cards-servicing, clearing-settlement | `merchant-gateway`, `fraud-decisioning-svc`, `cards-ci-workflows`, `txn-history-builder`, `merchant-analytics-stream`, `disputes-svc`, `card-lifecycle-svc`, `card-statements-batch`, `clearing-settlement-svc` |
| Financial Crime & Risk | risk-platform, compliance-platform | `fraud-case-management`, `aml-transaction-screening`, `sanctions-screening-svc`, `kyc-onboarding-svc` |
| Customer & Channels | customer-platform, digital-channels | `customer-profile-svc`, `mobile-banking-app`, `internet-banking-web` |
| Core Technology | core-banking, platform-engineering | `core-banking-adapter`, `payments-hub`, `kafka-platform`, `.github-private` (org profile) |

Every repo carries a Backstage `catalog-info.yaml` (owner, PagerDuty
service, topics in and out, consumer group), CODEOWNERS and topics: the
breadcrumbs a human on call would follow. Commit authors are personas on the
reserved `dss26bank.example` domain.

## Where the incident lives

Nothing in the prompts, skills or alerts names these; the agent has to find
them.

| | PI7K3FQ: consumer lag |
|---|---|
| Culprit (merged by `make induce`) | `merchant-gateway`: `amount` becomes a decimal string, `country` is dropped, and the subject's compatibility is set to `NONE` in the pom because the registry refused v2 |
| Set up in the history | the shared schema-compatibility CI job disabled since April (`cards-ci-workflows`), so the culprit's check shows *skipped*; the consumer-side change still an open PR in `fraud-decisioning-svc` |
| Decoys merged the same morning | a `session.timeout.ms` change and a client bump in the paged service, a harmless gateway fix, an ACL change in `kafka-platform`, a consumer tweak in `txn-history-builder` |

A new scenario declares its own culprit and decoys under its name (see
[Adding a scenario](../harness/scenarios/README.md#adding-a-scenario)).

## How it's built

- [`repos/`](../harness/github_org/repos): one module per main repo, plus
  `backdrop.py` for the neighbours that make code search look like a real
  estate. Each declares its commits (author, date, file writes and edits)
  and its scenario PRs.
- [`files/`](../harness/github_org/files): file contents the declarations
  reference.
- [`model.py`](../harness/github_org/model.py),
  [`replay.py`](../harness/github_org/replay.py): the data model, and a
  replay that rebuilds every repo's history locally.
- [`seed.py`](../harness/github_org/seed.py): pushes the org to GitHub.
- [`scenario.py`](../harness/github_org/scenario.py),
  [`gitops.py`](../harness/github_org/gitops.py): merge a culprit or its
  revert, and apply what `main` says to the cluster (used by the induce and
  reset scripts).
- [`snapshot.py`](../harness/github_org/snapshot.py): regenerates the stub's
  snapshot.

After changing a declaration:

```sh
make gh-validate    # offline: replay every repo, check every scenario PR applies and reverts
make gh-snapshot    # refresh the stub's snapshot
```

## Seeding your own org

```sh
gh auth refresh -h github.com -s admin:org,delete_repo   # teams need admin:org
export GITHUB_ORG=<your-org>
make gh-seed        # create the teams and private repos, push their history (idempotent)
make gh-warmup      # 30+ minutes before a run: merge the day's decoy PRs
make induce         # merges the culprit, applies it, breaks the cluster
make reset          # merges the revert, restores the cluster
make gh-status      # what is merged, pending or open
make gh-rebuild CONFIRM=<your-org>   # delete and re-seed every repo (drops all PRs)
```

Then set `GITHUB_MODE=live`, `GITHUB_ORG` and a read-only `GITHUB_TOKEN` for
the agent ([Going live](going-live.md#github)).

The induce and reset scripts write with `GITHUB_SCENARIO_TOKEN`, then
`GH_TOKEN`, then your `gh` login, never the agent's read-only
`GITHUB_TOKEN`. A fine-grained write token needs Contents and Pull requests
read/write on every scenario repo. If GitHub can't be written to, the
scripts say so on their `github>` lines and fall back to applying the local
files: the cluster still breaks, but there's no PR for the agent to find.

**What GitHub can't fake.** Commits can be backdated; pull requests can't:
GitHub stamps them with the wall-clock time, which is why decoys and culprits
are merged on the day rather than seeded. Every PR is opened by the token's
account (the persona stays the commit author, kept by rebase-merging). Code
search takes a few minutes to index a new repo. Each induce/reset cycle adds
a culprit and revert pair; `gh-rebuild` returns the org to a clean history.
