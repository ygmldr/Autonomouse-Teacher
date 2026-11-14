#!/bin/sh
# POSIX launcher for the read-only PR2 verifier. This script never unlocks Live.
# The fixed OCI image used for PR2 has no shell, so evidence runs invoke the .py
# directly with /opt/python/bin/python3.11; this wrapper exists for reviewed
# deployments that provide a shell.
set -eu
PYTHON="${AT_M0_PYTHON:-/opt/python/bin/python3.11}"
exec "$PYTHON" "$(dirname "$0")/verify_runtime_profile.py" "$@"
