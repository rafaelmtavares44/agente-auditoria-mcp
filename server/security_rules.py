"""Regras de segurança por AST (Abstract Syntax Tree).

O código analisado é apenas PARSEADO com ast.parse — nunca importado ou executado.

Cada achado significa "a regra encontrou este padrão sintático", e NÃO
"a vulnerabilidade é explorável". A confirmação de exploração exige revisão humana.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass

from server.sanitizer import BENIGN_VALUES, SENSITIVE_NAME, sanitize_text


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    category: str
    cwe: str
    severity: str  # estimativa: low | medium | high | critical
    explanation: str
    recommendation: str
    limitations: str


RULES: dict[str, Rule] = {r.rule_id: r for r in [
    Rule("PY-SEC-001", "Segredo fixado no código", "hardcoded_secret", "CWE-798", "high",
         "Um literal de texto é atribuído a um nome sensível (senha, token, chave) ou contém credenciais em URL.",
         "Ler o valor de variável de ambiente ou cofre de segredos; revogar o segredo exposto.",
         "Baseada em nomes e formatos. Não detecta segredos com nomes neutros nem valida se o valor é real."),
    Rule("PY-SEC-002", "SQL construído dinamicamente", "sql_injection", "CWE-89", "high",
         "Texto SQL montado com f-string, concatenação, % ou .format() é passado a execute().",
         "Usar consultas parametrizadas (placeholders ? / %s / :nome) ou um ORM.",
         "Não rastreia fluxo entre funções; não confirma se o valor vem do usuário. Rastreia só variáveis da mesma função."),
    Rule("PY-SEC-003", "Verificação de assinatura JWT desativada", "jwt_verification_disabled", "CWE-347", "critical",
         "Chamada a decode() com verify_signature=False, verify=False ou algoritmo 'none'.",
         "Validar assinatura com chave secreta e lista explícita de algoritmos (ex.: ['HS256']).",
         "Reconhece apenas argumentos literais na própria chamada; opções montadas em variáveis não são vistas."),
    Rule("PY-SEC-004", "Uso de eval/exec com valor não literal", "code_injection", "CWE-95", "high",
         "eval() ou exec() recebe expressão não constante, o que permite executar código arbitrário.",
         "Remover eval/exec; usar ast.literal_eval para literais ou um parser específico.",
         "Não verifica se o argumento vem de entrada externa; qualquer valor não literal é sinalizado."),
    Rule("PY-SEC-005", "Detalhes internos de exceção expostos", "information_exposure", "CWE-209", "medium",
         "Dentro de um bloco except, a mensagem/traceback da exceção é devolvida em return ou raise.",
         "Registrar o erro no log do servidor e responder com mensagem genérica.",
         "Considera só return/raise dentro do próprio except; não segue a exceção para outras funções."),
]}

_SENSITIVE_RE = re.compile(r"(?i)" + SENSITIVE_NAME)
_URL_CRED_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s@]+:[^@/\s]+@")
_SQL_RE = re.compile(r"(?is)\b(select\b.*\bfrom|insert\s+into|update\b.*\bset|delete\s+from|drop\s+table)\b")
_EXECUTE_ATTRS = {"execute", "executemany", "executescript", "raw"}


def _is_str_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _looks_like_secret_value(node: ast.AST) -> bool:
    return (_is_str_const(node) and len(node.value) >= 8
            and node.value.strip().lower() not in BENIGN_VALUES)


def _flatten_add(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_add(node.left) + _flatten_add(node.right)
    return [node]


def _is_dynamic_sql(node: ast.AST) -> bool:
    """True se o nó monta SQL com partes não constantes."""
    if isinstance(node, ast.JoinedStr):
        text = "".join(v.value for v in node.values if _is_str_const(v))
        has_expr = any(isinstance(v, ast.FormattedValue) for v in node.values)
        return has_expr and bool(_SQL_RE.search(text))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts = _flatten_add(node)
        text = "".join(p.value for p in parts if _is_str_const(p))
        return any(not _is_str_const(p) for p in parts) and bool(_SQL_RE.search(text))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _is_str_const(node.left) and bool(_SQL_RE.search(node.left.value))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format" and _is_str_const(node.func.value)):
        return bool(_SQL_RE.search(node.func.value.value))
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str], rel_path: str):
        self.lines = lines
        self.rel_path = rel_path
        self.findings: list[dict] = []
        self._seen: set[tuple[str, int]] = set()
        self._sql_vars: list[dict[str, int]] = [{}]  # pilha de escopos

    # ---------- utilitários ----------
    def _add(self, rule_id: str, node: ast.AST, extra: str = "") -> None:
        line = getattr(node, "lineno", 0)
        if (rule_id, line) in self._seen:
            return
        self._seen.add((rule_id, line))
        rule = RULES[rule_id]
        raw = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        evidence = sanitize_text(raw)[:240]
        if extra:
            evidence += f"  [{extra}]"
        data = asdict(rule)
        data.update(file=self.rel_path, line=line, evidence=evidence,
                    detection="ast_rule", status="confirmed_by_rule")
        self.findings.append(data)

    # ---------- escopos (para rastrear variáveis SQL) ----------
    def _visit_scope(self, node: ast.AST) -> None:
        self._sql_vars.append({})
        self.generic_visit(node)
        self._sql_vars.pop()

    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope

    # ---------- PY-SEC-001 e rastreio de SQL ----------
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            name = _target_name(target)
            if name and _SENSITIVE_RE.search(name) and _looks_like_secret_value(node.value):
                self._add("PY-SEC-001", node)
            if isinstance(target, ast.Name):
                if _is_dynamic_sql(node.value):
                    self._sql_vars[-1][target.id] = node.lineno
                else:
                    self._sql_vars[-1].pop(target.id, None)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        name = _target_name(node.target)
        if name and node.value is not None and _SENSITIVE_RE.search(name) and _looks_like_secret_value(node.value):
            self._add("PY-SEC-001", node)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if key is not None and _is_str_const(key) and _SENSITIVE_RE.search(key.value) \
                    and _looks_like_secret_value(value):
                self._add("PY-SEC-001", value)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _URL_CRED_RE.search(node.value):
            self._add("PY-SEC-001", node, "credencial embutida em URL")

    # ---------- chamadas: 001 (kwargs), 002, 003, 004 ----------
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        for kw in node.keywords:
            if kw.arg and _SENSITIVE_RE.search(kw.arg) and _looks_like_secret_value(kw.value):
                self._add("PY-SEC-001", kw.value)

        if isinstance(func, ast.Attribute) and func.attr in _EXECUTE_ATTRS and node.args:
            first = node.args[0]
            if _is_dynamic_sql(first):
                self._add("PY-SEC-002", node)
            elif isinstance(first, ast.Name):
                built_at = next((s[first.id] for s in reversed(self._sql_vars) if first.id in s), None)
                if built_at is not None:
                    self._add("PY-SEC-002", node, f"SQL montado na linha {built_at}")

        if isinstance(func, ast.Attribute) and func.attr == "decode":
            if self._jwt_verification_disabled(node):
                self._add("PY-SEC-003", node)

        if isinstance(func, ast.Name) and func.id in {"eval", "exec"} and node.args \
                and not isinstance(node.args[0], ast.Constant):
            self._add("PY-SEC-004", node)

        self.generic_visit(node)

    @staticmethod
    def _jwt_verification_disabled(node: ast.Call) -> bool:
        for kw in node.keywords:
            if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                return True
            if kw.arg == "options" and isinstance(kw.value, ast.Dict):
                for k, v in zip(kw.value.keys, kw.value.values):
                    if _is_str_const(k) and k.value == "verify_signature" \
                            and isinstance(v, ast.Constant) and v.value is False:
                        return True
            if kw.arg == "algorithms" and isinstance(kw.value, (ast.List, ast.Tuple)):
                if any(_is_str_const(e) and e.value.lower() == "none" for e in kw.value.elts):
                    return True
        return False

    # ---------- PY-SEC-005 ----------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        exc_name = node.name
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Return, ast.Raise)) and self._exposes_exception(sub, exc_name):
                    self._add("PY-SEC-005", sub)
        self.generic_visit(node)

    @staticmethod
    def _exposes_exception(node: ast.AST, exc_name: str | None) -> bool:
        for sub in ast.walk(node):
            # traceback.format_exc() / format_exception(...)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr in {"format_exc", "format_exception", "format_tb"}:
                return True
            if not exc_name:
                continue
            # str(e) / repr(e)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                    and sub.func.id in {"str", "repr"} and sub.args \
                    and isinstance(sub.args[0], ast.Name) and sub.args[0].id == exc_name:
                return True
            # f"{e}"
            if isinstance(sub, ast.FormattedValue) and isinstance(sub.value, ast.Name) \
                    and sub.value.id == exc_name:
                return True
            # e.args
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                    and sub.value.id == exc_name and sub.attr == "args":
                return True
        return False


def analyze_source(source: str, rel_path: str) -> list[dict]:
    """Analisa um arquivo e devolve achados ordenados por linha. Lança SyntaxError se inválido."""
    tree = ast.parse(source, filename=rel_path)
    visitor = _Visitor(source.splitlines(), rel_path)
    visitor.visit(tree)
    return sorted(visitor.findings, key=lambda f: (f["line"], f["rule_id"]))


def rules_catalog() -> list[dict]:
    return [asdict(r) for r in RULES.values()]
