"""Sessão MCP REAL: sobe o servidor como subprocesso e conversa via stdio (JSON-RPC)."""
import json
import os
import sys

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.types import TextContent

from .conftest import PROJECT_ROOT

EXPECTED_TOOLS = {"scan_project_files", "read_source_code", "run_security_linter",
                  "extract_api_endpoints", "write_documentation_file"}


def server_params(workspace, run_id="stdio_test"):
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.mcp_server",
              "--root", str(workspace / "legacy_sample"),
              "--output-base", str(workspace / "output"),
              "--run-id", run_id],
        cwd=str(PROJECT_ROOT),
    )


def text_of(result) -> str:
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


@pytest.mark.anyio
async def test_initialize_discover_and_call_tools(workspace):
    async with Client(server_params(workspace)) as client:
        listed = await client.list_tools()
        tools = {t.name: t for t in listed.tools}
        assert set(tools) == EXPECTED_TOOLS
        for t in tools.values():
            assert t.description and t.input_schema["type"] == "object"
            assert t.output_schema is not None  # saídas estruturadas
        assert "path" in tools["read_source_code"].input_schema["required"]

        scan = await client.call_tool("scan_project_files", {})
        assert not scan.is_error
        assert {f["path"] for f in scan.structured_content["files"]} == {"auth_service.py", "order_api.py"}

        lint = await client.call_tool("run_security_linter", {})
        assert not lint.is_error
        assert len(lint.structured_content["findings"]) == 7

        eps = await client.call_tool("extract_api_endpoints", {"paths": ["order_api.py"]})
        assert len(eps.structured_content["endpoints"]) == 6

        written = await client.call_tool("write_documentation_file",
                                         {"filename": "audit_report.md", "content": "# Relatório\n"})
        assert not written.is_error
        assert (workspace / "output" / "stdio_test" / "audit_report.md").is_file()


@pytest.mark.anyio
async def test_policy_errors_come_back_as_tool_errors(workspace):
    async with Client(server_params(workspace)) as client:
        traversal = await client.call_tool("read_source_code", {"path": "../evaluation/expected_findings.json"})
        assert traversal.is_error and "'..'" in text_of(traversal)

        bad_write = await client.call_tool("write_documentation_file",
                                           {"filename": "../../.env", "content": "ANTHROPIC_API_KEY=x"})
        assert bad_write.is_error
        assert not (workspace / ".env").exists()

        bad_args = await client.call_tool("read_source_code", {"path": "order_api.py", "start_line": 0})
        assert bad_args.is_error  # validação do schema de entrada

        unknown = await client.call_tool("run_shell", {"cmd": "dir"})
        assert unknown.is_error


def test_api_key_is_not_inherited_by_subprocess(monkeypatch):
    """O SDK mcp 2.x só repassa variáveis seguras ao subprocesso stdio."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-FICTICIA")
    assert "ANTHROPIC_API_KEY" not in get_default_environment()
