import sys
from pathlib import Path

import pytest

# Make the src layout importable without installation.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from god_agent.config import Config  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """A throwaway project directory."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def config(project):
    return Config.load(project)
