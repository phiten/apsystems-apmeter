"""Test setup: make the HA-free protocol module importable without Home Assistant."""

from __future__ import annotations

from pathlib import Path
import sys

# sem_tcp.py has no Home Assistant imports, so it is imported as a plain module.
# Importing it through the package would run __init__.py, which needs Home Assistant.
INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "apsystemsSEM"
sys.path.insert(0, str(INTEGRATION_DIR))
