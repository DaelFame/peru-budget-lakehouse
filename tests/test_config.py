import os
import sys

# Ensure src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from config import get_optimal_memory_limit

def test_get_optimal_memory_limit_happy_path(monkeypatch):
    """
    Test get_optimal_memory_limit happy path (80% of RAM).
    Mocking 16 GB of physical RAM:
    16 GB = 17,179,869,184 bytes.
    With SC_PAGE_SIZE = 4096 bytes and SC_PHYS_PAGES = 4,194,304 pages.
    Optimal RAM allocation is 80% of 16 GB = 12.8 GB -> 12GB.
    """
    def mock_sysconf(name):
        if name == 'SC_PAGE_SIZE':
            return 4096
        elif name == 'SC_PHYS_PAGES':
            return 4194304
        raise ValueError(f"Unknown sysconf parameter: {name}")

    monkeypatch.setattr(os, "sysconf", mock_sysconf)
    
    limit = get_optimal_memory_limit()
    assert limit == "12GB"

def test_get_optimal_memory_limit_fallback_value_error(monkeypatch):
    """
    Test get_optimal_memory_limit fallback path (4GB) when os.sysconf raises a ValueError.
    """
    def mock_sysconf_raise_value_error(name):
        raise ValueError("Simulated ValueError reading sysconf")

    monkeypatch.setattr(os, "sysconf", mock_sysconf_raise_value_error)

    limit = get_optimal_memory_limit()
    assert limit == "4GB"

def test_get_optimal_memory_limit_fallback_attribute_error(monkeypatch):
    """
    Test get_optimal_memory_limit fallback path (4GB) when os.sysconf is not available (AttributeError).
    This simulates environments like Windows.
    """
    monkeypatch.delattr(os, "sysconf", raising=False)

    limit = get_optimal_memory_limit()
    assert limit == "4GB"
