"""Regras AST: casos positivos, negativos e comparação com o gabarito."""
import json

import pytest

from server.security_rules import analyze_source

from .conftest import EXPECTED_FILE


def rules(src):
    return [(f["rule_id"], f["line"]) for f in analyze_source(src, "t.py")]


@pytest.mark.parametrize("src, expected", [
    # PY-SEC-001 segredo fixo
    ('API_KEY = "abcd1234efgh"', [("PY-SEC-001", 1)]),
    ('db_password: str = "senhaFicticia"', [("PY-SEC-001", 1)]),
    ('connect(password="senhaFicticia")', [("PY-SEC-001", 1)]),
    ('cfg = {"client_secret": "valorFicticio99"}', [("PY-SEC-001", 1)]),
    ('URL = "mysql://root:toor1234@localhost/db"', [("PY-SEC-001", 1)]),
    # PY-SEC-002 SQL dinâmico
    ('c.execute(f"SELECT * FROM t WHERE id = {x}")', [("PY-SEC-002", 1)]),
    ('c.execute("SELECT * FROM t WHERE n = \'" + n + "\'")', [("PY-SEC-002", 1)]),
    ('c.execute("DELETE FROM t WHERE id = %s" % x)', [("PY-SEC-002", 1)]),
    ('c.execute("UPDATE t SET a = {}".format(x))', [("PY-SEC-002", 1)]),
    ('def f(x):\n    q = f"SELECT a FROM t WHERE b = {x}"\n    c.execute(q)', [("PY-SEC-002", 3)]),
    # PY-SEC-003 JWT
    ('jwt.decode(t, options={"verify_signature": False})', [("PY-SEC-003", 1)]),
    ('jwt.decode(t, k, verify=False)', [("PY-SEC-003", 1)]),
    ('jwt.decode(t, k, algorithms=["none"])', [("PY-SEC-003", 1)]),
    # PY-SEC-004 eval/exec
    ('eval(user_input)', [("PY-SEC-004", 1)]),
    ('exec(code)', [("PY-SEC-004", 1)]),
    # PY-SEC-005 exceção exposta
    ('try:\n    f()\nexcept Exception as e:\n    return {"erro": str(e)}', [("PY-SEC-005", 4)]),
    ('try:\n    f()\nexcept Exception as err:\n    raise HTTPException(500, detail=f"falhou: {err}")', [("PY-SEC-005", 4)]),
    ('try:\n    f()\nexcept Exception:\n    return traceback.format_exc()', [("PY-SEC-005", 4)]),
])
def test_positive_cases(src, expected):
    assert rules(src) == expected


@pytest.mark.parametrize("src", [
    'API_KEY = os.environ["API_KEY"]',
    'token_type = "bearer"',
    'password = ""',
    'PASSWORD_MIN_LENGTH = 12',
    'URL = "https://exemplo.com/api"',
    'c.execute("SELECT * FROM t WHERE id = ?", (x,))',
    'c.execute(QUERY_CONSTANTE)',
    'msg = f"Olá {nome}"',
    'def f(x):\n    q = "SELECT a FROM t WHERE b = ?"\n    c.execute(q, (x,))',
    'def f(x):\n    q = f"SELECT a FROM t WHERE b = {x}"\n    q = "SELECT 1"\n    c.execute(q)',
    'jwt.decode(t, k, algorithms=["HS256"])',
    'base64.b64decode(data)',
    'ast.literal_eval(x)',
    'eval("1 + 1")',
    'try:\n    f()\nexcept Exception as e:\n    logger.exception(e)\n    raise HTTPException(500, "Erro interno")',
])
def test_negative_cases(src):
    assert rules(src) == []


def test_evidence_is_sanitized():
    finding = analyze_source('API_KEY = "sk-ant-FICTICIO-000000000000"', "t.py")[0]
    assert "FICTICIO" not in finding["evidence"]
    assert finding["status"] == "confirmed_by_rule"
    assert finding["limitations"]


def test_linter_matches_gabarito_on_sample(tools):
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    tol = expected["matching_rule"]["line_tolerance"]
    produced = tools.run_security_linter().findings
    unmatched = list(produced)
    for exp in expected["expected_findings"]:
        match = next((f for f in unmatched if f.file == exp["file"] and f.category == exp["category"]
                      and abs(f.line - exp["line"]) <= tol), None)
        assert match is not None, f"Falso negativo: {exp['id']}"
        unmatched.remove(match)
    assert unmatched == [], f"Falsos positivos: {[(f.file, f.line, f.rule_id) for f in unmatched]}"


def test_syntax_error_is_reported_not_raised(tools, workspace):
    (workspace / "legacy_sample" / "quebrado.py").write_text("def x(:\n")
    result = tools.run_security_linter()
    assert any("quebrado.py" in e for e in result.errors)
