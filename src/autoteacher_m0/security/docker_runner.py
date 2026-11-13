"""Candidate execution via a separate, credential-free external container.

This controller itself needs independent human review before host deployment.
No exec/import of candidates, host home mount, socket, user flags or env forwarding.
This module does NOT grant Live authorization and cannot prove host/daemon policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import threading
import uuid
from typing import Mapping

from .gates import SecurityBlocked

_IMAGE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[a-f0-9]{64}\Z")
_ENGINES = {"docker": "/usr/bin/docker", "podman": "/usr/bin/podman"}


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int = 10
    memory_mb: int = 256
    pids: int = 32
    cpus: float = 1.0
    scratch_mb: int = 16
    output_bytes: int = 65536

    def __post_init__(self):
        if not (1 <= self.timeout_seconds <= 60 and 32 <= self.memory_mb <= 512
                and 4 <= self.pids <= 64 and 0 < self.cpus <= 1
                and 1 <= self.scratch_mb <= 64 and 1024 <= self.output_bytes <= 65536):
            raise ValueError("Sandbox resources exceed the fixed M0 policy")


@dataclass(frozen=True)
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool


class ContainerRunner:
    def __init__(self, *, image: str, engine: str = "docker",
                 limits: SandboxLimits | None = None):
        if not _IMAGE.fullmatch(image):
            raise ValueError("Use an independently verified image pinned by sha256 digest")
        if engine not in _ENGINES:
            raise ValueError("Only fixed Docker/Podman executable paths are supported")
        self.image, self.engine = image, engine
        self.executable = _ENGINES[engine]
        self.limits = limits or SandboxLimits()

    def command(self, *, stage: Path, name: str) -> list[str]:
        """Stage is controller-created temporary public input, never a repo/home."""
        if not name.startswith("at-m0-") or not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Invalid sandbox name")
        if not stage.is_absolute() or "," in str(stage):
            raise ValueError("Stage must be an absolute path without mount delimiters")
        limits = self.limits
        command = [self.executable, "run", "--rm", "--name", name,
                   "--pull=never", "--network=none", "--read-only",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges",
                   "--user=65534:65534", f"--pids-limit={limits.pids}",
                   f"--memory={limits.memory_mb}m", f"--memory-swap={limits.memory_mb}m",
                   f"--cpus={limits.cpus}", "--ulimit=nofile=64:64",
                   "--ipc=none", "--workdir=/work", "--log-driver=none"]
        if self.engine == "podman":
            command += ["--http-proxy=false", "--unsetenv-all", "--read-only-tmpfs=false",
                        "--systemd=false", f"--timeout={limits.timeout_seconds}"]
        for destination in ("/tmp", "/work"):
            command += ["--tmpfs", f"{destination}:rw,noexec,nosuid,nodev,"
                        f"size={limits.scratch_mb}m,mode=1777"]
        command += ["--mount", f"type=bind,src={stage},dst=/input,readonly",
                    "--env=HOME=/work", "--env=PATH=/usr/local/bin:/usr/bin:/bin",
                    "--env=PYTHONDONTWRITEBYTECODE=1", "--entrypoint=python3",
                    self.image, "-I", "-B", "/input/exercise.py"]
        return command

    def run(self, files: Mapping[str, bytes]) -> SandboxResult:
        """Only explicitly supplied public candidate bytes cross the boundary.

        The bytes must not include credentials, labels, grader or policy sources.
        The caller supplies that classification; this API cannot detect secrets.
        """
        if not Path(self.executable).is_file():
            raise SecurityBlocked("Container engine unavailable; no host fallback")
        if "exercise.py" not in files or len(files) > 64:
            raise ValueError("Provide exercise.py and at most 64 explicit public inputs")
        if sum(len(value) for value in files.values()) > 1024 * 1024:
            raise ValueError("Candidate inputs exceed 1 MiB")
        for name, content in files.items():
            path = PurePosixPath(name)
            if (not isinstance(content, bytes) or path.is_absolute() or ".." in path.parts
                    or path.as_posix() != name or "\\" in name or not path.parts
                    or any(part.startswith(".") for part in path.parts)):
                raise ValueError("Only normalized, non-hidden relative public file names")
        name = "at-m0-" + uuid.uuid4().hex
        # No inherited environment, including proxies, API keys or Docker contexts.
        with tempfile.TemporaryDirectory(prefix="at-m0-sandbox-") as temporary:
            stage = Path(temporary) / "input"
            stage.mkdir(mode=0o755)
            # Parent traversal is needed only for mount setup by the engine.
            for relative, content in files.items():
                destination = stage / relative
                destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o444)
            environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": temporary}
            process = None
            buffers = [bytearray(), bytearray()]
            truncated = [False, False]
            threads = []

            def drain(stream, index):
                try:
                    while chunk := stream.read(4096):
                        remaining = self.limits.output_bytes - len(buffers[index])
                        buffers[index].extend(chunk[:remaining])
                        truncated[index] |= len(chunk) > remaining
                finally:
                    stream.close()

            timed_out = False
            try:
                process = subprocess.Popen(self.command(stage=stage, name=name),
                                           env=environment, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           close_fds=True)
                for index, stream in enumerate((process.stdout, process.stderr)):
                    thread = threading.Thread(target=drain, args=(stream, index), daemon=True)
                    thread.start()
                    threads.append(thread)
                try:
                    process.wait(timeout=self.limits.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    process.wait(timeout=5)
            finally:
                # Kill/removal is mandatory even if the CLI is killed before --rm.
                # No candidate-supplied name or shell expansion reaches this command.
                try:
                    subprocess.run([self.executable, "rm", "--force", name],
                                   env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=5, check=False)
                    # --rm may already have deleted it. A generic rc=1 is NOT
                    # absence; daemon/permission failures can also return 1.
                    # Independently query ALL container states even after rc=0.
                    absence = subprocess.run(
                        [self.executable, "ps", "--all", "--filter", f"name=^{name}$",
                         "--format", "{{.Names}}"], env=environment,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, timeout=5, check=False)
                    if absence.returncode != 0 or absence.stdout.strip():
                        raise SecurityBlocked(
                            "Container cleanup not confirmed; operator inspection required")
                except (subprocess.TimeoutExpired, OSError) as error:
                    raise SecurityBlocked(
                        "Container cleanup unavailable; operator inspection required") from error
                for thread in threads:
                    thread.join(timeout=5)
                if any(thread.is_alive() for thread in threads):
                    raise SecurityBlocked("Container output pipes did not close after cleanup")
            return SandboxResult(process.returncode, buffers[0].decode(errors="replace"),
                                 buffers[1].decode(errors="replace"), timed_out, any(truncated))
