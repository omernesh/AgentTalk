"""Unit tests for record_demo helper functions."""
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
