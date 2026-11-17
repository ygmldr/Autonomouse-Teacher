#!/usr/bin/env bash
# G3-C Node tests in the fixed rootfs: real adapter build + guard plugin.
# Node/TS never runs on the host; only podman/cp/chmod/tar.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
SPIKE="$ROOT/spikes/g3b-trusted-bridge"
NPM="$ROOT/plugins/offline-fixture/node_modules"
GUARD="$ROOT/plugins/runtime-budget-guard"
EV="$ROOT/artifacts/g3c"
STAGE="$EV/stage"
NODETEST="$EV/node-test"
LOGS="$EV/logs"
ROOTFS_CANON="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
mkdir -p "$LOGS" "$NODETEST"
hash_tree() { tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$1" . | sha256sum | cut -d' ' -f1; }
rootfs_cleanup() {
  for d in src npm out var build-src evidence seed debug plugin; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
}
trap rootfs_cleanup EXIT
test -f "$STAGE/runtime/bridge/lib/index.js" || { echo "STAGE_BRIDGE_MISSING"; exit 2; }
ROOTFS_BEFORE="$(hash_tree "$ROOTFS")"
rm -rf "$NODETEST"
mkdir -p "$NODETEST"
cp -a "$SPIKE/src" "$SPIKE/test" "$SPIKE/package.json" "$SPIKE/tsconfig.json" "$NODETEST/"
cp -a "$NPM" "$NODETEST/node_modules"
cp -a "$STAGE/runtime/bridge/lib" "$NODETEST/lib"
chmod -R a+rX "$NODETEST" "$GUARD"
run_node() {
  local name="$1"; shift
  local log="$LOGS/$name.log"
  {
    echo "UTC_START=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    podman run --rm --name "g3c-$name" \
      --network none --http-proxy=false --unsetenv-all \
      --env PATH=/usr/bin --env HOME=/work --env TMPDIR=/tmp \
      --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
      --user 65534:65534 --pids-limit 96 --memory 1g --memory-swap 1g --cpus 1 \
      --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
      --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
      --workdir /work --timeout 120 --systemd=false \
      --mount "type=bind,src=$NODETEST,dst=/probe,ro=true" \
      --mount "type=bind,src=$GUARD,dst=/plugin,ro=true" \
      --rootfs "$ROOTFS" /usr/bin/node --test "$@"
    echo "EXIT=$?"
    echo "UTC_END=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  } 2>&1 | tee "$log"
}
run_node node-adapter /probe/test/adapter-signal.test.mjs
run_node node-guard /plugin/tests/guard-pr1.test.mjs /plugin/tests/precheck.test.mjs
rootfs_cleanup
ROOTFS_AFTER="$(hash_tree "$ROOTFS")"
echo "ROOTFS_BEFORE=$ROOTFS_BEFORE" | tee -a "$LOGS/node-tests-summary.txt"
echo "ROOTFS_AFTER=$ROOTFS_AFTER" | tee -a "$LOGS/node-tests-summary.txt"
[ "$ROOTFS_BEFORE" = "$ROOTFS_CANON" ] || { echo "ROOTFS_NOT_CANONICAL_BEFORE"; exit 3; }
[ "$ROOTFS_AFTER" = "$ROOTFS_CANON" ] || { echo "ROOTFS_DRIFT_AFTER"; exit 3; }
grep -q "^# fail 0" "$LOGS/node-adapter.log" || { echo "NODE_ADAPTER_FAILED"; exit 1; }
grep -q "^# fail 0" "$LOGS/node-guard.log" || { echo "NODE_GUARD_FAILED"; exit 1; }
echo "NODE_TESTS_OK"
