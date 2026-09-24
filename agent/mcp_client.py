"""Cliente MCP: sobe o servidor como subprocesso (stdio), descobre e chama ferramentas.

Também adapta os schemas MCP para o formato de ferramentas da API da Anthropic e
valida nome + argumentos ANTES de qualquer chamada chegar ao servidor.
"""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from agent.config import PROJECT_DIR

# Allowlist fixa no código. Mesmo que o servidor anunciasse outra ferramenta,
# ela não seria oferecida ao modelo.
ALLOWED_TOOLS = (
    "scan_project_files",
    "read_source_code",
    "run_security_linter",
    "extract_api_endpoints",
    "write_documentation_file",
)


@dataclass
class ToolOutcome:
    is_error: bool
    text: str                         # o que volta para o modelo
    structured: dict[str, Any] | None


class ToolValidationError(ValueError):
    """Nome ou argumentos recusados pelo orquestrador (o servidor nem é chamado)."""


def build_server_params(root: Path, output_base: Path, run_id: str) -> StdioServerParameters:
    """Parâmetros do subprocesso. `env` NÃO inclui ANTHROPIC_API_KEY: o SDK mcp 2.x
    herda só variáveis seguras (PATH, TEMP...) e somamos apenas as de codificação."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.mcp_server",
              "--root", str(root), "--output-base", str(output_base), "--run-id", run_id],
        cwd=str(PROJECT_DIR),
        env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )


class MCPToolClient:
    def __init__(self, params: StdioServerParameters, server_log_path: Path):
        self._params = params
        self._server_log_path = server_log_path
        self._stack = AsyncExitStack()
        self._client: Client | None = None
        self.tools: dict[str, Any] = {}     # nome -> definição MCP (apenas as permitidas)
        self.ignored_tools: list[str] = []  # anunciadas pelo servidor mas fora da allowlist

    async def __aenter__(self) -> "MCPToolClient":
        self._server_log_path.parent.mkdir(parents=True, exist_ok=True)
        # stderr do servidor vai para arquivo; stdout fica exclusivo do protocolo.
        errlog = self._stack.enter_context(self._server_log_path.open("a", encoding="utf-8"))
        transport = stdio_client(self._params, errlog=errlog)
        self._client = await self._stack.enter_async_context(Client(transport))
        listed = await self._client.list_tools()
        for tool in listed.tools:
            if tool.name in ALLOWED_TOOLS:
                self.tools[tool.name] = tool
            else:
                self.ignored_tools.append(tool.name)
        missing = set(ALLOWED_TOOLS) - set(self.tools)
        if missing:
            raise RuntimeError(f"Servidor MCP não expôs ferramentas obrigatórias: {sorted(missing)}")
        return self

    async def __aexit__(self, *exc) -> None:
        # Fecha a sessão e encerra o subprocesso (também em Ctrl+C / erro).
        await self._stack.aclose()

    # ---------------------------------------------------------------- adaptação
    def anthropic_tools(self) -> list[dict[str, Any]]:
        """Converte a definição MCP para o formato `tools` da Messages API."""
        return [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in self.tools.values()
        ]

    def validate(self, name: str, arguments: Any) -> dict[str, Any]:
        if name not in self.tools:
            raise ToolValidationError(f"Ferramenta '{name}' não está na allowlist.")
        if not isinstance(arguments, dict):
            raise ToolValidationError("Argumentos devem ser um objeto JSON.")
        try:
            jsonschema.validate(arguments, self.tools[name].input_schema)
        except jsonschema.ValidationError as exc:
            where = "/".join(str(p) for p in exc.absolute_path) or "(raiz)"
            raise ToolValidationError(f"Argumento inválido em {where}: {exc.message}") from None
        return arguments

    # ---------------------------------------------------------------- chamada
    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        assert self._client is not None, "Use 'async with MCPToolClient(...)'"
        result = await self._client.call_tool(name, arguments)
        text_blocks = [b.text for b in result.content if isinstance(b, TextContent)]
        structured = None if result.is_error else result.structured_content
        if structured is not None:
            text = json.dumps(structured, ensure_ascii=False)
        else:
            text = "\n".join(text_blocks) or "(sem conteúdo)"
        return ToolOutcome(is_error=bool(result.is_error), text=text, structured=structured)
