"""Bounded hostile resource probes; ONLY execute in an already limited container."""
import json
from pathlib import Path
import subprocess
import sys
import time

mode = sys.argv[1]
if mode == 'memory':
    # Finite 512 MiB attempted allocation, only under a <=256 MiB cgroup.
    assert int(Path('/sys/fs/cgroup/memory.max').read_text()) <= 268435456
    def events():
        return dict(line.split() for line in
                    Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
    before = events()
    child = subprocess.Popen([sys.executable, '-c',
        'blocks = [bytearray(4 * 1024 * 1024) for _ in range(128)]'])
    try:
        code = child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)
        raise AssertionError('Memory probe did not terminate within its bound')
    after = events()
    assert code == -9, f'Expected OOM victim SIGKILL, got {code}'
    assert int(after['oom_kill']) > int(before['oom_kill']), 'No kernel OOM event'
    print(json.dumps({'probe': 'MEMORY_CGROUP_OOM_ENFORCED', 'child_returncode': code,
                      'memory_events_before': before, 'memory_events_after': after}))
elif mode == 'pids':
    assert int(Path('/sys/fs/cgroup/pids.max').read_text()) <= 32
    children = []
    blocked = False
    try:
        for _ in range(40):  # Finite, not an unbounded fork bomb.
            try:
                children.append(subprocess.Popen([sys.executable, '-c',
                                                   'import time; time.sleep(10)']))
            except BlockingIOError:
                blocked = True
                break
    finally:
        for child in children:
            child.kill()
        for child in children:
            child.wait(timeout=3)
    assert blocked, 'Process cgroup limit failed'
    print(json.dumps({'probe': 'PIDS_LIMIT_ENFORCED', 'children': len(children)}))
elif mode == 'timeout':
    while True:
        time.sleep(1)
elif mode == 'recovery':
    assert not Path('/work/allowed').exists(), 'Scratch persisted across containers'
    print('FRESH_CONTAINER_RECOVERY_OK')
else:
    raise ValueError('Unknown probe mode')
