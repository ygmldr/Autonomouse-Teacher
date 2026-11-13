#!/bin/sh
# Intentional hard stop; do not replace with a key-reading convenience wrapper.
printf '%s\n' 'BLOCKED SECURITY_BLOCKED: no independent authorization/controller boundary.' >&2
printf '%s\n' 'Review docs/M0_RUNBOOK.md; a Markdown approval is not an execution capability.' >&2
exit 3
