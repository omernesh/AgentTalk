"""Unit tests for record_demo helper functions."""
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import requests
from record_demo import check_agenttalk, check_ffmpeg, check_prerequisites


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
