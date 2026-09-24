"""Lista os modelos disponíveis para a SUA chave (usa ANTHROPIC_API_KEY do ambiente ou do .env).

    .\\.venv\\Scripts\\python.exe -m agent.list_models

Serve para validar o valor de ANTHROPIC_MODEL antes da demonstração.
Não imprime a chave.
"""

from __future__ import annotations

import os
import sys

import anthropic

from agent.config import PROJECT_DIR, load_dotenv


def main() -> int:
    load_dotenv(PROJECT_DIR / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY não encontrada no ambiente nem no .env.", file=sys.stderr)
        return 1
    try:
        models = list(anthropic.Anthropic().models.list(limit=100))
    except anthropic.AuthenticationError:
        print("Chave recusada pela API (confira ANTHROPIC_API_KEY no .env).", file=sys.stderr)
        return 1
    except anthropic.APIError as exc:
        print(f"Erro ao consultar a API: {type(exc).__name__}", file=sys.stderr)
        return 1

    configured = os.environ.get("ANTHROPIC_MODEL", "").strip()
    print(f"{'ID (use em ANTHROPIC_MODEL)':<36} NOME")
    for m in models:
        mark = "  <- configurado" if m.id == configured else ""
        print(f"{m.id:<36} {m.display_name}{mark}")
    if configured and configured not in {m.id for m in models}:
        print(f"\nATENÇÃO: ANTHROPIC_MODEL='{configured}' não aparece na lista da sua conta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
