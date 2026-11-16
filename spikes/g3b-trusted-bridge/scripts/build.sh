#!/usr/bin/env bash
# Container-only build for the G3-B B1 adapter. Host executes only
# podman/cp/chmod/tar/sha256; project Node/TS runs in the fixed rootfs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
SPIKE="$ROOT/spikes/g3b-trusted-bridge"
NPM="$ROOT/plugins/offline-fixture/node_modules"
STAGE="$ROOT/artifacts/g3b-trusted-bridge/stage"
LOGS="$ROOT/artifacts/g3b-trusted-bridge/logs"
mkdir -p "$LOGS" "$STAGE/runtime/bridge"
chmod 0777 "$STAGE/runtime/bridge"
chmod -R a+rX "$SPIKE" "$NPM"
rootfs_hash() {
  tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$ROOTFS" . | sha256sum | cut -d' ' -f1
}
cleanup() {
  # Keep the frozen baseline empty /work dir; remove only mount targets
  # created by this build. Removing /work would change the canonical rootfs hash.
  # Baseline empty dirs /work and /deps are part of the canonical rootfs hash;
  # keep them and remove only mount targets created by this build.
  for d in src npm out var; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then rm -f "$ROOTFS/etc/resolv.conf"; fi
}
trap cleanup EXIT
BEFORE="$(rootfs_hash)"
{
  echo "G3B_BUILD_START_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "ROOTFS_BEFORE=$BEFORE"
  podman run --rm --name g3b-bridge-build \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/usr/bin --env HOME=/work --env G3B_BUILD_IN_CONTAINER=1 \
    --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
    --user 65534:65534 --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
    --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
    --workdir /work --timeout 100 --systemd=false \
    --mount "type=bind,src=$SPIKE,dst=/src,ro=true" \
    --mount "type=bind,src=$NPM,dst=/npm,ro=true" \
    --mount "type=bind,src=$STAGE/runtime/bridge,dst=/out,rw=true" \
    --rootfs "$ROOTFS" /usr/bin/node /src/scripts/build.mjs
  echo "BUILD_EXIT=$?"
} 2>&1 | tee "$LOGS/build.log"
cleanup
AFTER="$(rootfs_hash)"
chmod -R a+rX "$STAGE/runtime/bridge/lib"
echo "ROOTFS_AFTER=$AFTER" | tee -a "$LOGS/build.log"
test "$BEFORE" = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
test "$AFTER" = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
echo "G3B_BUILD_ROOTFS_OK before=$BEFORE after=$AFTER" | tee -a "$LOGS/build.log"
