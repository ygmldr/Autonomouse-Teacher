# Local OCI validation — task 16

## Result and non-results

On 2026-11-13 UTC, a real, **fully offline local OCI path** was validated using
Podman 4.9.3/crun 1.14.1 in the existing LXC host. No registry/proxy request was
retried. The prior registry refusal is unchanged; it is not a permanent blocker
to using already-installed public runtime files as a local image.

| Item | Actual result |
|---|---|
| Public-runtime tar -> official Podman import | PASS |
| Existing strict `name@sha256` reference with `--pull=never` | PASS; no Runner relaxation |
| Uncompressed OCI save, manifest/config/layer SHA verification | PASS (archive bytes only) |
| Offline load / cross-machine original-pin roundtrip | **NOT RUN**; no migration/replay claim |
| Existing Dockerfile `candidate` target, exact current recipe | PASS, offline local digest base |
| Generated `ContainerRunner.command()` argv as DATA, independently audited | PASS |
| Exact audited image-based candidate OS command | PASS, exit 0; named-container absence query exit 0/empty |
| Full Python unit + integration regression | **241 passed**, exit 0 |
| Full staged public Python Ruff check | PASS, exit 0 |
| Real `ContainerRunner.run()` orchestration lifecycle | **NOT RUN**; subprocess/cleanup tests remain mocks |
| Dockerfile `python-test` and `plugin-test` dependency stages | **NOT RUN / BLOCKED** without offline dependency/tool image inputs |
| Independent E5-PreLive human authority / E5-P03 / all Live | **BLOCKED, unchanged** |

No model request, real env/key read, credential injection, privileged execution,
engine socket mount, private evaluation mount, host project import/test/controller
execution, or promotion to trusted baseline occurred. The reviewed offline argv
is **not** human Live authorization. Actual DSH Live registry checks and SDK
initialization status are not changed by this task. No overall GO is claimed.

The starting document commit was `e0181942161937e93ecd79635d29bca532dae61c`;
the previously tested implementation baseline was `c155789`. This task changes
only six local-pin regression cases, Dockerfile status comments and this document;
**Runner implementation, Gate, flags, resource policy and model code are unchanged**.
The new Git commit is produced by foundation after owner freeze/review, not by
this worker. Any new baseline still requires independent human review.

## Inputs and frozen shared boundary

All mutable construction and evidence are under the independent, gitignored
`artifacts/local-oci/` directory. The shared rootfs and dependency trees were not
changed. Their full actual normalized tar hashes were checked before and after:

- shared rootfs: `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`;
- shared Python dependencies: `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`;
- independent dependency copy: identical to the shared dependency hash.

Normalization uses GNU tar 1.35: `--sort=name --mtime=@0 --owner=0 --group=0
--numeric-owner -cf - -C <explicit tree> . | sha256sum`, with pipefail. No exclusion
was used for these actual hashes; the existing empty `/probe` mountpoint remains
part of the shared rootfs hash. The local subset rootfs can acquire its own empty
engine-created mountpoint; this cannot alter the already imported tar/OCI blobs.

The candidate image contains **no controller source, grader, dependency test tree,
hidden labels or sentinels**. Its rootfs was constructed in a new directory from
only these explicit installed public inputs:

- shared `/opt/python` (uv CPython **3.11.15**, public runtime/stdlib);
- shared `/lib/x86_64-linux-gnu/` with the previously whitelisted libc/libm/libz/
  libexpat/libpthread/libdl/libutil/librt/libstdc++/libgcc_s/libssl/libcrypto/libffi;
- shared ELF loader `/lib64/ld-linux-x86-64.so.2`;
- new `/usr/local/bin/python3` symlink to `/opt/python/bin/python3.11`;
- newly written synthetic nobody-only passwd/group; empty work/tmp/input/proc/dev.

No host `/etc` or surrounding home was copied. Public runtime binary hashes and
the deterministic rootfs tar hash are retained. The raw tar/layer SHA is:
`aed8d7ef3f3c7fbabb601ed99d5e705e39dc1f779c8486f1865e340dfba94641`.
This records one observed immutable artifact, not a claim that every future
Podman import will reproduce identical config timestamps.

## Actual content identities (not tags)

| Object | SHA-256 |
|---|---|
| Imported local **manifest** | `64c125c83fa76c2f92c9f004aceea2ff4d7aac07f80297668ab7fe0c550110b0` |
| Imported config/content image ID | `c83e44ab5b5dffc3b048ad33ccbb567c3955e6a634b2fbc3956057233969e896` |
| Built candidate **manifest** | `62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b` |
| Built candidate config/content image ID | `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715` |

Actual execution used
`localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`,
not a floating tag or a config ID masquerading as a manifest. Existing Runner
validation accepts this qualified manifest form without any code change.
Six tests confirm identical command boundaries and rejection of local tags,
raw config IDs, uppercase/malformed digests and appended arguments.

`podman save --format oci-dir --uncompressed` preserved the exact imported and
candidate manifest digests. The OCI index points to a blob whose filename and
computed SHA equal each manifest; its config and uncompressed layer objects were
also hashed. Normal compressed save re-encodes the layer and therefore produces
a **different valid manifest** `c1a10073f1ef8fb05253b60fe54fd30b06cf8e62c087bbc7ca4ff06ec5788cf1`
with the same imported config ID; it is not substituted for the executed pin.
This compressed export was of the imported base (`64c125...`), whereas the saved
candidate uses the uncompressed representation (`62d356...`); these identities
must not be conflated.

**Offline load and cross-machine original-name@digest roundtrip were NOT RUN.**
Even an uncompressed archive whose manifest bytes hash exactly matches the local
store proves only the saved content, not that a receiving engine will recreate
the same repository/digest association, image metadata or executable behavior.
No migratable replay or original-pin restoration claim is made. A later roundtrip
must use an independent destination/reference without destroying these images,
inspect the actual loaded immutable manifest/config identities (which may differ
after re-encoding), then independently audit and execute under that actual pin.
A stable config ID alone is not proof of original manifest-pin portability.

## Dockerfile scope

The exact current Dockerfile was built with official Podman, `--target candidate`,
`--pull=never --retry=0 --network=none --http-proxy=false`, explicit digest-pinned
arguments for **all three FROM arguments**, `--skip-unused-stages=true`, OCI format
and `--timestamp=0`. Its minimal context contains only that Dockerfile.
All base arguments point to the imported local manifest above. The candidate
stage has metadata instructions only; no project code or RUN is executed.
The rebuilt current file hash matches the staged Dockerfile and yields the same
candidate manifest/config ID. Raw build stdout records exactly the five candidate
instructions; unused uv/npm dependency stages were not run and are not claimed.
No source, dependency hook or build command ran on the host.

The unchanged production dependency targets still require separately reviewed,
pinned tool/base images and frozen offline wheel/npm inputs. A successful
candidate metadata build does **not** prove those targets are buildable offline.

## Command DATA and actual OS assertions

A newly written export helper ran **only inside a restricted container**. It
imported the existing controller code solely to call `command()`, emitting JSON
argv to a file. That JSON was treated as untrusted **DATA**, never eval'd or
passed to host project Python. The worker and Lead independently read the full
argv, original 53-line fixture, image inspect, canonical absolute input path,
file permissions and image manifest/config identity before manual CLI execution.
Lead's audit was only for this no-key offline command.

The exact command included: absolute `/usr/bin/podman`, unique fixed container
name, pull never, network none, read-only root, cap-drop ALL, no-new-privileges,
UID/GID 65534, pids 32, memory/swap 256 MiB, CPU 1, nofile 64, IPC none, log driver
none, no proxy/env inheritance, systemd false, engine timeout 10 seconds, only
16 MiB noexec/nosuid/nodev tmpfs at `/tmp` and `/work`, and exactly one readonly
mount of the verified public `candidate-input` directory at `/input`.
Entrypoint `python3 -I -B /input/exercise.py` and the exact candidate manifest pin
were unchanged from the exported argv. An independent outer timeout was 20s.

The input directory contained exactly two regular 0644 files (directory 0755):
fixture-identical `exercise.py` and `host_paths.json`. JSON exposes known absolute
paths only, not sentinel contents. Separate host synthetic sentinel directories
were 0700, files 0600: fake key, home-A and home-B same-name logs and fake private
labels. They were **not mounted** and were not placed in either image. A fake
key was deliberately supplied only to the external launcher's clean environment;
`--unsetenv-all` prevented inheritance.

Actual assertions passed: non-root identity, no KEY/TOKEN/SECRET environment name,
known host fake-key/cross-home/private-label/controller-source paths unreadable,
no engine socket/private-home visibility, denied root/usr/input writes, writable
work/tmp, network socket creation/connect denied, zero effective capabilities,
NoNewPrivs=1. Actual cgroup files read `memory.max=268435456`, `pids.max=32`,
`cpu.max=100000 100000`; returned environment names were only HOME/HOSTNAME/PATH/
PYTHONDONTWRITEBYTECODE. This task read actual image resource limits; it did not
repeat every bounded abuse/timeout test previously performed on the rootfs path.

The image command exited 0. An independent official engine all-state exact-name
query exited 0 with empty stdout. No project controller orchestrated the container
lifecycle, and no engine/socket was exposed to any candidate. Therefore
`ContainerRunner.run()`'s real subprocess/timeout/cleanup lifecycle remains
**NOT RUN end-to-end**, although its mocked regressions pass.

## Evidence and failed attempts

The gitignored `artifacts/local-oci/` contains raw import/inspect/save/build logs,
OCI layouts/blobs, argv JSON and independent audit record, exact manual commands,
exit files, OS assertion output, full pytest/Ruff output, source/evidence hashes,
versions and before/after shared-input hashes. All three background jobs were
collected; no related container remained after final checks.

Two local setup mistakes are preserved rather than hidden: the first import put
`HOME=/work` inside PATH due to Podman import ENV syntax (corrected with separate
ENV instructions before validated runs); the first isolated version command
omitted explicit PATH under `--unsetenv-all` and exited 127. It succeeded after
adding only the explicit nonsecret PATH used by the unchanged Runner. Neither
failure caused a registry retry, host execution fallback or security relaxation.

This closes the earlier **image-command/candidate-build evidence gap only**.
Historical threat-model/image-blocked statements describe the earlier phase;
this document supplies the incremental result. Independent human deployment,
actual reviewed DSH tool registry, credential boundary, all required Live work
and complete E5 acceptance remain separate **BLOCKED** items.
