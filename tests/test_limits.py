"""Limites de tamanho, quantidade e orçamento de leitura."""
import pytest

from server.config import Limits
from server.tools import ToolInputError


def test_file_larger_than_limit_is_refused(make_tools, workspace):
    (workspace / "legacy_sample" / "grande.py").write_text("x = 1\n" * 5000)  # 30 KB
    tools = make_tools(Limits(max_file_bytes=10_000))
    with pytest.raises(ToolInputError, match="excede o limite"):
        tools.read_source_code("grande.py")
    scan = tools.scan_project_files()
    assert any("grande.py" in w for w in scan.warnings)


def test_total_read_budget(make_tools):
    tools = make_tools(Limits(max_total_read_bytes=3_000))
    tools.read_source_code("auth_service.py", 1, 40)
    with pytest.raises(ToolInputError, match="Orçamento"):
        for _ in range(10):
            tools.read_source_code("order_api.py")


def test_max_files_truncates_with_warning(make_tools, workspace):
    for i in range(5):
        (workspace / "legacy_sample" / f"extra_{i}.py").write_text("x = 1\n")
    tools = make_tools(Limits(max_files=3))
    scan = tools.scan_project_files()
    assert scan.total_files == 3
    assert any("Limite" in w for w in scan.warnings)


def test_lines_per_read_are_capped(make_tools, workspace):
    (workspace / "legacy_sample" / "longo.py").write_text("x = 1\n" * 1000)
    result = make_tools().read_source_code("longo.py", 1, 1000)
    assert result.end_line - result.start_line + 1 == 400


def test_too_many_paths_in_one_call(tools):
    with pytest.raises(ToolInputError):
        tools.run_security_linter(["order_api.py"] * 51)
