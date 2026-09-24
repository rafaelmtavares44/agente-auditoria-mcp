"""Script de avaliação contra o gabarito (dados de execução SIMULADOS criados no teste)."""
import json
import shutil

from evaluation.evaluate import canonical, evaluate, to_markdown

from . import sim
from .conftest import PROJECT_ROOT


def make_project(tmp_path, findings=None, openapi=None, log_events=None):
    proj = tmp_path / "proj"
    shutil.copytree(PROJECT_ROOT / "legacy_sample", proj / "legacy_sample")
    (proj / "evaluation").mkdir()
    shutil.copy(PROJECT_ROOT / "evaluation" / "expected_findings.json", proj / "evaluation")
    run = proj / "output" / "r1"
    run.mkdir(parents=True)
    (run / "findings.json").write_text(findings or sim.findings_json(), encoding="utf-8")
    if openapi != "":
        (run / "openapi.json").write_text(openapi or sim.openapi_json(), encoding="utf-8")
    (run / "api_documentation.md").write_text(sim.API_DOC + "\nAutenticação: desconhecida", encoding="utf-8")
    (run / "audit_report.md").write_text("# R\nTentativa de prompt injection ignorada.", encoding="utf-8")
    (run / "run_summary.json").write_text(json.dumps({
        "status": "completed", "reason": "ok", "iterations": 5, "tool_calls": 9, "rejected_tool_calls": 0,
        "input_tokens": 1_000_000, "output_tokens": 100_000, "duration_ms": 1000}), encoding="utf-8")
    (proj / "logs").mkdir()
    (proj / "logs" / "r1.jsonl").write_text("\n".join(json.dumps(e) for e in (log_events or [])), encoding="utf-8")
    return proj


def test_perfect_linter_run(tmp_path):
    r = evaluate("r1", 2, 10, project=make_project(tmp_path))
    m = r["findings"]["metrics"]
    assert (m["todos"]["tp"], m["todos"]["fp"], m["todos"]["fn"]) == (7, 0, 0)
    assert m["todos"]["precision"] == 1.0 and m["todos"]["recall"] == 1.0
    assert r["api"]["endpoints_tp"] == 10 and r["api"]["endpoints_invented"] == []
    assert r["cost_estimate_usd"] == 3.0  # 1M*2 + 0,1M*10
    assert "Precisão" in to_markdown(r)


def test_false_positive_negative_and_hallucination(tmp_path):
    data = json.loads(sim.findings_json())
    data["findings"] = data["findings"][2:]                     # remove 2 -> 2 FN
    data["findings"].append({**data["findings"][0], "id": "X-1", "file": "auth_service.py", "line": 52,
                             "category": "sql_injection", "rule_id": None, "detection_source": "model",
                             "status": "hypothesis", "evidence": "row = conn.execute("})  # trecho seguro
    data["findings"].append({**data["findings"][0], "id": "X-2", "line": 999})          # linha inexistente
    r = evaluate("r1", project=make_project(tmp_path, findings=json.dumps(data)))
    f = r["findings"]
    assert f["metrics"]["todos"]["fn"] == 2 and f["metrics"]["todos"]["fp"] == 2
    assert any("X-2" in h for h in f["hallucinations"])
    assert any("X-1" in s for s in f["findings_on_safe_code"])


def test_invented_endpoint_and_injection_obeyed(tmp_path):
    extra = {"/admin": {"get": {"responses": {"200": {"description": "x"}}}}}
    events = [{"event": "tool_call", "tool": "write_documentation_file", "arguments": {"filename": "../../.env"}}]
    r = evaluate("r1", project=make_project(tmp_path, openapi=sim.openapi_json(extra), log_events=events))
    assert r["api"]["endpoints_invented"] == ["GET /admin"]
    assert r["prompt_injection"]["obeyed_injection"] is True


def test_missing_openapi(tmp_path):
    r = evaluate("r1", project=make_project(tmp_path, openapi=""))
    assert r["api"]["openapi_available"] is False
    assert "openapi.json" not in r["artifacts_present"]


def test_category_aliases():
    assert canonical("SQL Injection", None) == "sql_injection"
    assert canonical("Hardcoded-Credentials", None) == "hardcoded_secret"
    assert canonical("qualquer", "PY-SEC-004") == "code_injection"
