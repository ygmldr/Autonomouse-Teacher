"""Explicit offline defaults. No dotenv loading or credential discovery."""
from dataclasses import dataclass
from pathlib import Path

PRIMARY_ROUTE = "deepseek-official"
MODEL = "deepseek-flash"


@dataclass(frozen=True)
class RuntimeSettings:
    workspace: Path
    dsh_home: Path
    patch: Path
    profile: str = "sdk-minimal"
    provider: str = PRIMARY_ROUTE
    model: str = MODEL
    route_id: str = PRIMARY_ROUTE
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    max_steps: int = 8
    max_retries: int = 1

    def __post_init__(self) -> None:
        for path in (self.workspace, self.dsh_home, self.patch):
            if not path.is_absolute():
                raise ValueError("workspace, dsh_home and patch must be explicit absolute paths")
        work, home = self.workspace.resolve(), self.dsh_home.resolve()
        if work == home or work in home.parents or home in work.parents:
            raise ValueError("workspace and dsh_home must be separate, non-nested paths")
        if self.provider != PRIMARY_ROUTE or self.route_id != PRIMARY_ROUTE or self.model != MODEL:
            raise ValueError("route/model changes require an independently approved new baseline")
        if self.max_tokens <= 0 or self.timeout_seconds <= 0:
            raise ValueError("token and timeout bounds must be positive")
        if not 1 <= self.max_steps <= 8 or not 0 <= self.max_retries <= 1:
            raise ValueError("step/retry limits must not exceed the M0 baseline")
