#!/usr/bin/env bash
# G3-C host regressions (pinned host Python 3.11, no bytecode, no network).
# Logs: artifacts/g3c/logs/host-*.log ; JUnit: artifacts/g3c/evidence/*.xml
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
EV=artifacts/g3c
LOGS="$EV/logs"
EVID="$EV/evidence"
mkdir -p "$LOGS" "$EVID"
HOSTPY=/root/.local/bin/python3.11
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="src:artifacts/foundation/deps"
FAILED=()

run() {
  local name="$1"; shift
  local log="$LOGS/$name.log"
  echo "=== $name $(date -u '+%Y-%m-%dT%H:%M:%SZ') argv=$*" | tee "$log"
  "$@" >>"$log" 2>&1
  local code=$?
  echo "=== $name EXIT=$code $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$log"
  [ "$code" -eq 0 ] || FAILED+=("$name:$code")
}

run host-g3c-joint "$HOSTPY" -B -m pytest tests/integration/g3c tests/integration/g3_bridge -q \
  --junitxml="$EVID/junit-g3c-joint.xml"
run host-g3c-only "$HOSTPY" -B -m pytest tests/integration/g3c -q \
  --junitxml="$EVID/junit-g3c.xml"
run host-full "$HOSTPY" -B -m pytest tests/ -q --junitxml="$EVID/junit-full.xml"
run host-ruff "$HOSTPY" -B -m ruff check src tests spikes/g3b-trusted-bridge/run_c3
run gates-unit "$HOSTPY" -B -m pytest tests/unit/security/test_gates.py -q \
  --junitxml="$EVID/junit-gates.xml"
run g2-accounting "$HOSTPY" -B -m pytest tests/unit/accounting tests/integration/g2_closure -q \
  --junitxml="$EVID/junit-g2.xml"

{
  echo "HOST_PYTHON_VERSION=$("$HOSTPY" -B -c 'import sys; print(sys.version.split()[0])')"
  echo "PYTEST_VERSION=$("$HOSTPY" -B -m pytest --version 2>&1 | head -1)"
  echo "RUFF_VERSION=$("$HOSTPY" -B -m ruff --version)"
  echo "HEAD=$(git rev-parse HEAD)"
  echo "FINISHED_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  if [ "${#FAILED[@]}" -ne 0 ]; then printf 'HOST_FAILURES=%s\n' "${FAILED[*]}"; else echo "HOST_FAILURES=none"; fi
} | tee "$EV/env/host-regression.txt"
[ "${#FAILED[@]}" -eq 0 ]
