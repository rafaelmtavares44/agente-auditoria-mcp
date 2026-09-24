"""Configuração do agente: lida do ambiente (e opcionalmente de um arquivo .env).

A chave ANTHROPIC_API_KEY fica apenas neste processo. Ela não é repassada ao
subprocesso MCP (ver agent/mcp_client.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Carrega KEY=VALUE de um .env simples, sem sobrescrever variáveis já definidas."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"{name} deve ser um número inteiro.") from None
    if parsed < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}.")
    return parsed


@dataclass(frozen=True)
class AgentLimits:
    max_iterations: int = 15          # chamadas ao modelo
    max_tool_calls: int = 30          # chamadas de ferramenta somadas
    max_output_tokens: int = 8192     # por resposta do modelo
    max_total_tokens: int = 300_000   # entrada + saída somadas na execução
    timeout_seconds: int = 600        # tempo total da execução
    max_retries: int = 2              # retentativas do SDK para erros transitórios (429/5xx/rede)
    tool_result_max_chars: int = 30_000  # tamanho máximo de um resultado devolvido ao modelo
    max_validation_feedback: int = 2  # quantas vezes o agente pode corrigir artefatos inválidos


@dataclass(frozen=True)
class AgentSettings:
    model: str
    api_key: str | None
    limits: AgentLimits

    @classmethod
    def from_env(cls, require_api_key: bool = True) -> "AgentSettings":
        load_dotenv(PROJECT_DIR / ".env")
        model = os.environ.get("ANTHROPIC_MODEL", "").strip()
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip() or None
        if require_api_key and not api_key:
            raise ValueError("ANTHROPIC_API_KEY não definida (veja .env.example).")
        if require_api_key and not model:
            raise ValueError("ANTHROPIC_MODEL não definido (veja .env.example).")
        limits = AgentLimits(
            max_iterations=_int_env("AGENT_MAX_ITERATIONS", AgentLimits.max_iterations),
            max_tool_calls=_int_env("AGENT_MAX_TOOL_CALLS", AgentLimits.max_tool_calls),
            max_output_tokens=_int_env("AGENT_MAX_OUTPUT_TOKENS", AgentLimits.max_output_tokens),
            max_total_tokens=_int_env("AGENT_MAX_TOTAL_TOKENS", AgentLimits.max_total_tokens),
            timeout_seconds=_int_env("AGENT_TIMEOUT_SECONDS", AgentLimits.timeout_seconds),
            max_retries=_int_env("AGENT_MAX_RETRIES", AgentLimits.max_retries, minimum=0),
        )
        return cls(model=model, api_key=api_key, limits=limits)
