"""Verify a genuinely installed wheel ONLY inside the no-credential container.

Mount this file, a trusted uv binary and one built wheel in a wheel-only /input.
No source checkout or Git metadata is visible. Emit only four explicit public
artifact payloads to stdout for the external evidence collector.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ENV = {"PATH": "/opt/python/bin:/usr/bin", "HOME": "/work",
       "PYTHONPATH": "/work/site:/deps", "PYTHONDONTWRITEBYTECODE": "1",
       "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CACHE": "1"}


def execute(argv: list[str]) -> str:
    print("INSTALLED_COMMAND " + json.dumps(argv), flush=True)
    result = subprocess.run(argv, cwd="/work", env=ENV, capture_output=True,
                            text=True, timeout=30, check=False)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    print("INSTALLED_EXIT " + str(result.returncode), flush=True)
    if result.returncode:
        raise RuntimeError("installed-wheel verification command failed")
    return result.stdout


def emit(name: str, content: bytes) -> None:
    if len(content) > 4 * 1024 * 1024:
        raise ValueError("unexpectedly large public evidence")
    print("PUBLIC_ARTIFACT " + json.dumps({
        "name": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "base64": base64.b64encode(content).decode("ascii"),
    }), flush=True)


def main() -> int:
    assert os.getuid() == 65534
    assert Path.cwd() == Path("/work")
    assert "/project/src" not in sys.path
    # The reusable rootfs contains empty mountpoint directories, not a checkout.
    assert not list(Path("/project/src").glob("**/*.py")), "source checkout must not be mounted"
    assert not Path("/project/src/autoteacher_m0/__init__.py").exists()
    wheels = list(Path("/input").glob("autoteacher_m0-*.whl"))
    assert len(wheels) == 1
    execute(["/input/uv", "pip", "install", "--no-index", "--no-deps", "--no-build",
             "--python", sys.executable, "--target", "/work/site", str(wheels[0])])
    # uv really created both package files and the console entrypoint.
    assert Path("/work/site/bin/at-m0").is_file()
    sys.path.insert(0, "/work/site")
    import autoteacher_m0
    from autoteacher_m0.experiments.fixtures import load_cases
    assert str(autoteacher_m0.__file__).startswith("/work/site/")
    assert len(load_cases()) == 20
    print("INSTALLED_ORIGIN " + str(autoteacher_m0.__file__), flush=True)
    executable = [sys.executable, "-B", "/work/site/bin/at-m0"]
    info = json.loads(execute(executable + ["inspect-runtime"]))
    assert info["sdk_initialized"] is False and info["live_status"] == "BLOCKED"
    smoke = json.loads(execute(executable + ["smoke", "--mock", "--artifact-dir", "/work/smoke"]))
    assert smoke["mock_smoke"] == "PASS" and smoke["count"] == 3
    paired = json.loads(execute(executable + ["paired", "--mock", "--artifact-dir", "/work/paired"]))
    directory = Path(paired["artifact_dir"])
    report = json.loads(execute(executable + ["report", "--artifact-dir", "/work/paired",
                                            "--experiment", directory.name]))
    latest = json.loads(execute(executable + ["report", "--artifact-dir", "/work/paired",
                                            "--experiment", "latest"]))
    assert report["report"] == latest["report"] == str(directory / "comparison.md")
    document = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    assert len(document["runs"]) == 40 and len(document["pairs"]) == 20
    assert len({entry["record"]["run_id"] for entry in document["runs"]}) == 40
    assert len({entry["record"]["session_id"] for entry in document["runs"]}) == 40
    assert all(entry["billable_cost_usd"] == "0" for entry in document["runs"])
    assert document["mode"] == "mock" and document["route_id"] == "mock"
    for name in ("experiment.json", "experiment.sqlite3", "comparison.md"):
        emit(name, (directory / name).read_bytes())
    emit("installed-summary.json", json.dumps({
        "package_origin": str(autoteacher_m0.__file__), "cwd": str(Path.cwd()),
        "source_checkout_visible": False, "cases": 20, "runs": 40,
        "live_status": "BLOCKED", "billable_cost_usd": "0",
        "synthetic_cost_usd": document["budget"]["spent_usd"],
        "python": sys.version.split()[0], "packages": info["packages"],
    }, indent=2).encode())
    print("INSTALLED_WHEEL_VERIFICATION_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
