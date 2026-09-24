"""Logs estruturados em JSON Lines (um evento JSON por linha).

Tudo passa pelo sanitizador antes de ser gravado. Registramos AÇÕES OBSERVÁVEIS
(pedidos de ferramenta, resultados, uso de tokens, status) e o texto curto que o
modelo escreve junto das chamadas — nunca raciocínio interno privado.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from server.sanitizer import sanitize_obj

MAX_FIELD_CHARS = 1500


def truncate(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    """Limita textos longos dentro de estruturas (para não gravar arquivos inteiros no log)."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...[+{len(value) - limit} caracteres]"
    if isinstance(value, dict):
        return {k: truncate(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [truncate(v, limit) for v in value]
    return value


def console_line(r: dict) -> str | None:
    """Resumo de uma linha para acompanhar a execução no terminal (demo ao vivo)."""
    ev = r["event"]
    if ev == "mcp_connected":
        return f"  MCP conectado (stdio): {len(r.get('tools', []))} ferramentas"
    if ev == "model_request":
        return f"  [{r['iteration']}] consultando o modelo..."
    if ev == "model_response":
        just = f" — {r['justification'][:110]}" if r.get("justification") else ""
        u = r.get("usage", {})
        return f"      resposta em {r['duration_ms']} ms ({r['stop_reason']}, {u.get('output_tokens')} tokens){just}"
    if ev == "tool_call":
        arg = r.get("arguments", {})
        hint = arg.get("path") or arg.get("filename") or ""
        return f"      -> {r['tool']}({hint})"
    if ev == "tool_result":
        return f"         {'ERRO' if r['is_error'] else 'ok'} em {r['duration_ms']} ms"
    if ev == "tool_rejected":
        return f"         RECUSADA: {r.get('reason')}"
    if ev == "response_truncated":
        return "      resposta cortada pelo limite de saída"
    if ev == "validation":
        return f"  validação: {'OK' if r['ok'] else 'FALHOU'} ({len(r['errors'])} erros, {len(r['warnings'])} avisos)"
    if ev == "model_error":
        return f"  ERRO DA API: {r.get('error')} {r.get('status_code', '')} {r.get('message', '')}"
    return None


class JsonlLogger:
    def __init__(self, path: Path, run_id: str, echo: Callable[[str], None] | None = None):
        self.path = path
        self.run_id = run_id
        self.echo = echo
        self._seq = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    def event(self, event: str, stage: str, **data: Any) -> dict:
        self._seq += 1
        record = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "seq": self._seq,
            "event": event,
            "stage": stage,
            **truncate(sanitize_obj(data)),
        }
        self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()
        if self.echo:
            line = console_line(record)
            if line:
                self.echo(line)
        return record

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()


class Stopwatch:
    def __init__(self):
        self._start = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
