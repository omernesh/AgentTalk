"""
Unit tests for agenttalk/setup.py.

Tests use tmp_path fixture for all file I/O — does NOT modify the real
~/.claude/settings.json or %APPDATA%\\AgentTalk\\.

Requirements: HOOK-05
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Import the setup module
sys.path.insert(0, str(Path(__file__).parent.parent))
from agenttalk.setup import (
    register_hooks,
    _write_path_files,
    _is_agenttalk_hook_present,
    _merge_hook_into_array,
)

EXISTING_SETTINGS = {
    "hooks": {
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "powershell -Command \"Start-Sound.ps1\""
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "node \"C:/Users/omern/.claude/hooks/gsd-check-update.js\""
                    }
                ]
            }
        ]
    }
}


def _count_agenttalk_entries(inner_hooks: list, filename: str) -> int:
    """Count hook entries that reference both 'agenttalk' and the given filename."""
    return sum(
        1 for h in inner_hooks
        if 'agenttalk' in h.get('command', '').lower()
        and filename.lower() in h.get('command', '').lower()
    )


def _make_fake_pythonw(tmp_path: Path) -> Path:
    """Create a real fake pythonw.exe in tmp_path so resolve() works."""
    p = tmp_path / 'pythonw.exe'
    p.touch()
    return p


# ---------------------------------------------------------------------------
# Helper: call register_hooks with tmp_path isolation
# ---------------------------------------------------------------------------

def _call_register_hooks(tmp_path: Path, settings_dict: dict | None = None) -> Path:
    """
    Call register_hooks() with isolated tmp_path settings and AGENTTALK_DIR.
    Returns the settings_path used.
    """
    settings_path = tmp_path / 'settings.json'
    appdata_dir = tmp_path / 'appdata'
    fake_pythonw = _make_fake_pythonw(tmp_path)

    if settings_dict is not None:
        settings_path.write_text(json.dumps(settings_dict), encoding='utf-8')

    with patch('agenttalk.setup.AGENTTALK_DIR', appdata_dir):
        register_hooks(pythonw=fake_pythonw, settings_path=settings_path)

    return settings_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegisterHooksFreshSettings:

    def test_register_hooks_fresh_settings(self, tmp_path):
        """settings.json does not exist — register_hooks() creates it with both hooks."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=None)

        assert settings_path.exists()
        data = json.loads(settings_path.read_text(encoding='utf-8'))

        # Stop hook present
        stop_inner = data['hooks']['Stop'][0]['hooks']
        assert any(
            'stop_hook.py' in h['command'] for h in stop_inner
        ), "Stop hook command should reference stop_hook.py"
        assert any(h.get('async') is True for h in stop_inner if 'stop_hook.py' in h['command'])
        assert any(h.get('timeout') == 10 for h in stop_inner if 'stop_hook.py' in h['command'])

        # SessionStart hook present
        session_inner = data['hooks']['SessionStart'][0]['hooks']
        assert any(
            'session_start_hook.py' in h['command'] for h in session_inner
        ), "SessionStart hook command should reference session_start_hook.py"
        assert any(h.get('async') is True for h in session_inner if 'session_start_hook.py' in h['command'])
        assert any(h.get('timeout') == 10 for h in session_inner if 'session_start_hook.py' in h['command'])


class TestRegisterHooksPreservesExisting:

    def test_register_hooks_preserves_existing_stop(self, tmp_path):
        """Existing Stop powershell command must be preserved after register_hooks()."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)

        data = json.loads(settings_path.read_text(encoding='utf-8'))
        stop_inner = data['hooks']['Stop'][0]['hooks']

        # Original powershell command still there
        assert any('powershell' in h['command'] for h in stop_inner), \
            "Existing powershell Stop hook must be preserved"
        # AgentTalk stop hook also added
        assert any('stop_hook.py' in h['command'] for h in stop_inner), \
            "AgentTalk Stop hook must be added"
        # Total: 2 entries (original + agenttalk)
        assert len(stop_inner) == 2

    def test_register_hooks_preserves_existing_session_start(self, tmp_path):
        """Existing SessionStart node command must be preserved after register_hooks()."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)

        data = json.loads(settings_path.read_text(encoding='utf-8'))
        session_inner = data['hooks']['SessionStart'][0]['hooks']

        # Original node command still there
        assert any('node' in h['command'] for h in session_inner), \
            "Existing node SessionStart hook must be preserved"
        # AgentTalk session hook also added
        assert any('session_start_hook.py' in h['command'] for h in session_inner), \
            "AgentTalk SessionStart hook must be added"
        # Total: 2 entries (original + agenttalk)
        assert len(session_inner) == 2


class TestRegisterHooksIdempotent:

    def test_register_hooks_idempotent_stop(self, tmp_path):
        """Calling register_hooks() twice produces exactly 1 AgentTalk Stop entry."""
        # First call
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)
        # Second call (settings.json now exists with AgentTalk entry)
        with patch('agenttalk.setup.AGENTTALK_DIR', tmp_path / 'appdata'):
            register_hooks(
                pythonw=_make_fake_pythonw(tmp_path),
                settings_path=settings_path,
            )

        data = json.loads(settings_path.read_text(encoding='utf-8'))
        stop_inner = data['hooks']['Stop'][0]['hooks']
        count = _count_agenttalk_entries(stop_inner, 'stop_hook.py')
        assert count == 1, f"Expected exactly 1 AgentTalk Stop entry, got {count}"

    def test_register_hooks_idempotent_session_start(self, tmp_path):
        """Calling register_hooks() twice produces exactly 1 AgentTalk SessionStart entry."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)
        with patch('agenttalk.setup.AGENTTALK_DIR', tmp_path / 'appdata'):
            register_hooks(
                pythonw=_make_fake_pythonw(tmp_path),
                settings_path=settings_path,
            )

        data = json.loads(settings_path.read_text(encoding='utf-8'))
        session_inner = data['hooks']['SessionStart'][0]['hooks']
        count = _count_agenttalk_entries(session_inner, 'session_start_hook.py')
        assert count == 1, f"Expected exactly 1 AgentTalk SessionStart entry, got {count}"


class TestSettingsJsonFormat:

    def test_settings_json_no_bom(self, tmp_path):
        """Written settings.json must NOT start with a UTF-8 BOM."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)

        raw_bytes = settings_path.read_bytes()
        bom = b'\xef\xbb\xbf'
        assert not raw_bytes.startswith(bom), \
            "settings.json must not start with UTF-8 BOM (Claude Code JSON parser fails on BOM)"

    def test_settings_json_valid_json(self, tmp_path):
        """Written settings.json must parse as valid JSON without exception."""
        settings_path = _call_register_hooks(tmp_path, settings_dict=EXISTING_SETTINGS)

        content = settings_path.read_text(encoding='utf-8')
        # Should not raise
        data = json.loads(content)
        assert isinstance(data, dict)


class TestWritePathFiles:

    def test_write_path_files(self, tmp_path):
        """_write_path_files() writes pythonw_path.txt and service_path.txt with correct content."""
        fake_pythonw = _make_fake_pythonw(tmp_path)
        appdata_dir = tmp_path / 'appdata_test'

        with patch('agenttalk.setup.AGENTTALK_DIR', appdata_dir):
            _write_path_files(fake_pythonw)

        pythonw_txt = appdata_dir / 'pythonw_path.txt'
        service_txt = appdata_dir / 'service_path.txt'

        assert pythonw_txt.exists(), "pythonw_path.txt must be created"
        assert service_txt.exists(), "service_path.txt must be created"

        pythonw_content = pythonw_txt.read_text(encoding='utf-8')
        assert str(fake_pythonw.resolve()) == pythonw_content, \
            "pythonw_path.txt must contain the resolved pythonw.exe path"

        service_content = service_txt.read_text(encoding='utf-8')
        # service_path.txt should point to service.py (relative to setup.py location)
        assert 'service.py' in service_content, \
            "service_path.txt must contain a path referencing service.py"
