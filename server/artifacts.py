"""Validação dos artefatos que o agente pode gravar em output/<run_id>/.

Somente 4 nomes são aceitos. JSON é validado antes de gravar, e todo conteúdo
passa pelo sanitizador. A validação completa do OpenAPI (schema oficial) é
feita pelo orquestrador na etapa 4; aqui fica a checagem estrutural mínima.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from server.sanitizer import sanitize_obj, sanitize_text

ALLOWED_ARTIFACTS = {
    "findings.json": "json",
    "audit_report.md": "markdown",
    "api_documentation.md": "markdown",
    "openapi.json": "json",
}


class ArtifactError(ValueError):
    """Conteúdo ou nome inválido. Mensagem segura para o modelo."""


class FindingRecord(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    evidence: str
    rule_id: str | None = None          # None quando a origem é o modelo
    detection_source: Literal["ast_rule", "model"]
    category: str
    severity: Literal["low", "medium", "high", "critical", "info"]
    justification: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    status: Literal["confirmed_by_rule", "hypothesis"]


class FindingsFile(BaseModel):
    findings: list[FindingRecord]
    notes: str | None = None


def _validate_openapi_minimal(data: dict) -> None:
    if not isinstance(data, dict):
        raise ArtifactError("openapi.json deve ser um objeto JSON.")
    version = data.get("openapi")
    if not (isinstance(version, str) and version.startswith("3.1")):
        raise ArtifactError("openapi.json deve declarar 'openapi': '3.1.x'.")
    info = data.get("info")
    if not (isinstance(info, dict) and isinstance(info.get("title"), str) and isinstance(info.get("version"), str)):
        raise ArtifactError("openapi.json precisa de info.title e info.version (texto).")
    if not isinstance(data.get("paths"), dict):
        raise ArtifactError("openapi.json precisa de 'paths' como objeto.")


def prepare_artifact(filename: str, content: str, max_bytes: int) -> tuple[str, bool]:
    """Valida e sanitiza. Devolve (conteúdo final, houve_redação)."""
    if filename not in ALLOWED_ARTIFACTS:
        raise ArtifactError(f"Nome não permitido. Use um de: {', '.join(sorted(ALLOWED_ARTIFACTS))}.")
    if len(content.encode("utf-8")) > max_bytes:
        raise ArtifactError(f"Conteúdo excede o limite de {max_bytes} bytes.")
    if not content.strip():
        raise ArtifactError("Conteúdo vazio.")

    if ALLOWED_ARTIFACTS[filename] == "json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"JSON inválido: {exc.msg} (linha {exc.lineno}).") from None
        if filename == "findings.json":
            try:
                FindingsFile.model_validate(data)
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"])
                raise ArtifactError(f"findings.json fora do schema em '{where}': {first['msg']}") from None
        else:
            _validate_openapi_minimal(data)
        clean = sanitize_obj(data)
        final = json.dumps(clean, ensure_ascii=False, indent=2)
        return final, clean != data

    clean_text = sanitize_text(content)
    return clean_text, clean_text != content
