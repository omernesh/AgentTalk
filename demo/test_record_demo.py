"""Unit tests for record_demo helper functions."""
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import requests
from record_demo import check_agenttalk, check_ffmpeg, check_prerequisites, detect_audio_device


def test_check_ffmpeg_success():
    with patch("record_demo.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert check_ffmpeg() is True


def test_check_ffmpeg_missing():
    with patch("record_demo.subprocess.run", side_effect=FileNotFoundError):
        assert check_ffmpeg() is False


def test_check_ffmpeg_bad_exit():
    with patch("record_demo.subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
        assert check_ffmpeg() is False


def test_check_agenttalk_success():
    with patch("record_demo.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        assert check_agenttalk() is True


def test_check_agenttalk_down():
    with patch("record_demo.requests.get", side_effect=requests.exceptions.ConnectionError):
        assert check_agenttalk() is False


# Sample FFmpeg dshow output (written to stderr)
FFMPEG_DSHOW_OUTPUT = b"""
[dshow @ 0000] DirectShow audio devices (some may be both input and output)
[dshow @ 0000]  "Microphone Array (Realtek(R) Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{33D9A762}..."
[dshow @ 0000]  "Stereo Mix (Realtek(R) Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{33D9A762}..."
"""

FFMPEG_DSHOW_MIC_ONLY = b"""
[dshow @ 0000] DirectShow audio devices
[dshow @ 0000]  "Microphone (USB Audio Device)"
"""


def test_detect_stereo_mix():
    with patch("record_demo.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=FFMPEG_DSHOW_OUTPUT)
        device = detect_audio_device()
    assert device == "Stereo Mix (Realtek(R) Audio)"


def test_detect_no_loopback_exits():
    with patch("record_demo.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=FFMPEG_DSHOW_MIC_ONLY)
        with pytest.raises(SystemExit):
            detect_audio_device()


from record_demo import build_ffmpeg_cmd


def test_ffmpeg_cmd_contains_gdigrab():
    cmd = build_ffmpeg_cmd("Stereo Mix (Realtek)", Path("demo/01-auto.mp4"))
    assert "-f" in cmd
    assert "gdigrab" in cmd


def test_ffmpeg_cmd_contains_audio_device():
    cmd = build_ffmpeg_cmd("Stereo Mix (Realtek)", Path("demo/01-auto.mp4"))
    joined = " ".join(cmd)
    assert "Stereo Mix (Realtek)" in joined


def test_ffmpeg_cmd_output_path():
    cmd = build_ffmpeg_cmd("Stereo Mix", Path("demo/clip.mp4"))
    assert str(Path("demo/clip.mp4")) == cmd[-1]


from record_demo import reset_speech_mode, reset_voice


def test_reset_voice():
    with patch("record_demo.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        reset_voice("af_heart")
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["voice"] == "af_heart"


def test_reset_speech_mode():
    with patch("record_demo.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        reset_speech_mode("auto")
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["speech_mode"] == "auto"
