"""Sanitização de valores sensíveis."""
from server.sanitizer import REDACTED, sanitize_obj, sanitize_text


def test_redacts_assignments_and_keeps_names():
    out = sanitize_text('JWT_SECRET = "demo-secret-NAO-E-REAL-123456"')
    assert out == f'JWT_SECRET = "{REDACTED}"'


def test_redacts_common_token_formats():
    samples = [
        "sk-ant-api03-FICTICIO0000000000",
        "AKIAABCDEFGHIJKLMNOP",
        "ghp_ABCDEFGHIJKLMNOPQRSTuvwxyz0123",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJhZmljdGljaWE",
        "Authorization: Bearer abcdefghijklmnop123",
    ]
    for s in samples:
        assert REDACTED in sanitize_text(s), s


def test_redacts_url_credentials_only_password():
    out = sanitize_text("postgresql://admin:SenhaFicticia@host/db")
    assert out == f"postgresql://admin:{REDACTED}@host/db"


def test_private_key_block_preserves_line_count():
    text = "a = 1\n-----BEGIN RSA PRIVATE KEY-----\nAAAA\nBBBB\n-----END RSA PRIVATE KEY-----\nb = 2"
    out = sanitize_text(text)
    assert "AAAA" not in out and out.count("\n") == text.count("\n")
    assert out.splitlines()[-1] == "b = 2"


def test_benign_values_and_code_are_kept():
    for s in ['token_type: str = "bearer"', 'password = os.environ["PW"]',
              'SELECT id, password_hash FROM users', 'x = "texto qualquer"']:
        assert sanitize_text(s) == s


def test_sanitize_obj_recursive():
    data = {"args": {"content": 'api_key = "abc12345678"'}, "list": ['password="segredo123"']}
    out = sanitize_obj(data)
    assert "abc12345678" not in str(out) and "segredo123" not in str(out)


def test_read_source_never_returns_sample_secrets(tools):
    for path in ("auth_service.py", "order_api.py"):
        text = tools.read_source_code(path).numbered_content
        assert "demo-secret-NAO-E-REAL" not in text
        assert "SenhaFicticia2024" not in text
