"""Linha de comando do agente.

Exemplo (PowerShell, a partir da pasta do projeto):
    .\\.venv\\Scripts\\python.exe -m agent.cli "Audite o projeto e documente a API"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agent.config import PROJECT_DIR, AgentSettings
from agent.orchestrator import AnthropicBackend, AuditAgent

DEFAULT_OBJECTIVE = ("Faça uma auditoria estática de segurança do projeto e documente os endpoints "
                     "da API, gerando os quatro artefatos obrigatórios.")

EXIT_CODES = {"completed": 0, "failed": 1, "limit_reached": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente de auditoria estática via MCP")
    parser.add_argument("objective", nargs="?", default=DEFAULT_OBJECTIVE, help="Objetivo em linguagem natural")
    parser.add_argument("--root", default=str(PROJECT_DIR / "legacy_sample"), help="Raiz de análise")
    parser.add_argument("--output-base", default=str(PROJECT_DIR / "output"))
    parser.add_argument("--logs-dir", default=str(PROJECT_DIR / "logs"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--quiet", action="store_true", help="Não mostrar o progresso no terminal")
    args = parser.parse_args(argv)

    try:
        settings = AgentSettings.from_env(require_api_key=True)
    except ValueError as exc:
        print(f"Configuração inválida: {exc}", file=sys.stderr)
        return 1

    backend = AnthropicBackend(settings.api_key, settings.limits.max_retries)
    agent = AuditAgent(settings, backend, Path(args.root), Path(args.output_base),
                       Path(args.logs_dir), run_id=args.run_id,
                       echo=None if args.quiet else (lambda line: print(line, flush=True)))
    print(f"run_id: {agent.run_id}  |  modelo: {settings.model}")
    print("Enviando à API da Anthropic: instruções, objetivo e resultados das ferramentas "
          "(inclui trechos de código sanitizados).")
    try:
        result = asyncio.run(agent.run(args.objective))
    except KeyboardInterrupt:
        print("\nInterrompido. Subprocesso MCP encerrado; veja o log para detalhes.", file=sys.stderr)
        return 130

    print(f"\nstatus: {result.status}  ({result.reason})")
    print(f"iterações: {result.iterations}  |  chamadas de ferramenta: {result.tool_calls} "
          f"(recusadas: {result.rejected_tool_calls})")
    print(f"tokens: entrada={result.input_tokens} saída={result.output_tokens}  |  tempo: {result.duration_ms} ms")
    if result.validation:
        print(f"validação: {'OK' if result.validation['ok'] else 'FALHOU'}  "
              f"erros={len(result.validation['errors'])} avisos={len(result.validation['warnings'])}")
    print(f"artefatos: {result.output_dir}")
    print(f"log: {result.log_path}")
    return EXIT_CODES.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
