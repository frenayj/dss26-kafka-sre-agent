# Kafka SRE Agent - demo lifecycle. `make help` lists every target.
#
#   make up             # boot the stack, then open http://localhost:8080
#   make scenario       # reset -> break the cluster -> run the agent from the CLI
#   make down
#
# Scenario targets take SCENARIO=<folder under harness/scenarios/>
# (default consumer-lag).

COMPOSE_FILE := harness/stack/docker-compose.yml
ENV_FILE     := .env
COMPOSE      := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE)
VENV         := .venv
PYTHON       := $(VENV)/bin/python

# Opt-in alternative host ports, to run next to another Lenses/Kafka stack:
# `cp ports.parallel.sample ports.parallel`. Its presence activates it for
# compose (as a second --env-file) and for every script started from here.
PARALLEL_PORTS := ports.parallel
ifneq ($(wildcard $(PARALLEL_PORTS)),)
COMPOSE := docker compose --env-file $(ENV_FILE) --env-file $(PARALLEL_PORTS) -f $(COMPOSE_FILE)
include $(PARALLEL_PORTS)
# Export exactly what the file defines: `export` on an undefined variable
# would hand the scripts an empty string instead of their default.
export $(shell sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' $(PARALLEL_PORTS))
endif

HOST_PORT_PHOENIX ?= 6006

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@echo "Kafka SRE Agent"
	@echo
	@echo "Usage: make <target>"
	@awk 'BEGIN {FS = ":.*?## "} \
		/^# === / {section=$$0; sub(/^# === /, "", section); sub(/ ===$$/, "", section); \
		           printf "\n\033[1m%s\033[0m\n", section; next} \
		/^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)

# === Stack ===

.PHONY: up
up: ## Build and start the stack, then seed it (idempotent)
	@# Two phases: lenses-mcp and agent-server need a Lenses service account,
	@# which can only be minted once HQ is running.
	$(COMPOSE) up -d --build lenses-hq
	@$(MAKE) --no-print-directory provision
	$(COMPOSE) up -d --build --remove-orphans
	@$(MAKE) --no-print-directory phoenix-costs
	@echo "[up] the seeder container is creating topics, schemas and the datagen producer: $(COMPOSE) logs -f seeder"
	@echo "[up] dashboard: http://localhost:$${HOST_PORT_UI:-8080}   Phoenix: http://localhost:$(HOST_PORT_PHOENIX)"

.PHONY: down
down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down --remove-orphans

.PHONY: clean
clean: ## Stop the stack AND delete its volumes - full reset
	$(COMPOSE) down -v --remove-orphans

.PHONY: agent-up
agent-up: ## Rebuild and recreate only the agent server and UI (after a code or *_MODE change)
	$(COMPOSE) up -d --build --no-deps agent-server ui

.PHONY: gateway-up
gateway-up: ## Recreate only the LLM gateway (after a provider key or agent/gateway/litellm.yaml change)
	$(COMPOSE) up -d --no-deps --force-recreate llm-gateway

.PHONY: ps
ps: ## Status of the compose services
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail the compose logs
	$(COMPOSE) logs -f --tail=100

.PHONY: provision
provision: ## Mint the Lenses service account the agent and MCP use (idempotent)
	@LENSES_HQ_URL=$${LENSES_HQ_URL:-http://localhost:$${HOST_PORT_HQ:-9991}} \
	  python3 harness/seed/provision_service_account.py --write

.PHONY: phoenix-costs
phoenix-costs: ## Register model pricing in Phoenix so traces show cost (idempotent)
	@HOST_PORT_PHOENIX=$(HOST_PORT_PHOENIX) python3 harness/seed/seed_phoenix_costs.py || \
	  echo "[phoenix-costs] failed (see above) - traces will show no cost; re-run 'make phoenix-costs'"

.PHONY: preflight
preflight: ## Check the env file, services and gateway before a run
	harness/stack/preflight.sh

# === Scenarios (SCENARIO=consumer-lag by default; see harness/scenarios/) ===

SCENARIO  ?= consumer-lag
SCENARIOS := $(sort $(notdir $(patsubst %/,%,$(dir $(wildcard harness/scenarios/*/scenario.json)))))
# How long after induce the alert is worth paging: the scenario's page_delay_s.
PAGE_DELAY_S ?= $(shell python3 -m harness.scenarios get $(SCENARIO) page_delay_s)

.PHONY: scenarios
scenarios: ## List the scenarios
	@python3 -m harness.scenarios list

.PHONY: ops
ops: ## Operator console: live status and a button per target below, at http://localhost:8080/#/ops
	python3 harness/ops/ops_server.py

.PHONY: induce
induce: ## Break the cluster for SCENARIO (and merge its culprit PR)
	harness/scenarios/$(SCENARIO)/induce.sh

.PHONY: reset
reset: ## Restore a healthy cluster: every scenario's reset (idempotent)
	@for s in $(SCENARIOS); do harness/scenarios/$$s/reset.sh || exit 1; done

.PHONY: run
run: $(PYTHON) ## Run the agent from the terminal on SCENARIO's alert
	python3 -m harness.scenarios incident $(SCENARIO) | $(PYTHON) -m agent.cli

.PHONY: scenario
scenario: reset induce run ## reset -> induce -> run, from the terminal

# === Live PagerDuty (PAGERDUTY_MODE=live, see docs/going-live.md) ===

.PHONY: pd-setup
pd-setup: ## Create the demo services, integrations and P1 rule in PagerDuty (idempotent)
	python3 harness/pagerduty/pagerduty_demo.py setup

.PHONY: page
page: ## Page PagerDuty with SCENARIO's alert (after induce)
	python3 harness/pagerduty/pagerduty_demo.py page $(SCENARIO)

.PHONY: pd-resolve
pd-resolve: ## Resolve every open incident on the demo services
	python3 harness/pagerduty/pagerduty_demo.py resolve

.PHONY: live
live: reset pd-resolve induce ## reset -> resolve old pages -> induce -> wait -> page; the open dashboard runs it
	@echo "[live] waiting $(PAGE_DELAY_S)s for $(SCENARIO) to show before paging..."
	@sleep $(PAGE_DELAY_S)
	@$(MAKE) --no-print-directory page

# === GitHub org (maintainers, see docs/github-org.md) ===

GH_ORG ?= $(or $(GITHUB_ORG),dss26-org)

.PHONY: gh-validate
gh-validate: ## Replay every repo's history offline and check every scenario PR applies and reverts
	python3 harness/github_org/seed.py validate

.PHONY: gh-snapshot
gh-snapshot: ## Regenerate the GitHub stub's snapshot from the repo declarations
	python3 harness/github_org/snapshot.py

.PHONY: gh-seed
gh-seed: ## Create the org's teams and repos and push their history (idempotent)
	python3 harness/github_org/seed.py teams
	python3 harness/github_org/seed.py push

.PHONY: gh-rebuild
gh-rebuild: ## DELETE and recreate every repo in the org (drops all PRs). Requires CONFIRM=<org>
	@if [ "$(CONFIRM)" != "$(GH_ORG)" ]; then \
	  echo "Refusing: this deletes every repo in $(GH_ORG). Re-run with CONFIRM=$(GH_ORG)"; exit 1; fi
	python3 harness/github_org/seed.py push --rebuild

.PHONY: gh-warmup
gh-warmup: ## Merge the day's decoy PRs (30+ minutes before a live run, so the timeline looks natural)
	python3 harness/github_org/scenario.py warmup

.PHONY: gh-status
gh-status: ## Repos in the org and the state of every scenario PR
	python3 harness/github_org/seed.py status

# === Development ===

.PHONY: venv
venv: $(PYTHON) ## Create .venv with the agent and dev dependencies

$(PYTHON):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r agent/requirements.txt -r requirements-dev.txt

.PHONY: test
test: $(PYTHON) ## Run the Python tests (no stack needed)
	$(PYTHON) -m pytest

.PHONY: lint
lint: $(PYTHON) ## Lint the Python code and the UI
	$(VENV)/bin/ruff check .
	cd ui && pnpm install --frozen-lockfile && pnpm lint
