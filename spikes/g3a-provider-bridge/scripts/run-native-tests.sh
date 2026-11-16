#!/usr/bin/env bash
# Run Guard, Skill Lookup and the committed synthetic-provider suite in the fixed rootfs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
STAGE="$ROOT/artifacts/g3a-provider-bridge/stage"
SDKSTAGE="$ROOT/artifacts/sdk-fixture/stage"
LOGS="$ROOT/artifacts/g3a-provider-bridge/logs"
mkdir -p "$LOGS"

cleanup() {
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then rm -f "$ROOTFS/etc/resolv.conf"; fi
  if [ -d "$ROOTFS/var" ] && [ -z "$(find "$ROOTFS/var" -mindepth 1 -print -quit 2>/dev/null)" ]; then rmdir "$ROOTFS/var" 2>/dev/null || true; fi
}
trap cleanup EXIT

podman run --rm --name g3a-native-guard \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work --env TMPDIR=/tmp --env RBG_TEST_PYTHON=/opt/python/bin/python3.11 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 64 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 110 --systemd=false \
  --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
  --rootfs "$ROOTFS" /usr/bin/node --test /probe/native/guard/tests/guard-pr1.test.mjs \
  > "$LOGS/native-guard.log" 2>&1

# The skill test harness targets the plugin's declared 0.2.1-rc.2 test deps;
# it does not run under 0.2.2 ToolRuntime config. The built plugin artifact is
# separately exercised by the 0.2.2 runtime bridge suite.
podman run --rm --name g3a-native-skill \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work --env TMPDIR=/tmp \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 64 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 110 --systemd=false \
  --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
  --mount "type=bind,src=$ROOT/plugins/skill-lookup/node_modules,dst=/probe/native/skill-lookup/node_modules,ro=true" \
  --rootfs "$ROOTFS" /usr/bin/node --test /probe/native/skill-lookup/test/plugin.test.mjs \
  > "$LOGS/native-skill.log" 2>&1

podman run --rm --name g3a-native-synthetic \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work/user-home --env PYTHONPATH=/deps:/probe/validator \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp --env DSH_RUNTIME_MODE=exe \
  --env DSH_RESOURCE_CACHE=/work/resources --env NARB_NATIVE_CACHE_DIR=/probe/native-cache \
  --env PKG_NATIVE_CACHE_PATH=/probe/pkg-cache --env NO_COLOR=1 --env AUTOTEACHER_OFFLINE_FIXTURE=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 64 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 170 --systemd=false \
  --mount "type=bind,src=$SDKSTAGE,dst=/probe,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --rootfs "$ROOTFS" /opt/python/bin/python3.11 /probe/suite.py \
  > "$LOGS/native-synthetic-suite.log" 2>&1
echo "G3A_NATIVE_LOGS=$LOGS"
