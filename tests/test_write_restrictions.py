"""Restrições de escrita de artefatos."""
import json

import pytest

from server.config import Limits, ServerConfig
from server.tools import ToolInputError

VALID_FINDINGS = {"findings": [{
    "id": "F-01", "file": "order_api.py", "line": 63, "evidence": "eval(payload.expression)",
    "rule_id": "PY-SEC-004", "detection_source": "ast_rule", "category": "code_injection",
    "severity": "high", "justification": "eval em campo do corpo", "recommendation": "usar literal_eval",
    "status": "confirmed_by_rule"}]}
VALID_OPENAPI = {"openapi": "3.1.0", "info": {"title": "Demo", "version": "0.1.0"}, "paths": {}}


def test_write_allowed_artifacts(tools, workspace):
    for name, content in [("findings.json", json.dumps(VALID_FINDINGS)),
                          ("openapi.json", json.dumps(VALID_OPENAPI)),
                          ("audit_report.md", "# Relatório\n"),
                          ("api_documentation.md", "# API\n")]:
        res = tools.write_documentation_file(name, content)
        assert res.status == "written"
        assert res.relative_path == f"output/test_run/{name}"
        assert (workspace / "output" / "test_run" / name).is_file()
        assert len(res.sha256) == 64


@pytest.mark.parametrize("name", [
    "../../.env", "..\\x.md", "sub/findings.json", "/tmp/findings.json",
    "C:\\temp\\findings.json", "relatorio.txt", "script.py", "findings.JSON", ".env", "",
])
def test_write_rejects_other_names(tools, workspace, name):
    with pytest.raises(ToolInputError):
        tools.write_documentation_file(name, "conteúdo")
    assert not (workspace / ".env").exists()


def test_write_never_touches_analysis_root(tools, workspace):
    before = sorted(p.name for p in (workspace / "legacy_sample").iterdir())
    tools.write_documentation_file("audit_report.md", "# ok")
    assert sorted(p.name for p in (workspace / "legacy_sample").iterdir()) == before


def test_invalid_json_is_rejected(tools):
    with pytest.raises(ToolInputError, match="JSON inválido"):
        tools.write_documentation_file("openapi.json", "{nao é json")


def test_findings_schema_is_enforced(tools):
    bad = {"findings": [{**VALID_FINDINGS["findings"][0], "status": "certeza absoluta"}]}
    with pytest.raises(ToolInputError, match="status"):
        tools.write_documentation_file("findings.json", json.dumps(bad))
    bad_line = {"findings": [{**VALID_FINDINGS["findings"][0], "line": 0}]}
    with pytest.raises(ToolInputError):
        tools.write_documentation_file("findings.json", json.dumps(bad_line))


def test_openapi_minimal_structure(tools):
    with pytest.raises(ToolInputError, match="3.1"):
        tools.write_documentation_file("openapi.json", json.dumps({**VALID_OPENAPI, "openapi": "2.0"}))
    with pytest.raises(ToolInputError, match="paths"):
        tools.write_documentation_file("openapi.json", json.dumps({"openapi": "3.1.0", "info": {"title": "a", "version": "1"}}))


def test_size_limit(make_tools):
    tools = make_tools(Limits(max_output_bytes=100))
    with pytest.raises(ToolInputError, match="limite"):
        tools.write_documentation_file("audit_report.md", "x" * 200)


def test_secrets_are_redacted_before_writing(tools, workspace):
    res = tools.write_documentation_file(
        "audit_report.md", 'Evidência: DATABASE_URL = "postgresql://u:SenhaFicticia2024@h/db"\n')
    text = (workspace / "output" / "test_run" / "audit_report.md").read_text(encoding="utf-8")
    assert "SenhaFicticia2024" not in text
    assert res.redactions_applied is True


def test_config_rejects_overlap_and_bad_run_id(workspace):
    root = workspace / "legacy_sample"
    with pytest.raises(ValueError):
        ServerConfig.create(root, root, "x")          # saída dentro da raiz
    with pytest.raises(ValueError):
        ServerConfig.create(root, workspace / "output", "../fora")
    with pytest.raises(ValueError):
        ServerConfig.create(root, workspace / "output", "a b")
