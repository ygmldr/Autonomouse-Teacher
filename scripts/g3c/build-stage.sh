#!/usr/bin/env bash
# G3-C stage assembly (host executes only cp/chmod/tar/sha256/podman).
# The adapter build runs Node/TS only inside the fixed rootfs with --network none.
# Rootfs and deps are canonicalised by tar hash before and after.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
SPIKE="$ROOT/spikes/g3b-trusted-bridge"
G3A="$ROOT/artifacts/g3a-provider-bridge/stage"
EV="$ROOT/artifacts/g3c"
STAGE="$EV/stage"
BUILD="$EV/build/bridge"
LOGS="$EV/logs"
ENVLOG="$EV/env"
NPM="$ROOT/plugins/offline-fixture/node_modules"
ROOTFS_CANON="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON="e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
mkdir -p "$LOGS" "$ENVLOG" "$EV/traces" "$EV/ledger" "$EV/receipts" "$EV/evidence" \
  "$EV/stage" "$EV/build"
LOG="$LOGS/build-stage.log"
: > "$LOG"

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
test -x "$ROOTFS/usr/bin/node"
test -d "$DEPS"
test -f "$G3A/native/skill-lookup/lib/index.js"
test -d "$NPM"
test -f "$ROOT/scripts/g3c/build-adapter.mjs"

ROOTFS_BEFORE="$(hash_tree "$ROOTFS")"
DEPS_BEFORE="$(hash_tree "$DEPS")"
{
  echo "G3C_BUILD_STAGE_START_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "ROOTFS_BEFORE=$ROOTFS_BEFORE"
  echo "DEPS_BEFORE=$DEPS_BEFORE"
} | tee -a "$LOG"
test "$ROOTFS_BEFORE" = "$ROOTFS_CANON"
test "$DEPS_BEFORE" = "$DEPS_CANON"

# 1) Adapter build in the fixed rootfs (Node/TS never runs on the host).
rm -rf "$EV/build"
mkdir -p "$BUILD"
chmod 0777 "$BUILD"
chmod -R a+rX "$SPIKE" "$NPM" "$ROOT/scripts/g3c"
{
  echo "G3C_ADAPTER_BUILD_START_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  podman run --rm --name g3c-adapter-build \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/usr/bin --env HOME=/work --env G3C_BUILD_IN_CONTAINER=1 \
    --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
    --user 65534:65534 --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
    --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
    --workdir /work --timeout 100 --systemd=false \
    --mount "type=bind,src=$SPIKE,dst=/src,ro=true" \
    --mount "type=bind,src=$NPM,dst=/npm,ro=true" \
    --mount "type=bind,src=$ROOT/scripts/g3c,dst=/build-src,ro=true" \
    --mount "type=bind,src=$BUILD,dst=/out,rw=true" \
    --rootfs "$ROOTFS" /usr/bin/node /build-src/build-adapter.mjs
  echo "ADAPTER_BUILD_EXIT=$?"
} 2>&1 | tee -a "$LOG"
test -f "$BUILD/lib/index.js"
chmod -R a+rX "$BUILD/lib"

# 2) Stage assembly from the current committed sources.
rm -rf "$STAGE"
mkdir -p "$STAGE"/{config,run_c3,fake,fixtures,src,runtime/bridge,runtime/skill/lib} \
  "$STAGE"/{native/guard/lib,native-cache,pkg-cache,node_modules,evidence}
cp -a "$ROOT/src/." "$STAGE/src/"
cp -a "$BUILD/lib" "$STAGE/runtime/bridge/lib"
cp -a "$BUILD/build-meta.json" "$STAGE/runtime/bridge/build-meta.json"
cp -a "$SPIKE/fake/fake_provider.py" "$STAGE/fake/"
cp -a "$SPIKE/run_c3/." "$STAGE/run_c3/"
cp -a "$SPIKE/config/bridge.patch.yml" "$SPIKE/config/broker.policy.template.json" \
      "$SPIKE/config/admission.template.json" "$SPIKE/config/controller.template.json" \
      "$SPIKE/config/guard-broker-policy.json" "$SPIKE/config/guard.precheck.patch.yml" \
      "$SPIKE/config/guard.invalid.patch.yml" "$SPIKE/config/guard.reserve.patch.yml" \
      "$STAGE/config/"
cp -a "$G3A/native/skill-lookup/lib/." "$STAGE/runtime/skill/lib/"
cp -a "$ROOT/plugins/runtime-budget-guard/lib/." "$STAGE/native/guard/lib/"
cp -a "$G3A/runtime/node_modules/." "$STAGE/node_modules/"
cp -a "$G3A/native-cache/." "$STAGE/native-cache/"
cp -a "$G3A/pkg-cache/." "$STAGE/pkg-cache/"
cp -a "$G3A/fixtures/skills.json" "$STAGE/fixtures/skills.json"
cp -a "$SPIKE/run_c3/fixtures/slow_broker.py" "$STAGE/fixtures/slow_broker.py"
chmod 0755 "$STAGE/fixtures/slow_broker.py"
chmod -R a+rX "$STAGE"
chmod 0777 "$STAGE/evidence"

# 3) Post-build canonical checks (rootfs/deps must be unchanged).
rootfs_cleanup
ROOTFS_AFTER="$(hash_tree "$ROOTFS")"
DEPS_AFTER="$(hash_tree "$DEPS")"
STAGE_HASH="$(hash_tree "$STAGE")"
{
  echo "ROOTFS_AFTER=$ROOTFS_AFTER"
  echo "DEPS_AFTER=$DEPS_AFTER"
  echo "STAGE_HASH=$STAGE_HASH"
  echo "G3C_BUILD_STAGE_END_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} | tee -a "$LOG"
test "$ROOTFS_AFTER" = "$ROOTFS_CANON"
test "$DEPS_AFTER" = "$DEPS_CANON"

PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B - "$STAGE" "$ROOTFS_AFTER" "$DEPS_AFTER" "$STAGE_HASH" <<'PY' | tee "$ENVLOG/stage.json"
import json, sys
from pathlib import Path
stage, rootfs, deps, stage_hash = sys.argv[1:5]
build = Path(stage) / "runtime/bridge/build-meta.json"
meta = json.loads(build.read_text()) if build.exists() else None
print(json.dumps({"stage": stage, "stage_hash": stage_hash,
                  "rootfs_hash": rootfs, "deps_hash": deps,
                  "adapter_build": meta}, indent=2, sort_keys=True))
PY
echo "G3C_BUILD_STAGE_OK"
