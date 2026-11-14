#!/bin/sh
# Read-only PR4a verifier launcher; never a Live/egress unlock.
set -eu
PYTHON="${AT_M0_PYTHON:-/opt/python/bin/python3.11}"
exec "$PYTHON" "$(dirname "$0")/verify_egress_policy.py" "$@"
