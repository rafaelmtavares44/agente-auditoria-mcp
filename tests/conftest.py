import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server.config import Limits, ServerConfig  # noqa: E402
from server.tools import AuditTools  # noqa: E402

SAMPLE_DIR = PROJECT_ROOT / "legacy_sample"
EXPECTED_FILE = PROJECT_ROOT / "evaluation" / "expected_findings.json"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def workspace(tmp_path):
    """Cópia isolada: <tmp>/project/legacy_sample (raiz), <tmp>/project/evaluation, <tmp>/project/output."""
    project = tmp_path / "project"
    shutil.copytree(SAMPLE_DIR, project / "legacy_sample")
    (project / "evaluation").mkdir()
    shutil.copy(EXPECTED_FILE, project / "evaluation" / "expected_findings.json")
    return project


@pytest.fixture
def make_tools(workspace):
    def _make(limits: Limits | None = None, run_id: str = "test_run") -> AuditTools:
        cfg = ServerConfig.create(workspace / "legacy_sample", workspace / "output", run_id, limits)
        return AuditTools(cfg)
    return _make


@pytest.fixture
def tools(make_tools):
    return make_tools()
