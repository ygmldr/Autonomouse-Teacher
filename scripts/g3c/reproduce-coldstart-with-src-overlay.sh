#!/usr/bin/env bash
# G3-C P2-1 reproduction helper (no key / no model / no external network).
#
# WHY
#   The frozen packet-v2 `reproduce/README.md` R5 command mounts
#   `artifacts/g3c/stage` at `/probe` and sets PYTHONPATH=/probe/src:/deps.
#   That stage was built at 13:40 from the pre-PR1 source (e6fde1c batch):
#   its stage/src/autoteacher_m0/bridge/attempts.py has
#   `journal_mode=WAL` before `busy_timeout`, so a stage-only two-controller
#   cold start reproduces the v1 P1-2 `database is locked` traceback.
#
# WHAT THIS DOES
#   * verifies the fixed environment (canonical rootfs/deps/stage hashes);
#   * copies the frozen `artifacts/g3c/stage` to a temporary directory and
#     replaces its `src/` with `git archive <impl> src` (default b2f6af0);
#   * mounts that overlay at `/probe` in the fixed rootfs and runs N rounds of
#     two simultaneous real Controllers through the existing `run_c3` path
#     (`/probe/run_c3/coldstart_overlay_probe.py` -> controller/Broker/Fake);
#   * checks loser exit 5 + CONTROLLER_SINGLETON_LOCKED, 0 traceback, Fake=1,
#     one receipt, Attempt SETTLED, reservation OK, claim COMPLETED,
#     admission=1, winner SIGTERM exit 0, socket removed;
#   * verifies the canonical hashes after the run; the temporary overlay is
#     deleted.  It never edits the repo, the canonical stage or existing
#     artifacts/evidence.
#
# USAGE
#   bash scripts/g3c/reproduce-coldstart-with-src-overlay.sh --rounds 5
#   bash scripts/g3c/reproduce-coldstart-with-src-overlay.sh \
#       --impl b2f6af054555705192c4e1ae3019a68078764736 --rounds 20 \
#       --out artifacts/g3c/repro-coldstart-$(date -u +%Y%m%dT%H%M%SZ)
#
#   Expected for b2f6af0: `SUMMARY {"fail": 0, "pass": N, "loser_exits": [5],
#   "tracebacks": 0, "fake_counters": [1], "attempt_states": ["SETTLED"]}` and
#   exit 0.
#
# REQUIREMENTS
#   fixed rootfs artifacts/security/rootfs (25491e45...), deps
#   artifacts/foundation/deps (e07729d7...), frozen stage artifacts/g3c/stage
#   (fcdb0de4...), podman 4.9.x, the impl commit in this repository.
#   Run on the host; host Python is not used.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ROOTFS="$ROOT/artifacts/security/rootfs"
DEPS="$ROOT/artifacts/foundation/deps"
STAGE="$ROOT/artifacts/g3c/stage"
PROBE_SRC="$ROOT/scripts/g3c/coldstart_overlay_probe.py"
HOSTPY=/root/.local/bin/python3.11

ROOTFS_CANON="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON="e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
STAGE_CANON="fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0"

IMPL="b2f6af054555705192c4e1ae3019a68078764736"
ROUNDS=5
OUT=""
CHECK_CANON=1
OVERLAY=""

usage() {
  sed -n '1,45p' "$0" | sed -n 's/^# \{0,1\}//p'
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

hash_tree() {
  tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$1" . \
    | sha256sum | cut -d' ' -f1
}

rootfs_cleanup() {
  local dir
  for dir in src npm out var build-src evidence seed debug rv2; do
    if [ -d "$ROOTFS/$dir" ] \
      && [ -z "$(find "$ROOTFS/$dir" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      rmdir "$ROOTFS/$dir" 2>/dev/null || true
    fi
  done
  if [ -f "$ROOTFS/etc/resolv.conf" ] && [ ! -s "$ROOTFS/etc/resolv.conf" ]; then
    rm -f "$ROOTFS/etc/resolv.conf"
  fi
}

cleanup() {
  rootfs_cleanup
  if [ -n "$OVERLAY" ] && [ -d "$OVERLAY" ]; then
    rm -rf "$OVERLAY"
  fi
}
trap cleanup EXIT INT TERM

while [ "$#" -gt 0 ]; do
  case "$1" in
    --impl)
      [ "$#" -ge 2 ] || die "--impl needs a commit"
      IMPL="$2"; shift 2 ;;
    --impl=*) IMPL="${1#*=}"; shift ;;
    --rounds)
      [ "$#" -ge 2 ] || die "--rounds needs an integer"
      ROUNDS="$2"; shift 2 ;;
    --rounds=*) ROUNDS="${1#*=}"; shift ;;
    --out)
      [ "$#" -ge 2 ] || die "--out needs a directory"
      OUT="$2"; shift 2 ;;
    --out=*) OUT="${1#*=}"; shift ;;
    --no-canonical-check) CHECK_CANON=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

case "$ROUNDS" in
  ''|*[!0-9]*) die "--rounds must be an integer" ;;
esac
if [ "$ROUNDS" -lt 1 ] || [ "$ROUNDS" -gt 50 ]; then
  die "--rounds must be between 1 and 50 (5 is the P2-1 smoke; use 20+ for P1-2)"
fi

command -v podman >/dev/null 2>&1 || die "podman is required"
command -v git >/dev/null 2>&1 || die "git is required"
command -v tar >/dev/null 2>&1 || die "tar is required"
for path in "$ROOTFS" "$DEPS" "$STAGE" "$PROBE_SRC"; do
  [ -e "$path" ] || die "missing required path: $path"
done
[ -d "$STAGE/src" ] || die "stage/src missing: $STAGE/src"
[ -x "$ROOTFS/opt/python/bin/python3.11" ] \
  || die "rootfs python missing: $ROOTFS/opt/python/bin/python3.11"

IMPL_SHA="$(git -C "$ROOT" rev-parse --verify "${IMPL}^{commit}" 2>/dev/null)" \
  || die "impl is not a commit in this repository: $IMPL"

# Refuse to run if a previous podman mount left transient directories behind.
rootfs_cleanup

ROOTFS_BEFORE="$(hash_tree "$ROOTFS")"
DEPS_BEFORE="$(hash_tree "$DEPS")"
STAGE_BEFORE="$(hash_tree "$STAGE")"
if [ "$CHECK_CANON" = 1 ]; then
  [ "$ROOTFS_BEFORE" = "$ROOTFS_CANON" ] \
    || die "rootfs is not canonical: $ROOTFS_BEFORE (expected $ROOTFS_CANON)"
  [ "$DEPS_BEFORE" = "$DEPS_CANON" ] \
    || die "deps is not canonical: $DEPS_BEFORE (expected $DEPS_CANON)"
  [ "$STAGE_BEFORE" = "$STAGE_CANON" ] \
    || die "stage is not canonical: $STAGE_BEFORE (expected $STAGE_CANON)"
fi

if [ -z "$OUT" ]; then
  OUT="$ROOT/artifacts/g3c/repro-coldstart-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
chmod 0777 "$OUT"

OVERLAY="$(mktemp -d "${TMPDIR:-/tmp}/g3c-src-overlay.XXXXXX")"
chmod 0755 "$OVERLAY"
cp -a "$STAGE/." "$OVERLAY/"
rm -rf "$OVERLAY/src"
git -C "$ROOT" archive "$IMPL_SHA" src | tar -x -C "$OVERLAY"

OVERLAY_ATTEMPTS="$OVERLAY/src/autoteacher_m0/bridge/attempts.py"
STAGE_ATTEMPTS="$STAGE/src/autoteacher_m0/bridge/attempts.py"
[ -f "$OVERLAY_ATTEMPTS" ] || die "overlay attempts.py missing"
OVERLAY_SHA="$(sha256sum "$OVERLAY_ATTEMPTS" | cut -d' ' -f1)"
STAGE_SHA="$(sha256sum "$STAGE_ATTEMPTS" | cut -d' ' -f1)"
REF_SHA="$(git -C "$ROOT" show "$IMPL_SHA:src/autoteacher_m0/bridge/attempts.py" | sha256sum | cut -d' ' -f1)"
[ "$OVERLAY_SHA" = "$REF_SHA" ] \
  || die "overlay attempts.py does not match $IMPL_SHA: $OVERLAY_SHA != $REF_SHA"
if [ "$OVERLAY_SHA" = "$STAGE_SHA" ]; then
  die "overlay src equals the frozen stage src; choose a post-PR1 impl (b2f6af0)"
fi
grep -q "INIT_BUSY_TIMEOUT_MS = 250" "$OVERLAY_ATTEMPTS" \
  || die "overlay attempts.py lacks the b2f6af0 busy_timeout-before-WAL fix"
grep -q "def _initialize" "$OVERLAY_ATTEMPTS" \
  || die "overlay attempts.py lacks the bounded _initialize() fix"
grep -q "CONTROLLER_SINGLETON_LOCKED" "$OVERLAY/src/autoteacher_m0/bridge/controller.py" \
  || die "overlay controller.py lacks the PR1 singleton lock code"

cp "$PROBE_SRC" "$OVERLAY/run_c3/coldstart_overlay_probe.py"
chmod 0644 "$OVERLAY/run_c3/coldstart_overlay_probe.py"
# The probe is helper code copied into the throw-away overlay only; the repo
# and the canonical stage are never written.

{
  echo "utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "impl=$IMPL_SHA"
  echo "rounds=$ROUNDS"
  echo "rootfs_before=$ROOTFS_BEFORE"
  echo "deps_before=$DEPS_BEFORE"
  echo "stage_before=$STAGE_BEFORE"
  echo "stage_src_attempts_sha=$STAGE_SHA"
  echo "overlay_src_attempts_sha=$OVERLAY_SHA"
  echo "overlay=$OVERLAY"
  echo "out=$OUT"
} | tee "$OUT/repro.env"

NAME="g3c-repro-coldstart-$$"
set +e
podman run --rm --name "$NAME" \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/probe/src:/deps \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --env G3C_IMPL="$IMPL_SHA" \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 160 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --workdir /work --timeout 300 --systemd=false \
  --mount "type=bind,src=$OVERLAY,dst=/probe,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$OUT,dst=/evidence,rw=true" \
  --rootfs "$ROOTFS" \
  /opt/python/bin/python3.11 -B /probe/run_c3/coldstart_overlay_probe.py \
    --rounds "$ROUNDS" --evidence /evidence \
    --label "src-overlay-${IMPL_SHA:0:12}" \
    --fake /probe/fake/fake_provider.py \
  2>&1 | tee "$OUT/podman.log"
PODMAN_STATUS=${PIPESTATUS[0]}
set -e

rootfs_cleanup
ROOTFS_AFTER="$(hash_tree "$ROOTFS")"
DEPS_AFTER="$(hash_tree "$DEPS")"
STAGE_AFTER="$(hash_tree "$STAGE")"
{
  echo "rootfs_after=$ROOTFS_AFTER"
  echo "deps_after=$DEPS_AFTER"
  echo "stage_after=$STAGE_AFTER"
  echo "podman_status=$PODMAN_STATUS"
  echo "podman_ps=$(podman ps -a --format '{{.Names}}' | tr '\n' ' ')"
  echo "utc_end=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} | tee -a "$OUT/repro.env"

if [ "$CHECK_CANON" = 1 ] \
  && { [ "$ROOTFS_AFTER" != "$ROOTFS_CANON" ] \
       || [ "$DEPS_AFTER" != "$DEPS_CANON" ] \
       || [ "$STAGE_AFTER" != "$STAGE_CANON" ]; }; then
  echo "ERROR: canonical drift after run (rootfs=$ROOTFS_AFTER deps=$DEPS_AFTER stage=$STAGE_AFTER)" >&2
  exit 3
fi

if podman ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "ERROR: podman container still present: $NAME" >&2
  exit 4
fi

if [ "$PODMAN_STATUS" -ne 0 ]; then
  echo "COLDSTART_OVERLAY_FAILED exit=$PODMAN_STATUS out=$OUT" >&2
  exit 1
fi

RESULT_JSON="$OUT/coldstart-src-overlay-${IMPL_SHA:0:12}-${ROUNDS}.json"
if [ -f "$RESULT_JSON" ]; then
  echo "COLDSTART_OVERLAY_OK rounds=$ROUNDS result=$RESULT_JSON"
else
  echo "COLDSTART_OVERLAY_OK rounds=$ROUNDS out=$OUT (result json name not found)" >&2
fi
echo "EXPECTED: loser exit 5 / CONTROLLER_SINGLETON_LOCKED / 0 traceback / Fake=1 / Attempt SETTLED"
echo "CANONICAL: rootfs=$ROOTFS_AFTER deps=$DEPS_AFTER stage=$STAGE_AFTER"
exit 0
