import pytest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.helpers.context_manager import TestContextManager

@pytest.fixture
def context_manager():
    return TestContextManager()

@pytest.fixture
def test_data_dir():
    return Path("data/test_data")
