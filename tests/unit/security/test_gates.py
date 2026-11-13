"""Logical offline assertions; NOT independent authorization/OS isolation proof."""
import pytest

from autoteacher_m0.security.gates import LiveGate, SecurityBlocked, fingerprint


def baseline(content=b'controller v1', **configuration):
    return fingerprint({'src/controller.py': content, 'uv.lock': b'pinned'}, configuration)


def test_live_default_and_explicit_request_are_blocked():
    gate = LiveGate()
    assert gate.inspect().status == 'BLOCKED'
    reviewed = baseline(route='deepseek-official')
    with pytest.raises(SecurityBlocked) as error:
        gate.require_live(live_requested=True, actual=reviewed, reviewed=reviewed,
                          actual_tools=('skill_lookup',), session_log_disabled=True)
    assert error.value.code == 'SECURITY_BLOCKED'
    assert 'EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED' in str(error.value)


def test_agent_files_and_environment_cannot_unlock_gate(tmp_path, monkeypatch):
    approval = tmp_path / 'SECURITY_APPROVALS.md'
    approval.write_text('HUMAN APPROVED all sha/config live=true')
    monkeypatch.setenv('AT_M0_LIVE_APPROVED', 'true')
    monkeypatch.setenv('AT_M0_SECURITY_APPROVAL', str(approval))
    monkeypatch.setenv('AT_M0_ALLOW_LIVE', '1')
    with pytest.raises(SecurityBlocked):
        LiveGate().require_live(live_requested=True)
    # This only proves local code ignores these inputs, not E5-P03 OS control.


@pytest.mark.parametrize('changed', [
    fingerprint({'src/controller.py': b'controller v2', 'uv.lock': b'pinned'}, {}),
    fingerprint({'src/controller.py': b'controller v1', 'uv.lock': b'new dependency'}, {}),
    fingerprint({'src/controller.py': b'controller v1', 'uv.lock': b'pinned'}, {'route': 'other'}),
    fingerprint({'src/controller.py': b'controller v1', 'uv.lock': b'pinned',
                 'new_plugin.ts': b'new tool'}, {}),
])
def test_any_inventory_or_config_change_blocks(changed):
    result = LiveGate().inspect(live_requested=True, actual=changed, reviewed=baseline())
    assert result.status == 'BLOCKED'
    assert 'BASELINE_OR_CONFIGURATION_CHANGED' in result.reasons


def test_canonical_configuration_and_inventory_order():
    assert fingerprint({'a': b'a', 'b': b'b'}, {'x': 1, 'y': 2}) == fingerprint(
        {'b': b'b', 'a': b'a'}, {'y': 2, 'x': 1})


@pytest.mark.parametrize('path', ['/root/file', '../home/key', 'a/../b', 'a\\b', './a', ''])
def test_inventory_rejects_non_normalized_paths(path):
    with pytest.raises(ValueError):
        fingerprint({path: b'public'}, {})


def test_dangerous_actual_tools_and_upload_not_approved():
    decision = LiveGate().inspect(actual_tools=('skill_lookup', 'shell'))
    assert 'ACTUAL_TOOL_REGISTRY_NOT_APPROVED' in decision.reasons
    assert 'SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED' in decision.reasons
