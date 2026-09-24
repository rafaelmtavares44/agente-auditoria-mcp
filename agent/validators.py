"""Validação dos artefatos gerados — o agente só é 'completed' se isto passar.

Referência DETERMINÍSTICA: ao final, o próprio orquestrador chama o linter e o
extrator via MCP (sem passar pelo modelo). Assim dá para detectar:
- achados "confirmados pela regra" que o linter nunca produziu (alucinação);
- linhas/arquivos inexistentes;
- endpoints inventados no OpenAPI.

Erros bloqueiam a conclusão; avisos entram no relatório de avaliação.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openapi_spec_validator import validate as validate_openapi_spec
from pydantic import ValidationError

from server import path_guard
from server.artifacts import ALLOWED_ARTIFACTS, FindingsFile
from server.sanitizer import sanitize_text

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
LINE_TOLERANCE = 2


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "stats": self.stats}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _source_lines(root: Path, rel: str) -> list[str] | None:
    try:
        path = path_guard.resolve_readable_python(root, rel)
    except path_guard.PathAccessError:
        return None
    return sanitize_text(path.read_text(encoding="utf-8", errors="replace")).splitlines()


def _check_findings(data: dict, root: Path, linter: list[dict], rep: ValidationReport) -> None:
    try:
        parsed = FindingsFile.model_validate(data)
    except ValidationError as exc:
        rep.errors.append(f"findings.json fora do schema: {exc.errors()[0]['msg']}")
        return

    counts = {"total": 0, "confirmed_by_rule": 0, "hypothesis": 0, "from_model": 0}
    for f in parsed.findings:
        counts["total"] += 1
        counts[f.status] += 1
        counts["from_model"] += f.detection_source == "model"
        tag = f"findings.json[{f.id}]"
        lines = _source_lines(root, f.file)
        if lines is None:
            rep.errors.append(f"{tag}: arquivo '{f.file}' não existe na raiz analisada.")
            continue
        if f.line > len(lines):
            rep.errors.append(f"{tag}: linha {f.line} não existe ({f.file} tem {len(lines)} linhas).")
            continue
        if f.status == "confirmed_by_rule":
            if f.detection_source != "ast_rule" or not f.rule_id:
                rep.errors.append(f"{tag}: 'confirmed_by_rule' exige detection_source='ast_rule' e rule_id.")
            elif not any(l["file"] == f.file and l["rule_id"] == f.rule_id
                         and abs(l["line"] - f.line) <= LINE_TOLERANCE for l in linter):
                rep.errors.append(f"{tag}: marcado como confirmado, mas o linter não produziu "
                                  f"{f.rule_id} em {f.file}:{f.line}.")
        window = " ".join(lines[max(0, f.line - 1 - LINE_TOLERANCE): f.line + LINE_TOLERANCE])
        evidence = _norm(f.evidence.split("  [")[0])
        if evidence and evidence not in _norm(window):
            rep.warnings.append(f"{tag}: evidência não encontrada literalmente perto de {f.file}:{f.line}.")

    for l in linter:
        if not any(f.file == l["file"] and f.rule_id == l["rule_id"]
                   and abs(f.line - l["line"]) <= LINE_TOLERANCE for f in parsed.findings):
            rep.warnings.append(f"Achado do linter omitido: {l['rule_id']} em {l['file']}:{l['line']}.")
    rep.stats["findings"] = counts


def _check_openapi(data: dict, endpoints: list[dict], rep: ValidationReport) -> None:
    if not str(data.get("openapi", "")).startswith("3.1"):
        rep.errors.append("openapi.json deve usar OpenAPI 3.1.x.")
        return
    try:
        validate_openapi_spec(data)
    except Exception as exc:  # erros do validador oficial
        rep.errors.append(f"openapi.json inválido: {str(exc).splitlines()[0][:200]}")
        return

    known = {(e["method"].lower(), e["path"]) for e in endpoints}
    declared = {(m.lower(), p) for p, ops in data.get("paths", {}).items()
                if isinstance(ops, dict) for m in ops if m.lower() in HTTP_METHODS}
    for method, path in sorted(declared - known):
        rep.errors.append(f"openapi.json: endpoint inventado {method.upper()} {path} (não existe no código).")
    for method, path in sorted(known - declared):
        rep.warnings.append(f"openapi.json: endpoint do código ausente {method.upper()} {path}.")
    if data.get("components", {}).get("securitySchemes") or data.get("security"):
        rep.warnings.append("openapi.json declara esquema de segurança: conferir se há base no código.")
    rep.stats["openapi"] = {"declared_operations": len(declared), "code_operations": len(known)}


def validate_artifacts(output_dir: Path, root: Path, linter_findings: list[dict],
                       endpoints: list[dict]) -> ValidationReport:
    rep = ValidationReport()
    contents: dict[str, str] = {}
    for name in ALLOWED_ARTIFACTS:
        path = output_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            rep.errors.append(f"Artefato obrigatório ausente ou vazio: {name}")
        else:
            contents[name] = path.read_text(encoding="utf-8")

    for name in ("findings.json", "openapi.json"):
        if name not in contents:
            continue
        try:
            data = json.loads(contents[name])
        except json.JSONDecodeError:
            rep.errors.append(f"{name} não é JSON válido.")
            continue
        if name == "findings.json":
            _check_findings(data, root, linter_findings, rep)
        else:
            _check_openapi(data, endpoints, rep)

    doc = contents.get("api_documentation.md", "")
    if doc:
        for e in endpoints:
            if e["path"] not in doc:
                rep.warnings.append(f"api_documentation.md não menciona {e['method']} {e['path']}.")
    rep.stats["reference"] = {"linter_findings": len(linter_findings), "endpoints": len(endpoints)}
    return rep
