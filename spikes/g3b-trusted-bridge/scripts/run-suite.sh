#!/usr/bin/env bash
# G3-B B3-prep: assemble stage-b3 and run the non-DSH UDS smoke in the fixed
# rootfs. Host executes only git/cp/chmod/tar/sha256/podman; project Python/Node
# runs in the container. This is integration plumbing evidence, NOT B3 PASS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
SPIKE="$ROOT/spikes/g3b-trusted-bridge"
G3A="$ROOT/artifacts/g3a-provider-bridge/stage"
STAGE3="$ROOT/artifacts/g3b-trusted-bridge/stage-b3"
LOGS="$ROOT/artifacts/g3b-trusted-bridge/logs"
test -x "$ROOTFS/usr/bin/node"
test -d "$DEPS"
test -f "$ROOT/artifacts/g3b-trusted-bridge/stage/runtime/bridge/lib/index.js" || \
  bash "$SPIKE/scripts/build.sh"
mkdir -p "$LOGS"
UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGS/b3prep-smoke-$UTC.log"
EVIDENCE="$STAGE3/evidence"

rootfs_hash() {
  tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$ROOTFS" . | sha256sum | cut -d' ' -f1
}
cleanup_rootfs() {
  # Remove only mount targets created by this run or provably-empty dirs.
  for d in evidence src npm out debug; do
    if [ -d "$ROOTFS/$d" ] && [ -z "$(find "$ROOTFS/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$d" 2>/dev/null || true
    fi
  done
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then rm -f "$ROOTFS/etc/resolv.conf"; fi
}
trap cleanup_rootfs EXIT
test "$(rootfs_hash)" = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
BEFORE="$(rootfs_hash)"

# Assemble a fresh B3-preparation stage from the frozen B1 build + current B2
# fake and the G3-A runtime/native inputs. Never modify those source stages.
rm -rf "$STAGE3"
mkdir -p "$STAGE3"/{config,run,fake,evidence,src,runtime/bridge,runtime/skill/lib,node_modules} \
  "$STAGE3"/{native/guard/lib,native-cache,pkg-cache,fixtures} "$EVIDENCE"
cp -a "$ROOT/src/." "$STAGE3/src/"
cp -a "$ROOT/artifacts/g3b-trusted-bridge/stage/runtime/bridge/." "$STAGE3/runtime/bridge/"
cp -a "$SPIKE/fake/fake_provider.py" "$STAGE3/fake/"
cp -a "$SPIKE/run/." "$STAGE3/run/"
cp -a "$SPIKE/config/bridge.patch.yml" "$SPIKE/config/broker.policy.template.json" \
      "$SPIKE/config/admission.template.json" "$SPIKE/config/controller.template.json" \
      "$SPIKE/config/guard-precheck.patch.template.yml" \
      "$SPIKE/config/guard-broker-policy.json" "$SPIKE/config/guard.precheck.patch.yml" \
      "$SPIKE/config/guard.reserve.patch.yml" "$STAGE3/config/"
cp -a "$G3A/native/skill-lookup/lib/." "$STAGE3/runtime/skill/lib/"
cp -a "$ROOT/plugins/runtime-budget-guard/lib/." "$STAGE3/native/guard/lib/"
cp -a "$G3A/runtime/node_modules/." "$STAGE3/node_modules/"
cp -a "$G3A/native-cache/." "$STAGE3/native-cache/"
cp -a "$G3A/pkg-cache/." "$STAGE3/pkg-cache/"
cp -a "$G3A/fixtures/skills.json" "$STAGE3/fixtures/skills.json"
chmod -R a+rX "$STAGE3"
chmod 0777 "$EVIDENCE"

set +e
{
  echo "G3B_B3PREP_START_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "ROOTFS_BEFORE=$BEFORE"
  podman run --rm --name g3b-b3prep-smoke \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
    --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
    --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
    --user 65534:65534 --pids-limit 128 --memory 1g --memory-swap 1g --cpus 1 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
    --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
    --workdir /work --timeout 150 --systemd=false \
        --mount "type=bind,src=$STAGE3,dst=/probe,ro=true" \
    --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
    --mount "type=bind,src=$EVIDENCE,dst=/evidence,rw=true" \
    --rootfs "$ROOTFS" /opt/python/bin/python3.11 -B /probe/run/suite.py --mode smoke --evidence /evidence
  SUITE_EXIT=$?
  echo "SUITE_EXIT=$SUITE_EXIT"
  echo "G3B_B3PREP_END_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} > "$LOG" 2>&1
set -e
cat "$LOG"

cleanup_rootfs
AFTER="$(rootfs_hash)"
echo "ROOTFS_AFTER=$AFTER" | tee -a "$LOG"
test "$BEFORE" = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
test "$AFTER" = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
echo "G3B_B3PREP_ROOTFS_OK before=$BEFORE after=$AFTER" | tee -a "$LOG"
echo "G3B_B3PREP_SUITE_EXIT=$SUITE_EXIT" | tee -a "$LOG"
echo "G3B_B3PREP_LOG=$LOG"
echo "G3B_B3PREP_EVIDENCE=$EVIDENCE"
exit "$SUITE_EXIT"
