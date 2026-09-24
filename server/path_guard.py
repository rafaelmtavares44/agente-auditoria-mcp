"""Validação de caminhos: tudo que o modelo pedir passa por aqui.

Estratégia (defesa em camadas):
1. Rejeitar sintaticamente: vazio, byte nulo, caminho absoluto, letra de unidade,
   caminho UNC e qualquer componente "..".
2. Rejeitar nomes proibidos (.env, .git, venvs, chaves privadas...).
3. Rejeitar se algum componente for link simbólico ou junction (Windows).
4. Resolver o caminho real e exigir que continue DENTRO da raiz.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "__pycache__",
    "node_modules", "site-packages", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
PRIVATE_KEY_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der", ".crt"}
PRIVATE_KEY_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
ALLOWED_READ_SUFFIXES = {".py"}


class PathAccessError(ValueError):
    """Acesso negado. A mensagem é segura para ser mostrada ao modelo."""


def _is_link_or_junction(p: Path) -> bool:
    """Detecta symlink e junction. No Python 3.11 não existe Path.is_junction(),
    então também comparamos o caminho real com o esperado: se diferirem,
    algum redirecionamento (link/junction) existe no último componente."""
    if p.is_symlink():
        return True
    is_junction = getattr(p, "is_junction", None)  # Python 3.12+
    if is_junction and is_junction():
        return True
    try:
        return p.exists() and p.resolve() != p.parent.resolve() / p.name
    except OSError:
        return True


def is_excluded_name(name: str) -> bool:
    lower = name.lower()
    if lower in EXCLUDED_DIRS or lower in PRIVATE_KEY_NAMES:
        return True
    if lower.startswith(".env"):          # .env, .env.local, .env.prod...
        return True
    return Path(lower).suffix in PRIVATE_KEY_SUFFIXES


def _check_syntax(relative_path: str) -> tuple[str, ...]:
    if not relative_path or not relative_path.strip():
        raise PathAccessError("Caminho vazio.")
    if "\x00" in relative_path:
        raise PathAccessError("Caminho contém byte nulo.")
    if len(relative_path) > 300:
        raise PathAccessError("Caminho longo demais.")

    win = PureWindowsPath(relative_path)
    posix = PurePosixPath(relative_path.replace("\\", "/"))
    if win.is_absolute() or win.drive or posix.is_absolute() or relative_path.startswith(("\\\\", "//")):
        raise PathAccessError("Caminhos absolutos não são permitidos; use caminho relativo à raiz.")
    parts = tuple(p for p in posix.parts if p not in ("", "."))
    if ".." in parts:
        raise PathAccessError("Componentes '..' não são permitidos.")
    if not parts:
        raise PathAccessError("Caminho vazio.")
    return parts


def resolve_inside(root: Path, relative_path: str) -> Path:
    """Devolve o caminho absoluto validado de um arquivo EXISTENTE dentro da raiz."""
    parts = _check_syntax(relative_path)

    for part in parts:
        if is_excluded_name(part):
            raise PathAccessError(f"Acesso a '{part}' é bloqueado por política.")

    # Verifica cada componente antes de resolver (links e junctions).
    current = root
    for part in parts:
        current = current / part
        if _is_link_or_junction(current):
            raise PathAccessError("Links simbólicos/junctions não são seguidos.")

    try:
        resolved = current.resolve(strict=True)
    except (FileNotFoundError, OSError):
        raise PathAccessError("Arquivo não encontrado dentro da raiz autorizada.") from None

    if not resolved.is_relative_to(root):
        raise PathAccessError("Caminho resolvido fica fora da raiz autorizada.")
    return resolved


def resolve_readable_python(root: Path, relative_path: str) -> Path:
    path = resolve_inside(root, relative_path)
    if not path.is_file():
        raise PathAccessError("O caminho não é um arquivo.")
    if path.suffix.lower() not in ALLOWED_READ_SUFFIXES:
        raise PathAccessError("Somente arquivos .py podem ser lidos.")
    return path


def to_relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_python_files(root: Path):
    """Percorre a raiz sem seguir links e pulando diretórios excluídos."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if not is_excluded_name(d) and not _is_link_or_junction(base / d)
        )
        for name in sorted(filenames):
            p = base / name
            if is_excluded_name(name) or p.suffix.lower() not in ALLOWED_READ_SUFFIXES:
                continue
            if _is_link_or_junction(p):
                continue
            yield p
