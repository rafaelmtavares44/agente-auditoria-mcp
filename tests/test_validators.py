"""Validação dos artefatos: detecção de alucinações e artefatos inválidos."""
import json

from agent.validators import validate_artifacts
from server.security_rules import analyze_source
from server.endpoint_extractor import extract_endpoints

from . import sim


def reference(root):
    lint, eps = [], []
    for f in ("auth_service.py", "order_api.py"):
        src = (root / f).read_text(encoding="utf-8")
        lint += analyze_source(src, f)
        eps += extract_endpoints(src, f)["endpoints"]
    return lint, eps


def write_all(out, findings=None, openapi=None, doc=sim.API_DOC, report="# Auditoria"):
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(findings or sim.findings_json(), encoding="utf-8")
    (out / "openapi.json").write_text(openapi or sim.openapi_json(), encoding="utf-8")
    (out / "api_documentation.md").write_text(doc, encoding="utf-8")
    (out / "audit_report.md").write_text(report, encoding="utf-8")


def run(workspace, **kw):
    root = workspace / "legacy_sample"
    out = workspace / "output" / "v"
    write_all(out, **kw)
    return validate_artifacts(out, root, *reference(root))


def test_valid_artifacts_pass(workspace):
    rep = run(workspace)
    assert rep.ok, rep.errors
    assert rep.stats["findings"]["confirmed_by_rule"] == 7


def test_confirmed_finding_without_linter_evidence_is_hallucination(workspace):
    fake = {"id": "F-99", "file": "order_api.py", "line": 30, "evidence": "class OrderIn(BaseModel):",
            "rule_id": "PY-SEC-002", "detection_source": "ast_rule", "category": "sql_injection",
            "severity": "high", "justification": "x", "recommendation": "y", "status": "confirmed_by_rule"}
    rep = run(workspace, findings=sim.findings_json([fake]))
    assert any("F-99" in e and "linter não produziu" in e for e in rep.errors)


def test_nonexistent_file_or_line(workspace):
    base = {"evidence": "x", "rule_id": None, "detection_source": "model", "category": "outro",
            "severity": "low", "justification": "x", "recommendation": "y", "status": "hypothesis"}
    rep = run(workspace, findings=sim.findings_json([
        {**base, "id": "F-A", "file": "inventado.py", "line": 1},
        {**base, "id": "F-B", "file": "order_api.py", "line": 9999}]))
    assert any("F-A" in e for e in rep.errors) and any("F-B" in e for e in rep.errors)


def test_hypothesis_from_model_is_allowed(workspace):
    hyp = {"id": "F-H", "file": "auth_service.py", "line": 70, "evidence": 'def me(authorization: str = Header(...)):',
           "rule_id": None, "detection_source": "model", "category": "broken_authentication",
           "severity": "high", "justification": "usa token sem verificação", "recommendation": "usar me_safe",
           "status": "hypothesis"}
    rep = run(workspace, findings=sim.findings_json([hyp]))
    assert rep.ok, rep.errors
    assert rep.stats["findings"]["from_model"] == 1


def test_invented_endpoint_in_openapi(workspace):
    extra = {"/admin/reset": {"post": {"responses": {"200": {"description": "ok"}}}}}
    rep = run(workspace, openapi=sim.openapi_json(extra))
    assert any("inventado POST /admin/reset" in e for e in rep.errors)


def test_invalid_openapi_and_missing_endpoint_warning(workspace):
    rep = run(workspace, openapi=json.dumps({"openapi": "3.1.0", "info": {"title": "x"}, "paths": {}}))
    assert any("inválido" in e for e in rep.errors)
    rep2 = run(workspace, openapi=json.dumps({"openapi": "3.1.0", "info": {"title": "x", "version": "1"}, "paths": {}}))
    assert rep2.ok and any("ausente" in w for w in rep2.warnings)


def test_omitted_linter_finding_is_warning(workspace):
    data = json.loads(sim.findings_json())
    data["findings"] = data["findings"][1:]
    rep = run(workspace, findings=json.dumps(data))
    assert rep.ok and any("omitido" in w for w in rep.warnings)


def test_missing_artifact(workspace):
    root = workspace / "legacy_sample"
    out = workspace / "output" / "vazio"
    out.mkdir(parents=True)
    rep = validate_artifacts(out, root, *reference(root))
    assert not rep.ok and len([e for e in rep.errors if "ausente" in e]) == 4
