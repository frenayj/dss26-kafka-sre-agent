# shellcheck shell=bash
# GitHub half of the demo scenarios, sourced by each scenario's induce.sh / reset.sh.
#
# When the agent reads real GitHub (GITHUB_MODE=live) the change that breaks
# the cluster has to exist on GitHub too, as a merged pull request, or the
# forensics sub-agent has nothing to find. These helpers merge it (induce) or
# revert it (reset) and then let gitops.py apply what is on main.
#
# Every helper is best-effort: if GitHub is unreachable the caller falls back
# to its local files, so a dead conference network costs realism, not the demo.
#
# Requires: REPO_ROOT, PY (python interpreter) set by the caller.

GH_DIR="${REPO_ROOT}/harness/github_org"

gh_scenario_enabled() {
  "${PY}" "${GH_DIR}/scenario.py" enabled 2>/dev/null
}

# gh_run <log-tag> <scenario.py|gitops.py> args...  - prefixed output, real exit code
gh_run() {
  local tag="$1" script="$2"
  shift 2
  "${PY}" "${GH_DIR}/${script}" "$@" 2>&1 | sed "s/^/[${tag}]   github> /"
  return "${PIPESTATUS[0]}"
}
