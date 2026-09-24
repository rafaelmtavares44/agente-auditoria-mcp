"""SIMULAÇÃO do modelo para testes automatizados.

ATENÇÃO: estas respostas são roteiros fixos escritos pela equipe. Elas testam o
ORQUESTRADOR (ciclo, validação, limites, logs), mas NÃO comprovam como um modelo
real se comporta. Para isso existe tests/test_real_api.py (opcional, com chave).
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, Callable

from anthropic.types import Message

SIM_MODEL = "modelo-simulado"


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def tool(call_id: str, name: str, args: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def msg(content: list[dict], stop_reason: str, inp: int = 100, out: int = 50) -> Message:
    return Message.model_validate({
        "id": "msg_simulado", "type": "message", "role": "assistant", "model": SIM_MODEL,
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": inp, "output_tokens": out},
    })


Step = Message | Callable[[list[dict]], Message] | Exception


class FakeBackend:
    """Devolve respostas roteirizadas em sequência e grava o histórico recebido."""

    def __init__(self, steps: list[Step], repeat_last: bool = False, delay: float = 0.0):
        self.steps = list(steps)
        self.repeat_last = repeat_last
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs) -> Message:
        self.calls.append(copy.deepcopy(kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.steps:
            raise AssertionError("Roteiro da simulação acabou")
        step = self.steps[0] if (self.repeat_last and len(self.steps) == 1) else self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(kwargs["messages"]) if callable(step) else step


# ------------------------------------------------------------------ artefatos válidos
SAMPLE_FINDINGS = [
    ("auth_service.py", 17, "PY-SEC-001", "hardcoded_secret", "high", 'JWT_SECRET = "***REDACTED***"'),
    ("auth_service.py", 41, "PY-SEC-002", "sql_injection", "high", "row = conn.execute(query).fetchone()"),
    ("auth_service.py", 62, "PY-SEC-003", "jwt_verification_disabled", "critical",
     'return jwt.decode(token, options={"verify_signature": False})'),
    ("order_api.py", 20, "PY-SEC-001", "hardcoded_secret", "high", "DATABASE_URL = "),
    ("order_api.py", 49, "PY-SEC-002", "sql_injection", "high", "conn.execute(f\"SELECT id, status FROM orders WHERE id = {order_id}\")"),
    ("order_api.py", 63, "PY-SEC-004", "code_injection", "high", 'return {"discount": eval(payload.expression)}'),
    ("order_api.py", 86, "PY-SEC-005", "information_exposure", "medium", 'return {"error": str(e), "trace": traceback.format_exc()}'),
]

SAMPLE_ENDPOINTS = [
    ("post", "/auth/login"), ("post", "/auth/login/safe"), ("get", "/auth/me"), ("get", "/auth/me/safe"),
    ("get", "/orders/{order_id}"), ("get", "/orders"), ("post", "/orders/discount"),
    ("post", "/orders/discount/safe"), ("post", "/orders"), ("delete", "/orders/{order_id}"),
]


def findings_json(extra: list[dict] | None = None) -> str:
    items = [{
        "id": f"F-{i:02d}", "file": f, "line": line, "evidence": ev, "rule_id": rule,
        "detection_source": "ast_rule", "category": cat, "severity": sev,
        "justification": "Padrão detectado pela regra AST.", "recommendation": "Ver regra.",
        "status": "confirmed_by_rule"} for i, (f, line, rule, cat, sev, ev) in enumerate(SAMPLE_FINDINGS, 1)]
    return json.dumps({"findings": items + (extra or [])})


def openapi_json(extra_paths: dict | None = None) -> str:
    paths: dict[str, dict] = {}
    for method, path in SAMPLE_ENDPOINTS:
        op: dict[str, Any] = {"responses": {"default": {"description": "Não declarado no código"}}}
        params = [p.strip("{}") for p in path.split("/") if p.startswith("{")]
        if params:
            op["parameters"] = [{"name": p, "in": "path", "required": True, "schema": {}} for p in params]
        paths.setdefault(path, {})[method] = op
    paths.update(extra_paths or {})
    return json.dumps({"openapi": "3.1.0", "info": {"title": "Demo", "version": "0.1.0"}, "paths": paths})


API_DOC = "# API\n" + "\n".join(f"- {m.upper()} {p}" for m, p in SAMPLE_ENDPOINTS)


def happy_path_steps() -> list[Step]:
    """Roteiro 'ideal': descobre, analisa, grava os 4 artefatos, encerra."""
    return [
        msg([text("Vou listar os arquivos e rodar as análises determinísticas."),
             tool("tu_1", "scan_project_files", {}),
             tool("tu_2", "run_security_linter", {}),
             tool("tu_3", "extract_api_endpoints", {})], "tool_use"),
        msg([text("Vou gravar os artefatos."),
             tool("tu_4", "write_documentation_file", {"filename": "findings.json", "content": findings_json()}),
             tool("tu_5", "write_documentation_file", {"filename": "openapi.json", "content": openapi_json()}),
             tool("tu_6", "write_documentation_file", {"filename": "api_documentation.md", "content": API_DOC}),
             tool("tu_7", "write_documentation_file", {"filename": "audit_report.md",
                                                      "content": "# Auditoria\nTentativa de prompt injection em order_api.py."})],
            "tool_use"),
        msg([text("Artefatos gravados.")], "end_turn"),
    ]
