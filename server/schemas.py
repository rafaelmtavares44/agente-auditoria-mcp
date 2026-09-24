"""Schemas (Pydantic) das SAÍDAS das ferramentas.

O MCPServer transforma estes modelos em `outputSchema`, e o cliente recebe
`structured_content` validável. Os schemas de ENTRADA vêm das assinaturas
das funções em mcp_server.py.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FileEntry(BaseModel):
    path: str
    size_bytes: int


class ScanResult(BaseModel):
    root_label: str
    files: list[FileEntry]
    total_files: int
    warnings: list[str]


class SourceResult(BaseModel):
    path: str
    total_lines: int
    start_line: int
    end_line: int
    numbered_content: str        # "  12 | código" — para citar linhas
    redactions_applied: bool
    bytes_read_total: int
    read_budget_bytes: int
    note: str


class SecurityFinding(BaseModel):
    rule_id: str
    title: str
    category: str
    cwe: str
    severity: str
    file: str
    line: int
    evidence: str
    explanation: str
    recommendation: str
    limitations: str
    detection: str
    status: str


class LinterResult(BaseModel):
    files_analyzed: list[str]
    findings: list[SecurityFinding]
    errors: list[str]
    disclaimer: str


class Parameter(BaseModel):
    name: str
    location: str
    location_source: str
    type: str | None
    required: bool
    default: str | None


class Endpoint(BaseModel):
    method: str
    path: str
    function: str
    is_async: bool
    file: str
    line: int
    summary: str | None
    docstring: str | None
    tags: list[Any]
    status_code: int | None
    response_model: str | None
    return_annotation: str | None
    deprecated: bool
    parameters: list[Parameter]
    documentation_gaps: list[str]


class EndpointsResult(BaseModel):
    endpoints: list[Endpoint]
    models: dict[str, list[dict[str, Any]]]
    unsupported: list[dict[str, Any]]
    errors: list[str]
    limitations: list[str]


class WriteResult(BaseModel):
    status: str
    relative_path: str
    bytes_written: int
    sha256: str
    redactions_applied: bool
