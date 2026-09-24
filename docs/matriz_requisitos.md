# Matriz: requisito → implementação → evidência

Requisitos do enunciado N2 (Proposta 1) e dos critérios de avaliação, com onde cada um é atendido e como verificar.
"Evidência real" = gerada por execução/teste real em 23/09/2026 (ver `docs/evidencias/`).

## Proposta 1 — desafio prático e entregáveis específicos

| # | Requisito do professor | Implementação | Evidência |
|---|---|---|---|
| P1 | Solução em que agente(s) autônomo(s) realizam tarefa de engenharia de software | Agente de auditoria estática + documentação de API (`agent/orchestrator.py`) | Execução real `20260923-202619-11744e` → `completed` |
| P2 | Suporte a MCP ou chamada estruturada de ferramentas | MCP real, SDK oficial `mcp` 2.2.0, transporte stdio (`server/mcp_server.py`, `agent/mcp_client.py`) + tool use da Messages API | `tests/test_mcp_stdio.py`; log: evento `mcp_connected` |
| P3 | IA interage com arquivos locais de forma padronizada | 5 ferramentas com schemas de entrada e saída estruturada | `outputSchema` verificado em `test_mcp_stdio.py` |
| a | Repositório com código do agente e do servidor MCP | `agent/`, `server/` | Estrutura do repositório; README |
| b | Registro/logs estruturados de decisões, chamadas e resolução de problemas | JSONL com justificativa operacional, `tool_call`, `tool_result`, `validation`, `model_error` (`agent/logging_jsonl.py`) | `docs/evidencias/*/execucao.jsonl` |
| c | Análise de alucinações, limites de autonomia, prompt injection e vazamento de credenciais | Validadores contra referência determinística; limites no orquestrador; `path_guard`; sanitização; avaliação | Relatório §5–6; `evaluation/results/*.md`; `evaluation/demo_restricoes.py` |

## Entregáveis gerais

| # | Requisito | Implementação | Evidência |
|---|---|---|---|
| G1 | Repositório Git limpo, versionado e estruturado | Pastas separadas, `.gitignore` (segredos, saídas) | Estrutura; `git status` limpo após commit |
| G2 | README com arquitetura, pré-requisitos, passo a passo e decisões | `README.md` (PowerShell + Linux/macOS, problemas comuns) + `docs/arquitetura.md` (decisões P1–P9) | Instalação limpa seguindo o README (Linux e Windows) |
| G3 | Relatório técnico PDF, 3 a 5 páginas | `docs/relatorio/relatorio.md` → `build_pdf.py` | `docs/relatorio/relatorio.pdf` (4 páginas, conferido) |
| G3.1 | Introdução e tecnologia emergente adotada | Relatório §1 | — |
| G3.2 | Arquitetura e diagrama do fluxo de dados | Relatório §2 (Figura 1) + Mermaid em `docs/arquitetura.md` | — |
| G3.3 | Trade-offs: vantagens, gargalos, limitações, riscos de segurança/éticos | Relatório §6–7 | Métricas medidas de custo e latência |
| G3.4 | Conclusões e lições sobre prontidão para o mercado | Relatório §8 | — |
| G4 | Apresentação de 15 min com demo ao vivo e defesa técnica | `docs/roteiro_apresentacao.md` | Ensaio da equipe |

## Critérios de avaliação

| Critério (peso) | Onde a equipe mostra |
|---|---|
| Funcionalidade e Arquitetura (4,0) | Demo ao vivo da CLI; 125 testes; validação de artefatos; falhas controladas registradas |
| Rigor Técnico e Inovação (2,5) | MCP real (não simulado); verificação independente do "concluído"; avaliação com regra explícita; separação linter × modelo |
| Documentação e Relatório (2,0) | README, `docs/arquitetura.md`, esta matriz, relatório com métricas medidas |
| Apresentação e Demo (1,5) | Roteiro com divisão entre os 5 integrantes e plano B identificado |

## Escolhas da equipe (além do enunciado)

| Escolha | Onde | Evidência |
|---|---|---|
| Restrições no código, não só no prompt | `server/path_guard.py`, `agent/mcp_client.py` | `test_path_guard.py`, `demo_restricoes.py` |
| Chave de API fora do subprocesso MCP | `build_server_params` | `test_server_subprocess_env_has_no_api_key` |
| Estados `running/completed/failed/limit_reached` | `agent/orchestrator.py` | 4 testes de limite; execuções reais `failed` |
| Gabarito fora da raiz do agente | `evaluation/expected_findings.json` | Teste de traversal; demo de restrições |
| Modelo configurável (`ANTHROPIC_MODEL`) | `agent/config.py`, `agent/list_models.py` | Execução real com `claude-sonnet-5` |
