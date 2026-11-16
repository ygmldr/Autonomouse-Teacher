#!/usr/bin/env bash
# Run the 6-case real DSH SDK provider-bridge suite in the fixed rootfs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
STAGE="$ROOT/artifacts/g3a-provider-bridge/stage"
test -f "$STAGE/runtime/bridge/lib/index.js"
test -f "$STAGE/bridge/fake_provider.py"
mkdir -p "$ROOT/artifacts/g3a-provider-bridge/logs"
LOG="$ROOT/artifacts/g3a-provider-bridge/logs/suite-$(date -u +%Y%m%dT%H%M%SZ).log"

cleanup() {
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then rm -f "$ROOTFS/etc/resolv.conf"; fi
  if [ -d "$ROOTFS/var" ] && [ -z "$(find "$ROOTFS/var" -mindepth 1 -print -quit 2>/dev/null)" ]; then rmdir "$ROOTFS/var" 2>/dev/null || true; fi
}
trap cleanup EXIT

podman run --rm --name g3a-suite \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work/user-home --env PYTHONPATH=/deps \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 64 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --workdir /work --timeout 150 --systemd=false \
  --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --rootfs "$ROOTFS" /opt/python/bin/python3.11 /probe/run/suite.py 2>&1 | tee "$LOG"
echo "G3A_SUITE_LOG=$LOG"
