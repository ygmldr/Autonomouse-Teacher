"""External sandbox assertions, not host-launching or Live authorization tests.

Run only in the separately restricted Podman container. A standard offline run
skips when the external /input/host_paths.json mount is absent; never claims E5
passed because a logical unit test or environment variable was supplied.
"""
import os
from pathlib import Path
import runpy

import pytest


@pytest.mark.skipif(not Path('/input/host_paths.json').is_file(),
                    reason='Requires external public probe input mount; no host fallback')
def test_actual_os_negative_probe():
    assert os.getuid() == 65534, 'Probe must run under the external non-root launcher'
    source = Path(__file__).resolve().parents[3] / 'fixtures/sandbox/exercise.py'
    runpy.run_path(str(source), run_name='__main__')
