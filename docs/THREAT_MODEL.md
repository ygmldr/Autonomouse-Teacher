# M0 security boundary and actual evidence

## Status (2026-11-13 UTC)

**E5-PreLive / E5-P03: BLOCKED.** No independent human-maintained authorization
or credential broker is installed. Markdown, Agent-authored variables, CLI flags
and in-process test doubles are not independent human authorization. LiveGate
has no allow path; no model request or real key inspection was performed.

**E5-Full: partial evidence, NOT full PASS.** The actual host is Ubuntu 24.04
inside LXC, kernel 6.17.13-2-pve. Initial Docker/Podman and daemon sockets were
absent. Official apt installed Podman 4.9.3/crun 1.14.1. Default overlay info
works; explicit vfs failed with storage database mismatch and was not used.
There are no downloaded images. Pull of the versioned official Python image
failed (exit 125: proxy socket permission denied). No alternate proxy/registry,
privilege escalation or host application execution was attempted.

A **real Podman container using a local public-runtime rootfs** is usable without
any registry. This is not a changed cwd and not an in-process sandbox.
The first compatibility probe used system Python 3.12.3; the reusable rootfs now
also contains uv's trusted CPython **3.11.15** (version executed inside container)
and system Node **22.23.2**. This is distinct from a downloaded reproducible image.
All dependency/test versions and results must be recorded per run.

Raw local logs: `artifacts/security/` (gitignored; synthetic data only).
`environment.txt` preserves discovery and registry failure; `os-probe.log`
preserves actual assertions. These logs are not authorization tokens.

## Assets, actors and trust

Protect real API credentials, maintainer homes/SSH/env files, other DSH homes,
private evaluation labels/graders, policy, budgets and trusted controller state.
Every newly generated controller/plugin/test/candidate is unreviewed code. Human
review must cover the frozen code inventory, dependency lock, merged DSH profile,
actual registered tools, logs and credential flow before any credential use.

The container engine and host kernel remain in the trusted computing base.
An engine daemon/socket is never exposed inside a test/candidate container.
Rootful Podman authority exists only in the external system-tool launcher; the
candidate is UID/GID 65534 with all capabilities dropped and no-new-privileges.
A kernel/runtime escape remains a residual risk; use a stronger VM boundary for
higher-risk adversaries. Namespace tests are not a production security proof.

## Local rootfs construction (no credentials copied)

Rootfs: `/root/Autonomous Teacher/artifacts/security/rootfs`.
Only these public installed runtime files were copied:

- `/usr/bin/python3.12`, `/usr/lib/python3.12` (system interpreter/stdlib);
- uv's `/root/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu/`
  to `/opt/python` (public managed runtime, NOT the surrounding home);
- `/usr/bin/node`;
- `ldd`-identified system libraries: libc, libm, libz, libexpat, libpthread,
  libdl, libutil, librt, libstdc++, libgcc_s, libssl, libcrypto, libffi,
  and the ELF loader;
- newly created nonsecret passwd/group containing only synthetic nobody entries;
  empty input/project/deps/tmp/work/proc/dev mount points.

No host `/etc`, home, env, key, npm config, Docker config or private evaluation
source was copied. Python/package caches are not credentials and are not mounted.
Third-party dependencies can be installed by official tooling with no project
installation/hooks, then copied to `/deps`; unreviewed project execution remains
container-only. Keep rootfs modifications serialized before parallel test runs.

## Reusable offline execution contract

First copy **only explicit public source/test/fixture/config files** into a
worker-specific staging directory (never `.env`, private labels, homes, sockets,
Git metadata, or a broad host root). Make staged directories traversable and files
readable by UID 65534. Only this stage is mounted read-only at `/project`.
Create writable output inside `/work` or `/tmp`; capture stdout/stderr externally
into each worker's gitignored artifacts directory. Do not mount artifacts writable
just to obtain test output. The following is a command template, not proof of a
particular test result:

```bash
# PUBLIC_STAGE is an independently checked absolute public-only staging path.
# TEST_NAME is unique per worker. No env-file, env-host or user-supplied flags.
timeout 75s podman run --rm --name "$TEST_NAME" --rootfs \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/project/src:/deps --env PYTHONDONTWRITEBYTECODE=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges --user 65534:65534 \
  --pids-limit 32 --memory 256m --memory-swap 256m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --workdir /project --timeout 60 --systemd=false \
  --mount "type=bind,src=$PUBLIC_STAGE,dst=/project,ro=true" \
  '/root/Autonomous Teacher/artifacts/security/rootfs' \
  /opt/python/bin/python3.11 -B -m pytest -p no:cacheprovider tests/unit -q
```

Outer timeout is a second bound, but if it fires always inspect/force-remove the
unique named container using the external official engine. Podman's own timeout
is enabled. Never run pytest/Node build scripts on the host. No socket mount is
needed or permitted. An unreviewed test must not execute this launcher by itself
from a credentialed controller. `ContainerRunner` is a candidate-only image-based
implementation; it stages explicit byte inputs, pins image digest, bounds output,
uses no inherited environment and unconditionally force-removes its container.
After removal it independently queries the official engine's all-state container
list filtered by the exact unique name: only a successful empty result confirms
absence. A generic removal exit 1 is never accepted as absence on its own; daemon,
permission, timeout, residual-container and query failures are SECURITY_BLOCKED.
This cleanup behavior is regression-tested logically, not OS-verified for an image.
The local-rootfs launcher is external evidence, not proof the image runner ran.

## Actual OS negative probe

`fixtures/sandbox/exercise.py` was copied into an isolated public input directory
with only synthetic known-host paths JSON. Synthetic host sentinel directories
are mode 0700 and their files 0600: fake key, home-A/session same.jsonl,
home-B/session same.jsonl and private-eval fake labels. No real home/key was read.
The container was deliberately told their exact absolute paths. None was readable.
No controller policy source or engine socket was visible. Public stage permissions
were initially 0600 (expected non-root denial); corrected only for public inputs.

Probe assertions actually passed: UID/GID 65534, no KEY/TOKEN/SECRET environment
names (an explicit fake parent key was not inherited), no host fake key/known
cross-home/private labels, root and `/input` writes denied, `/work` and `/tmp`
writable, effective capabilities zero, NoNewPrivs=1. Network socket creation was
itself denied by host policy; this is stronger than a failed outbound connect but
does not independently characterize every socket family.

Kernel files actually read inside the container: `memory.max=268435456`,
`pids.max=32`, `cpu.max=100000 100000`. Despite limited Podman info controller
listing, actual CPU cgroup quota exists. CLI option acceptance alone was NOT used
as evidence. Further controlled probes actually executed under CPython 3.11.15:

- `resource-pids.log`: finite 40-attempt process probe failed at 31 children,
  then killed/reaped every child (32-PID container limit), exit 0.
- Initial finite memory allocation killed container init, exit 137. Podman's
  `State.OOMKilled` was false, so that flag was NOT claimed as OOM proof. The
  strengthened parent/child probe kept its parent alive and read kernel
  `memory.events`: `oom_kill` increased **0 -> 1**, child return code **-9**;
  `memory-final.log`, exit 0, confirms the actual cgroup memory bound.
- `state-timeout.log`: Podman's two-second deadline stopped a sleeping infinite
  candidate in about 2.25 seconds; container state was exited/not running,
  launcher exit 255, engine ExitCode -1. This platform-specific exit is recorded
  rather than assumed to be 137. Outer 25-second timeout did not fire.
- `resource-recovery.log`: subsequent fresh container had no previous `/work`
  contents and printed `FRESH_CONTAINER_RECOVERY_OK`, exit 0. This is fresh
  scratch recovery evidence, not a proof about every trusted controller state.
- `tests-cleanup-final.log`: **45 passed**, including actual external OS negative
  probe and eight cleanup-failure regressions added after independent static
  review. Logical gate/command/output/cleanup tests are explicitly distinguished
  from OS assertions. `lint-cleanup-final.log`: Ruff all checks passed. Both ran only inside
  the restricted CPython 3.11.15 container using hash-verified locked public
  dependencies staged by foundation. No host pytest/import/build was used.

Podman/conmon creates a zero-byte `oom` marker in the launcher's cwd when init is
OOM-killed on this host. The initial marker was independently reproduced in the
security artifacts cwd, then the precisely verified empty original was archived
from repository root into `artifacts/security/oom-marker-initial`. Nothing was
blindly deleted; `marker-confirm.log` records metadata and the reproduction.

Production image-based `ContainerRunner` execution and Dockerfile builds remain
**BLOCKED** by registry permission/no local image; these must not be inferred from
the rootfs results. Unit tests mock the image-runner subprocess boundary.
The external rootfs launcher, not that unverified image-runner deployment, produced
the OS evidence above. All containers were removed after evidence collection.

## Gate and admission limits

`security.gates.fingerprint` hashes explicit byte inventory plus canonical JSON
configuration. Any code/dependency/config/file-set change changes the diagnostic
baseline. Missing/changed baselines and non-whitelisted actual tools add blocking
reasons. Completeness of an Agent-supplied inventory is NOT independently trusted.
An external maintainer must verify the complete immutable inventory, deployment
and allowed commands. Even exact fingerprint matches never unlock Live today.

Actual merged DSH profile/tool registry and disabled session-log upload are not
verified by a mock list or config file alone. E5-P04/P05/P07 Live deployment
validation remains BLOCKED. Normal Session API/home separation is E3 logical
isolation only, never E5 filesystem evidence. Offline unit PASS cannot prove
E5-P03 or OS sandbox integrity. No GO/CONDITIONAL GO is justified by these partial
results. Default final decision remains DECISION PENDING.
