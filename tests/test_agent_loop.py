"""Ciclo do agente com MODELO SIMULADO + servidor MCP REAL (subprocesso stdio).

As respostas do modelo são roteiros (tests/sim.py): validam o orquestrador,
não o comportamento de um modelo real.
"""

import dataclasses
import json

import anthropic
import httpx2
import pytest

from agent.config import AgentLimits, AgentSettings
from agent.mcp_client import build_server_params
from agent.orchestrator import AuditAgent

from . import sim


def make_agent(workspace, backend, **limit_overrides):
    limits = dataclasses.replace(AgentLimits(), **limit_overrides)
    settings = AgentSettings(model=sim.SIM_MODEL, api_key=None, limits=limits)
    return AuditAgent(settings, backend, workspace / "legacy_sample", workspace / "output",
                      workspace / "logs", run_id="sim_run")


def read_log(agent):
    return [json.loads(line) for line in agent.log.path.read_text(encoding="utf-8").splitlines()]


def events(agent, name):
    return [e for e in read_log(agent) if e["event"] == name]


@pytest.mark.anyio
async def test_happy_path_completes_and_validates(workspace):
    backend = sim.FakeBackend(sim.happy_path_steps())
    agent = make_agent(workspace, backend)
    result = await agent.run("audite")

    assert result.status == "completed", result
    assert result.validation["ok"] is True
    assert result.tool_calls == 7 and result.iterations == 3
    assert (result.input_tokens, result.output_tokens) == (300, 150)
    out = workspace / "output" / "sim_run"
    for name in ("findings.json", "openapi.json", "api_documentation.md", "audit_report.md", "run_summary.json"):
        assert (out / name).is_file()
    names = [e["event"] for e in read_log(agent)]
    assert names[0] == "run_started" and names[-1] == "run_finished"
    assert names.count("tool_call") == 7 and names.count("tool_result") == 7
    assert "validation" in names


@pytest.mark.anyio
async def test_every_tool_use_gets_matching_tool_result(workspace):
    backend = sim.FakeBackend(sim.happy_path_steps())
    await make_agent(workspace, backend).run("audite")
    # 2ª chamada ao modelo recebeu: [user, assistant(tool_use x3), user(tool_result x3)]
    history = backend.calls[1]["messages"]
    tool_ids = [b["id"] for b in history[1]["content"] if b["type"] == "tool_use"]
    result_ids = [b["tool_use_id"] for b in history[2]["content"]]
    assert history[2]["role"] == "user" and tool_ids == result_ids == ["tu_1", "tu_2", "tu_3"]
    assert all(b["type"] == "tool_result" and not b["is_error"] for b in history[2]["content"])
    # ferramentas enviadas ao modelo no formato da Messages API
    assert {t["name"] for t in backend.calls[0]["tools"]} == {
        "scan_project_files", "read_source_code", "run_security_linter",
        "extract_api_endpoints", "write_documentation_file"}
    assert all("input_schema" in t for t in backend.calls[0]["tools"])


@pytest.mark.anyio
async def test_model_saying_done_is_not_success(workspace):
    backend = sim.FakeBackend([sim.msg([sim.text("Pronto, auditoria concluída!")], "end_turn")], repeat_last=True)
    agent = make_agent(workspace, backend)
    result = await agent.run("audite")
    assert result.status == "failed"
    assert any("ausente" in e for e in result.validation["errors"])
    # houve feedback de validação ao modelo antes de desistir
    feedback = [m for m in backend.calls[-1]["messages"] if m["role"] == "user" and isinstance(m["content"], str)
                and "validação automática" in m["content"]]
    assert len(feedback) == AgentLimits().max_validation_feedback


@pytest.mark.anyio
async def test_unknown_tool_and_bad_arguments_are_rejected_before_server(workspace):
    steps = [
        sim.msg([sim.tool("a", "run_shell", {"cmd": "del *"}),
                 sim.tool("b", "read_source_code", {"path": 123}),
                 sim.tool("c", "read_source_code", {"path": "order_api.py", "start_line": 0})], "tool_use"),
        sim.msg([sim.text("ok")], "end_turn"),
    ]
    backend = sim.FakeBackend(steps + [sim.msg([sim.text("ok")], "end_turn")] * 3)
    agent = make_agent(workspace, backend)
    result = await agent.run("audite")
    assert result.rejected_tool_calls == 3
    rejected = events(agent, "tool_rejected")
    assert [e["tool"] for e in rejected] == ["run_shell", "read_source_code", "read_source_code"]
    assert "allowlist" in rejected[0]["reason"]
    assert events(agent, "tool_result") == []  # nada chegou ao servidor
    results = backend.calls[1]["messages"][2]["content"]
    assert all(r["is_error"] for r in results)


@pytest.mark.anyio
async def test_policy_violations_blocked_by_server(workspace):
    steps = [
        sim.msg([sim.tool("a", "read_source_code", {"path": "../evaluation/expected_findings.json"}),
                 sim.tool("b", "write_documentation_file", {"filename": "../../.env", "content": "x=1"})],
                "tool_use"),
    ] + [sim.msg([sim.text("fim")], "end_turn")] * 3
    backend = sim.FakeBackend(steps)
    agent = make_agent(workspace, backend)
    await agent.run("audite")
    results = backend.calls[1]["messages"][2]["content"]
    assert all(r["is_error"] for r in results)
    assert not (workspace / ".env").exists()
    everything = json.dumps(backend.calls, ensure_ascii=False)
    assert "EXP-01" not in everything  # conteúdo do gabarito nunca chegou ao modelo


@pytest.mark.anyio
async def test_iteration_limit(workspace):
    backend = sim.FakeBackend([sim.msg([sim.tool("x", "scan_project_files", {})], "tool_use")], repeat_last=True)
    result = await make_agent(workspace, backend, max_iterations=3).run("audite")
    assert result.status == "limit_reached" and "iterações" in result.reason
    assert result.iterations == 3


@pytest.mark.anyio
async def test_tool_call_limit_still_answers_every_tool_use(workspace):
    three = sim.msg([sim.tool(f"t{i}", "scan_project_files", {}) for i in range(3)], "tool_use")
    backend = sim.FakeBackend([three])
    agent = make_agent(workspace, backend, max_tool_calls=2)
    result = await agent.run("audite")
    assert result.status == "limit_reached" and result.tool_calls == 2
    assert len(events(agent, "tool_result")) == 2
    assert len(events(agent, "tool_rejected")) == 1


@pytest.mark.anyio
async def test_token_budget(workspace):
    backend = sim.FakeBackend([sim.msg([sim.tool("x", "scan_project_files", {})], "tool_use", inp=100, out=50)],
                              repeat_last=True)
    result = await make_agent(workspace, backend, max_total_tokens=150).run("audite")
    assert result.status == "limit_reached" and "tokens" in result.reason
    assert result.iterations == 1


@pytest.mark.anyio
async def test_timeout_stops_run_and_closes_server(workspace):
    backend = sim.FakeBackend([sim.msg([sim.text("...")], "end_turn")], delay=5)
    agent = make_agent(workspace, backend, timeout_seconds=1)
    result = await agent.run("audite")
    assert result.status == "limit_reached" and "tempo" in result.reason
    assert result.duration_ms < 4000
    assert events(agent, "run_finished")[0]["status"] == "limit_reached"


@pytest.mark.anyio
async def test_truncated_response_does_not_execute_partial_tool_call(workspace):
    steps = [sim.msg([sim.tool("cut", "write_documentation_file", {"filename": "audit_report.md"})], "max_tokens")]
    steps += sim.happy_path_steps()
    backend = sim.FakeBackend(steps)
    agent = make_agent(workspace, backend)
    result = await agent.run("audite")
    assert result.status == "completed"
    assert events(agent, "response_truncated")
    reply = backend.calls[1]["messages"][2]["content"][0]
    assert reply["tool_use_id"] == "cut" and reply["is_error"] and "cortada" in reply["content"]
    assert "cut" not in [e["call_id"] for e in events(agent, "tool_call")]


@pytest.mark.anyio
async def test_api_error_after_retries_fails_cleanly(workspace):
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    agent = make_agent(workspace, sim.FakeBackend([err]))
    result = await agent.run("audite")
    assert result.status == "failed" and "APIConnectionError" in result.reason


@pytest.mark.anyio
async def test_logs_are_jsonl_with_timezone_and_sanitized(workspace):
    secret = 'api_key = "sk-ant-api03-SEGREDOFICTICIO000000"'
    steps = [sim.msg([sim.text(f"Vou registrar {secret}"),
                      sim.tool("w", "write_documentation_file", {"filename": "audit_report.md", "content": secret})],
                     "tool_use")] + [sim.msg([sim.text("fim")], "end_turn")] * 3
    agent = make_agent(workspace, sim.FakeBackend(steps))
    await agent.run("audite")
    raw = agent.log.path.read_text(encoding="utf-8")
    assert "SEGREDOFICTICIO" not in raw
    for record in read_log(agent):
        assert record["run_id"] == "sim_run" and record["ts"][-6] in "+-"  # ISO com fuso
    written = (workspace / "output" / "sim_run" / "audit_report.md").read_text(encoding="utf-8")
    assert "SEGREDOFICTICIO" not in written


def test_server_subprocess_env_has_no_api_key(workspace, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-FICTICIA")
    params = build_server_params(workspace / "legacy_sample", workspace / "output", "x")
    assert "ANTHROPIC_API_KEY" not in (params.env or {})


def test_settings_require_key_and_model(monkeypatch):
    monkeypatch.setattr("agent.config.load_dotenv", lambda path: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AgentSettings.from_env()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(ValueError, match="ANTHROPIC_MODEL"):
        AgentSettings.from_env()
    monkeypatch.setenv("ANTHROPIC_MODEL", "algum-modelo")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "0")
    with pytest.raises(ValueError):
        AgentSettings.from_env()


@pytest.mark.anyio
async def test_whitespace_text_blocks_are_not_sent_back(workspace):
    steps = [sim.msg([sim.text("\n\n"), sim.tool("a", "scan_project_files", {}), sim.text("  ")], "tool_use")]
    steps += sim.happy_path_steps()
    backend = sim.FakeBackend(steps)
    result = await make_agent(workspace, backend).run("audite")
    assert result.status == "completed"
    sent = backend.calls[1]["messages"][1]["content"]
    assert [b["type"] for b in sent] == ["tool_use"]


@pytest.mark.anyio
async def test_bad_request_is_logged_with_message_and_request_dump(workspace):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.BadRequestError("messages: text content blocks must contain non-whitespace text",
                                    response=httpx2.Response(400, request=req), body=None)
    agent = make_agent(workspace, sim.FakeBackend([err]))
    result = await agent.run("audite")
    assert result.status == "failed" and "400" in result.reason and "non-whitespace" in result.reason
    ev = events(agent, "model_error")[0]
    assert ev["status_code"] == 400 and ev["request_dump"].endswith("_failed_request.json")
    assert (workspace / "logs" / ev["request_dump"]).is_file()


@pytest.mark.anyio
async def test_console_progress_echo(workspace):
    lines = []
    settings = AgentSettings(model=sim.SIM_MODEL, api_key=None, limits=AgentLimits())
    agent = AuditAgent(settings, sim.FakeBackend(sim.happy_path_steps()), workspace / "legacy_sample",
                       workspace / "output", workspace / "logs", run_id="echo", echo=lines.append)
    await agent.run("audite")
    text = "\n".join(lines)
    assert "MCP conectado" in text and "-> run_security_linter" in text and "validação: OK" in text
