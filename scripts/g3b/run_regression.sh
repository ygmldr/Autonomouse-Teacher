#!/usr/bin/env bash
# G3-B B4 regression SKELETON. NOT executed by B4-prep and NOT evidence.
# B4 must fill <...> placeholders with the frozen final SHAs/paths, run it on the
# fixed no-key host/OCI, preserve raw argv/UTC/exit under the packet logs/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
IMPL="${G3B_IMPL_SHA:-<PENDING>}"
PACKET="${G3B_PACKET_DIR:-artifacts/review-packet-g3b-$IMPL}"
LOGS="$PACKET/logs"
mkdir -p "$LOGS"

run_host() {
  local id="$1"; shift
  local utc; utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "G3B_REGRESSION id=$id utc=$utc argv=$*" | tee -a "$LOGS/regression-host.log"
  # NEVER write host bytecode / deps __pycache__.
  PYTHONDONTWRITEBYTECODE=1 python3 -B "$@" >>"$LOGS/$id.stdout.log" 2>>"$LOGS/$id.stderr.log"
  echo "G3B_REGRESSION id=$id exit=$?" | tee -a "$LOGS/regression-host.log"
}

# Host Python/Ruff (project Python only; no host Node).
run_host host-g3b-pytest -m pytest tests/integration/g3_bridge -q
run_host host-full-pytest -m pytest tests/ -q
run_host host-ruff -m ruff check src tests

# Fixed no-key OCI: use the exact frozen argv recorded in logs/commands.jsonl.
# Template (B4 must fill actual paths/mounts; network none/read-only/uid 65534):
# podman run --rm --rootfs artifacts/security/rootfs \
#   --network none --http-proxy=false --unsetenv-all \
#   --env PATH=/opt/python/bin:/usr/bin --env HOME=/work --env PYTHONPATH=/probe/src:/deps \
#   --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
#   --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
#   --user 65534:65534 --pids-limit 128 --memory 1g --cpus 1 \
#   --tmpfs /tmp:rw,noexec,nosuid,nodev --tmpfs /work:rw,noexec,nosuid,nodev \
#   --mount "type=bind,src=<stage-b3>,dst=/probe,ro=true" \
#   --mount "type=bind,src=artifacts/foundation/deps,dst=/deps,ro=true" \
#   --mount "type=bind,src=<evidence>,dst=/evidence,rw=true" \
#   /opt/python/bin/python3.11 -B /probe/run/suite.py --mode dsh --evidence /evidence

echo "G3B_REGRESSION_STATUS=PENDING_B4"
exit 0
