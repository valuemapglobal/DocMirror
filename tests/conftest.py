"""
Test suite for docmirror package.

Test structure:
    tests/
    ├── conftest.py          # Shared fixtures
    ├── test_imports.py      # Import smoke tests
    ├── test_settings.py     # Configuration tests
    └── test_dispatcher.py   # Dispatcher routing tests
"""
import os
import sys

# Ensure the project root is on sys.path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
