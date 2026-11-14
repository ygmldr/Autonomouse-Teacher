"""Credential, mount and egress boundary primitives for the trusted controller.

These are *design-enforcing helpers*, not an OS security proof. They let the
controller and the offline no-key rehearsal prove that:

* a candidate container env is rebuilt from an allowlist and never inherits a
  launcher/real key, proxy or shell environment;
* fake keys placed in a launcher env, arguments or logs are not forwarded or
  printed unredacted;
* candidate mounts cannot reach a home directory, ``.config``, credentials,
  repository sources, the runtime socket or other host state;
* candidate argv keeps the no-network/read-only/non-root/clean-capability flags;
* the future OpenCode Go egress design permits only ``opencode.ai:443`` and only
  from a separately deployed launcher/egress proxy, never the candidate.

Real key custody, OS permissions and proxy deployment are PR4/human work; this
module never reads a real credential and adds no Live allow path.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

CANDIDATE_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
})
SECRET_ENV_NAMES = frozenset({
    "DEEPSEEK_API_KEY", "OPENCODE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "AZURE_OPENAI_API_KEY", "HTTP_PROXY",
    "HTTPS_PROXY", "ALL_PROXY", "DOCKER_HOST", "PODMAN_HOST",
})
_SECRET_KEY = re.compile(
    r"(?:API[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|SECRET|PASSWORD|PASSWD|"
    r"CREDENTIAL|PRIVATE[_-]?KEY|SESSION[_-]?TOKEN)", re.IGNORECASE)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"oc_sk_[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9][A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
)
_FORBIDDEN_MOUNT_FRAGMENTS = (
    "/root", "/home/", ".config", "autoteacher", "credentials", ".credentials",
    ".env", "id_rsa", "id_ed25519", "known_hosts", ".ssh", "podman.sock",
    "docker.sock", ".dsh", "dsh_home",
)
_REQUIRED_FLAGS = (
    ("--network=none", "--network", "none"),
    ("--read-only",),
    ("--cap-drop", "ALL"),
    ("--security-opt", "no-new-privileges"),
    ("--user", "65534:65534"),
)


class CredentialBoundaryViolation(RuntimeFailure):
    def __init__(self, reasons: Iterable[str]):
        super().__init__(ErrorCode.SECURITY_BLOCKED, "; ".join(reasons) or "CREDENTIAL_BOUNDARY_DENIED")


@dataclass(frozen=True)
class LauncherOnlySecret:
    """Opaque holder for a launcher/env broker secret; repr/str are always redacted."""

    env_name: str
    _value: str

    def __post_init__(self) -> None:
        if not self._value:
            raise ValueError("launcher secret value must be nonempty")
        if self.env_name not in SECRET_ENV_NAMES:
            raise ValueError("launcher secret must use a fixed credential env name")

    @property
    def redacted_reference(self) -> str:
        return f"{self.env_name}=[REDACTED:{len(self._value)}]"

    def __repr__(self) -> str:
        return f"LauncherOnlySecret({self.redacted_reference})"

    __str__ = __repr__

    def for_launcher_env(self) -> dict[str, str]:
        """Only a separately trusted launcher/env broker may call this."""
        return {self.env_name: self._value}


def scrub_candidate_env(env: Mapping[str, str], *, known_secret_values: Iterable[str] = ()
                        ) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return (clean env, violation names). Never forwards a secret-looking entry."""
    violations: list[str] = []
    secrets = tuple(value for value in known_secret_values if value)
    clean: dict[str, str] = {}
    for key, value in env.items():
        if key not in CANDIDATE_ENV_ALLOWLIST or _SECRET_KEY.search(key):
            violations.append(f"ENV_NOT_ALLOWED:{key}")
            continue
        if not isinstance(value, str):
            violations.append(f"ENV_NOT_STRING:{key}")
            continue
        if any(secret in value for secret in secrets) or any(
                pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
            violations.append(f"ENV_SECRET_VALUE:{key}")
            continue
        clean[key] = value
    return clean, tuple(violations)


def assert_candidate_env_clean(candidate_env: Mapping[str, str],
                               known_secrets: Iterable[str] = ()) -> None:
    _, violations = scrub_candidate_env(candidate_env, known_secret_values=known_secrets)
    if violations:
        raise CredentialBoundaryViolation(violations)


def redact_secrets(text: str, known_secrets: Iterable[str] = ()) -> str:
    redacted = text
    for secret in known_secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    for pattern in _SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def assert_log_clean(text: str, known_secrets: Iterable[str] = ()) -> None:
    for secret in known_secrets:
        if secret and secret in text:
            raise CredentialBoundaryViolation(("LOG_CONTAINS_LAUNCHER_SECRET",))
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            raise CredentialBoundaryViolation(("LOG_CONTAINS_SECRET_PATTERN",))


def validate_candidate_mounts(mount_specs: Sequence[str], *,
                              allowed_stage_root: Path) -> tuple[str, ...]:
    """Only controller-created public stage files may appear, read-only, at /input."""
    root = allowed_stage_root.resolve()
    violations: list[str] = []
    for spec in mount_specs:
        lowered = spec.lower()
        if "readonly" not in lowered and "ro=true" not in lowered and ",ro" not in lowered:
            violations.append("MOUNT_NOT_READ_ONLY")
        if any(fragment in lowered for fragment in _FORBIDDEN_MOUNT_FRAGMENTS):
            violations.append("MOUNT_FORBIDDEN_SOURCE")
        match = re.fullmatch(r"type=bind,src=([^,]+),dst=/input,readonly", spec)
        if match is None:
            violations.append("MOUNT_DESTINATION_NOT_INPUT")
            continue
        try:
            source = Path(match.group(1)).resolve(strict=True)
        except OSError:
            violations.append("MOUNT_SOURCE_MISSING")
            continue
        if not source.is_relative_to(root):
            violations.append("MOUNT_OUTSIDE_PUBLIC_STAGE")
    return tuple(dict.fromkeys(violations))


def validate_candidate_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Reject candidate commands that could inherit a key or use real egress."""
    joined = " ".join(argv)
    lowered = joined.lower()
    violations: list[str] = []
    network_none = "--network=none" in argv or (
        "--network" in argv and argv[argv.index("--network") + 1:][:1] == ["none"])
    read_only = "--read-only" in argv or "--read-only=true" in argv
    cap_drop_all = any(token == "--cap-drop=ALL" or token == "ALL" for token in argv)
    no_new_privileges = any(
        token == "--security-opt=no-new-privileges" or token == "no-new-privileges"
        for token in argv)
    fixed_user = any(token in {"--user=65534:65534", "65534:65534"} for token in argv)
    for required, present in (("--network=none", network_none),
                              ("--read-only", read_only),
                              ("--cap-drop=ALL", cap_drop_all),
                              ("--security-opt", no_new_privileges),
                              ("--user=65534:65534", fixed_user)):
        if not present:
            violations.append("REQUIRED_ISOLATION_FLAG_MISSING:" + required)
    if "--unsetenv-all" not in argv:
        violations.append("REQUIRED_ISOLATION_FLAG_MISSING:--unsetenv-all")
    if "--http-proxy=false" not in argv:
        violations.append("REQUIRED_ISOLATION_FLAG_MISSING:--http-proxy=false")
    if "--privileged" in argv or "--privileged=true" in argv:
        violations.append("PRIVILEGED_CONTAINER")
    for index, token in enumerate(argv):
        if token == "--env" or token.startswith("--env="):
            if token == "--env":
                pair = argv[index + 1] if index + 1 < len(argv) else ""
            else:
                pair = token[len("--env="):]
            key = pair.split("=", 1)[0]
            if key not in CANDIDATE_ENV_ALLOWLIST or _SECRET_KEY.search(key):
                violations.append("CANDIDATE_ENV_FORBIDDEN:" + key)
        if token in {"--mount", "--volume", "-v"} and index + 1 < len(argv):
            spec = argv[index + 1].lower()
            if any(fragment in spec for fragment in _FORBIDDEN_MOUNT_FRAGMENTS):
                violations.append("CANDIDATE_MOUNT_FORBIDDEN")
        if token in {"-p", "--publish"} or token.startswith("--publish="):
            violations.append("CANDIDATE_PORT_PUBLISHED")
    if "--network=host" in argv or ("--network" in argv and "host" in argv):
        violations.append("CANDIDATE_NETWORK_NOT_NONE")
    if "--network=none" not in argv and not ("--network" in argv and "none" in argv):
        violations.append("CANDIDATE_NETWORK_NOT_NONE")
    if "\n" in joined or "\x00" in joined:
        violations.append("ARGV_CONTROL_CHARACTER")
    if "socket" in lowered and any(flag in argv for flag in ("--mount", "--volume")):
        violations.append("CANDIDATE_SOCKET_MOUNT")
    return tuple(dict.fromkeys(violations))


@dataclass(frozen=True)
class EgressPolicy:
    host_ports: Mapping[str, frozenset[int]]
    methods: frozenset[str]
    path_prefix: str

    def violations(self, *, host: str, port: int, method: str, path: str) -> tuple[str, ...]:
        reasons: list[str] = []
        ports = self.host_ports.get(host)
        if ports is None or port not in ports:
            reasons.append("EGRESS_HOST_PORT_NOT_ALLOWED")
        if method.upper() not in self.methods:
            reasons.append("EGRESS_METHOD_NOT_ALLOWED")
        if not path.startswith(self.path_prefix):
            reasons.append("EGRESS_PATH_NOT_ALLOWED")
        return tuple(reasons)


# INTERNAL-TEST-ONLY OpenCode Go design constraint (see OPENCODE_GO_ACCESS.md §4).
# The launcher/proxy holds OPENCODE_API_KEY; the candidate has no network or key.
OPENCODE_GO_EGRESS = EgressPolicy(
    host_ports={"opencode.ai": frozenset({443})},
    methods=frozenset({"POST"}),
    path_prefix="/inference/go/",
)
