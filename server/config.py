"""Configuração imutável do servidor MCP.

Tudo aqui é definido UMA vez, quando o orquestrador inicia o subprocesso.
Nenhuma ferramenta pode alterar esses valores durante a execução.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Limits:
    max_files: int = 200              # arquivos listados por varredura
    max_file_bytes: int = 100_000     # tamanho máximo de um arquivo lido
    max_total_read_bytes: int = 1_000_000  # soma de bytes lidos na execução
    max_output_bytes: int = 300_000   # tamanho máximo de um artefato gravado


@dataclass(frozen=True)
class ServerConfig:
    root: Path          # raiz de leitura (resolvida, absoluta)
    output_dir: Path    # output/<run_id>/ (resolvido, absoluto)
    run_id: str
    limits: Limits = Limits()

    @classmethod
    def create(cls, root: str | Path, output_base: str | Path, run_id: str,
               limits: Limits | None = None) -> "ServerConfig":
        """Valida e congela a configuração. Lança ValueError se algo for inseguro."""
        if not RUN_ID_PATTERN.match(run_id):
            raise ValueError("run_id inválido: use apenas letras, números, '_' e '-' (até 64).")

        root_path = Path(root).resolve(strict=True)
        if not root_path.is_dir():
            raise ValueError(f"Raiz de análise não é um diretório: {root_path}")

        base = Path(output_base).resolve()
        output_dir = (base / run_id).resolve()

        # Leitura e escrita não podem se sobrepor: o agente não pode gravar
        # dentro do código analisado nem ler os próprios artefatos como código.
        if output_dir.is_relative_to(root_path) or root_path.is_relative_to(output_dir):
            raise ValueError("Diretório de saída e raiz de análise não podem se sobrepor.")

        output_dir.mkdir(parents=True, exist_ok=True)
        return cls(root=root_path, output_dir=output_dir, run_id=run_id,
                   limits=limits or Limits())
