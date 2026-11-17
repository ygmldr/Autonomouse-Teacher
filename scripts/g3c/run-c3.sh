#!/usr/bin/env bash
# G3-C evidence orchestrator: every case runs in the fixed read-only rootfs with
# --network none. Host executes only podman/cp/chmod/sha256/date and the pinned
# host Python for argv/JSON bookkeeping.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
STAGE="$ROOT/artifacts/g3c/stage"
EV="$ROOT/artifacts/g3c"
TRACES="$EV/traces"
LOGS="$EV/logs"
CMDS="$EV/commands.jsonl"
HOSTPY=/root/.local/bin/python3.11
ROOTFS_CANON="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON="e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
mkdir -p "$TRACES" "$LOGS" "$EV/ledger" "$EV/receipts" "$EV/evidence" "$EV/env"
: > "$CMDS"

hash_tree() { tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$1" . | sha256sum | cut -d' ' -f1; }
rootfs_cleanup() {
  for d in src npm out var build-src evidence seed debug; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then rm -f "$ROOTFS/etc/resolv.conf"; fi
}
trap rootfs_cleanup EXIT
test -d "$STAGE" || { echo "STAGE_MISSING: run scripts/g3c/build-stage.sh"; exit 2; }
# Normalise only transient podman mount targets left by an interrupted run.
rootfs_cleanup
ROOTFS_BEFORE="$(hash_tree "$ROOTFS")"
DEPS_BEFORE="$(hash_tree "$DEPS")"
STAGE_HASH="$(hash_tree "$STAGE")"
test "$ROOTFS_BEFORE" = "$ROOTFS_CANON" || { echo "ROOTFS_NOT_CANONICAL_BEFORE=$ROOTFS_BEFORE"; exit 2; }
test "$DEPS_BEFORE" = "$DEPS_CANON" || { echo "DEPS_NOT_CANONICAL_BEFORE=$DEPS_BEFORE"; exit 2; }
{
  echo "G3C_RUN_START_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "HEAD=$(git rev-parse HEAD)"
  echo "STAGE_HASH=$STAGE_HASH"
  echo "ROOTFS_BEFORE=$ROOTFS_BEFORE"
  echo "DEPS_BEFORE=$DEPS_BEFORE"
} | tee "$EV/env/run-start.txt"

FAILED=()
CASE_ENV=()
SEED_DIR=""

record_command() {
  local name="$1" started="$2" ended="$3" code="$4" log="$5" dir="$6" seed="$7"
  shift 7
  local argv_json
  argv_json="$(printf '%s\n' "$@")"
  PYTHONDONTWRITEBYTECODE=1 "$HOSTPY" -B - "$name" "$started" "$ended" "$code" "$log" "$dir" "$seed" "$ROOTFS_BEFORE" "$DEPS_BEFORE" "$STAGE_HASH" "$argv_json" <<'PY'
import json, sys
name, started, ended, code, log, directory, seed, rootfs, deps, stage, argv_text = sys.argv[1:12]
argv = [line for line in argv_text.splitlines() if line]
record = {"case": name, "utc_start": started, "utc_end": ended, "exit": int(code),
          "argv": argv, "log": log, "evidence": directory, "seed": seed or None,
          "rootfs_hash": rootfs, "deps_hash": deps, "stage_hash": stage,
          "container": "podman rootfs fixed --network none uid 65534"}
with open("artifacts/g3c/commands.jsonl", "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
  PYTHONDONTWRITEBYTECODE=1 "$HOSTPY" -B - "$dir" "$argv_json" <<'PY'
import json, sys
directory, argv_text = sys.argv[1], sys.argv[2]
json.dump({"argv": [line for line in argv_text.splitlines() if line]},
          open(directory + "/argv.json", "w", encoding="utf-8"), indent=2, sort_keys=True)
PY
}

run_case() {
  local name="$1" timeout_s="$2"
  shift 2
  local dir="$TRACES/$name" log="$LOGS/$name.log"
  rm -rf "$dir"
  mkdir -p "$dir"
  chmod -R a+rwX "$dir"
  local cmd=(podman run --rm --name "g3c-$name" \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
    --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp)
  local pair
  for pair in "${CASE_ENV[@]:-}"; do
    [ -n "$pair" ] && cmd+=(--env "$pair")
  done
  cmd+=(--read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges
    --user 65534:65534 --pids-limit 160 --memory 1g --memory-swap 1g --cpus 1
    --tmpfs "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777"
    --tmpfs "/work:rw,noexec,nosuid,nodev,size=512m,mode=1777"
    --workdir /work --timeout "$timeout_s" --systemd=false
    --mount "type=bind,src=$STAGE,dst=/probe,ro=true"
    --mount "type=bind,src=$DEPS,dst=/deps,ro=true"
    --mount "type=bind,src=$dir,dst=/evidence,rw=true")
  if [ -n "$SEED_DIR" ]; then
    cmd+=(--mount "type=bind,src=$SEED_DIR,dst=/seed,ro=true")
  fi
  cmd+=(--rootfs "$ROOTFS" /opt/python/bin/python3.11 -B /probe/run_c3/"$@")
  local started ended code
  started="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  "${cmd[@]}" >"$log" 2>&1
  code=$?
  ended="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  record_command "$name" "$started" "$ended" "$code" "$log" "$dir" "$SEED_DIR" "${cmd[@]}"
  if [ "$code" -ne 0 ]; then
    FAILED+=("$name:$code")
    echo "CASE_FAIL $name exit=$code log=$log"
  else
    echo "CASE_OK $name exit=0 log=$log"
  fi
  CASE_ENV=()
  SEED_DIR=""
  rootfs_cleanup
}

# ---- stage fixture: capture tool schemas from this exact DSH/adapter build ----
CASE_ENV=()
run_case capture-tools 150 capture_tools_c3.py --evidence /evidence
if [ -f "$TRACES/capture-tools/capture-tools.json" ]; then
  cp -f "$TRACES/capture-tools/capture-tools.json" "$STAGE/fixtures/capture-tools.json"
  chmod a+r "$STAGE/fixtures/capture-tools.json"
  sha256sum "$STAGE/fixtures/capture-tools.json" >> "$EV/env/run-start.txt"
else
  echo "CAPTURE_TOOLS_MISSING" | tee -a "$EV/env/run-start.txt"
fi

# ---- §8.1 positive real-DSH set ----
run_case echo 180 worker_c3.py --label echo --prompt G3C_ECHO --evidence /evidence
run_case tool 240 worker_c3.py --label tool --prompt "Use skill_lookup to look up binary_search" --scenario tool --evidence /evidence
run_case guard-on 180 worker_c3.py --label guard-on --prompt G3C_GUARD --guard --evidence /evidence
run_case guard-off 180 worker_c3.py --label guard-off --prompt G3C_NOGUARD --evidence /evidence
run_case resume-first 180 worker_c3.py --label resume-first --prompt G3C_RESUME --session g3c-resume-session --run-id g3c-resume-first --evidence /evidence
SEED_DIR="$TRACES/resume-first/work"
run_case resume-second 180 worker_c3.py --label resume-second --prompt G3C_RESUME_SECOND --session g3c-resume-session --seed /seed --resume --run-id g3c-resume-second --evidence /evidence
SEED_DIR=""
run_case no-controller 120 worker_c3.py --label no-controller --prompt G3C_NO_CONTROLLER --no-controller --evidence /evidence
run_case bad-admission 120 worker_c3.py --label bad-admission --prompt G3C_BAD_ADMISSION --bad-admission --evidence /evidence
run_case guard-invalid 120 worker_c3.py --label guard-invalid --prompt G3C_GUARD_INVALID --guard-invalid --evidence /evidence

# ---- C1-03 real-DSH admission enforcement (0 Reserve / 0 Fake on rejection) ----
run_case admission-output-limit 120 worker_c3.py --label admission-output-limit --prompt G3C_OUTPUT_LIMIT --limits '{"max_output_tokens":128}' --evidence /evidence
run_case admission-input-limit 120 worker_c3.py --label admission-input-limit --prompt G3C_INPUT_LIMIT --limits '{"max_input_tokens":100}' --evidence /evidence
run_case admission-max-calls 240 worker_c3.py --label admission-max-calls --prompt "Use skill_lookup to look up binary_search" --scenario tool --limits '{"max_calls":1}' --evidence /evidence

# ---- C1-02 / C2-01C usage negatives ----
run_case usage-error 150 worker_c3.py --label usage-error --prompt G3C_ERR --scenario error --evidence /evidence
run_case usage-no-usage 150 worker_c3.py --label usage-no-usage --prompt G3C_NOUSAGE --scenario no_usage --evidence /evidence
run_case usage-partial 150 worker_c3.py --label usage-partial --prompt G3C_PARTIAL --scenario partial_usage --evidence /evidence
run_case usage-invalid 150 worker_c3.py --label usage-invalid --prompt G3C_INVALID --scenario usage_invalid --evidence /evidence
run_case usage-eof 150 worker_c3.py --label usage-eof --prompt G3C_EOF --scenario eof --evidence /evidence

# ---- C2-01D multiple usage / usage after finish ----
run_case usage-multi 150 worker_c3.py --label usage-multi --prompt G3C_MULTI --scenario multi_usage --evidence /evidence
run_case usage-after-finish 150 worker_c3.py --label usage-after-finish --prompt G3C_AFTER --scenario usage_after_finish --evidence /evidence

# ---- C3-04 streaming / limits ----
run_case stream-slow 180 worker_c3.py --label stream-slow --prompt G3C_STREAM --scenario stream_slow --evidence /evidence
run_case stream-many 180 worker_c3.py --label stream-many --prompt G3C_MANY --scenario many_chunks --evidence /evidence
run_case stream-big 180 worker_c3.py --label stream-big --prompt G3C_BIG --scenario big_output --evidence /evidence
run_case stream-truncated 180 worker_c3.py --label stream-truncated --prompt G3C_TRUNC --scenario truncated_stream --evidence /evidence

# ---- C3-01D SDK process SIGTERM while Fake is slow ----
run_case sigterm 150 worker_c3.py --label sigterm --prompt G3C_SIGTERM --scenario timeout --kill-after-ms 2500 --evidence /evidence

# ---- C3-02C small admission deadline (100 / 300 ms) ----
run_case deadline-100 120 worker_c3.py --label deadline-100 --prompt G3C_DEADLINE100 --scenario slow_usage --limits '{"deadline_ms":100}' --evidence /evidence
run_case deadline-300 120 worker_c3.py --label deadline-300 --prompt G3C_DEADLINE300 --scenario slow_usage --limits '{"deadline_ms":300}' --evidence /evidence

# ---- C2-02 seven crash windows + new-process reconcile ----
for hook in after_reserve_before_claim after_claim_before_attempt_start \
            after_attempt_start_before_fake_send after_fake_receive_before_response \
            after_response_before_settlement after_broker_settle_before_journal_mark \
            after_journal_mark_before_sdk_finish; do
  CASE_ENV=("G3B_TEST_MODE=1" "G3B_CRASH_HOOK=$hook")
  run_case "crash-$hook" 150 worker_c3.py --label "crash-$hook" --prompt G3C_CRASH --evidence /evidence
  SEED_DIR="$TRACES/crash-$hook"
  run_case "reconcile-$hook" 120 reconcile_c3.py --seed /seed/work --run-id "g3c-reconcile-$hook" --evidence /evidence
  SEED_DIR=""
done
# C2-02F: Broker already FAILED must remain held, never OK.
CASE_ENV=("G3B_TEST_MODE=1" "G3B_CRASH_HOOK=after_broker_settle_before_journal_mark")
run_case crash-after_broker_settle-partial 150 worker_c3.py --label crash-after_broker_settle-partial --prompt G3C_CRASH_PARTIAL --scenario partial_usage --evidence /evidence
SEED_DIR="$TRACES/crash-after_broker_settle-partial"
run_case reconcile-after_broker_settle-partial 120 reconcile_c3.py --seed /seed/work --run-id g3c-reconcile-after_broker_settle-partial --evidence /evidence
SEED_DIR=""
# C2-02D: tampered receipt usage must not settle precisely.
SEED_DIR="$TRACES/crash-after_response_before_settlement"
run_case reconcile-tamper-receipt-usage 120 reconcile_c3.py --seed /seed/work --tamper receipt_usage --run-id g3c-reconcile-tamper-usage --evidence /evidence
SEED_DIR=""
# C2-02E: second reconcile of the same durable state is idempotent, no new Fake.
SEED_DIR="$TRACES/reconcile-after_response_before_settlement"
run_case reconcile2-after-response 120 reconcile_c3.py --seed /seed/work --run-id g3c-reconcile2-after-response --evidence /evidence
SEED_DIR=""

# ---- raw-UDS probes (real Controller/Broker/Fake children, not DSH) ----
run_case probe-replay 150 probes_c3.py --probe replay --evidence /evidence
run_case probe-cancel 150 probes_c3.py --probe cancel --delay-ms 300 --evidence /evidence
run_case probe-cancel-concurrent 180 probes_c3.py --probe cancel_concurrent --delay-ms 300 --evidence /evidence
run_case probe-deadline-100 120 probes_c3.py --probe deadline --deadline-ms 100 --evidence /evidence
run_case probe-deadline-300 120 probes_c3.py --probe deadline --deadline-ms 300 --evidence /evidence
run_case probe-fake-stall 120 probes_c3.py --probe fake_stall --deadline-ms 1500 --evidence /evidence
run_case probe-broker-hang 120 probes_c3.py --probe broker_hang --deadline-ms 1500 --evidence /evidence
run_case probe-ipc-bounds 180 probes_c3.py --probe ipc_bounds --evidence /evidence

rootfs_cleanup
ROOTFS_AFTER="$(hash_tree "$ROOTFS")"
DEPS_AFTER="$(hash_tree "$DEPS")"
STAGE_AFTER="$(hash_tree "$STAGE")"
{
  echo "ROOTFS_AFTER=$ROOTFS_AFTER"
  echo "DEPS_AFTER=$DEPS_AFTER"
  echo "STAGE_AFTER=$STAGE_AFTER"
  echo "G3C_RUN_END_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "PODMAN_PS=$(podman ps -a --format '{{.Names}}' | tr '\n' ' ')"
} | tee -a "$EV/env/run-start.txt"
if [ "${#FAILED[@]}" -ne 0 ]; then
  printf 'G3C_CASE_FAILURES=%s\n' "${FAILED[*]}" | tee -a "$EV/env/run-start.txt"
fi
if [ "$ROOTFS_AFTER" != "$ROOTFS_CANON" ] || [ "$DEPS_AFTER" != "$DEPS_CANON" ]; then
  echo "G3C_CANONICAL_DRIFT rootfs=$ROOTFS_AFTER deps=$DEPS_AFTER" | tee -a "$EV/env/run-start.txt"
  exit 3
fi
[ "${#FAILED[@]}" -eq 0 ] || exit 1
echo "G3C_RUN_OK"
