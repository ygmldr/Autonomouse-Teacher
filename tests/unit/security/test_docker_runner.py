"""Command-policy tests, never a substitute for external OS negative probes."""
import io
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from autoteacher_m0.security.docker_runner import ContainerRunner, SandboxLimits
from autoteacher_m0.security.gates import SecurityBlocked

IMAGE = 'docker.io/library/python@sha256:' + 'a' * 64
LOCAL_IMAGE = 'localhost/autoteacher-local-oci@sha256:' + 'b' * 64


def test_local_manifest_digest_uses_unchanged_candidate_boundary(tmp_path):
    local = ContainerRunner(image=LOCAL_IMAGE, engine='podman').command(
        stage=tmp_path, name='at-m0-local-manifest-test')
    existing = ContainerRunner(image=IMAGE, engine='podman').command(
        stage=tmp_path, name='at-m0-local-manifest-test')
    assert local[-4] == LOCAL_IMAGE
    # Only the content-addressed image reference differs; not a flag/timeout/mount.
    assert local[:-4] == existing[:-4]
    assert local[-3:] == existing[-3:]


@pytest.mark.parametrize('image', ['localhost/autoteacher-local-oci:rootfs',
    'localhost/autoteacher-local-oci', 'sha256:' + 'b' * 64,
    'localhost/x@sha256:' + 'B' * 64, 'localhost/x@sha256:' + 'b' * 64 + '--network=host'])
def test_local_tag_or_raw_config_id_is_not_a_manifest_pin(image):
    with pytest.raises(ValueError):
        ContainerRunner(image=image, engine='podman')


def test_container_policy_has_no_host_env_or_privilege_inheritance(tmp_path):
    command = ContainerRunner(image=IMAGE, engine='podman').command(
        stage=tmp_path, name='at-m0-policy-test')
    for required in ('--pull=never', '--network=none', '--read-only', '--cap-drop=ALL',
                     '--security-opt=no-new-privileges', '--user=65534:65534',
                     '--pids-limit=32', '--memory=256m', '--cpus=1.0',
                     '--http-proxy=false', '--unsetenv-all', '--read-only-tmpfs=false',
                     '--timeout=10'):
        assert required in command
    assert '--privileged' not in command
    assert '--env-host' not in command
    assert not any('docker.sock' in arg or 'podman.sock' in arg for arg in command)
    assert command.count('--mount') == 1
    assert f'type=bind,src={tmp_path},dst=/input,readonly' in command
    assert command[-4:] == [IMAGE, '-I', '-B', '/input/exercise.py']


@pytest.mark.parametrize('image', ['python:latest', 'python:3.11', 'x@sha256:short',
                                  '--privileged', 'python@sha256:' + 'f' * 63])
def test_image_requires_verified_digest(image):
    with pytest.raises(ValueError):
        ContainerRunner(image=image)


def test_engine_and_name_not_arbitrary_commands(tmp_path):
    with pytest.raises(ValueError):
        ContainerRunner(image=IMAGE, engine='/tmp/evil')
    runner = ContainerRunner(image=IMAGE)
    with pytest.raises(ValueError):
        runner.command(stage=tmp_path, name='at-m0-x;sh')
    with pytest.raises(ValueError):
        runner.command(stage=Path('/tmp/bad,src=/root'), name='at-m0-x')


@pytest.mark.parametrize('kwargs', [{'timeout_seconds': 0}, {'timeout_seconds': 61},
    {'memory_mb': 1024}, {'pids': 1024}, {'cpus': 2}, {'scratch_mb': 1024},
    {'output_bytes': 1048576}])
def test_resource_policy_cannot_be_relaxed(kwargs):
    with pytest.raises(ValueError):
        SandboxLimits(**kwargs)


def test_run_bounds_output_strips_environment_and_always_cleans_up(monkeypatch):
    calls = []

    class FakeProcess:
        stdout = io.BytesIO(b'x' * 70000)
        stderr = io.BytesIO(b'failure')
        returncode = 0

        def wait(self, timeout):
            return 0

    def launch(command, **kwargs):
        calls.append(('launch', command, kwargs))
        assert not any('KEY' in name or 'TOKEN' in name for name in kwargs['env'])
        assert set(kwargs['env']) == {'PATH', 'LANG', 'HOME'}
        return FakeProcess()

    def cleanup(command, **kwargs):
        calls.append(('cleanup', command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'')

    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    monkeypatch.setattr(subprocess, 'run', cleanup)
    monkeypatch.setenv('FAKE_API_KEY', 'M0_FAKE_NEVER_FORWARD')
    result = ContainerRunner(image=IMAGE).run({'exercise.py': b'print("public")'})
    assert result.returncode == 0 and not result.timed_out
    assert result.output_truncated and len(result.stdout) == 65536
    assert calls[-2][1][1:3] == ['rm', '--force']
    assert calls[-2][1][3] == calls[0][1][4]
    assert calls[-1][1][1] == 'ps'
    assert f'name=^{calls[0][1][4]}$' in calls[-1][1]


def test_timeout_kills_cli_then_removes_container(monkeypatch):
    killed = []
    removed = []

    class SlowProcess:
        stdout = io.BytesIO(b'')
        stderr = io.BytesIO(b'')
        returncode = -9

        def wait(self, timeout):
            if not killed:
                raise subprocess.TimeoutExpired('fixed-container-command', timeout)
            return -9

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: SlowProcess())
    def cleanup(command, **kwargs):
        removed.append(command)
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(subprocess, 'run', cleanup)
    result = ContainerRunner(image=IMAGE).run({'exercise.py': b'while True: pass'})
    assert result.timed_out and killed and removed


@pytest.mark.parametrize('filename', ['../escape', '/root/secret', 'a/../b',
                                     '.env', 'nested/.env', 'a\\b'])
def test_stage_input_rejects_escape_or_hidden_files(filename, monkeypatch):
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    with pytest.raises(ValueError):
        ContainerRunner(image=IMAGE).run({'exercise.py': b'pass', filename: b'public'})


@pytest.mark.parametrize('rm_code,query_code,query_output', [
    (1, 1, b''),  # daemon/permission error, NOT evidence of absence
    (2, 1, b''),
    (1, 0, b'at-m0-still-running\n'),
    (0, 0, b'at-m0-still-running\n'),  # even rm=0 must verify absence
    (0, 125, b''),
])
def test_cleanup_failure_or_remaining_container_is_blocked(
        rm_code, query_code, query_output, monkeypatch):
    class Process:
        stdout = io.BytesIO(b'')
        stderr = io.BytesIO(b'')
        returncode = 0
        def wait(self, timeout):
            return 0
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: Process())
    def cleanup(command, **kwargs):
        return SimpleNamespace(returncode=rm_code if command[1] == 'rm' else query_code,
                               stdout=query_output)
    monkeypatch.setattr(subprocess, 'run', cleanup)
    with pytest.raises(SecurityBlocked, match='cleanup not confirmed'):
        ContainerRunner(image=IMAGE).run({'exercise.py': b'pass'})


@pytest.mark.parametrize('timed_command', ['rm', 'ps'])
def test_cleanup_timeout_is_security_blocked(timed_command, monkeypatch):
    class Process:
        stdout = io.BytesIO(b'')
        stderr = io.BytesIO(b'')
        returncode = 0
        def wait(self, timeout):
            return 0
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: Process())
    def cleanup(command, **kwargs):
        if command[1] == timed_command:
            raise subprocess.TimeoutExpired('fixed-engine-command', 5)
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(subprocess, 'run', cleanup)
    with pytest.raises(SecurityBlocked, match='cleanup unavailable'):
        ContainerRunner(image=IMAGE).run({'exercise.py': b'pass'})


def test_nonzero_rm_only_accepted_after_successful_empty_query(monkeypatch):
    class Process:
        stdout = io.BytesIO(b'')
        stderr = io.BytesIO(b'')
        returncode = 0
        def wait(self, timeout):
            return 0
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: Process())
    commands = []
    def cleanup(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1 if command[1] == 'rm' else 0, stdout=b'')
    monkeypatch.setattr(subprocess, 'run', cleanup)
    assert ContainerRunner(image=IMAGE).run({'exercise.py': b'pass'}).returncode == 0
    assert [command[1] for command in commands] == ['rm', 'ps']
