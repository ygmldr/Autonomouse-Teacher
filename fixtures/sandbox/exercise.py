"""Hostile negative probe: run ONLY inside a fresh external container.

All sentinel values below are synthetic and public. Known host paths are supplied
as JSON by the test controller; they are NOT mounted inside the container.
"""
import json
import os
from pathlib import Path
import socket


def assert_denied(path):
    try:
        Path(path).read_bytes()
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return
    raise AssertionError(f"Unexpectedly readable host path: {path}")


assert os.getuid() == 65534
assert os.getgid() == 65534
assert not any("KEY" in name or "TOKEN" in name or "SECRET" in name
               for name in os.environ)
for target in json.loads(Path('/input/host_paths.json').read_text()):
    assert_denied(target)
for target in ('/var/run/docker.sock', '/run/podman/podman.sock',
               '/root/.ssh/id_rsa', '/home/maintainer/.env'):
    assert not Path(target).exists(), target
for target in ('/forbidden-write', '/usr/forbidden-write', '/input/tamper'):
    try:
        Path(target).write_text('must not persist')
    except (OSError, PermissionError):
        pass
    else:
        raise AssertionError(f"Unexpectedly writable: {target}")
for target in ('/work/allowed', '/tmp/allowed'):
    Path(target).write_text('scratch only')
try:
    with socket.socket() as connection:
        connection.settimeout(0.5)
        assert connection.connect_ex(('198.51.100.1', 443)) != 0
except PermissionError:
    pass  # Host policy can deny socket creation more strictly than netns.
status = Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\t1' in status
assert 'CapEff:\t0000000000000000' in status
limits = {name: Path('/sys/fs/cgroup', name).read_text().strip()
          for name in ('memory.max', 'pids.max', 'cpu.max')}
assert limits['memory.max'] != 'max'
assert limits['pids.max'] != 'max'
assert not limits['cpu.max'].startswith('max ')
print(json.dumps({'probe': 'OS_NEGATIVE_ASSERTIONS_PASSED', 'uid': os.getuid(),
                  'limits': limits, 'environment_names': sorted(os.environ)}))
