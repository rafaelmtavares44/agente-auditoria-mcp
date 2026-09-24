"""Redação de valores sensíveis antes de qualquer texto sair do servidor.

Regras:
- Substitui o VALOR, mantendo nome da variável, aspas e a numeração de linhas.
- Aplicado em: código lido, evidências de achados, docstrings, artefatos gravados.

Limitação importante (documentar no relatório): é baseado em padrões.
Segredos com nomes neutros (ex.: x = "a8f3...") ou formatos desconhecidos
podem passar. Por isso só usamos credenciais FICTÍCIAS no projeto de exemplo.
"""

from __future__ import annotations

import re

REDACTED = "***REDACTED***"
BENIGN_VALUES = {"bearer", "basic", "none", "null", "true", "false", "hs256", "rs256"}

SENSITIVE_NAME = r"(?:secret|passw(?:or)?d|pwd|token|api[_-]?key|apikey|private[_-]?key|access[_-]?key|client[_-]?secret|credential|auth[_-]?key)"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Bloco de chave privada (preserva quebras de linha)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "PRIVATE_KEY_BLOCK"),
    # nome_sensivel = "valor"  |  nome_sensivel: str = 'valor'  |  "nome_sensivel": "valor"
    (re.compile(
        r"(?i)(?P<prefix>[\"']?\b\w*" + SENSITIVE_NAME + r"\w*[\"']?\s*(?::\s*[\w\[\], ]+)?\s*[:=]\s*)"
        r"(?P<q>[rbuRBU]{0,2}[\"'])(?P<val>[^\"'\n]{4,})(?P=q)"), "ASSIGN"),
    # Credenciais em URL: esquema://usuario:senha@host
    (re.compile(r"(?P<pre>\b[a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s\"'@]+:)(?P<val>[^@/\s\"']+)(?P<post>@)"), "URL"),
    # Formatos conhecidos de token
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"), "TOKEN"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "TOKEN"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "TOKEN"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "TOKEN"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), "TOKEN"),
    (re.compile(r"(?i)(?P<pre>\bbearer\s+)(?P<val>[A-Za-z0-9._~+/=-]{12,})"), "BEARER"),
]


def _replace(kind: str, m: re.Match[str]) -> str:
    if kind == "PRIVATE_KEY_BLOCK":
        # Mantém o mesmo número de linhas para não quebrar referências.
        n_newlines = m.group(0).count("\n")
        return "-----BEGIN PRIVATE KEY-----" + (" " + REDACTED) + "\n" * n_newlines + "-----END PRIVATE KEY-----"
    if kind == "ASSIGN":
        if m.group("val").strip().lower() in BENIGN_VALUES:
            return m.group(0)  # ex.: token_type = "bearer" não é segredo
        return f"{m.group('prefix')}{m.group('q')}{REDACTED}{m.group('q')[-1]}"
    if kind in ("URL", "BEARER"):
        return m.group("pre") + REDACTED + (m.groupdict().get("post") or "")
    return REDACTED


def sanitize_text(text: str) -> str:
    for pattern, kind in _PATTERNS:
        text = pattern.sub(lambda m, k=kind: _replace(k, m), text)
    return text


def sanitize_obj(obj):
    """Aplica sanitize_text recursivamente em dicts/listas (para argumentos e logs)."""
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_obj(v) for v in obj]
    return obj
