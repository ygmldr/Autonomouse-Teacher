#!/usr/bin/env bash
# Container-only build for the G3-A bridge and the reviewed skill plugin.
# Host executes only podman/cp/chmod/sha256; project Node/TS runs in the rootfs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
SPIKE="$ROOT/spikes/g3a-provider-bridge"
NPM="$ROOT/plugins/offline-fixture/node_modules"
STAGE="$ROOT/artifacts/g3a-provider-bridge/stage"
test -x "$ROOTFS/usr/bin/node"
test -d "$NPM/@deepseek-ai/dsh-llm"
mkdir -p "$STAGE/runtime/bridge/lib" "$STAGE/native/skill-lookup"
chmod 0777 "$STAGE/runtime/bridge" "$STAGE/native/skill-lookup"
chmod -R a+rX "$SPIKE" "$NPM" "$ROOT/fixtures/skills.json"

cleanup() {
  # podman creates missing bind-mount targets inside --rootfs. Remove only empty
  # synthetic dirs and the zero-byte resolv.conf it writes; never delete data.
  for d in src spike npm fixtures out var; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then
    rm -f "$ROOTFS/etc/resolv.conf"
  fi
}
trap cleanup EXIT

podman run --rm --name g3a-bridge-build \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work --env G3A_BUILD_IN_CONTAINER=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --workdir /work --timeout 100 --systemd=false \
  --mount "type=bind,src=$SPIKE,dst=/src,ro=true" \
  --mount "type=bind,src=$NPM,dst=/npm,ro=true" \
  --mount "type=bind,src=$STAGE/runtime/bridge,dst=/out,rw=true" \
  --rootfs "$ROOTFS" /usr/bin/node /src/scripts/build.mjs

podman run --rm --name g3a-skill-build \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work --env G3A_BUILD_IN_CONTAINER=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --workdir /work --timeout 100 --systemd=false \
  --mount "type=bind,src=$SPIKE,dst=/spike,ro=true" \
  --mount "type=bind,src=$ROOT/plugins/skill-lookup,dst=/src,ro=true" \
  --mount "type=bind,src=$NPM,dst=/npm,ro=true" \
  --mount "type=bind,src=$ROOT/fixtures,dst=/fixtures,ro=true" \
  --mount "type=bind,src=$STAGE/native/skill-lookup,dst=/out,rw=true" \
  --rootfs "$ROOTFS" /usr/bin/node /spike/scripts/build-skill.mjs

chmod -R a+rX "$STAGE/runtime/bridge/lib" "$STAGE/native/skill-lookup/lib"
