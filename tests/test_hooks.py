"""
Unit tests for agenttalk/hooks/stop_hook.py and session_start_hook.py.

Tests import hooks as modules via importlib.util to avoid venv path issues.
All external calls (urllib.request.urlopen, os.kill, subprocess.Popen) are mocked.

Requirements: HOOK-01, HOOK-02, HOOK-03, HOOK-04
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import importlib.util
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_hook(hook_name: str):
    """Load a hook module from its file path, bypassing sys.path."""
    hooks_dir = Path(__file__).parent.parent / 'agenttalk' / 'hooks'
    spec = importlib.util.spec_from_file_location(
        hook_name, hooks_dir / f'{hook_name}.py'
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_stdin(payload: dict) -> MagicMock:
    """Create a mock stdin buffer returning the given payload as UTF-8 bytes."""
    raw = json.dumps(payload).encode('utf-8')
    m = MagicMock()
    m.read.return_value = raw
    return m


def _make_stdin_bytes(raw: bytes) -> MagicMock:
    """Create a mock stdin buffer returning raw bytes directly."""
    m = MagicMock()
    m.read.return_value = raw
    return m


# ---------------------------------------------------------------------------
# stop_hook tests
# ---------------------------------------------------------------------------

class TestStopHook:

    def test_stop_hook_guard_stop_hook_active(self):
        """When stop_hook_active is True, urlopen must NOT be called."""
        stop_hook = _load_hook('stop_hook')
        payload = {'stop_hook_active': True, 'last_assistant_message': 'Hello'}

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('urllib.request.urlopen') as mock_urlopen:
            with pytest.raises(SystemExit) as exc_info:
                stop_hook.main()

        assert exc_info.value.code == 0
        mock_urlopen.assert_not_called()

    def test_stop_hook_empty_message(self):
        """When last_assistant_message is empty, urlopen must NOT be called."""
        stop_hook = _load_hook('stop_hook')
        payload = {'stop_hook_active': False, 'last_assistant_message': ''}

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('urllib.request.urlopen') as mock_urlopen:
            with pytest.raises(SystemExit) as exc_info:
                stop_hook.main()

        assert exc_info.value.code == 0
        mock_urlopen.assert_not_called()

    def test_stop_hook_non_ascii_payload(self):
        """Non-ASCII UTF-8 payloads must not raise UnicodeDecodeError and urlopen IS called."""
        stop_hook = _load_hook('stop_hook')
        payload = {
            'stop_hook_active': False,
            'last_assistant_message': 'café naïve résumé',
        }
        raw = json.dumps(payload).encode('utf-8')

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin_bytes(raw)

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
            with pytest.raises(SystemExit) as exc_info:
                stop_hook.main()

        assert exc_info.value.code == 0
        mock_urlopen.assert_called_once()

    def test_stop_hook_posts_correct_body(self):
        """urlopen must be called with correct URL and body containing the message text."""
        stop_hook = _load_hook('stop_hook')
        payload = {
            'stop_hook_active': False,
            'last_assistant_message': 'Hello world.',
        }

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        captured_request = {}

        def capture_urlopen(req, timeout=None):
            captured_request['req'] = req
            return mock_response

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('urllib.request.urlopen', side_effect=capture_urlopen):
            with pytest.raises(SystemExit) as exc_info:
                stop_hook.main()

        assert exc_info.value.code == 0
        req = captured_request['req']
        assert req.full_url == 'http://localhost:5050/speak'
        body = json.loads(req.data.decode('utf-8'))
        assert body == {'text': 'Hello world.'}


# ---------------------------------------------------------------------------
# session_start_hook tests
# ---------------------------------------------------------------------------

class TestSessionStartHook:

    def test_session_start_hook_no_launch_when_running(self, tmp_path):
        """When service is already running (os.kill succeeds), Popen must NOT be called."""
        session_hook = _load_hook('session_start_hook')
        payload = {'source': 'startup'}

        # Create a real PID file so PID_FILE.exists() returns True
        pid_file = tmp_path / 'service.pid'
        pid_file.write_text('12345', encoding='utf-8')

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        # os.kill(pid, 0) returning None means process exists
        with patch.object(sys, 'stdin', mock_stdin), \
             patch('os.kill', return_value=None), \
             patch('subprocess.Popen') as mock_popen, \
             patch.object(session_hook, 'PID_FILE', pid_file):
            with pytest.raises(SystemExit) as exc_info:
                session_hook.main()

        assert exc_info.value.code == 0
        mock_popen.assert_not_called()

    def test_session_start_hook_no_launch_on_resume(self):
        """When source is 'resume', Popen must NOT be called (source filter exits early)."""
        session_hook = _load_hook('session_start_hook')
        payload = {'source': 'resume'}

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('subprocess.Popen') as mock_popen:
            with pytest.raises(SystemExit) as exc_info:
                session_hook.main()

        assert exc_info.value.code == 0
        mock_popen.assert_not_called()

    def test_session_start_hook_launches_when_not_running(self, tmp_path):
        """When service is not running (ProcessLookupError), Popen IS called with DETACHED_PROCESS."""
        session_hook = _load_hook('session_start_hook')
        payload = {'source': 'startup'}

        # Create real path files in tmp_path
        pythonw_path = tmp_path / 'pythonw.exe'
        pythonw_path.touch()
        service_path = tmp_path / 'service.py'
        service_path.touch()

        # Create real PID file with a nonexistent PID
        pid_file = tmp_path / 'service.pid'
        pid_file.write_text('99999', encoding='utf-8')

        # Create real path config files
        pythonw_path_file = tmp_path / 'pythonw_path.txt'
        pythonw_path_file.write_text(str(pythonw_path), encoding='utf-8')
        service_path_file = tmp_path / 'service_path.txt'
        service_path_file.write_text(str(service_path), encoding='utf-8')

        mock_stdin = MagicMock()
        mock_stdin.buffer = _make_stdin(payload)

        def kill_raises(*args, **kwargs):
            raise ProcessLookupError()

        with patch.object(sys, 'stdin', mock_stdin), \
             patch('os.kill', side_effect=kill_raises), \
             patch('subprocess.Popen') as mock_popen, \
             patch.object(session_hook, 'PID_FILE', pid_file), \
             patch.object(session_hook, 'PYTHONW_PATH_FILE', pythonw_path_file), \
             patch.object(session_hook, 'SERVICE_PATH_FILE', service_path_file):
            with pytest.raises(SystemExit) as exc_info:
                session_hook.main()

        assert exc_info.value.code == 0
        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        # Verify DETACHED_PROCESS flag is present in creationflags
        creationflags = call_kwargs.kwargs.get('creationflags', call_kwargs[1].get('creationflags', 0))
        assert creationflags & subprocess.DETACHED_PROCESS
