"""Leitura autorizada e bloqueio de escapes de diretório."""
import os
import sys

import pytest

from server.tools import ToolInputError


def test_scan_lists_only_sample_python_files(tools):
    result = tools.scan_project_files()
    assert sorted(f.path for f in result.files) == ["auth_service.py", "order_api.py"]
    assert all(f.size_bytes > 0 for f in result.files)


def test_scan_skips_excluded_names(tools, workspace):
    root = workspace / "legacy_sample"
    (root / ".env").write_text("API_KEY=ficticia\n")
    (root / ".env.local.py").write_text("x = 1\n")
    (root / ".git").mkdir()
    (root / ".git" / "hook.py").write_text("x = 1\n")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "mod.py").write_text("x = 1\n")
    (root / "server.key").write_text("-----BEGIN PRIVATE KEY-----\n")
    (root / "pkg").mkdir()
    (root / "pkg" / "util.py").write_text("x = 1\n")
    paths = [f.path for f in tools.scan_project_files().files]
    assert "pkg/util.py" in paths
    assert not any(p.startswith((".env", ".git", ".venv")) or p.endswith(".key") for p in paths)


def test_read_returns_numbered_lines(tools):
    result = tools.read_source_code("order_api.py", 49, 49)
    assert result.numbered_content.startswith("  49 | ")
    assert "SELECT id, status FROM orders WHERE id" in result.numbered_content
    assert result.total_lines > 90


@pytest.mark.parametrize("bad_path", [
    "../evaluation/expected_findings.json",       # gabarito fora da raiz
    "..\\evaluation\\expected_findings.json",
    "sub/../../evaluation/expected_findings.json",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "C:relative.py",
    "\\\\servidor\\share\\x.py",
    "//servidor/share/x.py",
    ".env",
    "config/.env",
    "nao_existe.py",
    "a\x00.py",
    "",
])
def test_read_blocks_escapes_and_forbidden(tools, bad_path):
    with pytest.raises(ToolInputError):
        tools.read_source_code(bad_path)


def test_read_rejects_non_python(tools, workspace):
    (workspace / "legacy_sample" / "notes.txt").write_text("texto")
    with pytest.raises(ToolInputError, match=r"\.py"):
        tools.read_source_code("notes.txt")


def _can_symlink(tmp_path) -> bool:
    try:
        os.symlink(tmp_path, tmp_path / "_probe_link")
        return True
    except (OSError, NotImplementedError):
        return False


def test_symlink_file_escape_is_blocked(tools, workspace, tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("Sistema sem permissão para criar symlinks (comum no Windows sem modo desenvolvedor).")
    secret = workspace / "evaluation" / "expected_findings.json"
    os.symlink(secret, workspace / "legacy_sample" / "gabarito.py")
    with pytest.raises(ToolInputError, match="[Ll]ink"):
        tools.read_source_code("gabarito.py")
    assert "gabarito.py" not in [f.path for f in tools.scan_project_files().files]


def test_symlink_directory_escape_is_blocked(tools, workspace, tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("Sistema sem permissão para criar symlinks.")
    outside = tmp_path / "fora"
    outside.mkdir()
    (outside / "vazado.py").write_text("SEGREDO = 'x'\n")
    os.symlink(outside, workspace / "legacy_sample" / "linkdir", target_is_directory=True)
    with pytest.raises(ToolInputError):
        tools.read_source_code("linkdir/vazado.py")
    assert not any("vazado" in f.path for f in tools.scan_project_files().files)


@pytest.mark.skipif(sys.platform != "win32", reason="Junctions existem apenas no Windows")
def test_windows_junction_escape_is_blocked(tools, workspace, tmp_path):
    import subprocess
    outside = tmp_path / "fora_junction"
    outside.mkdir()
    (outside / "vazado.py").write_text("x = 1\n")
    link = workspace / "legacy_sample" / "junc"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    with pytest.raises(ToolInputError):
        tools.read_source_code("junc/vazado.py")
    assert not any("vazado" in f.path for f in tools.scan_project_files().files)
