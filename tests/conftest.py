import os
import sys
from pathlib import Path
from unittest.mock import patch

# 1. Inject the 'src' directory into sys.path so tests and imported modules can locate 'config' and other modules
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 2. Globally patch Path.mkdir to mock data/hardware creations, but allow pytest's internal cache dirs to be created safely.
original_mkdir = Path.mkdir

def custom_mkdir(self, *args, **kwargs):
    if ".pytest_cache" in str(self):
        return original_mkdir(self, *args, **kwargs)
    # Intercept and mock all other directory creations (e.g., Lakehouse data/medallion directories)
    return None

mkdir_patcher = patch("pathlib.Path.mkdir", custom_mkdir)
mock_mkdir = mkdir_patcher.start()

def pytest_unconfigure(config):
    """Clean up the global patcher after all tests are finished."""
    mkdir_patcher.stop()
