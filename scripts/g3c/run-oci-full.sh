#!/usr/bin/env bash
# G3-C full Python suite inside the fixed rootfs (the environment the two
# container-only host tests require: /project/src layout, read-only config).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
EV="$ROOT/artifacts/g3c"
STAGE="$EV/oci-test"
EVID="$EV/evidence"
LOGS="$EV/logs"
ROOTFS_CANON="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
mkdir -p "$EVID" "$LOGS"
chmod 0777 "$EVID" "$LOGS"
hash_tree() { tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$1" . | sha256sum | cut -d' ' -f1; }
rootfs_cleanup() {
  for d in src npm out var build-src evidence seed debug; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
}
trap rootfs_cleanup EXIT
rootfs_cleanup
ROOTFS_BEFORE="$(hash_tree "$ROOTFS")"
test "$ROOTFS_BEFORE" = "$ROOTFS_CANON" || { echo "ROOTFS_NOT_CANONICAL=$ROOTFS_BEFORE"; exit 2; }
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a src tests config scripts plugins fixtures spikes pyproject.toml "$STAGE/"
mkdir -p "$STAGE/artifacts/foundation/deps"
chmod -R a+rX "$STAGE"
# The target-profile test expects frozen read-only text.
chmod 0444 "$STAGE/config/dsh/target-runtime.patch.yml" \
           "$STAGE/config/dsh/target-runtime-opencode-go.patch.yml" \
           "$STAGE/config/dsh/target-broker-policy.json" \
           "$STAGE/scripts/verify_runtime_profile.py"
LOG="$LOGS/oci-full.log"
{
  echo "UTC_START=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "ROOTFS_BEFORE=$ROOTFS_BEFORE"
  podman run --rm --name g3c-oci-full \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
    --env PYTHONPATH=/project/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
    --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
    --user 65534:65534 --pids-limit 192 --memory 1500m --memory-swap 1500m --cpus 1 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
    --tmpfs /work:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
    --workdir /project --timeout 600 --systemd=false \
    --mount "type=bind,src=$STAGE,dst=/project,rw=true" \
    --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
    --mount "type=bind,src=$DEPS,dst=/project/artifacts/foundation/deps,ro=true" \
    --mount "type=bind,src=$EVID,dst=/evidence,rw=true" \
    --rootfs "$ROOTFS" /opt/python/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider \
    --junitxml=/evidence/junit-oci-full.xml
  echo "EXIT=$?"
  echo "UTC_END=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} 2>&1 | tee "$LOG"
rootfs_cleanup
ROOTFS_AFTER="$(hash_tree "$ROOTFS")"
echo "ROOTFS_AFTER=$ROOTFS_AFTER" | tee -a "$LOG"
test "$ROOTFS_AFTER" = "$ROOTFS_CANON"
grep -q "passed" "$LOG" || { echo "OCI_FULL_NO_SUMMARY"; exit 1; }
if grep -q "failed" "$LOG"; then echo "OCI_FULL_HAS_FAILURES"; exit 1; fi
echo "OCI_FULL_OK"
