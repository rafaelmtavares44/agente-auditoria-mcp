"""Orquestrador: o ciclo do agente.

    modelo pede ferramentas -> orquestrador valida -> servidor MCP executa ->
    resultado volta ao modelo com o mesmo tool_use_id -> ... até concluir, falhar ou bater limite.

O modelo DECIDE os passos; este código DECIDE o que é permitido e quando parar.
Status possíveis: running -> completed | failed | limit_reached.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import anthropic

from agent.config import AgentSettings
from agent.logging_jsonl import JsonlLogger, Stopwatch
from agent.mcp_client import MCPToolClient, ToolValidationError, build_server_params
from agent.prompts import SYSTEM_PROMPT, build_user_message
from agent.validators import validate_artifacts
from server.sanitizer import sanitize_obj, sanitize_text


# --------------------------------------------------------------------------- backends
class ModelBackend(Protocol):
    async def create(self, *, model: str, max_tokens: int, system: str,
                     tools: list[dict], messages: list[dict]) -> Any: ...


class AnthropicBackend:
    """Backend real (API da Anthropic). Retentativas de erros transitórios (429, 5xx,
    falha de rede) ficam a cargo do SDK, limitadas por max_retries."""

    def __init__(self, api_key: str, max_retries: int, request_timeout: float = 120.0):
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries,
                                                timeout=request_timeout)

    async def create(self, **kwargs) -> Any:
        return await self._client.messages.create(**kwargs)


# --------------------------------------------------------------------------- resultado
@dataclass
class RunResult:
    run_id: str
    status: str = "running"
    reason: str = ""
    iterations: int = 0
    tool_calls: int = 0
    rejected_tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    validation: dict | None = None
    output_dir: str = ""
    log_path: str = ""
    tools_used: dict[str, int] = field(default_factory=dict)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _block_to_param(block: Any) -> dict | None:
    """Converte um bloco da resposta em parâmetro para reenviar no histórico.
    Blocos de texto vazios/só com espaços são descartados: a API rejeita (400) se voltarem."""
    if block.type == "text":
        return {"type": "text", "text": block.text} if block.text.strip() else None
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump(mode="json", exclude_none=True)


def _short(text: str, limit: int = 400) -> str:
    text = sanitize_text(text.strip())
    return text if len(text) <= limit else text[:limit] + "..."


# --------------------------------------------------------------------------- agente
class AuditAgent:
    def __init__(self, settings: AgentSettings, backend: ModelBackend, root: Path,
                 output_base: Path, logs_dir: Path, run_id: str | None = None,
                 echo=None):
        self.settings = settings
        self.limits = settings.limits
        self.backend = backend
        self.root = Path(root).resolve()
        self.output_base = Path(output_base).resolve()
        self.run_id = run_id or new_run_id()
        self.output_dir = self.output_base / self.run_id
        self.log = JsonlLogger(Path(logs_dir) / f"{self.run_id}.jsonl", self.run_id, echo=echo)
        self.server_log = Path(logs_dir) / f"{self.run_id}_server.log"
        self.result = RunResult(run_id=self.run_id, output_dir=str(self.output_dir),
                                log_path=str(self.log.path))

    # ------------------------------------------------------------------ público
    async def run(self, objective: str) -> RunResult:
        clock = Stopwatch()
        self.log.event("run_started", "setup", status="running", objective=objective,
                       model=self.settings.model, limits=asdict(self.limits),
                       root_label=self.root.name)
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                params = build_server_params(self.root, self.output_base, self.run_id)
                async with MCPToolClient(params, self.server_log) as mcp:
                    self.log.event("mcp_connected", "setup", tools=list(mcp.tools),
                                   ignored_tools=mcp.ignored_tools, transport="stdio")
                    await self._loop(objective, mcp)
        except TimeoutError:
            self._finish("limit_reached", f"tempo máximo de {self.limits.timeout_seconds}s atingido")
        except asyncio.CancelledError:
            self._finish("failed", "execução interrompida pelo usuário")
            self._close(clock)
            raise
        except anthropic.AuthenticationError:
            self._finish("failed", "falha de autenticação na API (verifique ANTHROPIC_API_KEY)")
        except anthropic.APIStatusError as exc:
            detail = _short(str(getattr(exc, "message", exc)), 500)
            self.log.event("model_error", "reasoning", error=type(exc).__name__,
                           status_code=exc.status_code, request_id=getattr(exc, "request_id", None),
                           message=detail, request_dump=self._dump_request())
            self._finish("failed", f"erro da API ({exc.status_code} {type(exc).__name__}): {detail}")
        except anthropic.APIError as exc:
            self.log.event("model_error", "reasoning", error=type(exc).__name__,
                           message=_short(str(exc), 500))
            self._finish("failed", f"erro da API após retentativas: {type(exc).__name__}")
        except Exception as exc:  # erro inesperado: registra sem vazar detalhes sensíveis
            self._finish("failed", f"erro inesperado: {type(exc).__name__}: {_short(str(exc), 200)}")
        self._close(clock)
        return self.result

    # ------------------------------------------------------------------ ciclo
    async def _loop(self, objective: str, mcp: MCPToolClient) -> None:
        tools = mcp.anthropic_tools()
        messages: list[dict] = [{"role": "user", "content": build_user_message(objective)}]
        self._messages = messages  # referência para diagnóstico em caso de erro da API
        feedback_rounds = 0

        while True:
            if self.result.iterations >= self.limits.max_iterations:
                return self._finish("limit_reached", f"máximo de {self.limits.max_iterations} iterações")
            used = self.result.input_tokens + self.result.output_tokens
            remaining = self.limits.max_total_tokens - used
            if remaining <= 0:
                return self._finish("limit_reached", f"orçamento de {self.limits.max_total_tokens} tokens esgotado")

            self.result.iterations += 1
            it = self.result.iterations
            max_tokens = min(self.limits.max_output_tokens, remaining)
            self.log.event("model_request", "reasoning", iteration=it, messages=len(messages),
                           max_tokens=max_tokens)
            sw = Stopwatch()
            response = await self.backend.create(model=self.settings.model, max_tokens=max_tokens,
                                                 system=SYSTEM_PROMPT, tools=tools, messages=messages)
            usage = response.usage
            self.result.input_tokens += usage.input_tokens
            self.result.output_tokens += usage.output_tokens
            text = " ".join(b.text for b in response.content if b.type == "text")
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            self.log.event("model_response", "reasoning", iteration=it, duration_ms=sw.ms,
                           stop_reason=response.stop_reason,
                           usage={"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                           justification=_short(text) if text else None,
                           tool_requests=[{"id": b.id, "name": b.name} for b in tool_uses])
            params = [p for p in (_block_to_param(b) for b in response.content) if p is not None]
            messages.append({"role": "assistant",
                             "content": params or [{"type": "text", "text": "(sem texto)"}]})

            stop = response.stop_reason
            if stop == "tool_use":
                results, hit_limit = await self._execute_tools(tool_uses, mcp, it)
                messages.append({"role": "user", "content": results})
                if hit_limit:
                    return self._finish("limit_reached", f"máximo de {self.limits.max_tool_calls} chamadas de ferramenta")
                continue

            if stop == "max_tokens":
                # Resposta cortada: um tool_use incompleto não pode ser executado com segurança.
                self.log.event("response_truncated", "reasoning", iteration=it,
                               incomplete_tool_calls=[b.name for b in tool_uses])
                if tool_uses:
                    messages.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                         "content": "Resposta cortada pelo limite de saída; a chamada não foi executada. "
                                    "Reenvie com conteúdo menor (ex.: grave um artefato por vez)."}
                        for b in tool_uses]})
                else:
                    messages.append({"role": "user", "content":
                                     "Sua resposta foi cortada pelo limite de saída. Continue de forma mais concisa."})
                continue

            if stop == "pause_turn":
                continue

            if stop in ("end_turn", "stop_sequence"):
                report = await self._verify(mcp)
                if report.ok:
                    return self._finish("completed", "artefatos gerados e validados")
                if feedback_rounds >= self.limits.max_validation_feedback:
                    return self._finish("failed", "artefatos inválidos após as tentativas de correção")
                feedback_rounds += 1
                problems = "\n".join(f"- {e}" for e in report.errors[:15])
                messages.append({"role": "user", "content":
                                 "A validação automática dos artefatos falhou. Corrija e grave novamente:\n" + problems})
                continue

            return self._finish("failed", f"parada inesperada do modelo: {stop}")

    # ------------------------------------------------------------------ ferramentas
    async def _execute_tools(self, tool_uses: list, mcp: MCPToolClient, it: int) -> tuple[list[dict], bool]:
        """Processa TODOS os tool_use da resposta; cada um recebe um tool_result com o mesmo id."""
        results, hit_limit = [], False
        for block in tool_uses:
            if self.result.tool_calls >= self.limits.max_tool_calls:
                hit_limit = True
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "Limite de chamadas de ferramenta atingido; chamada não executada."})
                self.log.event("tool_rejected", "action", iteration=it, call_id=block.id,
                               tool=block.name, reason="limite de chamadas")
                continue
            self.result.tool_calls += 1
            self.result.tools_used[block.name] = self.result.tools_used.get(block.name, 0) + 1
            args_for_log = block.input if isinstance(block.input, dict) else {"_raw": str(block.input)}
            self.log.event("tool_call", "action", iteration=it, call_id=block.id, tool=block.name,
                           arguments=args_for_log)
            sw = Stopwatch()
            try:
                args = mcp.validate(block.name, block.input)
            except ToolValidationError as exc:
                self.result.rejected_tool_calls += 1
                self.log.event("tool_rejected", "action", iteration=it, call_id=block.id,
                               tool=block.name, reason=str(exc))
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": f"Chamada recusada pelo orquestrador: {exc}"})
                continue

            outcome = await mcp.call(block.name, args)
            content = outcome.text
            if len(content) > self.limits.tool_result_max_chars:
                content = content[: self.limits.tool_result_max_chars] + "\n[resultado truncado pelo orquestrador]"
            self.log.event("tool_result", "observation", iteration=it, call_id=block.id,
                           tool=block.name, is_error=outcome.is_error, duration_ms=sw.ms,
                           result_chars=len(outcome.text), summary=_summarize(block.name, outcome))
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "is_error": outcome.is_error, "content": content})
        return results, hit_limit

    async def _verify(self, mcp: MCPToolClient):
        """Referência determinística chamada pelo orquestrador (não conta nos limites do modelo)."""
        lint = await mcp.call("run_security_linter", {})
        eps = await mcp.call("extract_api_endpoints", {})
        report = validate_artifacts(
            self.output_dir, self.root,
            (lint.structured or {}).get("findings", []),
            (eps.structured or {}).get("endpoints", []),
        )
        self.result.validation = report.as_dict()
        self.log.event("validation", "verification", ok=report.ok, errors=report.errors,
                       warnings=report.warnings, stats=report.stats)
        return report

    def _dump_request(self) -> str | None:
        """Salva o histórico enviado (sanitizado) para diagnosticar erros 400. Fica em logs/ (fora do Git)."""
        messages = getattr(self, "_messages", None)
        if messages is None:
            return None
        path = self.log.path.with_name(f"{self.run_id}_failed_request.json")
        summary = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else
                    [{k: (_short(v, 300) if isinstance(v, str) else v) for k, v in b.items()
                      if k != "input"} | ({"input_keys": list(b["input"])} if "input" in b else {})
                     for b in m["content"]]} for m in messages]
        path.write_text(json.dumps(sanitize_obj(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        return path.name

    # ------------------------------------------------------------------ encerramento
    def _finish(self, status: str, reason: str) -> None:
        self.result.status = status
        self.result.reason = reason

    def _close(self, clock: Stopwatch) -> None:
        self.result.duration_ms = clock.ms
        summary = asdict(self.result)
        self.log.event("run_finished", "finish", **summary)
        self.log.close()
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            (self.output_dir / "run_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def _summarize(tool: str, outcome) -> Any:
    """Resumo curto do resultado para o log (o resultado completo não é gravado)."""
    if outcome.is_error:
        return _short(outcome.text, 300)
    s = outcome.structured or {}
    if tool == "scan_project_files":
        return {"files": [f["path"] for f in s.get("files", [])], "warnings": s.get("warnings")}
    if tool == "read_source_code":
        return {"path": s.get("path"), "lines": [s.get("start_line"), s.get("end_line")],
                "redactions_applied": s.get("redactions_applied")}
    if tool == "run_security_linter":
        return {"findings": [f"{f['rule_id']} {f['file']}:{f['line']}" for f in s.get("findings", [])],
                "errors": s.get("errors")}
    if tool == "extract_api_endpoints":
        return {"endpoints": [f"{e['method']} {e['path']}" for e in s.get("endpoints", [])]}
    if tool == "write_documentation_file":
        return {k: s.get(k) for k in ("relative_path", "bytes_written", "sha256", "redactions_applied")}
    return None
