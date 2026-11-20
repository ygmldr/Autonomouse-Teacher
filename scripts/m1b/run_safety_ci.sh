#!/usr/bin/env bash
# B-PR1 safety CI entry point (review P1-3 wiring).
#
# Purpose: run the judge/teacher suite in *safety mode*, where a missing OS
# sandbox or a non-root-principal violation must FAIL the job instead of being
# skipped.  The repository itself does not configure a CI workflow here
# (`.github/workflows` is owned by maintainers/CI owners, see
# docs/M1_B_JUDGE_IMPLEMENTATION.md "CI wiring"); call this script from the
# security job once wired.
#
# Environment:
#   PYTHON                 python executable (default: python3; CI should pass
#                          the venv interpreter explicitly)
#   M1B_REQUIRE_OS_SANDBOX (default 1; missing bwrap => fail, never skip)
#   M1B_REQUIRE_NONROOT_SANDBOX (default 1; root host/uid_map->0 => fail closed)
#
# Usage:
#   PYTHON=/path/to/venv/bin/python ./scripts/m1b/run_safety_ci.sh
#   ./scripts/m1b/run_safety_ci.sh --allow-root-synthetic   # LOCAL ONLY
#
# --allow-root-synthetic sets M1B_REQUIRE_NONROOT_SANDBOX=0 so a root developer
# host can still exercise sandbox/OS tests with synthetic fixtures; it must NOT
# be used by the deployment safety job.  Ordinary unit-test CI may keep the
# default skips via plain `pytest` without this script.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ALLOW_ROOT_SYNTHETIC=0
for arg in "$@"; do
  case "${arg}" in
    --allow-root-synthetic) ALLOW_ROOT_SYNTHETIC=1 ;;
    -h|--help)
      sed -n '2,40p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "unknown argument: ${arg}" >&2
      exit 2
      ;;
  esac
done

export M1B_REQUIRE_OS_SANDBOX=1
if [[ "${ALLOW_ROOT_SYNTHETIC}" -eq 1 ]]; then
  export M1B_REQUIRE_NONROOT_SANDBOX=0
  echo "WARNING: --allow-root-synthetic sets M1B_REQUIRE_NONROOT_SANDBOX=0;" \
       "this is LOCAL synthetic evaluation only, not deployment safety evidence." >&2
else
  export M1B_REQUIRE_NONROOT_SANDBOX="${M1B_REQUIRE_NONROOT_SANDBOX:-1}"
fi

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "python executable not found: ${PYTHON_BIN}" >&2
  exit 2
fi

echo "== B-PR1 safety CI =="
echo "repo:        ${REPO_ROOT}"
echo "git head:    $(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "host:        $(uname -srm 2>/dev/null || echo unknown)  uid=$(id -u)"
echo "python:      ${PYTHON_BIN} ($("${PYTHON_BIN}" --version 2>&1))"
if command -v bwrap >/dev/null 2>&1; then
  echo "bwrap:       $(bwrap --version 2>&1)"
else
  echo "bwrap:       MISSING"
fi
echo "M1B_REQUIRE_OS_SANDBOX=${M1B_REQUIRE_OS_SANDBOX}"
echo "M1B_REQUIRE_NONROOT_SANDBOX=${M1B_REQUIRE_NONROOT_SANDBOX}"
echo

LOG_FILE="$(mktemp -t m1b-safety-ci.XXXXXX.log)"
trap 'rm -f "${LOG_FILE}"' EXIT

set +e
"${PYTHON_BIN}" -m pytest tests/m1_teacher -q -rs 2>&1 | tee "${LOG_FILE}"
STATUS=${PIPESTATUS[0]}
set -e

echo
if [[ "${STATUS}" -ne 0 ]]; then
  echo "SAFETY CI FAILED: pytest exit=${STATUS}" >&2
  exit "${STATUS}"
fi

# The safety job must not silently skip isolation evidence.
if grep -qiE '(^|[^a-z])skipped([^a-z]|$)' "${LOG_FILE}"; then
  echo "SAFETY CI FAILED: suite reported skipped tests (see log above)" >&2
  exit 1
fi
if grep -qE '^[sS]' "${LOG_FILE}"; then
  echo "SAFETY CI FAILED: progress output contains skipped ('s') markers" >&2
  exit 1
fi
if ! grep -qE '[0-9]+ passed' "${LOG_FILE}"; then
  echo "SAFETY CI FAILED: no pytest passed summary found" >&2
  exit 1
fi

echo "SAFETY CI OK: 0 skipped, pytest exit=0"
